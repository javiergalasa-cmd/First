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
  4-oct, `qwen3.8-27b:free` de OpenRouter, que el catálogo marca `entrena_si`). Cualquier anonimización
  hecha por el cerebro llegaba tarde: el proveedor ya había visto el texto. Decisión de Javier:
  cerebro en local y que lo que salga del PC vaya seudonimizado.
- **Investigado** (sesión en la nube; repo `First`, rama `claude/magical-darwin-gcbo0m`,
  `cerebro-local/PLAN.md`):
  - Qwen3.8-27B (14-ago-2026, Apache 2.0, híbrido Gated DeltaNet, MTP).
  - AirLLM, descartado: relee el modelo por token.
  - Los motores dedicados (NInfer, vinf, Lucebox, qengine): ninguno sirve con 8 GB.
  - llama.cpp con reparto GPU/CPU y MTP: es el elegido.
  - La cuantización GSQ-RCO de ISTA-DASLab: IQ3_S de 11,8 GB, casi sin pérdida según sus
    autores.
  - Las versiones sin censura: ojo, la de huihui-ai tiene el MTP roto.
- **Estimación** en la RTX 4060 de 8 GB: ~10-12 tok/s con IQ3_S + MTP si la RAM es DDR5. Está
  por medir.
- **Riesgo nº 1**: la caché de prompt de los modelos híbridos en llama.cpp. Si el principio del
  prompt cambia, relee todo cada turno. La Fase 0 lo mide.
- **No existe todavía** la seudonimización reversible `[USUARIO]` ↔ nombre; lo que hay es el
  proxy de redacción de secretos de Hindsight (`:8900`) y la marca `privado` del router. Pendiente
  de confirmar con `git grep` por si estuviera en el código.
- **Siguiente paso**: Fase 0, medir en el PC con `cerebro-local/fase0/`, sin tocar JADIS.
```

## Para §4 Pendiente

```markdown
N. **Cerebro local + frontera de privacidad** (plan del 6-oct, `cerebro-local/PLAN.md` del repo
   First):
   - Fase 0: medir.
   - Fase 1: modelo sin censura verificado (con MTP).
   - Fase 2: integrar. Router con `local` y `solo_local`; supervisor con "modo GPU ocupada";
     cola con prioridad.
   - Fase 3: seudonimización + DLP en el router.
   - Fase 4: minimización en la herramienta de orquestación.
   - Fase 5: resto de salidas (voz, búsquedas, ntfy, MCP).

   Falta de Javier: RAM (GB y tipo), CPU, disco libre, el enlace del motor dedicado que vio y
   las decisiones D1-D10.
```
