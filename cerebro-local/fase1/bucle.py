"""Bucle rapido de revision: en vez de pensar 20-60 s, responde sin pensar (1-2 s) y el CODIGO revisa.

Idea de Javier (9-oct): mejor 3-5 pasadas rapidas que una lenta. Para que las pasadas mejoren de
verdad hace falta una opinion de fuera del modelo: un modelo pequeno que se autocorrige "a ojo"
suele no mejorar, pero con avisos concretos y comprobables si corrige. Aqui los avisos los da el
codigo, con reglas deterministas (no hay segundo modelo):

  - dice que ha hecho algo ("he guardado", "hecho") sin haber llamado a ninguna herramienta;
  - usa una herramienta que Javier ha dicho expresamente que no ("no lo envies", "no borres");
  - un encargo a un subagente lleva datos personales (correos, telefonos, DNI, nombres del mensaje);
  - repite lo que un subagente ya le entrego a Javier;
  - tutea, usa emojis o frases de asistente generico ("como asistente de IA").

Si hay avisos, se le devuelven como un mensaje "[Revision automatica de JADIS]" y responde otra vez,
hasta MAX_RONDAS. Los avisos van al final de la conversacion: la cache del prompt no se rompe.

Este modulo es el que usara JADIS. La bateria de la Fase 1 lo mide con --bucle.
"""
from __future__ import annotations

import json
import re

MAX_RONDAS = 3

AFIRMA_HECHO = re.compile(
    r"\b(he (guardado|anotado|creado|puesto|programado|enviado|borrado|eliminado|vaciado|movido|apuntado|"
    r"reenviado)|hecho[,.]|queda (guardad|anotad|programad|creada|puesta)|alarma (puesta|creada|programada)|"
    r"(ya )?est[áa] (guardad|anotad|programad|enviad|borrad))", re.IGNORECASE)
PROHIBE = {
    "enviar_correo": re.compile(r"\bno (lo |la |le )?(env[ií]es|mandes)|sin enviar|todav[ií]a no", re.IGNORECASE),
    "borrar_correos": re.compile(r"\bno (lo |la |los |las )?borres|no elimines", re.IGNORECASE),
    "borrar_archivo": re.compile(r"\bno (lo |la |los |las )?borres|no elimines", re.IGNORECASE),
}
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TELEFONO = re.compile(r"\b[6789]\d{2}[ .]?\d{3}[ .]?\d{3}\b")
DNI = re.compile(r"\b\d{8}[A-HJ-NP-TV-Z]\b")
NOMBRE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)")
NO_NOMBRES = {"Python", "España", "Madrid", "Museo", "Prado", "Internet", "RTX", "JADIS", "Javier"}
TUTEO = re.compile(r"\b(tú|tienes|quieres|puedes|necesitas|estás|deberías|prefieres)\b", re.IGNORECASE)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GENERICO = re.compile(r"como (modelo|asistente|ia) de|como inteligencia artificial", re.IGNORECASE)


def _texto_usuario(mensajes: list[dict]) -> str:
    return "\n".join(m.get("content") or "" for m in mensajes if m.get("role") == "user")


def _datos_personales(texto_usuario: str) -> set[str]:
    """Lo que en el mensaje de Javier parece un dato personal: correos, telefonos, DNI y nombres propios."""
    datos = set(CORREO.findall(texto_usuario)) | set(TELEFONO.findall(texto_usuario)) | set(DNI.findall(texto_usuario))
    for frase in re.split(r"(?<=[.!?\n])\s*", texto_usuario):
        for m in NOMBRE.finditer(frase):
            if m.start() > 0 and m.group(1).split()[0] not in NO_NOMBRES:
                datos.add(m.group(1))
    return datos | {"Javier"}


def revisar(mensajes: list[dict], respuesta: dict) -> list[str]:
    """Avisos concretos sobre la respuesta, o [] si esta bien. Sin modelo: solo reglas."""
    mensaje = ((respuesta.get("choices") or [{}])[0].get("message") or {})
    texto = mensaje.get("content") or ""
    llamadas = mensaje.get("tool_calls") or []
    nombres = [(c.get("function") or {}).get("name") for c in llamadas]
    usuario = _texto_usuario(mensajes)
    avisos = []

    if not llamadas and AFIRMA_HECHO.search(texto):
        avisos.append("Dices que lo has hecho, pero no has llamado a ninguna herramienta: nada se ha hecho. "
                      "Llama ahora a la herramienta que corresponda.")
    for herramienta, patron in PROHIBE.items():
        if herramienta in nombres and patron.search(usuario):
            avisos.append(f"Javier ha dicho expresamente que no. No llames a {herramienta}: prepara el borrador "
                          "(delegalo o escribelo) y espera su visto bueno.")
    personales = _datos_personales(usuario)
    for c in llamadas:
        f = c.get("function") or {}
        if f.get("name") != "delegar":
            continue
        try:
            args = json.loads(f.get("arguments") or "{}")
        except json.JSONDecodeError:
            avisos.append("Los argumentos de delegar no son JSON valido. Repite la llamada bien formada.")
            continue
        if args.get("privacidad") == "externo-seudonimizado":
            continue  # la frontera del router los sustituye
        encargo = json.dumps(args, ensure_ascii=False)
        fugas = sorted(d for d in personales if d.lower() in encargo.lower())
        if fugas:
            avisos.append("El encargo lleva datos personales (" + ", ".join(fugas) + "). Quitalos, o usa "
                          "privacidad 'externo-seudonimizado' si de verdad hacen falta.")
    ultimo = mensajes[-1] if mensajes else {}
    if ultimo.get("role") == "tool" and "[ENTREGADO" in (ultimo.get("content") or "") and len(texto.split()) > 20:
        avisos.append("Javier ya ha leido la respuesta del subagente. No la repitas: una linea como mucho, o nada.")
    if TUTEO.search(texto):
        avisos.append("Has tuteado a Javier. Tratale de usted y llamale 'señor', como JARVIS.")
    if EMOJI.search(texto):
        avisos.append("Sin emojis.")
    if GENERICO.search(texto):
        avisos.append("No hables como un asistente generico ('como asistente de IA'): eres JADIS.")
    return avisos


def con_bucle(pedir, cuerpo: dict, max_rondas: int = MAX_RONDAS):
    """Pide una respuesta y la corrige hasta max_rondas con los avisos de revisar().

    pedir(cuerpo) -> (respuesta, segundos). Devuelve (respuesta_final, segundos_totales, rondas, avisos)."""
    mensajes = list(cuerpo["messages"])
    total, historial_avisos = 0.0, []
    for ronda in range(1, max_rondas + 1):
        respuesta, segundos = pedir(dict(cuerpo, messages=mensajes))
        total += segundos
        avisos = revisar(mensajes, respuesta)
        if not avisos or ronda == max_rondas:
            return respuesta, total, ronda, historial_avisos + ([avisos] if avisos else [])
        historial_avisos.append(avisos)
        mensaje = (respuesta.get("choices") or [{}])[0].get("message") or {}
        anterior = {"role": "assistant", "content": mensaje.get("content") or ""}
        if mensaje.get("tool_calls"):
            anterior["tool_calls"] = mensaje["tool_calls"]
            # Cada llamada necesita su resultado; se marca como no ejecutada.
            mensajes = mensajes + [anterior] + [
                {"role": "tool", "tool_call_id": c.get("id", ""), "content": "[No ejecutada: revision pendiente]"}
                for c in mensaje["tool_calls"]]
        else:
            mensajes = mensajes + [anterior]
        mensajes.append({"role": "user", "content": "[Revision automatica de JADIS] " + " ".join(avisos)})
    return respuesta, total, max_rondas, historial_avisos
