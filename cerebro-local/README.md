# Cerebro local para JADIS

Investigación y plan para que el cerebro de JADIS corra en local (Qwen3.8-27B, versión sin
censura) y para que todo lo que salga del PC vaya seudonimizado.

| Archivo | Qué es |
|---|---|
| [`PLAN.md`](PLAN.md) | **Empieza aquí.** Resumen, conceptos explicados, qué esperar de una RTX 4060 de 8 GB, herramientas investigadas con veredicto, diseño de la frontera de privacidad, decisiones y plan por fases |
| [`ENCARGO-papel-del-cerebro.md`](ENCARGO-papel-del-cerebro.md) | El papel del cerebro (Fase 4) listo para construir en JADIS: identidad, herramienta `delegar`, candado de procedencia, paso directo, lectura en dos pasos, pruebas y el texto para pegar en la sesión de JADIS |
| [`fase1/`](fase1/) | **Fase 1 en un comando** (`python calidad.py`): 23 casos reales de JADIS (charla, delegar, personal, inyección, sin censura) con comprobaciones automáticas y las respuestas para que las juzgues |
| [`ESTILO-JADIS.md`](ESTILO-JADIS.md) | Cómo habla JADIS: breve y con humor, para escribir menos tokens (el mayor ahorro de velocidad gratis) |
| [`fase0/`](fase0/) | **Fase 0 en un comando** (`python fase0.py`): inventario del PC, descargas verificadas y pruebas con y sin MTP. Informe sin datos personales. Incluye 61 tests con un `llama-server` simulado. `--exprimir` busca los ajustes más rápidos |
| [`ESTADO-entrada.md`](ESTADO-entrada.md) | Texto listo para pegar en `docs/ESTADO.md` de JADIS (bitácora + pendiente) |
