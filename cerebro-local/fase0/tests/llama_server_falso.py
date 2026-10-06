#!/usr/bin/env python3
"""Imita a llama-server para probar fase0.py de punta a punta sin GPU ni modelo.

Acepta la misma linea de comandos que genera arrancar_cerebro.py. Imprime las lineas de registro
que fase0.py lee (capas en GPU, aceptacion del borrador), tarda un poco en estar "listo" y sirve
las rutas de la API con el ServidorFalso de test_fase0.py.
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_fase0 import ServidorFalso  # noqa: E402


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

    time.sleep(0.5)  # "cargando el modelo"
    servidor = ServidorFalso(puerto=puerto, al_completar=al_completar)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with servidor:
        while True:
            time.sleep(0.2)


if __name__ == "__main__":
    sys.exit(main())
