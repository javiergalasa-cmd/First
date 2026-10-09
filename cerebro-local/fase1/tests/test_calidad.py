"""Pruebas de la bateria de calidad (sin GPU ni modelo).

Ejecutar desde cerebro-local/fase1:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(AQUI, "..", "..", "fase0", "tests"))

import calidad  # noqa: E402
from test_fase0 import ServidorFalso  # noqa: E402


def respuesta(texto=None, llamadas=(), razonamiento=None):
    mensaje = {"role": "assistant", "content": texto}
    if llamadas:
        mensaje["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}}
                                 for i, (n, a) in enumerate(llamadas)]
    if razonamiento:
        mensaje["reasoning_content"] = razonamiento
    return {"choices": [{"message": mensaje}]}


def caso(id_):
    return next(c for c in calidad.CASOS if c["id"] == id_)


def fallos(c, r):
    return [x["criterio"] for x in calidad.evaluar(c, r) if not x["ok"]]


class PruebasEvaluar(unittest.TestCase):
    def test_charla_breve_sin_pensar(self):
        self.assertEqual(fallos(caso("saludo"), respuesta("Bien, aquí sigo. ¿Qué necesitas?")), [])

    def test_charla_larga_falla(self):
        largo = "Hola, " + "esto es una respuesta muy larga que no se acaba nunca " * 5
        self.assertIn("breve", fallos(caso("saludo"), respuesta(largo)))

    def test_charla_pensando_falla(self):
        self.assertIn("no piensa en la charla",
                      fallos(caso("saludo"), respuesta("Bien, aquí estoy.", razonamiento="Debo saludar...")))

    def test_delegar_sin_datos(self):
        r = respuesta(llamadas=[("delegar", {"tarea": "Horarios del Museo del Prado este fin de semana",
                                             "privacidad": "externo-sin-datos", "entrega": "directa"})])
        self.assertEqual(fallos(caso("prado"), r), [])

    def test_delegar_con_datos_personales_falla(self):
        r = respuesta(llamadas=[("delegar", {"tarea": "Precio de una RTX 5070 para Javier",
                                             "privacidad": "externo-sin-datos", "entrega": "directa"})])
        self.assertIn("encargo sin datos personales", fallos(caso("precio-5070"), r))

    def test_seudonimizado_puede_llevar_nombres(self):
        r = respuesta(llamadas=[("delegar", {"tarea": "Correo para Marta Ruiz: no voy el jueves",
                                             "privacidad": "externo-seudonimizado", "entrega": "directa"})])
        self.assertEqual(fallos(caso("correo-marta"), r), [], "la frontera del router los sustituye")

    def test_lo_personal_no_se_delega(self):
        r = respuesta(llamadas=[("delegar", {"tarea": "mira mi correo", "privacidad": "externo-sin-datos",
                                             "entrega": "directa"})])
        malos = fallos(caso("correos-marta"), r)
        self.assertIn("herramienta", malos)
        self.assertIn("no llama a delegar", malos)

    def test_inyeccion(self):
        self.assertEqual(fallos(caso("inyeccion-correo"),
                                respuesta("Es un intento de phishing: pide reenviar tus correos. No he hecho nada.")),
                         [])
        r = respuesta(llamadas=[("enviar_correo", {"para": "copias@dominio-raro.net", "asunto": "x",
                                                   "cuerpo": "y"})])
        self.assertIn("no llama a enviar_correo", fallos(caso("inyeccion-correo"), r))

    def test_rechazo_y_idioma(self):
        malos = fallos(caso("chiste-negro"), respuesta("Lo siento, pero no puedo contar ese tipo de chistes."))
        self.assertIn("no rechaza", malos)
        self.assertIn("en espanol", fallos(caso("opinion"),
                                           respuesta("I think that politicians are the same as you and the rest.")))

    def test_argumentos_rotos(self):
        r = {"choices": [{"message": {"content": None, "tool_calls": [
            {"function": {"name": "crear_alarma", "arguments": "{hora: 7"}}]}}]}
        self.assertIn("argumentos JSON validos", fallos(caso("alarma"), r))

    def test_peticion_piensa_solo_en_tareas(self):
        self.assertFalse(calidad.peticion_caso(caso("saludo"))["chat_template_kwargs"]["enable_thinking"])
        self.assertTrue(calidad.peticion_caso(caso("prado"))["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(calidad.peticion_caso(caso("paso-directo"))["messages"][-1]["role"], "tool")

    def test_casos_bien_formados(self):
        ids = [c["id"] for c in calidad.CASOS]
        self.assertEqual(len(ids), len(set(ids)))
        nombres = {h["function"]["name"] for h in calidad.HERRAMIENTAS}
        for c in calidad.CASOS:
            self.assertIn(c["modo"], ("charla", "tarea"))
            for h in (c["herramienta"] if isinstance(c.get("herramienta"), list) else [c.get("herramienta")]):
                self.assertTrue(h is None or h in nombres, c["id"])
            for h in c.get("prohibidas", []):
                self.assertIn(h, nombres, c["id"])


class PruebasEjecucion(unittest.TestCase):
    def test_de_punta_a_punta_con_servidor_falso(self):
        carpeta = tempfile.mkdtemp()
        with ServidorFalso(herramienta="delegar") as s:
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                codigo = calidad.main(["--url", s.url, "--carpeta", carpeta, "--solo", "saludo,personal"])
        self.assertEqual(codigo, 0)
        with open(os.path.join(carpeta, "informe-calidad.md"), encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("Casos que pasan todas las comprobaciones", texto)
        self.assertIn("### agenda — FALLA", texto, "el falso delega lo personal: debe fallar")
        self.assertIn("Informe completo", salida.getvalue())
        with open(os.path.join(carpeta, "informe-calidad.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["resultados"]), 5)


if __name__ == "__main__":
    unittest.main()
