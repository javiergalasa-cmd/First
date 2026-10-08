#!/usr/bin/env python3
"""Fase 0 automatica: inventario del PC + descargas + pruebas del cerebro local de JADIS.

Un solo comando hace toda la Fase 0 de ../PLAN.md:
  1. Inventario del equipo: GPU, VRAM, CPU, RAM (tipo, velocidad, modulos y canales), disco.
  2. Descarga (pidiendo confirmacion) la ultima compilacion oficial de llama.cpp para Windows con
     CUDA y el modelo de referencia (Qwen3.8-27B GSQ-RCO de ISTA-DASLab, con cabezal MTP).
     Reanuda descargas cortadas y comprueba el SHA256 de cada archivo.
  3. Prueba cada variante con y sin MTP usando arrancar_cerebro.py y bench_cerebro.py.
  4. Deja <carpeta>/informe-fase0.md y .json. NO llevan nombre del equipo, usuario, rutas ni
     numeros de serie: se pueden compartir tal cual.

Uso (PowerShell, dentro de la carpeta fase0):
  python fase0.py --solo-inventario          # ~10 s, no descarga nada
  python fase0.py                            # todo; pregunta antes de descargar
  python fase0.py --variantes iq3_s,iq2_s    # medir tambien la de 2,75 bits
  python fase0.py --sin-descargas --llama-server C:\\llama\\llama-server.exe --modelo D:\\m.gguf

Solo usa la biblioteca estandar de Python 3.9+. Solo se conecta a github.com (llama.cpp) y a
huggingface.co (el modelo) para descargar; las pruebas hablan solo con 127.0.0.1.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import arrancar_cerebro  # noqa: E402
import bench_cerebro  # noqa: E402

REPO_MODELO = "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF"
REPO_DFLASH = "z-lab/Qwen3.8-27B-DFlash2-GGUF"  # borrador DFlash 2 para Qwen3.8-27B (opcional)
# No "/releases/latest": llama.cpp publica cada version como pre-release y "latest" se las salta
# (devolvia una version vieja con otros nombres de archivo). La lista va de la mas nueva a la mas vieja.
RELEASES_LLAMA = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15"
AGENTE = "jadis-fase0/1.0"
VARIANTES = {  # nombre -> cuantizacion que debe aparecer en el nombre del archivo
    "iq2_xs": "IQ2_XS", "iq2_s": "IQ2_S", "iq3_xxs": "IQ3_XXS", "iq3_s": "IQ3_S",
    "iq4_xs": "IQ4_XS", "q4_k_m": "Q4_K_M",
}
CONFIGS = {  # nombre -> (opciones de arrancar_cerebro, opciones de bench_cerebro)
    "mtp2": (["--borrador-n", "2"], []),
    "mtp3": (["--borrador-n", "3"], ["--pensar", "no"]),
    "sin-mtp": (["--sin-mtp"], ["--pensar", "no"]),
}
# Ajustes que prueba --exprimir. Cada uno cambia UNA cosa respecto a "base".
# (nombre, opciones de arrancar_cerebro, grupo excluyente, coste en calidad, que hace)
AJUSTES = [
    ("base", ["--borrador-n", "2"], None, "ninguno", "la configuracion del plan (MTP con 2 tokens)"),
    ("sin-mtp", ["--sin-mtp"], "borrador", "ninguno", "referencia: sin decodificacion especulativa"),
    ("mtp1", ["--borrador-n", "1"], "borrador", "ninguno", "MTP con 1 token de borrador"),
    ("mtp3", ["--borrador-n", "3"], "borrador", "ninguno", "MTP con 3 tokens de borrador"),
    ("dflash", ["--dflash", "{dflash}", "--borrador-n", "7"], "borrador", "ninguno",
     "borrador DFlash 2 (~1 GB en la GPU) en vez del cabezal MTP"),
    ("hilos-nucleos", ["--hilos", "{nucleos}"], "hilos", "ninguno", "un hilo de CPU por nucleo fisico"),
    ("hilos-mitad", ["--hilos", "{mitad}"], "hilos", "ninguno", "la mitad de hilos (menos atascos en la RAM)"),
    ("margen-512", ["--fit-target", "512"], "margen", "ninguno",
     "deja 512 MiB libres en la GPU en vez de 1024: caben mas capas"),
    ("ubatch-2048", ["--ubatch", "2048"], "ubatch", "ninguno",
     "lee el prompt en bloques de 2048 (menos viajes por el PCIe, mas VRAM de trabajo)"),
    ("sin-op-offload", ["--sin-op-offload"], "op", "ninguno", "no sube capas de la CPU a la GPU al leer el prompt"),
    ("sin-mmap", ["--sin-mmap"], "mmap", "ninguno",
     "carga todo el modelo en RAM al arrancar (en modelos MoE suele acelerar los expertos de la CPU)"),
    ("kv-q4", ["--cache-k", "q4_0", "--cache-v", "q4_0"], "kv", "pequeno",
     "cache KV a 4 bits: libera VRAM para mas capas, pierde algo de precision"),
]
BENCH_RAPIDO = ["--turnos", "2", "--pensar", "no", "--sin-herramientas", "--tokens-sistema", "4000",
                "--max-tokens", "200"]
TIPOS_SMBIOS = {26: "DDR4", 34: "DDR5", 30: "LPDDR4", 35: "LPDDR5"}
MARGEN_DISCO = 2 * 1024**3
MINIMO_MODELO = 4 * 1024**3  # un 27B no baja de ~7 GB ni a 2 bits
# El IQ3_S pesa ~11,8 GB y en 8 GB de VRAM caben ~6: el resto (~6 GB), la cache de prompts y los
# buferes van a la RAM. Por debajo de esto, Windows empieza a paginar y las medidas no valen.
RAM_DISPONIBLE_MINIMA_GB = 12


def decir(texto: str = "") -> None:
    print(texto, flush=True)


# --------------------------------------------------------------------------- inventario

def _powershell_json(comando: str):
    """Ejecuta un comando de PowerShell y devuelve su salida como lista de objetos (o None)."""
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
             + comando + " | ConvertTo-Json -Depth 3 -Compress"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    try:
        datos = json.loads(cp.stdout)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, list) else [datos]


def _nvidia_smi() -> dict:
    campos = ["name", "memory.total", "memory.used", "driver_version", "pcie.link.gen.max",
              "pcie.link.width.max"]
    salida: dict = {}
    try:
        cp = subprocess.run(["nvidia-smi", "--query-gpu=" + ",".join(campos),
                             "--format=csv,noheader,nounits"],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        if cp.returncode == 0 and cp.stdout.strip():
            valores = [v.strip() for v in cp.stdout.strip().splitlines()[0].split(",")]
            salida = dict(zip(campos, valores))
        cp = subprocess.run(["nvidia-smi"], capture_output=True, encoding="utf-8", errors="replace",
                            timeout=30)
        m = re.search(r"CUDA(?: Driver)? Version\s*:\s*([\d.]+)", cp.stdout or "")
        if m:
            salida["cuda_max_driver"] = m.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return salida


def tipo_y_velocidad(modulo: dict) -> tuple[str | None, int | None, int | None]:
    """Deduce de un modulo de Win32_PhysicalMemory: tipo (DDR4/DDR5), MT/s a los que va y MT/s
    para los que esta hecho (la referencia de Kingston FURY lo dice: KF432C16.. = DDR4-3200,
    KF560C36.. = DDR5-6000). Si va mas lento de lo nominal, falta activar XMP/EXPO en la BIOS."""
    tipo = TIPOS_SMBIOS.get(int(modulo.get("SMBIOSMemoryType") or 0))
    configurada = int(modulo.get("ConfiguredClockSpeed") or 0) or None
    nominal = int(modulo.get("Speed") or 0) or None
    m = re.match(r"^KF([45])(\d{2})C", (modulo.get("PartNumber") or "").strip().upper())
    if m:
        tipo = tipo or f"DDR{m.group(1)}"
        nominal = max(nominal or 0, int(m.group(2)) * 100)
    return tipo, configurada or nominal, nominal


def canales_probables(modulos: list[dict]) -> int:
    """1 modulo = 1 canal. Con 2 o 4, casi todas las placas de consumo usan los 2 canales."""
    n = len(modulos)
    if n <= 1:
        return n
    etiquetas = " ".join(f"{m.get('DeviceLocator', '')} {m.get('BankLabel', '')}" for m in modulos).upper()
    if "CHANNEL A" in etiquetas and "CHANNEL B" not in etiquetas:
        return 1
    return 2


def resumir_ram(modulos: list[dict], ranuras: int | None) -> dict:
    modulos = [m for m in modulos if int(m.get("Capacity") or 0) > 0]
    if not modulos:
        return {"modulos": 0}
    tipo, velocidad, nominal = tipo_y_velocidad(modulos[0])
    canales = canales_probables(modulos)
    ancho = round(velocidad * 8 * canales / 1000, 1) if velocidad else None
    return {
        "total_gb": round(sum(int(m["Capacity"]) for m in modulos) / 1024**3),
        "modulos": len(modulos),
        "gb_por_modulo": sorted({round(int(m["Capacity"]) / 1024**3) for m in modulos}),
        "ranuras_en_placa": ranuras,
        "tipo": tipo,
        "velocidad_mts": velocidad,
        "velocidad_nominal_mts": nominal,
        "fabricante": (modulos[0].get("Manufacturer") or "").strip() or None,
        "referencia": (modulos[0].get("PartNumber") or "").strip() or None,
        "canales_probables": canales,
        "ancho_banda_teorico_gbs": ancho,
    }


def inventario(carpeta: str) -> dict:
    inv: dict = {"sistema": platform.system(), "version_sistema": platform.release(),
                 "python": platform.python_version()}
    if platform.system() == "Windows":
        cpu = _powershell_json("Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,"
                               "NumberOfLogicalProcessors,MaxClockSpeed")
        ram = _powershell_json("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,"
                               "ConfiguredClockSpeed,SMBIOSMemoryType,Manufacturer,PartNumber,"
                               "DeviceLocator,BankLabel")
        ranuras = _powershell_json("Get-CimInstance Win32_PhysicalMemoryArray | Select-Object MemoryDevices")
        placa = _powershell_json("Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product")
        graficas = _powershell_json("Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion")
        sistema = _powershell_json("Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory")
        inv["cpu"] = (cpu or [{}])[0]
        inv["ram"] = resumir_ram(ram or [], max((int(r.get("MemoryDevices") or 0) for r in ranuras or []),
                                                default=0) or None)
        inv["placa"] = (placa or [{}])[0]
        inv["graficas"] = [g.get("Name") for g in graficas or []]
        libre_kb = int((sistema or [{}])[0].get("FreePhysicalMemory") or 0)
        inv["ram_disponible_gb"] = round(libre_kb / 1024**2, 1) if libre_kb else None
    inv["nvidia"] = _nvidia_smi()
    os.makedirs(carpeta, exist_ok=True)
    inv["disco_libre_gb"] = round(shutil.disk_usage(carpeta).free / 1024**3, 1)
    # Programas que pueden estar ocupando la GPU y falsear las medidas.
    inv["abiertos"] = [nombre for nombre, puerto in (("Ollama", 11434), ("JADIS (backend)", 8400),
                                                       ("JADIS (router)", 8420))
                       if not puerto_libre(puerto)]
    return inv


def avisos_inventario(inv: dict) -> list[str]:
    avisos = []
    ram = inv.get("ram") or {}
    if ram.get("canales_probables") == 1:
        avisos.append("La RAM funciona en UN canal (un solo modulo): la mitad de ancho de banda posible. "
                      "Anadir un segundo modulo igual es la mejora mas barata para el cerebro local.")
    va, nominal = ram.get("velocidad_mts"), ram.get("velocidad_nominal_mts")
    if va and nominal and nominal - va >= 200:
        avisos.append(f"La RAM va a {va} MT/s pero es de {nominal}: activa el perfil XMP/EXPO (DOCP en placas "
                      f"ASUS) en la BIOS. Es gratis y sube hasta un {round((nominal / va - 1) * 100)}% la "
                      "velocidad de la parte del modelo que va en la CPU.")
    disponible = inv.get("ram_disponible_gb")
    if disponible is not None and disponible < RAM_DISPONIBLE_MINIMA_GB:
        avisos.append(f"Solo hay {disponible} GB de RAM disponibles (lo que el Administrador de tareas llama "
                      f"'Disponible'). La parte del modelo que no cabe en la GPU va a la RAM: con menos de "
                      f"{RAM_DISPONIBLE_MINIMA_GB} GB, Windows puede tirar del disco y las medidas saldrian mucho "
                      "mas lentas de lo real. Cierra el navegador, juegos y lo que no uses.")
    if ram.get("total_gb") and ram["total_gb"] < 32:
        avisos.append("Menos de 32 GB de RAM: solo caben las variantes pequenas (IQ2_S / IQ3_XXS).")
    usada = inv.get("nvidia", {}).get("memory.used")
    if usada and usada.isdigit() and int(usada) > 1500:
        avisos.append(f"La GPU ya tiene {usada} MiB ocupados antes de empezar (navegador, juegos, Ollama...). "
                      "Cierra lo que puedas para medir bien.")
    if inv.get("abiertos"):
        avisos.append("Estan abiertos: " + ", ".join(inv["abiertos"]) + ". Pueden ocupar GPU y RAM y falsear "
                      "las medidas: cierralos durante la prueba (en Ollama: 'ollama stop <modelo>').")
    return avisos


# --------------------------------------------------------------------------- descargas

def pedir_json(url: str, timeout: float = 60):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def listar_archivos_hf(repo: str) -> list[dict]:
    """Lista los archivos de un repo de Hugging Face con tamano y SHA256 (formato de /tree)."""
    try:
        arbol = pedir_json(f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true")
        if isinstance(arbol, list):
            return arbol
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError(f"{repo} pide iniciar sesion o aceptar condiciones en Hugging Face") from e
    # Plan B: la ficha del modelo con ?blobs=true trae los mismos datos con otro formato.
    info = pedir_json(f"https://huggingface.co/api/models/{repo}?blobs=true")
    archivos = []
    for s in info.get("siblings", []):
        lfs = s.get("lfs") or {}
        archivos.append({"type": "file", "path": s["rfilename"], "size": s.get("size"),
                         "lfs": {"oid": lfs.get("sha256"), "size": lfs.get("size") or s.get("size")}
                         if lfs else None})
    if not archivos:
        raise RuntimeError(f"Hugging Face no devolvio la lista de archivos de {repo}")
    return archivos


def _version(texto: str) -> tuple[int, ...]:
    return tuple(int(x) for x in texto.split("."))


def elegir_llama_cpp(release: dict, cuda_driver: str | None) -> dict:
    """Elige el zip de llama.cpp para Windows+CUDA y su cudart, con la CUDA mas alta que admita el driver."""
    assets = {a["name"]: a for a in release.get("assets", [])}
    candidatos = []
    for nombre, asset in assets.items():
        m = re.match(r"^llama-.*-bin-win-cuda-([\d.]+)-x64\.zip$", nombre)
        if not m:
            continue
        cudart = assets.get(f"cudart-llama-bin-win-cuda-{m.group(1)}-x64.zip")
        if cudart:
            candidatos.append((_version(m.group(1)), asset, cudart))
    if not candidatos:
        raise RuntimeError("La ultima release de llama.cpp no trae zips de Windows con CUDA")
    candidatos.sort(key=lambda c: c[0])
    aviso = None
    if cuda_driver:
        validos = [c for c in candidatos if c[0] <= _version(cuda_driver)]
        if validos:
            elegido = validos[-1]
        else:
            elegido = candidatos[0]
            aviso = (f"Tu driver solo admite CUDA {cuda_driver}; uso la compilacion mas antigua. "
                     "Si falla, actualiza el driver de NVIDIA.")
    else:
        elegido = candidatos[0]
        aviso = "No pude leer la version de CUDA del driver; uso la compilacion mas compatible."
    return {"tag": release.get("tag_name"), "cuda": ".".join(map(str, elegido[0])),
            "zips": [elegido[1], elegido[2]], "aviso": aviso}


def elegir_release_llama(releases: list[dict] | dict, cuda_driver: str | None) -> dict:
    """La release mas nueva que ya tenga los zips de Windows+CUDA completos.

    La mas reciente puede estar a medio subir (los zips llegan durante unos minutos tras crearla):
    en ese caso se usa la anterior."""
    if isinstance(releases, dict):  # por si la API devuelve una sola
        releases = [releases]
    ultimo_error = None
    for release in releases:
        if release.get("draft"):
            continue
        try:
            return elegir_llama_cpp(release, cuda_driver)
        except RuntimeError as e:
            ultimo_error = e
    raise RuntimeError(f"Ninguna de las ultimas {len(releases)} releases de llama.cpp trae zips de Windows "
                       f"con CUDA ({ultimo_error}). Descarga a mano llama-...-bin-win-cuda-12.4-x64.zip y "
                       "cudart-llama-bin-win-cuda-12.4-x64.zip de github.com/ggml-org/llama.cpp/releases, "
                       "descomprimelos en la misma carpeta y usa --sin-descargas --llama-server <ruta>")


def elegir_archivos_modelo(arbol: list[dict], variante: str, exigir_mtp: bool = True) -> dict:
    """Elige el/los GGUF de una variante. Prefiere el que lleva el cabezal MTP ('mtp' en el nombre)."""
    cuant = VARIANTES[variante]
    patron = re.compile(rf"(?<![a-z0-9]){re.escape(cuant)}(?![a-z0-9])", re.IGNORECASE)
    ggufs = [f for f in arbol if f.get("type", "file") == "file" and f["path"].lower().endswith(".gguf")
             and "mmproj" not in f["path"].lower() and patron.search(os.path.basename(f["path"]))]
    con_mtp = [f for f in ggufs if "mtp" in os.path.basename(f["path"]).lower()]
    elegidos, mtp = (con_mtp, True) if con_mtp else (ggufs, False)
    if not elegidos:
        raise RuntimeError(f"No encuentro archivos {cuant} en el repo")
    if exigir_mtp and not mtp:
        aviso = f"El repo no tiene {cuant} con cabezal MTP: se probara sin MTP."
    else:
        aviso = None
    # Si viene troceado (-00001-of-00003.gguf) hacen falta todas las partes del mismo grupo.
    primero = sorted(elegidos, key=lambda f: f["path"])[0]
    m = re.match(r"^(.*)-\d{5}-of-(\d{5})\.gguf$", primero["path"], re.IGNORECASE)
    if m:
        grupo = [f for f in elegidos if f["path"].startswith(m.group(1) + "-")]
        elegidos = sorted(grupo, key=lambda f: f["path"])
    else:
        elegidos = [primero]
    archivos = [{"ruta": f["path"], "tam": (f.get("lfs") or {}).get("size") or f.get("size"),
                 "sha256": (f.get("lfs") or {}).get("oid")} for f in elegidos]
    total = sum(a["tam"] or 0 for a in archivos)
    if total and total < MINIMO_MODELO:
        # Algunos repos publican el cabezal MTP como archivo aparte (~0,5 GB): no es el modelo.
        raise RuntimeError(f"{archivos[0]['ruta']} ocupa {total / 1024**3:.1f} GB: parece solo el cabezal "
                           "MTP, no el modelo completo. Revisa el repo.")
    return {"variante": variante, "mtp": mtp, "aviso": aviso, "archivos": archivos}


def elegir_borrador(arbol: list[dict]) -> dict:
    """Elige el GGUF del borrador DFlash 2: prefiere Q4_K_M (~1,1 GB), si no Q8_0, si no el mas pequeno."""
    ggufs = [f for f in arbol if f.get("type", "file") == "file" and f["path"].lower().endswith(".gguf")
             and "mmproj" not in f["path"].lower()]
    if not ggufs:
        raise RuntimeError("El repo del borrador DFlash no tiene archivos .gguf")

    def tam(f):
        return (f.get("lfs") or {}).get("size") or f.get("size") or 0

    for cuant in ("Q4_K_M", "Q8_0"):
        candidatos = [f for f in ggufs if cuant.lower() in os.path.basename(f["path"]).lower()]
        if candidatos:
            elegido = min(candidatos, key=tam)
            break
    else:
        elegido = min(ggufs, key=tam)
    return {"ruta": elegido["path"], "tam": tam(elegido) or None, "sha256": (elegido.get("lfs") or {}).get("oid")}


def sha256_de(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def descargar(url: str, destino: str, tam: int | None = None, sha256: str | None = None,
              timeout: float = 60) -> str:
    """Descarga con reanudacion (cabecera Range) y comprueba tamano y SHA256. Devuelve la ruta final."""
    if os.path.exists(destino):
        if sha256 and sha256_de(destino) != sha256:
            raise RuntimeError(f"{os.path.basename(destino)} ya existe pero su SHA256 no coincide; borralo")
        return destino
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    parcial = destino + ".parcial"
    inicio = os.path.getsize(parcial) if os.path.exists(parcial) else 0
    cabeceras = {"User-Agent": AGENTE}
    if inicio:
        cabeceras["Range"] = f"bytes={inicio}-"
    if not (tam and inicio == tam):  # si el .parcial ya esta completo, solo falta comprobarlo
        req = urllib.request.Request(url, headers=cabeceras)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if inicio and r.status != 206:
                inicio = 0  # el servidor ignoro el Range: se empieza de cero
            total = tam or (int(r.headers.get("Content-Length", 0)) + inicio) or None
            hecho, ultimo = inicio, -1
            with open(parcial, "ab" if inicio else "wb") as f:
                for bloque in iter(lambda: r.read(1024 * 1024), b""):
                    f.write(bloque)
                    hecho += len(bloque)
                    if total:
                        pct = int(hecho * 100 / total)
                        if pct != ultimo and pct % 5 == 0:
                            decir(f"    {os.path.basename(destino)}: {pct}% ({hecho / 1024**3:.1f} GB)")
                            ultimo = pct
    if tam and os.path.getsize(parcial) != tam:
        raise RuntimeError(f"{os.path.basename(destino)}: tamano {os.path.getsize(parcial)} != {tam}; "
                           "vuelve a lanzar para reanudar")
    if sha256:
        decir(f"    comprobando SHA256 de {os.path.basename(destino)}...")
        obtenido = sha256_de(parcial)
        if obtenido != sha256:
            os.replace(parcial, destino + ".corrupto")
            raise RuntimeError(f"{os.path.basename(destino)}: SHA256 no coincide (esperado {sha256[:12]}..., "
                               f"obtenido {obtenido[:12]}...)")
    os.replace(parcial, destino)
    return destino


def bytes_pendientes(destino: str, tam: int | None) -> int:
    """Lo que falta por bajar de un archivo (para no pedir espacio de mas al reanudar)."""
    if not tam or os.path.exists(destino):
        return 0
    parcial = destino + ".parcial"
    return max(0, tam - (os.path.getsize(parcial) if os.path.exists(parcial) else 0))


def instalar_llama_cpp(eleccion: dict, carpeta: str) -> str:
    destino = os.path.join(carpeta, "llama.cpp", f"{eleccion['tag']}-cuda-{eleccion['cuda']}")
    marca = os.path.join(destino, ".instalado")
    exe = buscar_archivo(destino, "llama-server.exe")
    if exe and os.path.exists(marca):  # la marca asegura que tambien se extrajo el zip de cudart
        return exe
    for asset in eleccion["zips"]:
        digest = asset.get("digest") or ""  # GitHub publica "sha256:<hex>" en los assets recientes
        zip_ruta = descargar(asset["browser_download_url"],
                             os.path.join(carpeta, "descargas", asset["name"]), asset.get("size"),
                             digest.split(":", 1)[1] if digest.startswith("sha256:") else None)
        with zipfile.ZipFile(zip_ruta) as z:
            z.extractall(destino)
    exe = buscar_archivo(destino, "llama-server.exe")
    if not exe:
        raise RuntimeError("El zip de llama.cpp no trae llama-server.exe")
    with open(marca, "w", encoding="utf-8") as f:
        f.write(" + ".join(a["name"] for a in eleccion["zips"]))
    return exe


def llama_cpp_instalado(carpeta: str) -> dict | None:
    """El llama.cpp ya instalado mas reciente (completo, con su marca), o None.

    Se reutiliza en vez de bajar la ultima version en cada ejecucion: llama.cpp publica varias al
    dia, y cada una va a una carpeta distinta. Cambiar de version entre ejecuciones romperia el
    ajuste del panel de NVIDIA (que apunta a la ruta del .exe) y mezclaria motores distintos al
    comparar velocidades. --actualizar-llama baja la ultima a proposito."""
    base = os.path.join(carpeta, "llama.cpp")
    candidatos = []
    for nombre in (os.listdir(base) if os.path.isdir(base) else []):
        marca = os.path.join(base, nombre, ".instalado")
        exe = buscar_archivo(os.path.join(base, nombre), "llama-server.exe")
        if exe and os.path.exists(marca):
            candidatos.append((os.path.getmtime(marca), nombre, exe))
    if not candidatos:
        return None
    _, nombre, exe = max(candidatos)
    tag, _, cuda = nombre.partition("-cuda-")
    return {"tag": tag, "cuda": cuda, "exe": exe}


def buscar_archivo(carpeta: str, nombre: str) -> str | None:
    for raiz, _, archivos in os.walk(carpeta):
        if nombre in archivos:
            return os.path.join(raiz, nombre)
    return None


def soporta_mtp(llama_server: str) -> bool | None:
    try:
        cp = subprocess.run([llama_server, "--help"], capture_output=True, encoding="utf-8",
                            errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "draft-mtp" in (cp.stdout + cp.stderr)


# --------------------------------------------------------------------------- pruebas

class _Duplicar(io.TextIOBase):
    """Escribe a la vez en la consola y en un archivo (para ver el banco en vivo y guardarlo)."""

    def __init__(self, *destinos):
        self.destinos = destinos

    def write(self, texto):
        for d in self.destinos:
            d.write(texto)
        return len(texto)

    def flush(self):
        for d in self.destinos:
            d.flush()


def puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def esperar_listo(url: str, proceso: subprocess.Popen, limite_s: float) -> bool:
    fin = time.time() + limite_s
    while time.time() < fin:
        if proceso.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                if r.status == 200 and json.loads(r.read() or b"{}").get("status") == "ok":
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(2)
    return False


def esperar_liberado(puerto: int, vram_ref: int | None, limite_s: float = 90) -> None:
    """Tras cerrar llama-server, espera a que Windows suelte el puerto y la VRAM.

    Si la siguiente prueba arranca antes, --fit ve menos memoria libre de la real y llama-server
    puede abortar al no caber (lo que paso en la primera prueba del MoE)."""
    fin = time.time() + limite_s
    while time.time() < fin:
        usada = vram_usada_mib()
        if puerto_libre(puerto) and (vram_ref is None or usada is None or usada <= vram_ref + 300):
            break
        time.sleep(2)
    if platform.system() == "Windows":
        time.sleep(3)  # margen para que el driver termine de soltar la memoria


def cola_del_log(ruta: str, lineas: int = 15) -> str:
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lineas:])
    except OSError:
        return ""


def leer_log(ruta: str) -> dict:
    """Saca del registro de llama-server lo que el informe necesita (sin rutas)."""
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError:
        return {}
    datos: dict = {}
    m = re.search(r"offloaded (\d+)/(\d+) layers to GPU", texto)
    if m:
        datos["capas_gpu"] = f"{m.group(1)}/{m.group(2)}"
    tasas = re.findall(r"draft acceptance rate\s*=\s*([\d.]+)", texto)
    if tasas:
        valores = [float(t) for t in tasas]
        datos["aceptacion_mtp_media"] = round(sum(valores) / len(valores), 3)
    errores = [linea.strip() for linea in texto.splitlines()
               if re.search(r"out of memory|failed to|error:", linea, re.IGNORECASE)]
    if errores:
        datos["errores"] = [re.sub(r"[A-Za-z]:\\[^\s'\"]+|/[^\s'\"]+/", "<ruta>", e)[:200] for e in errores[-5:]]
    return datos


def vram_usada_mib() -> int | None:
    datos = _nvidia_smi().get("memory.used")
    return int(datos) if datos and datos.isdigit() else None


def memoria_compartida_mib(pid: int) -> int | None:
    """Memoria de GPU 'compartida' (RAM) que usa el proceso, segun los contadores de Windows."""
    if platform.system() != "Windows":
        return None
    comando = (f"(Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Shared Usage' -ErrorAction SilentlyContinue)"
               ".CounterSamples | Measure-Object -Property CookedValue -Sum | Select-Object Sum")
    datos = _powershell_json(comando)
    try:
        return round(float(datos[0]["Sum"]) / 1024**2)
    except (TypeError, KeyError, IndexError, ValueError):
        return None


def probar(nombre: str, llama_server: str, modelo: str, opciones_arranque: list[str],
           opciones_bench: list[str], carpeta: str, puerto: int, limite_carga_s: float) -> dict:
    url = f"http://127.0.0.1:{puerto}"
    os.makedirs(os.path.join(carpeta, "logs"), exist_ok=True)
    log_ruta = os.path.join(carpeta, "logs", f"{nombre}.log")
    informe_ruta = os.path.join(carpeta, "logs", f"{nombre}-bench.json")
    resultado: dict = {"prueba": nombre, "modelo": os.path.basename(modelo)}
    if not puerto_libre(puerto):
        resultado["error"] = f"el puerto {puerto} esta ocupado"
        return resultado
    args = arrancar_cerebro.parser().parse_args(
        ["--llama-server", llama_server, "--modelo", modelo, "--puerto", str(puerto), *opciones_arranque])
    cmd = arrancar_cerebro.construir_comando(args)
    vram_antes = vram_usada_mib()
    t0 = time.time()
    with open(log_ruta, "w", encoding="utf-8", errors="replace") as log:
        proceso = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            if not esperar_listo(url, proceso, limite_carga_s):
                resultado["error"] = "llama-server no llego a estar listo (mira logs/" + nombre + ".log)"
                log.flush()
                decir("   llama-server no arranco. Ultimas lineas de su registro:\n"
                      + "\n".join("   | " + l for l in cola_del_log(log_ruta).splitlines()))
                return resultado
            resultado["carga_s"] = round(time.time() - t0, 1)
            resultado["vram_antes_mib"] = vram_antes
            resultado["vram_cargado_mib"] = vram_usada_mib()
            consola = sys.stdout
            with open(os.path.join(carpeta, "logs", f"{nombre}-bench.txt"), "w", encoding="utf-8") as txt, \
                    contextlib.redirect_stdout(_Duplicar(consola, txt)):
                codigo = bench_cerebro.main(["--url", url, "--salida", informe_ruta, *opciones_bench])
            resultado["vram_final_mib"] = vram_usada_mib()
            resultado["compartida_mib"] = memoria_compartida_mib(proceso.pid)
            if os.path.exists(informe_ruta):
                with open(informe_ruta, encoding="utf-8") as f:
                    bench = json.load(f)
                # El informe se comparte: fuera rutas (el prompt de sistema puede venir de tu carpeta).
                for clave in ("modelo", "prompt_sistema"):
                    if isinstance(bench.get(clave), str):
                        bench[clave] = os.path.basename(bench[clave].replace("\\", "/"))
                resultado["bench"] = bench
            if codigo != 0:
                resultado["error"] = "el banco de pruebas no termino bien"
        finally:
            proceso.terminate()
            try:
                proceso.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=30)
            esperar_liberado(puerto, vram_antes)
    resultado.update(leer_log(log_ruta))
    return resultado


# --------------------------------------------------------------------------- informe

def _mediana(valores):
    valores = sorted(v for v in valores if v is not None)
    return valores[len(valores) // 2] if valores else None


def resumen_prueba(r: dict) -> dict:
    bloques = (r.get("bench") or {}).get("bloques") or []
    sin_pensar = [b for b in bloques if not b.get("pensar")]
    turnos = [t for b in sin_pensar for t in b.get("turnos", [])]
    primero = turnos[0] if turnos else {}
    caches = [t.get("cache_ok") for t in turnos if "cache_ok" in t]
    herramientas = [b.get("herramientas", {}).get("herramienta_ok") for b in bloques if b.get("herramientas")]
    propuestos = sum(t.get("borrador_propuestos") or 0 for b in bloques for t in b.get("turnos", []))
    aceptados = sum(t.get("borrador_aceptados") or 0 for b in bloques for t in b.get("turnos", []))
    return {
        "genera_tok_s": _mediana([t.get("decode_tok_s") or t.get("decode_tok_s_aprox") for t in turnos]),
        "lee_tok_s": primero.get("prefill_tok_s"),
        "primer_turno_s": primero.get("segundos_totales"),
        "cache": (None if not caches or None in caches else all(caches)),
        "herramienta": (None if not herramientas else all(herramientas)),
        "aceptacion_mtp": (round(aceptados / propuestos, 2) if propuestos else r.get("aceptacion_mtp_media")),
    }


def _v(valor) -> str:
    return "?" if valor in (None, "", []) else str(valor)


def informe_markdown(inv: dict, pruebas: list[dict], avisos: list[str]) -> str:
    ram = inv.get("ram") or {}
    nv = inv.get("nvidia") or {}
    cpu = inv.get("cpu") or {}
    placa = inv.get("placa") or {}
    lineas = ["# Informe de la Fase 0 (cerebro local de JADIS)", "",
              f"Generado: {time.strftime('%Y-%m-%d %H:%M')}. Sin nombres de equipo, usuario, rutas ni "
              "numeros de serie.", "", "## Equipo", "",
              f"- GPU: {_v(nv.get('name'))} | VRAM {_v(nv.get('memory.total'))} MiB | driver "
              f"{_v(nv.get('driver_version'))} (CUDA {_v(nv.get('cuda_max_driver'))}) | PCIe gen "
              f"{_v(nv.get('pcie.link.gen.max'))} x{_v(nv.get('pcie.link.width.max'))}",
              f"- CPU: {_v(cpu.get('Name'))} ({_v(cpu.get('NumberOfCores'))} nucleos)",
              f"- RAM: {_v(ram.get('total_gb'))} GB en {_v(ram.get('modulos'))} modulo(s), placa con "
              f"{_v(ram.get('ranuras_en_placa'))} ranuras | {_v(ram.get('tipo'))}-{_v(ram.get('velocidad_mts'))} | "
              f"referencia {_v(ram.get('referencia'))} | canales probables: {_v(ram.get('canales_probables'))} | "
              f"ancho de banda teorico: {_v(ram.get('ancho_banda_teorico_gbs'))} GB/s",
              f"- Placa: {_v(placa.get('Manufacturer'))} {placa.get('Product') or ''}".rstrip(),
              f"- Graficas vistas por Windows: {_v(', '.join(g for g in inv.get('graficas') or [] if g))}",
              f"- RAM disponible al empezar: {_v(inv.get('ram_disponible_gb'))} GB",
              f"- Disco libre en la carpeta de trabajo: {_v(inv.get('disco_libre_gb'))} GB", ""]
    if avisos:
        lineas += ["## Avisos", ""] + [f"- {a}" for a in avisos] + [""]
    if pruebas:
        lineas += ["## Resultados", "",
                   "| Prueba | Capas en GPU | VRAM cargado | Lee prompt (tok/s) | Primer turno (s) | "
                   "Genera sin pensar (tok/s) | Cache entre turnos | Herramienta | Aceptacion MTP |",
                   "|---|---|---|---|---|---|---|---|---|"]
        marca = {True: "OK", False: "FALLO", None: "?"}
        for r in pruebas:
            if r.get("error") and not r.get("bench"):
                lineas.append(f"| {r['prueba']} | ERROR: {r['error']} |  |  |  |  |  |  |  |")
                continue
            s = resumen_prueba(r)
            vram = r.get("vram_cargado_mib")
            lineas.append(
                f"| {r['prueba']} | {_v(r.get('capas_gpu'))} | {_v(vram) + ' MiB' if vram is not None else '?'} | "
                f"{_v(s['lee_tok_s'])} | {_v(s['primer_turno_s'])} | {_v(s['genera_tok_s'])} | "
                f"{marca[s['cache']]} | {marca[s['herramienta']]} | "
                f"{'-' if s['aceptacion_mtp'] is None else s['aceptacion_mtp']} |")
        lineas += ["", "Detalle de cada prueba en `informe-fase0.json` y en `logs/`.", ""]
    return "\n".join(lineas)


# --------------------------------------------------------------------------- prueba de velocidad

def resolver_ajustes(inv: dict, dflash: str | None, con_mtp: bool = True) -> list[tuple]:
    """Rellena {nucleos}, {mitad} y {dflash}; quita los ajustes que no se pueden probar en este PC.

    Sin cabezal MTP en el modelo (p. ej. los MoE sin censura), 'base' va sin borrador y no se
    prueban las variantes del borrador."""
    nucleos = int((inv.get("cpu") or {}).get("NumberOfCores") or 0) or (os.cpu_count() or 0) // 2 or None
    valores = {"nucleos": nucleos, "mitad": max(1, nucleos // 2) if nucleos else None, "dflash": dflash}
    resueltos = []
    for nombre, opciones, grupo, coste, que in AJUSTES:
        if not con_mtp:
            if grupo == "borrador":
                continue
            if nombre == "base":
                opciones, que = ["--sin-mtp"], "la configuracion de partida (sin borrador: el modelo no trae MTP)"
        if any(not valores.get(k) for k in re.findall(r"\{(\w+)\}", " ".join(opciones))):
            continue
        resueltos.append((nombre, [o.format(**valores) for o in opciones], grupo, coste, que))
    return resueltos


def medir_ajuste(r: dict) -> dict:
    s = resumen_prueba(r)
    return {"genera": s["genera_tok_s"], "lee": s["lee_tok_s"], "capas": r.get("capas_gpu"),
            "vram": r.get("vram_cargado_mib"), "aceptacion": s["aceptacion_mtp"],
            "error": r.get("error") if not s["genera_tok_s"] else None}


def ganancia(valor, base) -> float | None:
    return None if not valor or not base else round((valor / base - 1) * 100, 1)


def elegir_ganadores(resultados: dict, ajustes: list[tuple]) -> list[str]:
    """Ajustes sin coste de calidad que mejoran a 'base' (>= 5 % al generar, o >= 10 % al leer el prompt
    sin empeorar la generacion). De cada grupo excluyente se queda el mejor."""
    base = resultados.get("base") or {}
    mejores: dict = {}
    for nombre, _, grupo, coste, _ in ajustes:
        r = resultados.get(nombre) or {}
        if nombre == "base" or coste != "ninguno" or r.get("error"):
            continue
        g_gen, g_lee = ganancia(r.get("genera"), base.get("genera")), ganancia(r.get("lee"), base.get("lee"))
        if g_gen is None:
            continue
        if not ((g_gen >= 5 and (g_lee is None or g_lee >= -30)) or (g_lee is not None and g_lee >= 10 and g_gen >= -5)):
            continue
        puntos = g_gen + 0.1 * (g_lee or 0)  # lo que mas cuenta es generar
        if grupo not in mejores or puntos > mejores[grupo][1]:
            mejores[grupo] = (nombre, puntos)
    return [nombre for nombre, _ in mejores.values()]


def opciones_de(nombres: list[str], ajustes: list[tuple]) -> list[str]:
    """Las opciones de 'base' con las de los ganadores encima. Si un ganador cambia una opcion que
    ya trae 'base' (p. ej. --borrador-n), se quita la de 'base' para no repetirla."""
    por_nombre = {n: o for n, o, *_ in ajustes}
    extra = [o for n in nombres for o in por_nombre[n]]
    pisadas = {o for o in extra if o.startswith("--")}
    opciones, base, i = [], por_nombre["base"], 0
    while i < len(base):
        if base[i] in pisadas:
            i += 2 if i + 1 < len(base) and not base[i + 1].startswith("--") else 1
            continue
        opciones.append(base[i])
        i += 1
    return opciones + extra


def exprimir(inv: dict, llama_server: str, modelo: str, dflash: str | None, carpeta: str, puerto: int,
             limite_carga: float) -> dict:
    """Prueba cada ajuste por separado, elige los que ganan y prueba su combinacion."""
    ajustes = resolver_ajustes(inv, dflash, "mtp" in os.path.basename(modelo).lower())
    salida: dict = {"modelo": os.path.basename(modelo), "ajustes": [], "resultados": {}, "pruebas": []}
    for nombre, opciones, grupo, coste, que in ajustes:
        decir(f"-- ajuste '{nombre}': {que}")
        r = probar(f"velocidad-{nombre}", llama_server, modelo, opciones, BENCH_RAPIDO, carpeta, puerto,
                   limite_carga)
        salida["pruebas"].append(r)
        salida["resultados"][nombre] = medir_ajuste(r)
        salida["ajustes"].append({"nombre": nombre, "grupo": grupo, "coste": coste, "que": que})
        if nombre == "base" and salida["resultados"]["base"]["error"]:
            salida["error"] = "la configuracion base no funciono: " + str(salida["resultados"]["base"]["error"])
            return salida
    ganadores = elegir_ganadores(salida["resultados"], ajustes)
    salida["ganadores"] = ganadores
    recomendadas = opciones_de([], ajustes)
    if ganadores:
        mejor = max(ganadores, key=lambda n: salida["resultados"][n]["genera"] or 0)
        recomendadas = opciones_de([mejor], ajustes)
        if len(ganadores) >= 2:
            decir(f"-- combinando los ganadores: {', '.join(ganadores)}")
            r = probar("velocidad-combinada", llama_server, modelo, opciones_de(ganadores, ajustes),
                       BENCH_RAPIDO, carpeta, puerto, limite_carga)
            salida["pruebas"].append(r)
            salida["combinada"] = medir_ajuste(r)
            if (salida["combinada"]["genera"] or 0) >= (salida["resultados"][mejor]["genera"] or 0):
                recomendadas = opciones_de(ganadores, ajustes)
    salida["opciones_recomendadas"] = [("<borrador DFlash>" if dflash and o == dflash else o) for o in recomendadas]
    return salida


def informe_velocidad(inv: dict, s: dict) -> str:
    base = (s.get("resultados") or {}).get("base") or {}
    ram = inv.get("ram") or {}
    lineas = ["# Prueba de velocidad del cerebro local", "",
              f"Modelo: `{s.get('modelo')}`. Generado: {time.strftime('%Y-%m-%d %H:%M')}. "
              f"RAM: {_v(ram.get('tipo'))}-{_v(ram.get('velocidad_mts'))} en {_v(ram.get('modulos'))} modulo(s).", "",
              "Cada ajuste cambia **una sola cosa** respecto a `base`. Diferencias por debajo de ~5 % son ruido "
              "(repite la prueba si dudas).", "",
              "| Ajuste | Que cambia | Coste en calidad | Genera (tok/s) | vs base | Lee prompt (tok/s) | vs base "
              "| Capas en GPU | VRAM (MiB) | Aceptacion borrador |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for aj in s.get("ajustes", []):
        r = s["resultados"].get(aj["nombre"], {})
        if r.get("error"):
            lineas.append(f"| {aj['nombre']} | {aj['que']} | {aj['coste']} | ERROR: {str(r['error'])[:80]} |"
                          "  |  |  |  |  |  |")
            continue
        g_gen, g_lee = ganancia(r.get("genera"), base.get("genera")), ganancia(r.get("lee"), base.get("lee"))
        fmt = (lambda g: "-" if g is None or aj["nombre"] == "base" else f"{g:+.0f} %")
        lineas.append(f"| {aj['nombre']} | {aj['que']} | {aj['coste']} | {_v(r.get('genera'))} | {fmt(g_gen)} | "
                      f"{_v(r.get('lee'))} | {fmt(g_lee)} | {_v(r.get('capas'))} | {_v(r.get('vram'))} | "
                      f"{'-' if r.get('aceptacion') is None else r['aceptacion']} |")
    lineas += ["", "## Resultado", ""]
    if s.get("error"):
        lineas.append(f"- No se pudo completar: {s['error']}")
    else:
        lineas.append("- Ajustes que ganan sin coste de calidad: "
                      + (", ".join(f"`{g}`" for g in s.get("ganadores", [])) or "ninguno (la base ya es lo mejor)"))
        if s.get("combinada"):
            c = s["combinada"]
            lineas.append(f"- Combinacion de ganadores: genera {_v(c.get('genera'))} tok/s "
                          f"({ganancia(c.get('genera'), base.get('genera'))} % frente a base)")
        lineas.append("- Comando recomendado: `python arrancar_cerebro.py --modelo <tu modelo> "
                      + " ".join(s.get("opciones_recomendadas", [])) + "`")
        kv = s["resultados"].get("kv-q4") or {}
        if kv.get("genera") and base.get("genera"):
            lineas.append(f"- Con coste de calidad: `kv-q4` da {ganancia(kv['genera'], base['genera'])} % al generar. "
                          "Solo si aceptas perder algo de precision en conversaciones largas.")
    lineas += ["", "## Lo que este script no puede probar solo", "",
               "- **XMP/EXPO (DOCP en ASUS)**: si el inventario avisa de que la RAM va por debajo de su velocidad, "
               "activalo en la BIOS y repite la prueba.",
               "- **Monitor en la grafica integrada**: libera VRAM de la 4060 para mas capas; repite la prueba "
               "despues y compara la columna 'Capas en GPU'.",
               "- **Segundo modulo de RAM igual**: pasa a dos canales; es el salto mas grande sin cambiar de GPU.", ""]
    return "\n".join(lineas)


# --------------------------------------------------------------------------- principal

def carpeta_por_defecto() -> str:
    if platform.system() == "Windows":
        return "C:\\jadis-cerebro"
    return os.path.join(os.path.expanduser("~"), "jadis-cerebro")


def confirmar(pregunta: str, si: bool) -> bool:
    if si:
        return True
    try:
        return input(pregunta + " [s/N] ").strip().lower() in ("s", "si", "y", "yes")
    except EOFError:
        return False


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fase 0 automatica del cerebro local de JADIS.")
    p.add_argument("--carpeta", default=carpeta_por_defecto(), help="donde se guarda todo (necesita ~15 GB)")
    p.add_argument("--solo-inventario", action="store_true", help="solo mira el equipo; no descarga nada")
    p.add_argument("--variantes", default="iq3_s,iq2_s",
                   help="variantes del modelo separadas por comas: " + ", ".join(VARIANTES)
                   + " (por defecto la de 3,5 bits y la de 2,75 bits, ~21 GB en total)")
    p.add_argument("--configs", default="mtp2,sin-mtp", help="pruebas por variante: " + ", ".join(CONFIGS))
    p.add_argument("--repo", default=REPO_MODELO, help="repo de Hugging Face del modelo")
    p.add_argument("--sin-descargas", action="store_true", help="usar --llama-server y --modelo ya descargados")
    p.add_argument("--llama-server", default=None, help="ruta a llama-server(.exe) ya instalado")
    p.add_argument("--modelo", action="append", default=[], help="ruta a un .gguf ya descargado (repetible)")
    p.add_argument("--puerto", type=int, default=8080)
    p.add_argument("--rapido", action="store_true", help="pruebas cortas: 2 turnos, sin pensar")
    p.add_argument("--sistema", default=None, help="archivo con el prompt de sistema real de Hermes")
    p.add_argument("--limite-carga", type=float, default=900, help="segundos maximos para cargar el modelo")
    p.add_argument("--si", action="store_true", help="no preguntar antes de descargar")
    p.add_argument("--solo-descargar", action="store_true",
                   help="descarga, dice donde ha quedado llama-server.exe (para el panel de NVIDIA) y para")
    p.add_argument("--exprimir", action="store_true",
                   help="prueba de velocidad: prueba ajustes uno a uno sobre la primera variante y recomienda")
    p.add_argument("--sin-dflash", action="store_true", help="con --exprimir, no bajar ni probar el borrador DFlash 2")
    p.add_argument("--actualizar-llama", action="store_true",
                   help="bajar la ultima version de llama.cpp aunque ya haya una instalada (cambia la ruta "
                        "de llama-server.exe: hay que repetir el ajuste de NVIDIA)")
    p.add_argument("--repo-dflash", default=REPO_DFLASH, help="repo de Hugging Face del borrador DFlash 2")
    p.add_argument("--borrador-dflash", default=None, help="ruta a un borrador DFlash 2 ya descargado")
    return p


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")
    a = parser().parse_args(argv)
    carpeta = os.path.abspath(a.carpeta)
    try:
        os.makedirs(carpeta, exist_ok=True)
    except OSError:
        carpeta = os.path.join(os.path.expanduser("~"), "jadis-cerebro")
        os.makedirs(carpeta, exist_ok=True)
        decir(f"No pude crear la carpeta pedida; uso {carpeta}")
    decir("== 1. Inventario del equipo ==")
    inv = inventario(carpeta)
    avisos = avisos_inventario(inv)
    informe = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "inventario": inv, "avisos": avisos, "pruebas": []}
    decir(json.dumps(inv, ensure_ascii=False, indent=2))
    for aviso in avisos:
        decir("AVISO: " + aviso)

    def guardar() -> None:
        with open(os.path.join(carpeta, "informe-fase0.json"), "w", encoding="utf-8") as f:
            json.dump(informe, f, ensure_ascii=False, indent=2)
        with open(os.path.join(carpeta, "informe-fase0.md"), "w", encoding="utf-8") as f:
            f.write(informe_markdown(inv, informe["pruebas"], avisos))

    if a.solo_inventario:
        guardar()
        decir(f"\nInventario guardado en {os.path.join(carpeta, 'informe-fase0.md')}")
        return 0

    variantes = [v.strip() for v in a.variantes.split(",") if v.strip()]
    configs = [c.strip() for c in a.configs.split(",") if c.strip()]
    for nombre in variantes + configs:
        if nombre not in VARIANTES and nombre not in CONFIGS:
            decir(f"No conozco '{nombre}'. Variantes: {', '.join(VARIANTES)}. Pruebas: {', '.join(CONFIGS)}")
            return 2
    if a.exprimir:
        variantes = variantes[:1]  # la prueba de velocidad se hace sobre una sola variante

    modelos: list[tuple[str, str, bool]] = []  # (nombre, ruta, lleva_mtp)
    dflash: str | None = None
    if a.sin_descargas:
        if not a.llama_server or not a.modelo:
            decir("Con --sin-descargas hacen falta --llama-server y al menos un --modelo")
            return 2
        llama_server = a.llama_server
        modelos = [(os.path.splitext(os.path.basename(m))[0], m, "mtp" in os.path.basename(m).lower())
                   for m in a.modelo]
        dflash = a.borrador_dflash
    else:
        decir("\n== 2. Que hay que descargar ==")
        instalado = None if a.actualizar_llama else llama_cpp_instalado(carpeta)
        try:
            eleccion = None if instalado else elegir_release_llama(pedir_json(RELEASES_LLAMA),
                                                                   inv["nvidia"].get("cuda_max_driver"))
            arbol = listar_archivos_hf(a.repo)
            planes = [elegir_archivos_modelo(arbol, v) for v in variantes]
        except (urllib.error.URLError, OSError, RuntimeError, ValueError, KeyError) as e:
            decir(f"No pude preparar las descargas: {e}")
            return 1
        borrador = None
        if a.exprimir and not a.sin_dflash:
            try:
                borrador = elegir_borrador(listar_archivos_hf(a.repo_dflash))
            except (urllib.error.URLError, OSError, RuntimeError, ValueError, KeyError) as e:
                decir(f"AVISO: no se probara DFlash 2 ({e})")
        if eleccion and eleccion["aviso"]:
            decir("AVISO: " + eleccion["aviso"])
        pendiente = sum(bytes_pendientes(os.path.join(carpeta, "descargas", z["name"]), z.get("size"))
                        for z in (eleccion["zips"] if eleccion else []))
        if instalado:
            decir(f"  llama.cpp {instalado['tag']} (CUDA {instalado['cuda']}): ya instalado, se reutiliza "
                  "(--actualizar-llama baja la ultima version; luego hay que repetir el ajuste de NVIDIA)")
        else:
            decir(f"  llama.cpp {eleccion['tag']} (CUDA {eleccion['cuda']}): "
                  + ", ".join(z["name"] for z in eleccion["zips"]))
        for plan in planes:
            for f in plan["archivos"]:
                pendiente += bytes_pendientes(os.path.join(carpeta, "modelos", os.path.basename(f["ruta"])),
                                              f["tam"])
                decir(f"  {a.repo}: {f['ruta']} ({(f['tam'] or 0) / 1024**3:.1f} GB)")
            if plan["aviso"]:
                decir("  AVISO: " + plan["aviso"])
        if borrador:
            pendiente += bytes_pendientes(os.path.join(carpeta, "modelos", os.path.basename(borrador["ruta"])),
                                          borrador["tam"])
            decir(f"  {a.repo_dflash}: {borrador['ruta']} ({(borrador['tam'] or 0) / 1024**3:.1f} GB, "
                  "borrador DFlash 2)")
        libre = shutil.disk_usage(carpeta).free
        decir(f"  Falta por bajar: {pendiente / 1024**3:.1f} GB | libre en {carpeta}: {libre / 1024**3:.1f} GB")
        if libre < pendiente + MARGEN_DISCO:
            decir("No hay espacio suficiente. Usa --carpeta en otro disco.")
            return 1
        if not confirmar("Descargar ahora?", a.si):
            decir("Cancelado. No se ha descargado nada.")
            guardar()
            return 0
        try:
            decir("\n== 3. Descargando ==")
            llama_server = instalado["exe"] if instalado else instalar_llama_cpp(eleccion, carpeta)
            for plan in planes:
                rutas = [descargar(f"https://huggingface.co/{a.repo}/resolve/main/"
                                   + urllib.parse.quote(f["ruta"]),
                                   os.path.join(carpeta, "modelos", os.path.basename(f["ruta"])),
                                   f["tam"], f["sha256"])
                         for f in plan["archivos"]]
                modelos.append((plan["variante"], rutas[0], plan["mtp"]))
            if borrador:
                dflash = descargar(f"https://huggingface.co/{a.repo_dflash}/resolve/main/"
                                   + urllib.parse.quote(borrador["ruta"]),
                                   os.path.join(carpeta, "modelos", os.path.basename(borrador["ruta"])),
                                   borrador["tam"], borrador["sha256"])
        except (urllib.error.URLError, OSError, RuntimeError, zipfile.BadZipFile) as e:
            decir(f"Fallo en la descarga: {e}. Vuelve a lanzar el mismo comando: reanuda donde se quedo.")
            return 1
        version = instalado or eleccion
        informe["llama_cpp"] = {"tag": version["tag"], "cuda": version["cuda"]}

    if a.solo_descargar:
        guardar()
        decir("\nDescargado. Para el panel de NVIDIA (Configuracion de programa > Agregar > Examinar...), "
              "el programa es:\n\n    " + os.path.abspath(llama_server) + "\n")
        decir("Cuando lo tengas, lanza otra vez sin --solo-descargar: no vuelve a bajar nada.")
        return 0

    mtp_ok = soporta_mtp(llama_server)
    informe["llama_server_con_mtp"] = mtp_ok
    if mtp_ok is False:
        decir("AVISO: esta version de llama-server no conoce --spec-type draft-mtp; se prueba sin MTP.")

    if a.exprimir:
        decir("\n== 4. Prueba de velocidad (un ajuste cada vez) ==")
        nombre_modelo, ruta, _ = modelos[0]
        velocidad = exprimir(inv, llama_server, ruta, dflash, carpeta, a.puerto, a.limite_carga)
        texto = informe_velocidad(inv, velocidad)
        with open(os.path.join(carpeta, "informe-velocidad.json"), "w", encoding="utf-8") as f:
            json.dump({"inventario": inv, "avisos": avisos, **velocidad}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(carpeta, "informe-velocidad.md"), "w", encoding="utf-8") as f:
            f.write(texto)
        decir("\n" + texto)
        decir(f"Listo. Pasame el archivo {os.path.join(carpeta, 'informe-velocidad.md')}.")
        return 1 if velocidad.get("error") else 0

    decir("\n== 4. Pruebas ==")
    opciones_extra = ["--turnos", "2", "--pensar", "no"] if a.rapido else []
    if a.sistema:
        opciones_extra += ["--sistema", a.sistema]
    for nombre_modelo, ruta, lleva_mtp in modelos:
        for config in configs:
            arranque, bench = CONFIGS[config]
            if config != "sin-mtp" and (not lleva_mtp or mtp_ok is False):
                decir(f"-- {nombre_modelo}/{config}: se salta (sin cabezal MTP o llama-server sin MTP)")
                continue
            nombre = f"{nombre_modelo}-{config}"
            decir(f"-- {nombre}: cargando el modelo (puede tardar varios minutos)...")
            r = probar(nombre, llama_server, ruta, arranque, bench + opciones_extra, carpeta,
                       a.puerto, a.limite_carga)
            informe["pruebas"].append(r)
            guardar()
            if r.get("error"):
                decir(f"   ERROR: {r['error']}")
    guardar()
    decir("\n" + informe_markdown(inv, informe["pruebas"], avisos))
    decir(f"Listo. Pasame el archivo {os.path.join(carpeta, 'informe-fase0.md')} (y si quieres el .json).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
