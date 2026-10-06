#!/usr/bin/env python3
"""Arranca llama-server con la configuracion recomendada para el cerebro local de JADIS.

Pensado para Windows + GPU NVIDIA de 8 GB (RTX 4060) + Qwen3.8-27B en GGUF, pero todo se
puede cambiar por parametro. El porque de cada opcion esta en ../PLAN.md (seccion 7).

Uso (PowerShell, una sola linea):
  python arrancar_cerebro.py --llama-server C:\\llama\\llama-server.exe --modelo D:\\modelos\\Qwen3.8-27B-IQ3_S-mtp.gguf

Ver el comando sin ejecutarlo:
  python arrancar_cerebro.py --modelo D:\\modelos\\X.gguf --solo-mostrar

Solo usa la biblioteca estandar. No descarga nada ni habla con Internet: solo lanza el
ejecutable que le indiques, escuchando por defecto SOLO en 127.0.0.1.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys

HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}


def construir_comando(a: argparse.Namespace) -> list[str]:
    """Devuelve la linea de comandos de llama-server como lista (sin pasar por la shell)."""
    cmd = [
        a.llama_server,
        "-m", a.modelo,
        # Nombre fijo del modelo en la API: sin el, llama-server anuncia la ruta completa del archivo.
        "--alias", a.alias,
        "--host", a.host,
        "--port", str(a.puerto),
        "-c", str(a.contexto),
        # Flash attention: necesaria para cuantizar la cache V y ahorra memoria.
        "-fa", "on",
        # Cache KV cuantizada: q8_0 casi no pierde calidad y ocupa ~la mitad que f16.
        "-ctk", a.cache_k,
        "-ctv", a.cache_v,
        # --fit reparte solo las capas entre GPU y CPU dejando este margen libre en la GPU.
        "--fit", "on",
        "--fit-target", str(a.fit_target),
        # Un solo "hueco": la decodificacion especulativa (MTP) rinde con 1 peticion a la vez.
        "-np", "1",
        "--jinja",
        "--reasoning-format", a.formato_razonamiento,
        # Puntos de control de contexto: lo que permite reutilizar la cache en modelos hibridos.
        "--ctx-checkpoints", str(a.checkpoints),
        "--cache-ram", str(a.cache_ram),
        "--metrics",
    ]
    if a.capas_gpu is not None:
        cmd += ["-ngl", str(a.capas_gpu)]
    if a.hilos:
        cmd += ["-t", str(a.hilos)]
    if a.ubatch:
        # Bloques mas grandes al leer el prompt: menos viajes de pesos CPU->GPU, mas VRAM de trabajo.
        cmd += ["-b", str(max(2048, a.ubatch)), "-ub", str(a.ubatch)]
    if a.dflash:
        # El borrador DFlash es pequeno (~1 GB): entero en la GPU o no compensa.
        cmd += ["--spec-type", "draft-dflash", "--spec-draft-model", a.dflash,
                "--spec-draft-n-max", str(a.borrador_n), "--spec-draft-ngl", "all"]
    elif not a.sin_mtp:
        # El cabezal MTP viaja dentro del GGUF (tensores blk.*.nextn): no hace falta otro archivo.
        cmd += ["--spec-type", "draft-mtp", "--spec-draft-n-max", str(a.borrador_n)]
    if a.mmproj:
        cmd += ["--mmproj", a.mmproj]
        if a.vision_en_cpu:
            cmd += ["--no-mmproj-offload"]
    if a.sin_op_offload:
        cmd += ["--no-op-offload"]
    if a.sin_pensar:
        # Valor por defecto del servidor; cada peticion puede cambiarlo con chat_template_kwargs.
        cmd += ["--chat-template-kwargs", json.dumps({"enable_thinking": False})]
    if a.plantilla:
        # Plantilla de chat oficial: evita depender de la que venga dentro de un GGUF de terceros.
        cmd += ["--chat-template-file", a.plantilla]
    cmd += a.extra
    return cmd


def mostrar(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def avisos(a: argparse.Namespace) -> list[str]:
    salida = []
    if a.host not in HOSTS_LOCALES:
        salida.append(f"AVISO: --host {a.host} expone el cerebro a la red. Para JADIS basta 127.0.0.1.")
    if a.cache_v != "f16" and a.cache_v != a.cache_k:
        salida.append("Nota: K y V con tipos distintos es valido, pero mide la calidad si bajas V a q4_0.")
    if a.dflash and not a.sin_mtp:
        salida.append("Nota: con --dflash se usa el borrador DFlash en lugar del cabezal MTP.")
    return salida


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Arranca llama-server para el cerebro local de JADIS.")
    p.add_argument("--llama-server", default="llama-server.exe" if os.name == "nt" else "llama-server",
                   help="ruta al ejecutable llama-server (por defecto, el del PATH)")
    p.add_argument("--modelo", required=True, help="ruta al .gguf del modelo")
    p.add_argument("--alias", default="qwen3.8-27b-local", help="nombre del modelo en la API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=8080)
    p.add_argument("--contexto", type=int, default=65536,
                   help="tokens de contexto (Hermes pide al menos 64K para trabajar con herramientas)")
    p.add_argument("--cache-k", default="q8_0", help="tipo de la cache K (f16, q8_0, q4_0...)")
    p.add_argument("--cache-v", default="q8_0", help="tipo de la cache V (f16, q8_0, q4_0...)")
    p.add_argument("--fit-target", type=int, default=1024,
                   help="MiB que --fit deja libres en la GPU (sube si el escritorio usa la grafica)")
    p.add_argument("--capas-gpu", type=int, default=None,
                   help="fuerza el numero de capas en la GPU (por defecto lo decide --fit)")
    p.add_argument("--hilos", type=int, default=None,
                   help="hilos de CPU al generar (por defecto los decide llama.cpp)")
    p.add_argument("--ubatch", type=int, default=None,
                   help="tamano de bloque al leer el prompt (por defecto 512)")
    p.add_argument("--sin-mtp", action="store_true", help="desactiva la decodificacion especulativa MTP")
    p.add_argument("--borrador-n", type=int, default=2,
                   help="tokens que propone el borrador por paso (2 es lo que mejor rinde en GPUs pequenas)")
    p.add_argument("--dflash", default=None, help="ruta al GGUF del borrador DFlash 2 (opcional)")
    p.add_argument("--mmproj", default=None, help="ruta al proyector de vision (mmproj) si quieres imagenes")
    p.add_argument("--vision-en-cpu", action="store_true",
                   help="deja el codificador de vision en la CPU para no gastar VRAM")
    p.add_argument("--sin-op-offload", action="store_true",
                   help="no sube a la GPU las capas de la CPU al leer prompts largos (probar en Fase 0)")
    p.add_argument("--sin-pensar", action="store_true",
                   help="por defecto responde sin 'pensar' (cada peticion puede activarlo)")
    p.add_argument("--formato-razonamiento", default="deepseek",
                   help="como devuelve el razonamiento (deepseek = en reasoning_content, aparte)")
    p.add_argument("--checkpoints", type=int, default=32, help="--ctx-checkpoints de llama-server")
    p.add_argument("--cache-ram", type=int, default=8192, help="MiB de RAM para la cache de prompts")
    p.add_argument("--plantilla", default=None, help="archivo .jinja con la plantilla de chat oficial")
    p.add_argument("--solo-mostrar", action="store_true", help="imprime el comando y no lo ejecuta")
    p.add_argument("extra", nargs=argparse.REMAINDER,
                   help="cualquier opcion extra de llama-server, despues de '--'")
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.extra and a.extra[0] == "--":
        a.extra = a.extra[1:]
    cmd = construir_comando(a)
    for linea in avisos(a):
        print(linea, file=sys.stderr)
    print(mostrar(cmd))
    if a.solo_mostrar:
        return 0
    if not os.path.isfile(a.modelo):
        print(f"No existe el modelo: {a.modelo}", file=sys.stderr)
        return 2
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print(f"No encuentro llama-server en: {a.llama_server}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
