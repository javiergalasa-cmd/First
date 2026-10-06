# Texto para añadir a `C:\J.A.D.I.S\docs\ESTADO.md`

`ESTADO.md` vive en tu PC, no en este repo. Por eso no lo he editado: aquí tienes el texto para
que lo pegue la sesión de JADIS en tu PC, o tú mismo.

- En **§6 Bitácora**, va arriba del todo, porque lo más reciente va primero.
- En **§4 Pendiente**, va con el número siguiente al último que haya.

---

## Para §6 Bitácora

```markdown
### 2026-10-06 — Plan: cerebro local (Qwen3.8-27B) y frontera de privacidad

- **Por qué**: el cerebro pensaba en la nube con modelos gratis (en las pruebas recogidas el
  4-oct, `qwen3.8-27b:free` de OpenRouter, que el catálogo marca `entrena_si`). Cualquier
  anonimización hecha por el cerebro llegaba tarde: el proveedor ya había visto el texto.
  Decisión de Javier: cerebro en local y que lo que salga del PC vaya seudonimizado
  (`[PERSONA_1]` o similar, cualquier marcador vale).
- **Investigado** (sesión en la nube; repo `First`, rama `claude/magical-darwin-gcbo0m`,
  `cerebro-local/PLAN.md`):
  - Qwen3.8-27B (14-ago-2026, Apache 2.0, híbrido Gated DeltaNet, MTP).
  - Su inteligencia según Artificial Analysis (índice vigente v4.3): Qwen3.8-27B 34 pensando a
    tope; Sonnet 5 38; Sonnet 5.5 56; Opus 5.5 58. El 52 de agosto era del índice v4.1.1,
    rehecho el 4-sep.
  - AirLLM, descartado: relee el modelo por token.
  - Los motores dedicados (NInfer, vinf, Lucebox, qengine): ninguno sirve con 8 GB.
  - llama.cpp con reparto GPU/CPU y MTP: es el elegido.
  - La cuantización GSQ-RCO de ISTA-DASLab.
  - Las versiones sin censura: ojo, la de huihui-ai tiene el MTP roto.
- **Equipo**: RTX 4060 de 8 GB + 32 GB de RAM en **un solo módulo** Kingston FURY, que va en
  **un canal**: la mitad de ancho de banda. Un segundo módulo igual casi duplicaría la velocidad
  del cerebro local. DDR4 o DDR5, pendiente del inventario.
- **Decisiones de Javier**:
  - **Principio**: el cerebro local es el único de confianza (local + sin censura), no el más
    listo. Delega casi todo en subagentes de la nube con la tarea mínima y sin datos; paso directo
    de las respuestas para que el cerebro escriba poco.
  - **D1**: si el cerebro local no responde, esperar; si sigue sin responder, preguntar a la vez
    en el PC (notificación de permiso de JADIS) y en el móvil (ntfy) si usar la nube
    seudonimizada; vale la primera respuesta; sin respuesta = no.
  - **D2**: modelo sin censura ya hecho, que conserve el MTP, con checklist (plantilla oficial,
    SHA256, A/B).
  - **D5**: lo personal (correos, archivos, mensajes, memoria) solo lo lee JADIS, nunca un
    subagente: en dos pasos, primero sin herramientas. Lo de fuera (webs, búsquedas) lo leen
    los subagentes. Lo que vuelve es dato, y lo peligroso pasa por tarjeta (patrón Dual LLM /
    CaMeL).
- **Fase 0 preparada**: `cerebro-local/fase0/fase0.py` hace inventario, descarga (llama.cpp
  oficial + Qwen3.8-27B GSQ-RCO IQ3_S e IQ2_S con MTP, SHA256 y reanudación) y pruebas con y sin
  MTP. Deja `C:\jadis-cerebro\informe-fase0.md` sin datos personales. 60 tests con un
  llama-server simulado.
- **Riesgo nº 1**: la caché de prompt de los modelos híbridos en llama.cpp. Si el principio del
  prompt cambia, relee todo cada turno. La Fase 0 lo mide.
- **Velocidad**: `fase0.py --exprimir` prueba los ajustes uno a uno (borrador MTP/DFlash 2,
  hilos, margen de VRAM, bloques) y recomienda el comando más rápido. Antes, comprobar
  D.O.C.P./EXPO en la BIOS y probar el monitor en la gráfica integrada.
- **Siguiente paso**: ejecutar la Fase 0 en el PC (con JADIS y Ollama cerrados), primero
  `--solo-descargar` para tener la ruta de `llama-server.exe` para el panel de NVIDIA, y
  analizar el informe.
```

## Para §4 Pendiente

```markdown
N. **Cerebro local + frontera de privacidad** (plan del 6-oct, `cerebro-local/PLAN.md` del repo
   First):
   - Fase 0: medir con `fase0.py`. **Siguiente.**
   - Fase 1: modelo sin censura verificado (con MTP).
   - Fase 2: integrar. Router con `local` y `solo_local`; D1 con espera y pregunta por ntfy;
     supervisor con "modo GPU ocupada"; cola con prioridad.
   - Fase 3: seudonimización + DLP en el router.
   - Fase 4: delegar por defecto, paso directo de respuestas, reparto de D5. Encargo listo en
     `cerebro-local/ENCARGO-papel-del-cerebro.md`: 4a tras la Fase 2, 4b tras la Fase 3.
   - Fase 5: resto de salidas (voz, búsquedas, ntfy, MCP).

   Hardware: valorar un segundo módulo de RAM igual (dos canales).
```
