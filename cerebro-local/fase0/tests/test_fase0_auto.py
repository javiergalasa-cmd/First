"""Pruebas de fase0.py (inventario, elecciones, descargas, registro y ejecucion completa simulada).

Ejecutar desde cerebro-local/fase0:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import fase0  # noqa: E402

FALSO = os.path.join(AQUI, "llama_server_falso.py")


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def silencio():
    return contextlib.ExitStack()


class ServidorArchivos:
    """Sirve bytes con soporte de Range, como el CDN de Hugging Face."""

    def __init__(self, datos: bytes, ignorar_range=False):
        self.datos, self.peticiones = datos, []
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                servidor.peticiones.append(self.headers.get("Range"))
                rango = self.headers.get("Range")
                if rango and not ignorar_range:
                    inicio = int(rango.split("=")[1].split("-")[0])
                    cuerpo = servidor.datos[inicio:]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {inicio}-{len(servidor.datos) - 1}/{len(servidor.datos)}")
                else:
                    cuerpo = servidor.datos
                    self.send_response(200)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/archivo.gguf"

    def __enter__(self):
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.http.shutdown()
        self.http.server_close()


class PruebasInventario(unittest.TestCase):
    def test_fury_ddr4_por_referencia(self):
        resultado = fase0.tipo_y_velocidad({"SMBIOSMemoryType": 0, "PartNumber": "KF432C16BB/32"})
        self.assertEqual(resultado, ("DDR4", 3200, 3200))

    def test_fury_ddr5_por_referencia(self):
        resultado = fase0.tipo_y_velocidad({"PartNumber": "KF560C36BBE-32"})
        self.assertEqual(resultado, ("DDR5", 6000, 6000))

    def test_tipo_smbios_manda_sobre_la_referencia(self):
        resultado = fase0.tipo_y_velocidad({"SMBIOSMemoryType": 34, "ConfiguredClockSpeed": 5600,
                                            "PartNumber": "XYZ"})
        self.assertEqual(resultado, ("DDR5", 5600, None))

    def test_avisa_si_falta_activar_xmp(self):
        ram = fase0.resumir_ram([{"Capacity": str(32 * 1024**3), "SMBIOSMemoryType": 26,
                                  "ConfiguredClockSpeed": 2400, "Speed": 2400,
                                  "PartNumber": "KF432C16BB/32"}], 4)
        self.assertEqual((ram["velocidad_mts"], ram["velocidad_nominal_mts"]), (2400, 3200))
        self.assertEqual(ram["ancho_banda_teorico_gbs"], 19.2, "el ancho se calcula con la velocidad real")
        avisos = fase0.avisos_inventario({"ram": ram, "nvidia": {}})
        self.assertTrue(any("XMP" in a and "33%" in a for a in avisos))

    def test_sin_aviso_xmp_si_va_a_su_velocidad(self):
        ram = fase0.resumir_ram([{"Capacity": str(32 * 1024**3), "ConfiguredClockSpeed": 3200,
                                  "PartNumber": "KF432C16BB/32"}], 4)
        self.assertFalse(any("XMP" in a for a in fase0.avisos_inventario({"ram": ram, "nvidia": {}})))

    def test_un_solo_modulo_es_un_canal(self):
        ram = fase0.resumir_ram([{"Capacity": str(32 * 1024**3), "SMBIOSMemoryType": 26,
                                  "ConfiguredClockSpeed": 3200, "PartNumber": "KF432C16BB/32"}], 4)
        self.assertEqual(ram["canales_probables"], 1)
        self.assertEqual(ram["ancho_banda_teorico_gbs"], 25.6)
        self.assertEqual(ram["total_gb"], 32)
        avisos = fase0.avisos_inventario({"ram": ram, "nvidia": {}})
        self.assertTrue(any("UN canal" in a for a in avisos))

    def test_dos_modulos_son_dos_canales(self):
        modulo = {"Capacity": str(16 * 1024**3), "SMBIOSMemoryType": 34, "ConfiguredClockSpeed": 6000}
        ram = fase0.resumir_ram([modulo, modulo], 4)
        self.assertEqual(ram["canales_probables"], 2)
        self.assertEqual(ram["ancho_banda_teorico_gbs"], 96.0)
        self.assertFalse(fase0.avisos_inventario({"ram": ram, "nvidia": {}}))

    def test_vram_ocupada_avisa(self):
        avisos = fase0.avisos_inventario({"ram": {}, "nvidia": {"memory.used": "3489"}})
        self.assertTrue(any("3489" in a for a in avisos))

    def test_avisa_si_hay_poca_ram_disponible(self):
        avisos = fase0.avisos_inventario({"ram": {}, "nvidia": {}, "ram_disponible_gb": 8.1})
        self.assertTrue(any("8.1 GB de RAM disponibles" in a for a in avisos))
        self.assertFalse(fase0.avisos_inventario({"ram": {}, "nvidia": {}, "ram_disponible_gb": 20.0}))

    def test_avisa_si_ollama_o_jadis_estan_abiertos(self):
        avisos = fase0.avisos_inventario({"ram": {}, "nvidia": {}, "abiertos": ["Ollama"]})
        self.assertTrue(any("Ollama" in a for a in avisos))

    def test_inventario_detecta_puertos_abiertos(self):
        original = fase0.puerto_libre
        fase0.puerto_libre = lambda p: p != 11434  # simula Ollama escuchando en su puerto
        try:
            inv = fase0.inventario(tempfile.mkdtemp())
        finally:
            fase0.puerto_libre = original
        self.assertEqual(inv["abiertos"], ["Ollama"])


class PruebasElecciones(unittest.TestCase):
    RELEASE = {"tag_name": "b9999", "assets": [
        {"name": "llama-b9999-bin-win-cuda-12.4-x64.zip", "browser_download_url": "u1", "size": 10},
        {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip", "browser_download_url": "u2", "size": 20},
        {"name": "llama-b9999-bin-win-cuda-13.1-x64.zip", "browser_download_url": "u3", "size": 10},
        {"name": "cudart-llama-bin-win-cuda-13.1-x64.zip", "browser_download_url": "u4", "size": 20},
        {"name": "llama-b9999-bin-win-vulkan-x64.zip", "browser_download_url": "u5", "size": 10},
    ]}

    def test_cuda_mas_alta_que_admite_el_driver(self):
        self.assertEqual(fase0.elegir_llama_cpp(self.RELEASE, "13.2")["cuda"], "13.1")
        self.assertEqual(fase0.elegir_llama_cpp(self.RELEASE, "13.0")["cuda"], "12.4")

    def test_driver_desconocido_usa_la_mas_compatible(self):
        e = fase0.elegir_llama_cpp(self.RELEASE, None)
        self.assertEqual(e["cuda"], "12.4")
        self.assertIsNotNone(e["aviso"])

    def test_sin_cudart_no_se_elige(self):
        release = {"tag_name": "b1", "assets": [a for a in self.RELEASE["assets"] if "cudart" not in a["name"]
                                                 or "12.4" in a["name"]]}
        self.assertEqual(fase0.elegir_llama_cpp(release, "13.2")["cuda"], "12.4")

    def test_salta_la_release_a_medio_subir(self):
        a_medias = {"tag_name": "b10000", "prerelease": True,
                    "assets": [{"name": "llama-b10000-bin-win-cpu-x64.zip"}]}
        borrador = dict(self.RELEASE, tag_name="b10001", draft=True)
        e = fase0.elegir_release_llama([borrador, a_medias, dict(self.RELEASE, prerelease=True)], "13.2")
        self.assertEqual((e["tag"], e["cuda"]), ("b9999", "13.1"))
        self.assertEqual(fase0.elegir_release_llama(self.RELEASE, "13.2")["tag"], "b9999")
        with self.assertRaises(RuntimeError) as ctx:
            fase0.elegir_release_llama([a_medias], "13.2")
        self.assertIn("--sin-descargas", str(ctx.exception))

    def test_lista_de_releases_no_latest(self):
        self.assertNotIn("/latest", fase0.RELEASES_LLAMA, "latest se salta las pre-releases de llama.cpp")

    def test_release_sin_cuda_falla(self):
        with self.assertRaises(RuntimeError):
            fase0.elegir_llama_cpp({"assets": [{"name": "llama-b1-bin-win-cpu-x64.zip"}]}, "13.0")

    GB = 1024**3
    ARBOL = [
        {"type": "file", "path": "README.md", "size": 100},
        {"type": "file", "path": "mmproj-Qwen3.8-27B-F16.gguf", "size": 1, "lfs": {"oid": "m", "size": GB}},
        {"type": "file", "path": "Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf", "size": 1, "lfs": {"oid": "a", "size": 11 * GB}},
        {"type": "file", "path": "Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf", "size": 1, "lfs": {"oid": "b", "size": 12 * GB}},
        {"type": "file", "path": "Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf", "size": 1, "lfs": {"oid": "c", "size": 10 * GB}},
        {"type": "file", "path": "Qwen3.8-27B-GSQ-RCO-IQ2_S-mtp.gguf", "size": 1, "lfs": {"oid": "d", "size": 9 * GB}},
        {"type": "file", "path": "Qwen3.8-27B-GSQ-RCO-IQ2_XS-mtp.gguf", "size": 1, "lfs": {"oid": "e", "size": 8 * GB}},
    ]

    def test_elige_la_variante_exacta_con_mtp(self):
        for variante, esperado in [("iq3_s", "IQ3_S-mtp"), ("iq3_xxs", "IQ3_XXS-mtp"),
                                   ("iq2_s", "IQ2_S-mtp"), ("iq2_xs", "IQ2_XS-mtp")]:
            plan = fase0.elegir_archivos_modelo(self.ARBOL, variante)
            self.assertEqual(len(plan["archivos"]), 1, variante)
            self.assertIn(esperado, plan["archivos"][0]["ruta"], variante)
            self.assertTrue(plan["mtp"])
        plan = fase0.elegir_archivos_modelo(self.ARBOL, "iq3_s")
        self.assertEqual((plan["archivos"][0]["sha256"], plan["archivos"][0]["tam"]), ("b", 12 * self.GB))

    def test_rechaza_un_cabezal_mtp_suelto(self):
        arbol = [{"type": "file", "path": "Qwen3.8-27B-IQ3_S-mtp.gguf", "lfs": {"oid": "x", "size": self.GB // 2}}]
        with self.assertRaises(RuntimeError) as ctx:
            fase0.elegir_archivos_modelo(arbol, "iq3_s")
        self.assertIn("cabezal", str(ctx.exception))

    def test_sin_mtp_avisa(self):
        arbol = [f for f in self.ARBOL if "mtp" not in f["path"]]
        plan = fase0.elegir_archivos_modelo(arbol, "iq3_s")
        self.assertFalse(plan["mtp"])
        self.assertIsNotNone(plan["aviso"])

    def test_archivos_troceados(self):
        arbol = [{"type": "file", "path": f"IQ4_XS/Qwen-IQ4_XS-mtp-0000{i}-of-00002.gguf",
                  "lfs": {"oid": str(i), "size": i * self.GB * 5}} for i in (2, 1)]
        plan = fase0.elegir_archivos_modelo(arbol, "iq4_xs")
        self.assertEqual([os.path.basename(f["ruta"]) for f in plan["archivos"]],
                         ["Qwen-IQ4_XS-mtp-00001-of-00002.gguf", "Qwen-IQ4_XS-mtp-00002-of-00002.gguf"])

    def test_variante_inexistente(self):
        with self.assertRaises(RuntimeError):
            fase0.elegir_archivos_modelo(self.ARBOL, "q4_k_m")

    def test_lista_de_hf_con_plan_b(self):
        def falso(url, timeout=60):
            if "/tree/" in url:
                return {"error": "no disponible"}
            return {"siblings": [{"rfilename": "Q-IQ3_S-mtp.gguf", "size": 12 * 1024**3,
                                  "lfs": {"sha256": "abc", "size": 12 * 1024**3}},
                                 {"rfilename": "README.md", "size": 3}]}
        original = fase0.pedir_json
        fase0.pedir_json = falso
        try:
            arbol = fase0.listar_archivos_hf("x/y")
        finally:
            fase0.pedir_json = original
        plan = fase0.elegir_archivos_modelo(arbol, "iq3_s")
        self.assertEqual(plan["archivos"][0], {"ruta": "Q-IQ3_S-mtp.gguf", "tam": 12 * 1024**3, "sha256": "abc"})


class PruebasDescarga(unittest.TestCase):
    DATOS = os.urandom(3 * 1024 * 1024 + 123)

    def test_reanuda_y_verifica(self):
        sha = hashlib.sha256(self.DATOS).hexdigest()
        with tempfile.TemporaryDirectory() as tmp, ServidorArchivos(self.DATOS) as srv:
            destino = os.path.join(tmp, "m.gguf")
            with open(destino + ".parcial", "wb") as f:
                f.write(self.DATOS[:1024 * 1024])
            with contextlib.redirect_stdout(io.StringIO()):
                fase0.descargar(srv.url, destino, len(self.DATOS), sha)
            with open(destino, "rb") as f:
                self.assertEqual(f.read(), self.DATOS)
            self.assertEqual(srv.peticiones, [f"bytes={1024 * 1024}-"])
            self.assertFalse(os.path.exists(destino + ".parcial"))

    def test_servidor_que_ignora_range_empieza_de_cero(self):
        with tempfile.TemporaryDirectory() as tmp, ServidorArchivos(self.DATOS, ignorar_range=True) as srv:
            destino = os.path.join(tmp, "m.gguf")
            with open(destino + ".parcial", "wb") as f:
                f.write(b"basura")
            with contextlib.redirect_stdout(io.StringIO()):
                fase0.descargar(srv.url, destino, len(self.DATOS), hashlib.sha256(self.DATOS).hexdigest())
            with open(destino, "rb") as f:
                self.assertEqual(f.read(), self.DATOS)

    def test_hash_incorrecto_no_deja_el_archivo_como_bueno(self):
        with tempfile.TemporaryDirectory() as tmp, ServidorArchivos(self.DATOS) as srv:
            destino = os.path.join(tmp, "m.gguf")
            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                fase0.descargar(srv.url, destino, len(self.DATOS), "0" * 64)
            self.assertFalse(os.path.exists(destino))
            self.assertTrue(os.path.exists(destino + ".corrupto"))

    def test_parcial_completo_solo_se_comprueba(self):
        with tempfile.TemporaryDirectory() as tmp, ServidorArchivos(self.DATOS) as srv:
            destino = os.path.join(tmp, "m.gguf")
            with open(destino + ".parcial", "wb") as f:
                f.write(self.DATOS)
            with contextlib.redirect_stdout(io.StringIO()):
                fase0.descargar(srv.url, destino, len(self.DATOS), hashlib.sha256(self.DATOS).hexdigest())
            self.assertEqual(srv.peticiones, [], "no debe pedir un rango vacio (daria 416)")
            self.assertTrue(os.path.exists(destino))

    def test_bytes_pendientes(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, "m.gguf")
            self.assertEqual(fase0.bytes_pendientes(destino, 100), 100)
            with open(destino + ".parcial", "wb") as f:
                f.write(b"x" * 30)
            self.assertEqual(fase0.bytes_pendientes(destino, 100), 70)
            os.replace(destino + ".parcial", destino)
            self.assertEqual(fase0.bytes_pendientes(destino, 100), 0)

    def test_archivo_ya_descargado_no_se_vuelve_a_bajar(self):
        with tempfile.TemporaryDirectory() as tmp, ServidorArchivos(self.DATOS) as srv:
            destino = os.path.join(tmp, "m.gguf")
            with open(destino, "wb") as f:
                f.write(self.DATOS)
            fase0.descargar(srv.url, destino, len(self.DATOS), hashlib.sha256(self.DATOS).hexdigest())
            self.assertEqual(srv.peticiones, [])


class PruebasRegistro(unittest.TestCase):
    def test_lee_capas_aceptacion_y_errores_sin_rutas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "x.log")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("load_tensors: offloaded 27/65 layers to GPU\n"
                        "slot print_timing: draft acceptance rate = 0.70000 ( 7 accepted / 10 generated)\n"
                        "slot print_timing: draft acceptance rate = 0.90000 ( 9 accepted / 10 generated)\n"
                        "error: failed to open C:\\Users\\alguien\\modelos\\m.gguf\n")
            datos = fase0.leer_log(ruta)
        self.assertEqual(datos["capas_gpu"], "27/65")
        self.assertEqual(datos["aceptacion_mtp_media"], 0.8)
        self.assertNotIn("alguien", " ".join(datos["errores"]))


class PruebasEjecucionCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chmod(FALSO, os.stat(FALSO).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def ejecutar(self, nombre_modelo, *extra):
        tmp = tempfile.mkdtemp()
        modelo = os.path.join(tmp, nombre_modelo)
        with open(modelo, "wb") as f:
            f.write(b"GGUF")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = fase0.main(["--carpeta", os.path.join(tmp, "trabajo"), "--sin-descargas",
                                 "--llama-server", FALSO, "--modelo", modelo, "--rapido",
                                 "--puerto", str(puerto_libre()), "--limite-carga", "60", *extra])
        with open(os.path.join(tmp, "trabajo", "informe-fase0.json"), encoding="utf-8") as f:
            informe = json.load(f)
        with open(os.path.join(tmp, "trabajo", "informe-fase0.md"), encoding="utf-8") as f:
            md = f.read()
        return codigo, informe, md, salida.getvalue()

    def test_matriz_con_y_sin_mtp(self):
        codigo, informe, md, salida = self.ejecutar("Qwen3.8-27B-IQ3_S-mtp.gguf")
        self.assertEqual(codigo, 0)
        self.assertTrue(informe["llama_server_con_mtp"])
        nombres = [p["prueba"] for p in informe["pruebas"]]
        self.assertEqual(nombres, ["Qwen3.8-27B-IQ3_S-mtp-mtp2", "Qwen3.8-27B-IQ3_S-mtp-sin-mtp"])
        con, sin = informe["pruebas"]
        self.assertEqual(con["capas_gpu"], "25/65")
        self.assertEqual(con["aceptacion_mtp_media"], 0.8)
        self.assertNotIn("aceptacion_mtp_media", sin, "sin MTP no hay borrador")
        resumen = fase0.resumen_prueba(con)
        self.assertTrue(resumen["cache"])
        self.assertTrue(resumen["herramienta"])
        self.assertEqual(resumen["genera_tok_s"], 10.0)
        self.assertIn("| Qwen3.8-27B-IQ3_S-mtp-mtp2 | 25/65 |", md)
        self.assertIn("criterios de la fase 0", salida.lower())
        self.assertNotIn(os.path.expanduser("~"), md, "el informe no debe llevar rutas personales")

    def test_modelo_sin_mtp_solo_prueba_sin_mtp(self):
        codigo, informe, md, _ = self.ejecutar("modelo-sin-cabezal.gguf")
        self.assertEqual(codigo, 0)
        self.assertEqual([p["prueba"] for p in informe["pruebas"]], ["modelo-sin-cabezal-sin-mtp"])

    def test_puerto_ocupado(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            puerto = s.getsockname()[1]
            r = fase0.probar("x", FALSO, "m.gguf", [], [], tempfile.mkdtemp(), puerto, 5)
        self.assertIn("ocupado", r["error"])

    def test_reutiliza_el_llama_cpp_instalado(self):
        carpeta = tempfile.mkdtemp()
        self.assertIsNone(fase0.llama_cpp_instalado(carpeta))
        for tag, completo in (("b9001", True), ("b9002", False), ("b8999", True)):
            destino = os.path.join(carpeta, "llama.cpp", f"{tag}-cuda-12.4")
            os.makedirs(destino)
            open(os.path.join(destino, "llama-server.exe"), "w").close()
            if completo:
                with open(os.path.join(destino, ".instalado"), "w") as f:
                    f.write("zip")
            time.sleep(0.05)
        r = fase0.llama_cpp_instalado(carpeta)
        self.assertEqual((r["tag"], r["cuda"]), ("b8999", "12.4"),
                         "el mas reciente de los completos; b9002 no tiene marca (zip a medias)")
        self.assertTrue(r["exe"].endswith("llama-server.exe"))

    def test_no_pregunta_a_github_si_ya_hay_llama_cpp(self):
        carpeta = tempfile.mkdtemp()
        destino = os.path.join(carpeta, "llama.cpp", "b9001-cuda-12.4")
        os.makedirs(destino)
        open(os.path.join(destino, "llama-server.exe"), "w").close()
        with open(os.path.join(destino, ".instalado"), "w") as f:
            f.write("zip")
        urls = []

        def falso(url, timeout=60):
            urls.append(url)
            raise urllib.error.URLError("sin red en la prueba")

        original = fase0.pedir_json
        fase0.pedir_json = falso
        try:
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                fase0.main(["--carpeta", carpeta, "--si"])
        finally:
            fase0.pedir_json = original
        self.assertFalse(any("llama.cpp/releases" in u for u in urls), urls)

    def test_solo_inventario_no_descarga(self):
        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            codigo = fase0.main(["--carpeta", tmp, "--solo-inventario"])
        self.assertEqual(codigo, 0)
        self.assertEqual(sorted(os.listdir(tmp)), ["informe-fase0.json", "informe-fase0.md"])

    def test_nombre_desconocido(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fase0.main(["--carpeta", tempfile.mkdtemp(), "--variantes", "q9"]), 2)


class PruebasVelocidad(unittest.TestCase):
    """--exprimir contra un llama-server falso cuya velocidad depende de las opciones (ver llama_server_falso)."""

    @classmethod
    def setUpClass(cls):
        os.chmod(FALSO, os.stat(FALSO).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def test_borrador_prefiere_q4_k_m(self):
        arbol = [{"type": "file", "path": "dflash-Q8_0.gguf", "lfs": {"oid": "a", "size": 2000}},
                 {"type": "file", "path": "dflash-Q4_K_M.gguf", "lfs": {"oid": "b", "size": 1100}},
                 {"type": "file", "path": "dflash-Q2_K.gguf", "lfs": {"oid": "c", "size": 700}}]
        self.assertEqual(fase0.elegir_borrador(arbol)["ruta"], "dflash-Q4_K_M.gguf")
        self.assertEqual(fase0.elegir_borrador(arbol[:1] + arbol[2:])["ruta"], "dflash-Q8_0.gguf")
        self.assertEqual(fase0.elegir_borrador(arbol[2:])["ruta"], "dflash-Q2_K.gguf")
        with self.assertRaises(RuntimeError):
            fase0.elegir_borrador([{"type": "file", "path": "README.md"}])

    def test_resolver_ajustes(self):
        ajustes = {n: o for n, o, *_ in fase0.resolver_ajustes({"cpu": {"NumberOfCores": 8}}, None)}
        self.assertEqual(ajustes["hilos-nucleos"], ["--hilos", "8"])
        self.assertEqual(ajustes["hilos-mitad"], ["--hilos", "4"])
        self.assertNotIn("dflash", ajustes, "sin borrador descargado no se prueba DFlash")
        ajustes = {n: o for n, o, *_ in fase0.resolver_ajustes({"cpu": {"NumberOfCores": 8}}, "d.gguf")}
        self.assertEqual(ajustes["dflash"], ["--dflash", "d.gguf", "--borrador-n", "7"])

    def test_cada_ajuste_va_encima_de_base(self):
        carpeta = tempfile.mkdtemp()
        lanzados = []
        original = fase0.probar

        def falso(nombre, servidor, modelo, opciones, *resto):
            lanzados.append((nombre, list(opciones)))
            return {"prueba": nombre, "error": "simulado"} if nombre != "velocidad-base" else {"prueba": nombre}
        fase0.probar = falso
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fase0.exprimir({"cpu": {"NumberOfCores": 6}}, "x", os.path.join(carpeta, "moe-IQ3_S.gguf"),
                               None, carpeta, 1, 1)
        finally:
            fase0.probar = original
        for nombre, opciones in lanzados:
            self.assertIn("--sin-mtp", opciones, f"{nombre} debe heredar --sin-mtp de base")

    def test_modelo_sin_mtp_no_prueba_borradores(self):
        ajustes = {n: o for n, o, *_ in fase0.resolver_ajustes({"cpu": {"NumberOfCores": 6}}, "d.gguf", False)}
        self.assertEqual(ajustes["base"], ["--sin-mtp"])
        for n in ("sin-mtp", "mtp1", "mtp3", "dflash"):
            self.assertNotIn(n, ajustes)
        self.assertEqual(ajustes["sin-mmap"], ["--sin-mmap"])

    def test_opciones_sin_repetir_las_de_base(self):
        ajustes = fase0.resolver_ajustes({"cpu": {"NumberOfCores": 6}}, None)
        self.assertEqual(fase0.opciones_de(["mtp1", "margen-512"], ajustes),
                         ["--borrador-n", "1", "--fit-target", "512"])
        self.assertEqual(fase0.opciones_de(["margen-512"], ajustes), ["--borrador-n", "2", "--fit-target", "512"])

    def test_elegir_ganadores(self):
        ajustes = fase0.resolver_ajustes({"cpu": {"NumberOfCores": 8}}, "d.gguf")
        resultados = {
            "base": {"genera": 10.0, "lee": 500.0},
            "sin-mtp": {"genera": 6.0, "lee": 500.0},
            "mtp3": {"genera": 10.6, "lee": 500.0},
            "dflash": {"genera": 14.0, "lee": 480.0},
            "hilos-nucleos": {"genera": 10.2, "lee": 500.0},   # +2 %: ruido
            "hilos-mitad": {"genera": None, "error": "no arranco"},
            "margen-512": {"genera": 11.0, "lee": 500.0},      # +10 %
            "ubatch-2048": {"genera": 9.8, "lee": 700.0},      # solo mejora al leer: gana
            "sin-op-offload": {"genera": 10.6, "lee": 200.0},  # genera algo mas pero lee mucho peor: no
            "kv-q4": {"genera": 12.0, "lee": 500.0},           # tiene coste de calidad: no se elige solo
        }
        self.assertEqual(sorted(fase0.elegir_ganadores(resultados, ajustes)),
                         ["dflash", "margen-512", "ubatch-2048"])

    def test_exprimir_de_punta_a_punta(self):
        carpeta = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            s = fase0.exprimir({"cpu": {"NumberOfCores": 8}}, FALSO, os.path.join(carpeta, "m-IQ3_S-mtp.gguf"),
                               "/ruta/privada/d.gguf", carpeta, puerto_libre(), 60)
        self.assertNotIn("error", s)
        self.assertEqual(s["resultados"]["base"]["genera"], 10.0)
        self.assertEqual(sorted(s["ganadores"]), ["dflash", "hilos-nucleos", "margen-512", "ubatch-2048"])
        self.assertAlmostEqual(s["combinada"]["genera"], round(14.0 * 1.2 * 1.1, 2), places=1)
        opciones = s["opciones_recomendadas"]
        self.assertIn("<borrador DFlash>", opciones, "el informe no debe llevar la ruta del borrador")
        self.assertNotIn("/ruta/privada/d.gguf", opciones)
        self.assertEqual(opciones[opciones.index("--hilos") + 1], "8")
        texto = fase0.informe_velocidad({"ram": {}}, s)
        self.assertIn("| dflash |", texto)
        self.assertIn("Comando recomendado", texto)
        self.assertIn("+40 %", texto)

    def test_main_exprimir_y_solo_descargar(self):
        tmp = tempfile.mkdtemp()
        modelo = os.path.join(tmp, "m-IQ3_S-mtp.gguf")
        with open(modelo, "wb") as f:
            f.write(b"GGUF")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = fase0.main(["--carpeta", os.path.join(tmp, "w"), "--sin-descargas", "--llama-server", FALSO,
                                 "--modelo", modelo, "--solo-descargar"])
        self.assertEqual(codigo, 0)
        self.assertIn(os.path.abspath(FALSO), salida.getvalue())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            codigo = fase0.main(["--carpeta", os.path.join(tmp, "w"), "--sin-descargas", "--llama-server", FALSO,
                                 "--modelo", modelo, "--exprimir", "--puerto", str(puerto_libre()),
                                 "--limite-carga", "60"])
        self.assertEqual(codigo, 0)
        with open(os.path.join(tmp, "w", "informe-velocidad.md"), encoding="utf-8") as f:
            self.assertIn("Prueba de velocidad", f.read())


if __name__ == "__main__":
    unittest.main()
