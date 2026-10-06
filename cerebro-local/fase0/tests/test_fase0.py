"""Pruebas del kit de la Fase 0 contra un llama-server simulado (sin GPU ni modelo).

Ejecutar desde cerebro-local/fase0:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arrancar_cerebro  # noqa: E402
import bench_cerebro  # noqa: E402


class ServidorFalso:
    """Imita las rutas de llama-server que usa el banco de pruebas.

    cache_ok:     True  -> reutiliza el prompt anterior (cache_n grande, prompt_n pequeno)
                  False -> relee todo en cada turno (el fallo tipico de los modelos hibridos)
    con_timings:  si devuelve el objeto 'timings' como llama-server
    herramienta:  nombre de la herramienta que "elige" el modelo
    """

    def __init__(self, cache_ok=True, con_timings=True, herramienta="obtener_tiempo"):
        self.cache_ok, self.con_timings, self.herramienta = cache_ok, con_timings, herramienta
        self.ultimo_prompt = 0
        self.peticiones = []
        falso = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _responder(self, cuerpo, codigo=200):
                datos = json.dumps(cuerpo).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def do_GET(self):
                if self.path == "/health":
                    self._responder({"status": "ok"})
                elif self.path == "/v1/models":
                    self._responder({"data": [{"id": "qwen3.8-27b-prueba"}]})
                else:
                    self._responder({"error": "no existe"}, 404)

            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
                if self.path == "/tokenize":
                    self._responder({"tokens": list(range(len(cuerpo["content"]) // 4))})
                elif self.path == "/v1/chat/completions":
                    falso.peticiones.append(cuerpo)
                    self._responder(falso.completar(cuerpo))
                else:
                    self._responder({"error": "no existe"}, 404)

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def completar(self, cuerpo):
        total = sum(len(m.get("content") or "") // 4 for m in cuerpo["messages"])
        cache_n = min(self.ultimo_prompt, total) if self.cache_ok else 0
        prompt_n = total - cache_n
        self.ultimo_prompt = total
        generados = 40
        mensaje = {"role": "assistant", "content": "Respuesta de prueba."}
        if cuerpo.get("chat_template_kwargs", {}).get("enable_thinking"):
            mensaje["reasoning_content"] = "Pensando un poco..."
        fin = "stop"
        if cuerpo.get("tools"):
            mensaje = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "llamada_1", "type": "function",
                "function": {"name": self.herramienta,
                             "arguments": json.dumps({"ciudad": "Madrid"})}}]}
            fin = "tool_calls"
        r = {"choices": [{"index": 0, "message": mensaje, "finish_reason": fin}],
             "usage": {"prompt_tokens": total, "completion_tokens": generados}}
        if self.con_timings:
            r["timings"] = {"cache_n": cache_n, "prompt_n": prompt_n,
                            "prompt_ms": prompt_n * 2.0, "prompt_per_second": 500.0,
                            "predicted_n": generados, "predicted_ms": generados * 100.0,
                            "predicted_per_second": 10.0, "draft_n": 30, "draft_n_accepted": 24}
        return r

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *exc):
        self.servidor.shutdown()
        self.servidor.server_close()


def ejecutar_bench(url, *extra):
    salida = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "informe.json")
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = bench_cerebro.main(["--url", url, "--tokens-sistema", "2000",
                                         "--turnos", "3", "--salida", ruta, *extra])
        with open(ruta, encoding="utf-8") as f:
            informe = json.load(f)
    return codigo, informe, salida.getvalue()


def criterio(informe, texto):
    return next(c["ok"] for c in informe["criterios"] if texto in c["criterio"])


class PruebasArranque(unittest.TestCase):
    def args(self, *extra):
        return arrancar_cerebro.parser().parse_args(["--modelo", "m.gguf", *extra])

    def test_comando_por_defecto(self):
        cmd = arrancar_cerebro.construir_comando(self.args())
        texto = " ".join(cmd)
        self.assertIn("--host 127.0.0.1", texto)
        self.assertIn("--spec-type draft-mtp", texto)
        self.assertIn("--spec-draft-n-max 2", texto)
        self.assertIn("-np 1", texto)
        self.assertIn("-ctk q8_0", texto)
        self.assertIn("--fit on", texto)
        self.assertNotIn("-ngl", cmd, "por defecto las capas las reparte --fit")

    def test_dflash_sustituye_a_mtp(self):
        cmd = arrancar_cerebro.construir_comando(self.args("--dflash", "d.gguf"))
        self.assertIn("draft-dflash", cmd)
        self.assertNotIn("draft-mtp", cmd)
        self.assertEqual(cmd[cmd.index("--spec-draft-model") + 1], "d.gguf")

    def test_sin_mtp(self):
        cmd = arrancar_cerebro.construir_comando(self.args("--sin-mtp"))
        self.assertNotIn("--spec-type", cmd)

    def test_sin_pensar_pasa_json_valido(self):
        cmd = arrancar_cerebro.construir_comando(self.args("--sin-pensar"))
        valor = cmd[cmd.index("--chat-template-kwargs") + 1]
        self.assertEqual(json.loads(valor), {"enable_thinking": False})

    def test_vision_en_cpu(self):
        cmd = arrancar_cerebro.construir_comando(self.args("--mmproj", "v.gguf", "--vision-en-cpu"))
        self.assertIn("--no-mmproj-offload", cmd)

    def test_extra_despues_de_doble_guion(self):
        a = self.args("--", "--threads", "8")
        self.assertEqual(a.extra, ["--", "--threads", "8"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            codigo = arrancar_cerebro.main(["--modelo", "m.gguf", "--solo-mostrar", "--", "--threads", "8"])
        self.assertEqual(codigo, 0)
        self.assertTrue(out.getvalue().strip().endswith("--threads 8"))

    def test_avisa_si_expone_a_la_red(self):
        self.assertTrue(any("expone" in a for a in arrancar_cerebro.avisos(self.args("--host", "0.0.0.0"))))
        self.assertFalse(arrancar_cerebro.avisos(self.args()))

    def test_modelo_inexistente(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(arrancar_cerebro.main(["--modelo", "/no/existe.gguf"]), 2)


class PruebasBench(unittest.TestCase):
    def test_cache_que_funciona(self):
        with ServidorFalso(cache_ok=True) as s:
            codigo, informe, texto = ejecutar_bench(s.url)
        self.assertEqual(codigo, 0)
        self.assertEqual(len(informe["bloques"]), 2, "sin pensar y pensando")
        self.assertTrue(criterio(informe, "cache de prompt"))
        self.assertTrue(criterio(informe, "herramienta"))
        self.assertTrue(criterio(informe, "genera >="))
        segundo = informe["bloques"][0]["turnos"][1]
        self.assertTrue(segundo["cache_ok"])
        self.assertEqual(segundo["borrador_aceptados"], 24)
        self.assertIn("MTP acepta 24/30", texto)

    def test_cache_que_falla(self):
        with ServidorFalso(cache_ok=False) as s:
            _, informe, texto = ejecutar_bench(s.url, "--pensar", "no")
        self.assertFalse(criterio(informe, "cache de prompt"))
        self.assertIn("FALLO: solo reutiliza el 0%", texto)

    def test_servidor_sin_timings(self):
        with ServidorFalso(con_timings=False) as s:
            codigo, informe, _ = ejecutar_bench(s.url, "--pensar", "no")
        self.assertEqual(codigo, 0)
        self.assertIsNone(criterio(informe, "cache"))
        self.assertIn("decode_tok_s_aprox", informe["bloques"][0]["turnos"][0])

    def test_herramienta_equivocada(self):
        with ServidorFalso(herramienta="buscar_en_memoria") as s:
            _, informe, _ = ejecutar_bench(s.url, "--pensar", "no")
        h = informe["bloques"][0]["herramientas"]
        self.assertFalse(h["herramienta_ok"])
        self.assertIn("buscar_en_memoria", h["herramienta"])

    def test_pide_pensar_o_no_al_servidor(self):
        with ServidorFalso() as s:
            ejecutar_bench(s.url, "--sin-herramientas")
            modos = [p["chat_template_kwargs"]["enable_thinking"] for p in s.peticiones]
            maximos = [p["max_tokens"] for p in s.peticiones]
        self.assertEqual(modos, [False, False, False, True, True, True])
        self.assertEqual(maximos, [256, 256, 256, 1024, 1024, 1024], "pensando necesita mas margen")

    def test_avisa_si_la_respuesta_se_corta(self):
        linea = bench_cerebro.linea_turno({"turno": 1, "segundos_totales": 3.0, "fin": "length"})
        self.assertIn("cortado", linea)

    def test_sin_servidor(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bench_cerebro.main(["--url", "http://127.0.0.1:9"]), 2)

    def test_prompt_sintetico_aproxima_el_tamano(self):
        texto = bench_cerebro.prompt_sintetico(3000)
        self.assertGreaterEqual(len(texto), 3000 * 4)
        self.assertLess(len(texto), 3000 * 4 + 1000)

    def test_veredicto_cache(self):
        self.assertEqual(bench_cerebro.veredicto_cache({"cache_n": 950, "prompt_n": 50})[0], True)
        self.assertEqual(bench_cerebro.veredicto_cache({"cache_n": 0, "prompt_n": 1000})[0], False)
        self.assertIsNone(bench_cerebro.veredicto_cache({})[0])


if __name__ == "__main__":
    unittest.main()
