#!/usr/bin/env python3
"""Banco de pruebas del cerebro local de JADIS (llama-server, API compatible con OpenAI).

Mide lo que decide si Qwen3.8-27B sirve como cerebro de un agente en tu PC:
  1. Velocidad al generar (tok/s) y al leer el prompt (prefill, tok/s).
  2. Cuanto tarda el primer turno con un prompt de sistema grande, como el de Hermes.
  3. Si la cache de prompt funciona entre turnos. En modelos hibridos (Gated DeltaNet) puede
     fallar y obligar a releer TODO el prompt en cada turno: eso haria inutil al cerebro.
  4. Si las llamadas a herramientas salen bien formadas.
  5. Todo lo anterior sin pensar y pensando (thinking).

Solo usa la biblioteca estandar de Python 3.9+. No manda nada fuera de tu PC: solo habla con
la URL que le des (por defecto http://127.0.0.1:8080).

Uso:
  python bench_cerebro.py
  python bench_cerebro.py --sistema mi_prompt_de_hermes.txt --turnos 4 --salida informe.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PARRAFO = (
    "JADIS es un asistente personal que corre en el ordenador de su usuario. Antes de actuar "
    "comprueba los permisos, explica lo que va a hacer y pide confirmacion para las acciones que "
    "tocan archivos, dinero o mensajes. Responde en espanol, con frases cortas y sin relleno. "
)

PREGUNTAS = [
    "Presentate en dos frases.",
    "Resume en tres puntos que harias si te pido organizar mi semana.",
    "Que necesitarias saber para planificar un viaje de fin de semana? Lista corta.",
    "Dime una curiosidad sobre la Luna en una frase.",
]

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "obtener_tiempo",
        "description": "Devuelve el tiempo actual en una ciudad.",
        "parameters": {"type": "object", "properties": {
            "ciudad": {"type": "string"},
            "unidades": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
            "required": ["ciudad"]}}},
    {"type": "function", "function": {
        "name": "buscar_en_memoria",
        "description": "Busca algo en la memoria de JADIS.",
        "parameters": {"type": "object", "properties": {"consulta": {"type": "string"}},
                       "required": ["consulta"]}}},
]


class ErrorServidor(Exception):
    pass


def peticion(url: str, ruta: str, cuerpo: dict | None = None, timeout: float = 900.0):
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + ruta, data=datos,
                                 method="POST" if datos is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            crudo = r.read()
    except urllib.error.HTTPError as e:
        raise ErrorServidor(f"{ruta}: HTTP {e.code} {e.read()[:300]!r}") from e
    except (urllib.error.URLError, OSError) as e:
        raise ErrorServidor(f"{ruta}: {e}") from e
    return json.loads(crudo.decode("utf-8")), time.perf_counter() - t0


def contar_tokens(url: str, texto: str) -> int | None:
    try:
        r, _ = peticion(url, "/tokenize", {"content": texto}, timeout=120)
        return len(r.get("tokens", []))
    except (ErrorServidor, ValueError):
        return None


def herramienta_falsa(i: int) -> dict:
    return {"name": f"herramienta_{i}", "description": f"Accion de prueba numero {i}.",
            "parameters": {"type": "object", "properties": {
                "objetivo": {"type": "string", "description": "sobre que actuar"},
                "confirmar": {"type": "boolean", "description": "pedir permiso antes"}}}}


def prompt_sintetico(tokens_objetivo: int) -> str:
    """Texto de relleno parecido a un prompt de agente (reglas + esquemas). ~4 caracteres/token."""
    partes, n, i = [], 0, 0
    while n < tokens_objetivo * 4:
        bloque = f"Regla {i + 1}. " + PARRAFO
        if i % 5 == 4:
            bloque += "\nHerramienta: " + json.dumps(herramienta_falsa(i), ensure_ascii=False)
        partes.append(bloque)
        n += len(bloque) + 1
        i += 1
    return "\n".join(partes)


def llamar(url: str, modelo: str, mensajes: list, max_tokens: int, pensar: bool,
           herramientas: list | None = None, timeout: float = 900.0):
    cuerpo = {"model": modelo, "messages": mensajes, "max_tokens": max_tokens,
              "temperature": 0.6, "top_p": 0.95, "stream": False,
              "chat_template_kwargs": {"enable_thinking": pensar}}
    if herramientas:
        cuerpo["tools"] = herramientas
    return peticion(url, "/v1/chat/completions", cuerpo, timeout=timeout)


def _redondear(x, d=2):
    return None if x is None else round(float(x), d)


def medir(r: dict, segundos: float) -> tuple[dict, dict]:
    t = r.get("timings") or {}
    u = r.get("usage") or {}
    eleccion = (r.get("choices") or [{}])[0]
    msg = eleccion.get("message") or {}
    m = {
        "segundos_totales": round(segundos, 2),
        "tokens_prompt": u.get("prompt_tokens"),
        "tokens_generados": u.get("completion_tokens"),
        "cache_n": t.get("cache_n"),
        "prompt_n": t.get("prompt_n"),
        "prefill_s": _redondear(t["prompt_ms"] / 1000) if t.get("prompt_ms") is not None else None,
        "prefill_tok_s": _redondear(t.get("prompt_per_second"), 1),
        "decode_tok_s": _redondear(t.get("predicted_per_second")),
        "borrador_propuestos": t.get("draft_n"),
        "borrador_aceptados": t.get("draft_n_accepted"),
        "fin": eleccion.get("finish_reason"),
        "chars_razonamiento": len(msg.get("reasoning_content") or ""),
        "chars_respuesta": len(msg.get("content") or ""),
    }
    if m["decode_tok_s"] is None and m["tokens_generados"]:
        # Sin 'timings' solo se puede aproximar: incluye el prefill, asi que se queda corto.
        m["decode_tok_s_aprox"] = round(m["tokens_generados"] / max(segundos, 1e-6), 2)
    return m, msg


def veredicto_cache(m: dict) -> tuple[bool | None, str]:
    c, p = m.get("cache_n"), m.get("prompt_n")
    if c is None or p is None or (c + p) == 0:
        return None, "desconocido (el servidor no devuelve 'timings')"
    fraccion = c / (c + p)
    if fraccion >= 0.8:
        return True, f"OK: reutiliza el {fraccion:.0%} del prompt"
    return False, f"FALLO: solo reutiliza el {fraccion:.0%}; relee {p} tokens"


def prueba_turnos(url, modelo, sistema, turnos, max_tokens, pensar, timeout):
    mensajes = [{"role": "system", "content": sistema}]
    resultados = []
    for i in range(turnos):
        mensajes.append({"role": "user", "content": PREGUNTAS[i % len(PREGUNTAS)]})
        r, seg = llamar(url, modelo, mensajes, max_tokens, pensar, timeout=timeout)
        m, msg = medir(r, seg)
        m["turno"] = i + 1
        if i > 0:
            m["cache_ok"], m["cache"] = veredicto_cache(m)
        resultados.append(m)
        mensajes.append({"role": "assistant", "content": msg.get("content") or ""})
    return resultados


def prueba_herramientas(url, modelo, pensar, timeout):
    mensajes = [
        {"role": "system", "content": "Eres JADIS. Usa una herramienta cuando haga falta."},
        {"role": "user", "content": "Que tiempo hace ahora en Madrid? Usa la herramienta adecuada."},
    ]
    r, seg = llamar(url, modelo, mensajes, 1024, pensar, HERRAMIENTAS, timeout=timeout)
    m, msg = medir(r, seg)
    llamadas = msg.get("tool_calls") or []
    ok, detalle = False, "no llamo a ninguna herramienta"
    if llamadas:
        f = llamadas[0].get("function") or {}
        try:
            args = json.loads(f.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = None
        if f.get("name") != "obtener_tiempo":
            detalle = f"llamo a {f.get('name')!r} en vez de 'obtener_tiempo'"
        elif not isinstance(args, dict):
            detalle = "los argumentos no son un objeto JSON valido"
        elif "madrid" not in str(args.get("ciudad", "")).lower():
            detalle = f"ciudad inesperada: {args.get('ciudad')!r}"
        else:
            ok, detalle = True, "obtener_tiempo(" + json.dumps(args, ensure_ascii=False) + ")"
    m["herramienta_ok"], m["herramienta"] = ok, detalle
    return m


def linea_turno(m: dict) -> str:
    partes = [f"turno {m['turno']}:"]
    if m.get("cache"):
        partes.append(f"cache {m['cache']} |")
    if m.get("prefill_s") is not None:
        partes.append(f"lee {m.get('prompt_n')} tok en {m['prefill_s']} s ({m.get('prefill_tok_s')} tok/s) |")
    if m.get("decode_tok_s") is not None:
        partes.append(f"genera {m.get('tokens_generados')} tok a {m['decode_tok_s']} tok/s |")
    elif m.get("decode_tok_s_aprox") is not None:
        partes.append(f"genera {m.get('tokens_generados')} tok a ~{m['decode_tok_s_aprox']} tok/s (aprox.) |")
    if m.get("borrador_propuestos"):
        acept = m.get("borrador_aceptados") or 0
        partes.append(f"MTP acepta {acept}/{m['borrador_propuestos']} |")
    partes.append(f"total {m['segundos_totales']} s")
    if m.get("fin") == "length":
        partes.append("(cortado por --max-tokens)")
    return " ".join(partes)


def evaluar_criterios(informe: dict, min_decode: float, max_turno_cacheado: float) -> list[tuple[bool | None, str]]:
    criterios = []
    turnos = [t for bloque in informe["bloques"] for t in bloque["turnos"]]
    decodes = [t.get("decode_tok_s") or t.get("decode_tok_s_aprox") for t in turnos]
    decodes = [d for d in decodes if d]
    if decodes:
        mediana = sorted(decodes)[len(decodes) // 2]
        criterios.append((mediana >= min_decode, f"genera >= {min_decode} tok/s (mediana {mediana})"))
    caches = [t.get("cache_ok") for t in turnos if "cache_ok" in t]
    if caches:
        if None in caches:
            criterios.append((None, "cache entre turnos: no se pudo medir"))
        else:
            criterios.append((all(caches), "la cache de prompt se reutiliza en todos los turnos"))
    cacheados = [t["segundos_totales"] for t in turnos if t.get("cache_ok")]
    if cacheados:
        peor = max(cacheados)
        criterios.append((peor <= max_turno_cacheado,
                          f"turno con cache <= {max_turno_cacheado} s (peor {peor} s)"))
    herramientas = [b["herramientas"] for b in informe["bloques"] if b.get("herramientas")]
    if herramientas:
        criterios.append((all(h["herramienta_ok"] for h in herramientas),
                          "llamada a herramienta bien formada"))
    return criterios


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Banco de pruebas del cerebro local de JADIS.")
    p.add_argument("--url", default="http://127.0.0.1:8080")
    p.add_argument("--modelo", default=None, help="id del modelo (por defecto, el que anuncia el servidor)")
    p.add_argument("--sistema", default=None, help="archivo con un prompt de sistema real (p. ej. el de Hermes)")
    p.add_argument("--tokens-sistema", type=int, default=12000, help="tamano del prompt sintetico")
    p.add_argument("--turnos", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=256, help="tokens maximos por respuesta sin pensar")
    p.add_argument("--max-tokens-pensando", type=int, default=1024,
                   help="tokens maximos por respuesta pensando (el razonamiento tambien cuenta)")
    p.add_argument("--pensar", choices=["no", "si", "ambos"], default="ambos")
    p.add_argument("--sin-herramientas", action="store_true")
    p.add_argument("--min-decode", type=float, default=8.0, help="criterio: tok/s minimos al generar")
    p.add_argument("--max-turno-cacheado", type=float, default=60.0,
                   help="criterio: segundos maximos de un turno con cache")
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--salida", default=None, help="guardar el informe completo en este .json")
    a = p.parse_args(argv)

    try:
        peticion(a.url, "/health", timeout=10)
        modelos, _ = peticion(a.url, "/v1/models", timeout=10)
    except ErrorServidor as e:
        print(f"No hay servidor en {a.url}: {e}", file=sys.stderr)
        return 2
    modelo = a.modelo or ((modelos.get("data") or [{}])[0].get("id") or "local")

    if a.sistema:
        with open(a.sistema, encoding="utf-8") as f:
            sistema, origen = f.read(), a.sistema
    else:
        sistema, origen = prompt_sintetico(a.tokens_sistema), "sintetico"
    n_sistema = contar_tokens(a.url, sistema)

    informe = {"url": a.url, "modelo": modelo, "prompt_sistema": origen,
               "tokens_prompt_sistema": n_sistema, "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
               "bloques": []}
    print(f"Servidor {a.url} | modelo {modelo} | prompt de sistema {origen}: "
          f"{n_sistema if n_sistema is not None else '?'} tokens")

    modos = {"no": [False], "si": [True], "ambos": [False, True]}[a.pensar]
    try:
        for pensar in modos:
            nombre = "pensando" if pensar else "sin pensar"
            print(f"\n== {nombre} ==")
            max_tokens = a.max_tokens_pensando if pensar else a.max_tokens
            turnos = prueba_turnos(a.url, modelo, sistema, a.turnos, max_tokens, pensar, a.timeout)
            for m in turnos:
                print("  " + linea_turno(m))
            bloque = {"pensar": pensar, "turnos": turnos}
            if not a.sin_herramientas:
                h = prueba_herramientas(a.url, modelo, pensar, a.timeout)
                bloque["herramientas"] = h
                estado = "OK" if h["herramienta_ok"] else "FALLO"
                print(f"  herramientas: {estado} {h['herramienta']} ({h['segundos_totales']} s)")
            informe["bloques"].append(bloque)
    except ErrorServidor as e:
        print(f"\nEl servidor fallo a mitad de la prueba: {e}", file=sys.stderr)
        informe["error"] = str(e)

    informe["criterios"] = [{"ok": ok, "criterio": c}
                            for ok, c in evaluar_criterios(informe, a.min_decode, a.max_turno_cacheado)]
    print("\nCriterios de la Fase 0:")
    for c in informe["criterios"]:
        marca = {True: "[OK]", False: "[NO]", None: "[??]"}[c["ok"]]
        print(f"  {marca} {c['criterio']}")
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(informe, f, ensure_ascii=False, indent=2)
        print(f"\nInforme guardado en {a.salida}")
    return 1 if "error" in informe else 0


if __name__ == "__main__":
    sys.exit(main())
