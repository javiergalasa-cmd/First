#!/usr/bin/env python3
"""Imita a llama-server para probar fase0.py de punta a punta sin GPU ni modelo.

Acepta la misma linea de comandos que genera arrancar_cerebro.py. Imprime las lineas de registro
que fase0.py lee (capas en GPU, aceptacion del borrador), tarda un poco en estar "listo" y sirve
las rutas de la API con el ServidorFalso de test_fase0.py. La velocidad que anuncia depende de las
opciones recibidas, para poder probar la eleccion de ajustes de --exprimir.
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_fase0 import ServidorFalso  # noqa: E402


def velocidades(argv: list[str]) -> tuple[float, float]:
    """(tok/s al generar, tok/s al leer el prompt) segun las opciones: un mundo de juguete conocido."""
    def valor(opcion):
        return argv[argv.index(opcion) + 1] if opcion in argv else None

    tok, lee = 10.0, 500.0
    tipo, n = valor("--spec-type"), valor("--spec-draft-n-max")
    if tipo is None:
        tok = 6.0
    elif tipo == "draft-dflash":
        tok = 14.0
    elif n == "1":
        tok = 9.5
    elif n == "3":
        tok = 9.0
    if valor("-t") == "8":
        tok *= 1.2
    elif valor("-t") == "4":
        tok *= 1.02
    if valor("--fit-target") == "512":
        tok *= 1.1
    if valor("-ctk") == "q4_0":
        tok *= 1.15
    if valor("-ub") == "2048":
        lee *= 1.4
    if "--no-op-offload" in argv:
        lee *= 0.4
        tok *= 1.03
    return round(tok, 2), round(lee, 1)


def main() -> int:
    argv = sys.argv[1:]
    if "--help" in argv:
        print("--spec-type none,draft-simple,draft-mtp,draft-dflash")
        return 0
    puerto = int(argv[argv.index("--port") + 1])
    con_borrador = "--spec-type" in argv
    print("load_tensors: offloaded 25/65 layers to GPU", flush=True)

    def al_completar(_cuerpo):
        if con_borrador:
            print("slot print_timing: draft acceptance rate = 0.80000 (   24 accepted /    30 generated)",
                  flush=True)

    tok_s, lee_s = velocidades(argv)
    time.sleep(0.5)  # "cargando el modelo"
    servidor = ServidorFalso(puerto=puerto, al_completar=al_completar, tok_s=tok_s, lee_s=lee_s)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with servidor:
        while True:
            time.sleep(0.2)


if __name__ == "__main__":
    sys.exit(main())
