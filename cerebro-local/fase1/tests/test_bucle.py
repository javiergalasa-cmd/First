"""Pruebas del bucle de revision (sin modelo)."""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fase0"))

import bucle  # noqa: E402


def resp(texto=None, llamadas=()):
    m = {"role": "assistant", "content": texto}
    if llamadas:
        m["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                           for i, (n, a) in enumerate(llamadas)]
    return {"choices": [{"message": m}]}


def usuario(t):
    return [{"role": "system", "content": "SOUL"}, {"role": "user", "content": t}]


class PruebasRevisar(unittest.TestCase):
    def test_afirma_sin_herramienta(self):
        avisos = bucle.revisar(usuario("Apúntate que mi DNI es 12345678Z."),
                               resp("Hecho, señor. He guardado su DNI en la memoria privada."))
        self.assertTrue(any("no has llamado a ninguna herramienta" in a for a in avisos))
        self.assertEqual(bucle.revisar(usuario("Apúntate mi DNI."), resp("Hecho, señor.", [("guardar_memoria", {"dato": "x"})])), [])

    def test_no_enviar(self):
        avisos = bucle.revisar(usuario("Redacta un correo para Marta. No lo envíes todavía."),
                               resp(llamadas=[("enviar_correo", {"para": "m", "asunto": "a", "cuerpo": "b"})]))
        self.assertTrue(any("No llames a enviar_correo" in a for a in avisos))

    def test_datos_personales_del_mensaje(self):
        msj = usuario("Redacta un correo para Marta Ruiz (marta.ruiz@ejemplo.com) diciendo que no voy.")
        mal = resp(llamadas=[("delegar", {"tarea": "Correo para Marta Ruiz: no voy", "privacidad": "externo-sin-datos",
                                          "entrega": "directa"})])
        self.assertTrue(any("Marta Ruiz" in a for a in bucle.revisar(msj, mal)))
        bien = resp(llamadas=[("delegar", {"tarea": "Correo breve y educado declinando una reunión",
                                           "privacidad": "externo-sin-datos", "entrega": "directa"})])
        self.assertEqual(bucle.revisar(msj, bien), [])
        seud = resp(llamadas=[("delegar", {"tarea": "Correo para Marta Ruiz", "privacidad": "externo-seudonimizado",
                                           "entrega": "directa"})])
        self.assertEqual(bucle.revisar(msj, seud), [])

    def test_no_marca_lugares_ni_productos(self):
        msj = usuario("Busca el mejor precio de una RTX 5070 en España.")
        r = resp(llamadas=[("delegar", {"tarea": "Mejor precio de una RTX 5070 en España",
                                        "privacidad": "externo-sin-datos", "entrega": "directa"})])
        self.assertEqual(bucle.revisar(msj, r), [])

    def test_paso_directo_y_estilo(self):
        msjs = usuario("Horarios del Prado") + [{"role": "tool", "tool_call_id": "c0", "content": "[ENTREGADO: ...] 10-20"}]
        largo = resp("El museo abre de 10:00 a 20:00 todos los días del fin de semana y además la entrada es gratis por la tarde.")
        self.assertTrue(any("No la repitas" in a for a in bucle.revisar(msjs, largo)))
        self.assertTrue(bucle.revisar(usuario("hola"), resp("¿Qué quieres hoy? 🤓")))
        self.assertTrue(any("asistente generico" in a for a in
                            bucle.revisar(usuario("chiste"), resp("Como asistente de IA, aquí va uno."))))


class PruebasConBucle(unittest.TestCase):
    def test_corrige_en_la_segunda_ronda(self):
        respuestas = [resp("Hecho, señor. He guardado su DNI."),
                      resp("Hecho, señor.", [("guardar_memoria", {"dato": "DNI"})])]
        vistos = []

        def pedir(cuerpo):
            vistos.append(cuerpo["messages"])
            return respuestas[len(vistos) - 1], 1.0
        final, segundos, rondas, avisos = bucle.con_bucle(pedir, {"messages": usuario("Apúntate mi DNI.")})
        self.assertEqual((rondas, segundos), (2, 2.0))
        self.assertEqual(final["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "guardar_memoria")
        self.assertTrue(vistos[1][-1]["content"].startswith("[Revision automatica de JADIS]"))
        self.assertEqual(vistos[1][:2], vistos[0][:2], "el principio del prompt no cambia: la cache sirve")

    def test_tope_de_rondas(self):
        final, _, rondas, avisos = bucle.con_bucle(lambda c: (resp("He guardado todo."), 0.5),
                                                   {"messages": usuario("guarda")}, max_rondas=3)
        self.assertEqual(rondas, 3)
        self.assertEqual(len(avisos), 3)

    def test_llamada_rechazada_lleva_su_resultado(self):
        respuestas = [resp(llamadas=[("enviar_correo", {"para": "x", "asunto": "a", "cuerpo": "b"})]),
                      resp("Borrador listo, señor. ¿Lo envío?")]
        vistos = []

        def pedir(cuerpo):
            vistos.append(cuerpo["messages"])
            return respuestas[len(vistos) - 1], 1.0
        bucle.con_bucle(pedir, {"messages": usuario("Redacta un correo. No lo envíes.")})
        roles = [m["role"] for m in vistos[1]]
        self.assertEqual(roles[-3:], ["assistant", "tool", "user"])


if __name__ == "__main__":
    unittest.main()
