# Cerebro local para JADIS

Investigación y plan para que el cerebro de JADIS corra en local (Qwen3.8-27B, versión sin
censura) y para que todo lo que salga del PC vaya seudonimizado.

| Archivo | Qué es |
|---|---|
| [`PLAN.md`](PLAN.md) | **Empieza aquí.** Resumen, conceptos explicados, qué esperar de una RTX 4060 de 8 GB, herramientas investigadas con veredicto, diseño de la frontera de privacidad, decisiones y plan por fases |
| [`fase0/`](fase0/) | **Fase 0 en un comando** (`python fase0.py`): inventario del PC, descargas verificadas y pruebas con y sin MTP. Informe sin datos personales. Incluye 49 tests con un `llama-server` simulado |
| [`ESTADO-entrada.md`](ESTADO-entrada.md) | Texto listo para pegar en `docs/ESTADO.md` de JADIS (bitácora + pendiente) |
