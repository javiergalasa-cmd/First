# Cerebro local para JADIS: Qwen3.8-27B sin censura en tu PC + frontera de privacidad

> **Estado:** plan e investigación. No se ha tocado JADIS.
> **Rama:** `claude/magical-darwin-gcbo0m` (repo `First`). **Fecha:** 6-oct-2026.
> **Repo público:** este documento no lleva claves, rutas personales ni datos privados.
> **Cómo leerlo:** la sección 0 es el resumen. Las secciones 3 y 4 explican los conceptos y qué
> esperar de tu PC. La 11 es el plan por fases. La 10 son las decisiones que necesito de ti.
> Cada cifra va marcada como **medida por terceros**, **declarada por sus autores** o
> **estimación mía**, con su fuente en la sección 14.

---

## 0. Resumen en 12 puntos

1. **Tu intuición es correcta, y es el centro de todo.** Hoy el cerebro (Hermes) piensa con
   modelos gratis de la nube a través del router. En las pruebas que recoge el resumen del 4-oct
   respondía con `qwen3.8-27b:free` de OpenRouter, y el propio catálogo del router marca esos
   `:free` como "puede entrenar con lo que mandas". Si ese cerebro anonimiza algo, lo hace tarde: el
   proveedor ya ha visto el texto original.
2. **La solución coherente es mover la frontera.** El cerebro corre en tu PC y ve todo en
   claro. Todo lo que sale a Internet pasa por **una única puerta, el router**, que
   seudonimiza (`Javier` → `⟦PERSONA_1⟧`), comprueba que no se escape nada y deshace el
   cambio en la respuesta. Lo hace código determinista, no la buena voluntad de un modelo.
3. **Qwen3.8-27B existe y es buena elección.** Lo publicó Alibaba el 14-ago-2026 con licencia
   Apache 2.0: denso, 27.000 millones de parámetros, visión, 262K de contexto y cabezal MTP.
   Tiene un 52 en el índice de Artificial Analysis, frente al 32 del Qwen3.6-35B-A3B. Es el
   mismo modelo que ya usa tu cerebro desde la nube: **no pierdes inteligencia, ganas
   privacidad.**
4. **No cabe entero en tu GPU.** Tu RTX 4060 tiene 8 GB y el modelo ocupa ~16 GB a 4 bits
   (~12 GB a 3,5 bits). Hay que repartirlo entre la GPU y la CPU.
5. **"Cargar a cachitos" (AirLLM) no te conviene.** Relee el modelo entero por cada token, y en
   un 27B eso son segundos por palabra. Lo que funciona es **llama.cpp con reparto GPU/CPU**:
   lo que cabe en la VRAM se calcula en la GPU, y el resto se calcula en la CPU **donde ya
   está**, en la RAM. Así no viaja por el bus PCIe, que en tu tarjeta es el tubo más estrecho.
6. **Los motores "solo para Qwen3.8-27B" existen, pero ninguno sirve con 8 GB.** He mirado
   NInfer, vinf, Lucebox, qengine y Qwen3.8-27B-in-C. Piden 12-24 GB de VRAM, una GPU concreta
   o Linux. Tampoco se pueden "usar dos a la vez": cada uno es un motor completo. Lo que sí se
   combina, dentro de llama.cpp, es el reparto GPU/CPU con la **decodificación especulativa**
   del cabezal MTP que trae el propio modelo. Terceros han medido entre +43 % y +142 % de
   velocidad según la GPU (+74 % en una de 8 GB), sin perder calidad.
7. **Velocidad esperable en tu PC** (estimación mía, a confirmar en la Fase 0):
   - ~10-12 tokens/s con la cuantización GSQ-RCO IQ3_S + MTP si tu RAM es DDR5.
   - ~7-8 tok/s con IQ4_XS.
   - Referencia medida por un tercero con una GPU de 8 GB parecida: 4,2 → 7,3 tok/s.
   - En la nube, Qwen3.8-27B va a ~48 tok/s (mediana de Artificial Analysis), pero los
     gratis tienen colas: el 6-oct un "hola" tardó 196 s.
8. **La cuantización importa más que el motor.** ISTA-DASLab, el laboratorio de GPTQ, publicó
   Qwen3.8-27B en GSQ-RCO. Su IQ3_S pesa 11,8 GB y, según sus autores, iguala al original en
   AIME25 y LiveCodeBench. Menos GB en la RAM es más velocidad.
9. **El "jailbreak" de los pesos se llama *abliteration*:** se borra la "dirección de rechazo"
   del modelo. Ya hay muchos Qwen3.8-27B así en Hugging Face (Heretic, abliterated). **Trampa:**
   en el más conocido (huihui-ai), sus usuarios documentan el cabezal MTP roto (0 % de
   aceptación), así que pierdes la aceleración. Hay versiones que lo conservan.
10. **Riesgos reales de un cerebro sin censura:**
    - Cambia también cómo decide. Un estudio de jul-2026 midió +7,4 puntos de optimismo en un
      Qwen (Qwen3-30B-A3B, no el 3.8) tras la abliteration, en una tarea donde nunca rechazaba
      nada.
    - Obedece también a las instrucciones que alguien esconda en una web o un correo.
    - Tus tarjetas de aprobación (ApprovalGate) pasan a ser la red de seguridad principal.
    - Los GGUF de terceros pueden traer la plantilla de chat envenenada: usa la oficial.
11. **Hay fugas que no son el cerebro.** Quedan fuera del cerebro, y hoy salen del PC:
    - los subagentes;
    - la memoria (Hindsight) y la wiki, que van a proveedores externos aunque sean "privados";
    - las tareas auxiliares de Hermes, que resumen la conversación;
    - las búsquedas web, los avisos por ntfy.sh y la voz por OpenAI.

    El plan las clasifica una a una (sección 8.2).
12. **Plan en 6 fases.** Empieza midiendo en tu PC sin tocar JADIS, con el kit incluido en
    `fase0/`. Necesito de ti tres datos: cuánta RAM tienes, si es DDR4 o DDR5, y qué motor
    viste exactamente. Además hay 10 decisiones que tomar (sección 10).

---

## 1. Qué he revisado y con qué límites

**Revisado:**

- **Sesión "Herramientas como código en JADIS"** (24-sep → 5-oct): la del router. He leído su
  resumen de compactación, que cubre del 24-sep al 4-oct, y en detalle sus últimas ~4 horas
  (tarde del 5-oct). **No** he leído lo que pasó entre el 4-oct y esa tarde. De ahí salen:
  - la arquitectura actual;
  - los perfiles del router (`principal`, `auxiliar`, `vision`, `subagente`, `memoria`, `wiki`),
    con su marca `privado`;
  - el respaldo universal `ollama:gemma4:12b`;
  - que la clave de OpenAI se quedó en Hermes para voz;
  - la lista de APIs gratis;
  - que el cerebro respondía con `qwen3.8-27b:free`.
- **"Auditoría del proyecto JARVIS"** y **"Handoff and master plan review"** (sus partes más
  recientes): la estructura de `docs/ESTADO.md` (secciones 0-7, ~1.500 líneas) y el **proxy de
  redacción de Hindsight (`:8900`)**, que redacta **secretos** antes de guardarlos en la
  memoria.
- **"CPU maxing instead of GPU usage"**: tu GPU es una **NVIDIA GeForce RTX 4060 de 8 GB**
  (`nvidia-smi`: 8188 MiB). El sistema también lista una **AMD Radeon(TM) Graphics**
  integrada.

**Lo que NO he podido hacer (y cómo lo he compensado):**

- **No he leído `ESTADO.md` entero.** Está en tu PC (`C:\J.A.D.I.S\docs\ESTADO.md`), no en
  este repo. Solo he visto los trozos que aparecen en las transcripciones: la lista de
  pendientes, entradas de la bitácora y ediciones del 4 y 6-oct. Si algo de este plan choca
  con ESTADO.md, manda ESTADO.md: dímelo y lo ajusto.
- **No he leído el código de JADIS** (también está en tu PC). Lo que digo del router, de Hermes
  y de Hindsight sale de lo que contaron esas sesiones.
- **Hugging Face está bloqueado desde este entorno** (y también arxiv.org y varias webs). Lo de
  Hugging Face lo he contrastado con:
  - los resultados del buscador;
  - las fichas reflejadas en otras webs;
  - los repos de GitHub, que sí se leen.

  **Hay que comprobar cada ficha de modelo antes de descargar** (Fase 1 lo incluye).
- **Sobre lo de `[USUARIO]`:** en las transcripciones **no he encontrado** una seudonimización
  reversible tipo `[USUARIO]` ↔ `Javier`. Lo que existe es:
  - el proxy de redacción de secretos para la memoria;
  - la marca `privado` del router, que excluye a los proveedores que entrenan con tus datos.

  Puede que exista en el código y no saliera en lo que leí. Se comprueba en 10 s en tu PC (en
  PowerShell, dentro de `C:\J.A.D.I.S`):
  `git grep -n -i -E "seudonim|anonimi|\[USUARIO\]|redact"`.

---

## 2. Lo que quieres conseguir, en limpio

| # | Objetivo | Cómo lo traduce el plan |
|---|---|---|
| O1 | Que los proveedores gratis no vean todo lo que haces | Cerebro local; seudonimización + comprobación en la única salida (el router); minimizar lo que se manda |
| O2 | Que JADIS sepa todo de ti pero no lo cuente | Dentro del PC todo en claro (cerebro, memoria, wiki); fuera, solo lo imprescindible y seudonimizado |
| O3 | Correr Qwen3.8-27B en tu RTX 4060 de 8 GB | llama.cpp con reparto GPU/CPU + MTP + cuantización GSQ-RCO |
| O4 | Que vaya lo más rápido posible | MTP/DFlash 2, la cuantización adecuada, caché de prompt, "pensar" solo cuando haga falta; hardware si quieres más |
| O5 | Un Qwen3.8-27B sin censura | Versión *abliterated*/Heretic que conserve el MTP, verificada; o hecha por ti desde los pesos oficiales |

**Requisitos derivados** (no los pediste, pero salen de JADIS):

- Hermes necesita **≥64K de contexto** para trabajar con herramientas. Lo dicen fuentes
  secundarias; no pude abrir su documentación oficial.
- Las llamadas a herramientas deben salir bien formadas.
- La caché de prompt debe funcionar entre turnos (sección 3.5).
- Hay que poder liberar la GPU cuando la uses para otra cosa.

---

## 3. Los conceptos, sin tecnicismos

### 3.1 Pesos y cuantización

- **Qué es un modelo.** Un modelo son sus **pesos**: miles de millones de números. Qwen3.8-27B
  tiene ~27.000 millones.
- **Cuánto ocupan.** En el formato original (16 bits por número) ocupan ~54 GB.
- **Qué es cuantizar.** **Cuantizar** es guardar cada número con menos bits:
  - a ~4 bits ocupa ~16 GB;
  - a ~3,5 bits, ~12 GB;
  - a ~2,5 bits, ~8,4 GB.
- **Qué se pierde.** Al bajar bits se pierde algo de precisión. Se mide con la **KLD**, que dice
  cuánto se aparta el modelo cuantizado del original: 0 es idéntico.
- **El formato.** El formato estándar para uso local es **GGUF**, el de llama.cpp, Ollama y
  LM Studio.

### 3.2 Por qué la velocidad depende del "ancho de banda" y no de la potencia

Para escribir **cada** token, un modelo denso tiene que **leer todos sus pesos una vez**. Por eso
la velocidad la marca lo rápido que se pueden leer esos GB, no la potencia de cálculo. Los tres
"tubos" de tu PC (cifras de catálogo):

| Tubo | Ancho de banda | Qué implica |
|---|---|---|
| VRAM de la RTX 4060 | 272 GB/s | Lo que está en la GPU se lee rapidísimo |
| RAM del sistema (DDR5 doble canal / DDR4) | ~60-70 / ~35-45 GB/s reales | 4-7 veces más lenta que la VRAM |
| Bus PCIe 4.0 **x8** (la 4060 de sobremesa usa 8 carriles) | ~13-14 GB/s reales | **El más estrecho**: mover pesos por aquí en cada token es lo peor |

Tiempo por token ≈ (GB en la GPU ÷ 272) + (GB en la CPU ÷ velocidad de tu RAM). La parte de la
CPU domina. Por eso cada GB que quitas al modelo se nota.

### 3.3 Tres formas de usar un modelo que no cabe en tu VRAM

| Forma | Ejemplo | Qué mueve en cada token | Velocidad para un 27B en tu PC |
|---|---|---|---|
| **A. Cargar capa a capa desde el disco** | AirLLM | Todo el modelo, del disco o la RAM a la GPU | Segundos por token (estimación); sin MTP; sin servidor tipo OpenAI |
| **B. Pasar los pesos a la GPU por PCIe ("streaming")** | vinf | La parte que no cabe (~5-10 GB) por PCIe x8 | ~1-2 tok/s sin especulativa (estimación): el PCIe es 3-5 veces más estrecho que tu RAM |
| **C. Repartir: la GPU calcula lo suyo y la CPU lo suyo** | **llama.cpp** (`--fit`, `-ngl`) | Nada: cada parte se calcula donde está | **~3-16 tok/s** según la cuantización, la RAM y el MTP (sección 4) |

Tu idea de "cargar cachito a cachito" es la forma A. Funciona, pero para **un usuario
generando de token en token** es la peor de las tres. La C es la que usan quienes corren
Qwen3.8-27B en GPUs de 8 GB.

### 3.4 Decodificación especulativa: MTP y DFlash 2 (gratis en calidad)

- **La idea.** Un "borrador" muy barato adivina los próximos 2-7 tokens. Después, el modelo
  grande los **comprueba todos de una vez**, que cuesta casi lo mismo que generar uno. Los
  acertados se quedan y el primer fallo se corrige.
- **No pierde calidad.** El resultado es **matemáticamente el mismo** que sin borrador; solo
  cambia la velocidad.
- **MTP.** Qwen3.8-27B **trae su propio borrador**: el cabezal MTP, los tensores `blk.64` /
  `nextn` dentro del GGUF. En llama.cpp se activa con `--spec-type draft-mtp`, integrado
  desde el 16-may-2026. En la tabla de terceros va de +43 % a +142 % según la GPU. En una de
  8 GB con reparto GPU/CPU midieron **+74 %**, con un 90 % de aciertos.
- **DFlash 2.** Es un borrador externo (~0,7-1,1 GB) que adivina bloques enteros. Está en
  llama.cpp desde el 27-ago-2026 (`--spec-type draft-dflash`). En tarjetas de 24 GB rinde
  algo más que MTP. En la tuya resta VRAM al modelo principal: hay que medirlo (Fase 6).

### 3.5 Contexto, caché KV y por qué los modelos "híbridos" tienen una trampa

- **Contexto.** Es lo que el modelo "tiene delante": el prompt de sistema de Hermes, las
  definiciones de herramientas, la conversación y los resultados de herramientas.
- **Leer el prompt (prefill).** Leerlo cuesta tiempo. En tu PC estimo **~300-600 tokens/s**: un
  prompt de 15.000 tokens tardaría **25-50 s** la primera vez.
- **La caché.** Gracias a la caché, en los turnos siguientes solo se lee lo nuevo.
- **La trampa de los híbridos.** Qwen3.8 es **híbrido**: 48 de sus 64 capas son *Gated
  DeltaNet* y guardan un "estado" en vez de la caché clásica. Eso abarata mucho el contexto
  largo. Pero llama.cpp no puede "rebobinar" ese estado, así que usa **puntos de control**.
- **El fallo conocido.** Si el principio del prompt cambia entre turnos, los puntos de control
  no valen y **relee TODO el prompt en cada turno**. Eso pasa, por ejemplo, si se inserta un
  recuerdo de la memoria o la hora al principio. En un agente eso sería catastrófico: 25-50 s
  por turno. Está documentado en llama.cpp con otro Qwen híbrido (issue #19794, cerrado sin
  arreglo).
- **Qué hacemos.** La Fase 0 lo mide (el kit lo detecta solo) y la Fase 2 lo previene: el
  prompt debe crecer solo por el final.

### 3.6 "Pensar" (thinking)

- **Qué es.** Qwen3.8 puede "pensar" antes de responder: genera cientos o miles de tokens de
  razonamiento.
- **Lo que cuesta.** A ~10 tok/s, 1.000 tokens de pensamiento son **100 s** antes de la
  primera palabra.
- **Qué hacemos.** Pensar **apagado por defecto** en conversación y encendido en tareas
  difíciles. Se controla por petición: `chat_template_kwargs: {"enable_thinking": false}`,
  `reasoning_effort`, o `--reasoning-budget` en el servidor.

### 3.7 "Jailbreak" vs *abliteration*

| Técnica | Qué hace | Para ti |
|---|---|---|
| **Jailbreak** (en el prompt) | Engaña al modelo con instrucciones | Frágil: cada actualización lo rompe |
| ***Abliteration*** | Localiza en los pesos la "dirección" que produce los rechazos y la borra (técnica de Arditi et al., 2024) | Permanente; es lo que llevan los modelos "uncensored"/"abliterated" |
| **Heretic** (p-e-w/heretic) | Abliteration **automática**: busca el ajuste que quita los rechazos cambiando lo mínimo el resto del modelo (mide la KLD) | Lo mejor si lo haces tú; ya hay Qwen3.8-27B hechos con él |
| **Fine-tune "uncensored"** | Reentrena con datos sin rechazos | Más caro; más riesgo de degradar |

---

## 4. Tu equipo y qué esperar

**Lo que sé:**

- RTX 4060 de 8 GB. `nvidia-smi` no dice "Laptop", así que la tomo como **de sobremesa**:
  272 GB/s, PCIe 4.0 x8.
- CPU AMD con gráfica integrada.
- Windows.

**Lo que no sé (y cambia mucho el resultado):**

- cuánta RAM tienes;
- si es DDR4 o DDR5;
- qué CPU exacta tienes.

**Mediciones de terceros con Qwen3.8-27B + MTP en llama.cpp:**

| Equipo (de otros) | Cuantización | Sin MTP | Con MTP |
|---|---|---|---|
| RTX 5060 Laptop **8 GB** + Ryzen 7 260 + 31 GB RAM; reparto GPU/CPU (25 capas en GPU); 64K de contexto | IQ4_XS (15,7 GB) | 4,2 tok/s | **7,3 tok/s** (+74 %) |
| RTX 4060 **8 GB** (portátil); fuente secundaria | ? | ~5 tok/s | — |
| RTX 4060 Ti **16 GB** | — | 17,6 | 40,0 |
| RTX 3090 **24 GB** | Q4_K_M | 31,9 | 52,8 |
| RTX 4090 **24 GB** | — | 47,7 | 76,3 |

**Mi estimación para tu PC** (tokens/s al generar). Cómo la he calculado:

- La fórmula de 3.2, suponiendo ~6,3 GB de pesos en la VRAM.
- Corregida con un factor de 0,75, calibrado con la medición de la RTX 5060 Laptop.
- MTP ×1,6-1,75.
- **Error esperable: ±30 %.**

| Cuantización | Tamaño | Parte en RAM | DDR5 sin MTP | **DDR5 con MTP** | DDR4 sin MTP | DDR4 con MTP |
|---|---|---|---|---|---|---|
| Unsloth IQ4_XS | 15,7 GB | ~9,4 GB | ~4,5 | **~7-8** | ~3 | ~4,5-5 |
| **GSQ-RCO IQ3_S** | 11,8 GB | ~5,5 GB | ~7 | **~11-12** | ~4,5 | ~7-8 |
| GSQ-RCO IQ3_XXS | 10,1 GB | ~3,8 GB | ~9 | **~14-16** | ~6 | ~10 |

**Cómo se traduce en uso real:**

- **A ~10 tok/s, la respuesta va más rápido de lo que se lee en voz alta** (~7 palabras/s
  frente a 2,5-3 palabras/s del habla). Con una voz que vaya leyendo por frases, la espera
  percibida es la del primer trozo.
- **Un turno con una herramienta** son ~15-40 s (estimación): generar la llamada, leer el
  resultado y responder.
- **El primer turno de una conversación** (leer el prompt de Hermes entero) son ~25-50 s, si
  el prompt ronda los 15.000 tokens; su tamaño real se mide en la Fase 0.
- **Comparación honesta:** Qwen3.8-27B en la nube va a ~48 tok/s (mediana de Artificial
  Analysis). Vas a ir 4-6 veces más lento, pero **sin colas** (el 6-oct un "hola" tardó 196 s
  por las colas de los gratis) y sin que nadie lea nada.

**RAM.**

- Con **32 GB** cabe todo con margen: el modelo (5-10 GB en RAM), Windows, Docker con Hindsight
  y Postgres, Hermes y el HUD.
- Con **16 GB** solo sería viable IQ3_XXS o menos, y muy justo.

---

## 5. Lo investigado, herramienta por herramienta

### 5.1 El modelo: Qwen3.8-27B (oficial)

- **Repo y licencia.** Repo oficial: [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8).
  Publicado el **14-ago-2026** en Hugging Face y ModelScope. **Apache 2.0**: puedes
  modificarlo y usarlo libremente.
- **Arquitectura.** Denso: usa **todos** sus parámetros en cada token. Tiene 64 capas: 48
  *Gated DeltaNet* (atención lineal) y 16 de atención completa (GQA 24/4).
  Dimensión 5.120.
- **Extras.** Cabezal MTP entrenado y visión nativa (imágenes y vídeo).
- **Contexto.** 262.144 tokens de contexto nativo, ampliable a 1M con YaRN.
- **Control del razonamiento.** `reasoning_effort` y `preserve_thinking`.
- **Herramientas.** El repo despliega con `--tool-call-parser qwen3_coder`: llamadas en formato
  XML, que llama.cpp interpreta con `--jinja`.
- **Inteligencia.** Índice de Artificial Analysis **52**; Qwen3.6-35B-A3B (MoE) **32**.
- **Ojo.** Las cifras de benchmarks de la ficha las publicó Alibaba. Que yo sepa, no las ha
  reproducido nadie independiente.

### 5.2 Carga por capas: AirLLM ([lyogavin/airllm](https://github.com/lyogavin/airllm))

**Qué es.** Mantiene **una sola capa en la GPU** y va cargando las demás desde el disco. Declara
soporte para Qwen3.8-27B en 3,33 GB de VRAM y para 405B en 8 GB.

**Por qué lo descarto:**

1. **Relee el modelo entero por cada token.** Los análisis independientes miden ~20 s por token
   en un 70B. No publica tablas reproducibles de tokens/s.
2. **No tiene decodificación especulativa (MTP) ni servidor compatible con OpenAI,** que es lo
   que necesita el router.
3. **Su documentación no menciona Windows.**

**Para qué sí sirve:** procesar por lotes, sin prisa, modelos enormes que no caben de ninguna
otra forma.

**Una corrección:** ninguna herramienta puede correr **Opus 5.5** en local. Sus pesos no son
públicos: Anthropic no los distribuye. Lo que sí es cierto es que modelos **abiertos** gigantes
se pueden "arrancar" con AirLLM en 8 GB… a minutos por palabra.

### 5.3 Motores dedicados solo a Qwen3.8-27B

| Motor | Para qué GPU | ¿Sirve con tu 4060 de 8 GB? | Notas |
|---|---|---|---|
| [NInfer-4090](https://github.com/UDPSendToFailed/ninfer-4090) | Solo RTX 4090 (24 GB, sm_89) | **No**: misma arquitectura que tu 4060, pero necesita los 24 GB | Windows 11; API OpenAI y Anthropic; MTP; 174★; formato propio `.ninfer` |
| [NInfer 16 GB](https://github.com/Ryan-gsq/ninfer-16g-5070ti-5080-5090-qwen3.8-27b-gsq-rco) | RTX 5070 Ti/5080/5090 (≥16 GB); 30/40 con 16 GB compilando | **No** (pide ≥16 GB; no documenta reparto con la CPU) | Windows; gestor web en la bandeja; DFlash 2; GSQ-RCO |
| [vinf-3080ti](https://github.com/andrem-eberle/vinf-3080ti) | Solo RTX 3080 Ti (12 GB, sm_86) | **No** (otra arquitectura; Linux) | El único que pasa pesos por PCIe para modelos más grandes que la VRAM: 11,66 tok/s con MTP en su GPU. 0★, sin licencia, solo muestreo *greedy* |
| [Lucebox hub](https://github.com/Luce-Org/lucebox-hub) | 3090/4090/5090, P40, AMD R9700… | **No** (sin reparto con la CPU documentado) | Proyecto serio: 2,9k★, Apache 2.0. Dice ser varias veces más rápido que llama.cpp con el mismo borrador |
| [qengine](https://github.com/Haru-neo/qengine) | Tarjetas sm_70 (V100, CMP de minería), multi-GPU | **No** | Hecho para los Qwen híbridos (3.5); 1,32-1,45× llama.cpp en varias GPUs |
| [Qwen3.8-27B-in-C](https://github.com/Julien-Bui/Qwen3.8-27B-in-C) | Solo CPU (AVX2) | Funcionaría, pero **más lento**: 1,2-1,6 tok/s | Educativo; API no compatible con OpenAI |

**Conclusión:** estos motores son rápidos precisamente porque **asumen que el modelo cabe en la
VRAM** y afinan cada núcleo de cálculo para una GPU concreta. Con 8 GB la VRAM no es tu
cuello de botella: lo es la RAM. Ahí no aportan.

**¿Cuál viste tú?** Lo describes "como Ollama, solo para Qwen3.8-27B y bastante más rápido".
Por eso lo más probable es **NInfer**: tiene gestor en la bandeja de Windows, API compatible
con OpenAI y solo sirve Qwen3.8-27B. Pásame el enlace y lo confirmo. Si algún día tienes una
GPU de 16-24 GB, NInfer y Lucebox pasan a ser candidatos serios (Fase 6).

### 5.4 ¿Usar los dos a la vez?

**No se puede.** Un "motor" es el programa que carga los pesos y hace las cuentas. Dos motores
no pueden repartirse el cálculo de un mismo token. Lo que buscas al combinarlos sí se puede
tener junto, **dentro de un solo motor (llama.cpp)**:

- reparto GPU/CPU (lo de "a cachitos", bien hecho);
- decodificación especulativa (MTP o DFlash 2);
- una cuantización eficiente (GSQ-RCO);
- caché de prompt.

### 5.5 Motor recomendado: llama.cpp (`llama-server`)

- **Corre nativo en Windows con CUDA.** Hay compilaciones oficiales en
  [ggml-org/llama.cpp/releases](https://github.com/ggml-org/llama.cpp/releases): el zip
  `…-bin-win-cuda-…-x64.zip` y su `cudart-…`.
- **Trae MTP y DFlash 2.** Además, `--fit` reparte las capas solo según la VRAM libre.
- **Habla la API de OpenAI** (`/v1/chat/completions`), igual que el router.
- **Devuelve `timings` con `cache_n`,** que permite verificar la caché.
- **Escucha solo en `127.0.0.1` por defecto.**
- **Por qué no Ollama** (aunque ya lo usas):
  1. Hermes conectado a Ollama por la ruta compatible con OpenAI se queda **en silencio con
     4.096 tokens de contexto**. Es el bug
     [hermes-agent#43900](https://github.com/NousResearch/hermes-agent/issues/43900), abierto
     cuando lo consulté.
  2. Hay menos control sobre el reparto y la caché.
  3. Las etiquetas de Qwen3.8 con MTP que encontré en Ollama son Q8/BF16 (30-56 GB),
     demasiado grandes para ti.
- **ik_llama.cpp** (bifurcación con mejores núcleos de CPU) da resultados mixtos en reparto
  GPU/CPU. Opcional en la Fase 6.

### 5.6 Cuantizaciones: la decisión que más velocidad da

**GSQ-RCO de ISTA-DASLab.** Asigna a cada tensor la precisión que necesita mediante una
búsqueda por gradientes. Es un **GGUF estándar** (llama.cpp, Ollama, LM Studio) y hay versión
`-mtp` (+0,35 GB). Cifras **declaradas por sus autores**:

| Variante | Bits/peso | Tamaño | AIME25 | GPQA-Diamond | LiveCodeBench v6 |
|---|---|---|---|---|---|
| IQ2_XS | 2,50 | 8,4 GB | 96,67 | 84,85 | 76,57 |
| IQ2_S | 2,75 | 9,3 GB | 100,00 | 86,36 | 82,29 |
| IQ3_XXS | 3,00 | 10,1 GB | 100,00 | 88,89 | 84,57 |
| **IQ3_S** | 3,50 | 11,8 GB | 100,00 | 89,39 | 85,71 |
| Original (BF16) | 16 | ~54 GB | 100,00 | ~89,9 | 85,71 |

**Unsloth (Dynamic 2.0).** Error medio respecto al original (KLD; menos es mejor):

| Variante | Tamaño | KLD |
|---|---|---|
| UD-Q2_K_XL | 9,83 GB | ~0,09 |
| UD-Q3_K_XL | 13,15 GB | ~0,026 |
| UD-Q4_K_M | 16,46 GB | ~0,010 |
| UD-Q4_K_XL | 17,56 GB | ~0,008 |

**Cautelas:**

- AIME25 son 30 problemas: un acierto de diferencia ya mueve ~3 puntos.
- Ningún benchmark mide **llamadas a herramientas en español**, que es lo que hará tu cerebro.
- Por eso la Fase 0 y la 1 lo prueban con tus casos.

**Recomendación de partida: GSQ-RCO IQ3_S-mtp.** Es casi sin pérdida según sus autores, 4 GB
menos que IQ4_XS, y lo publica un laboratorio con reputación.

### 5.7 Versiones sin censura de Qwen3.8-27B (candidatas)

Las he encontrado con el buscador; desde aquí **no he podido abrir las fichas**. Todas son de
terceros: hay que verificarlas (Fase 1).

| Repo en Hugging Face | Método | MTP | Lo que dice su ficha (según el buscador) |
|---|---|---|---|
| `darrellbest/Qwen3.8-27B-Heretic-GGUF` | Heretic | ¿? | **0/100 rechazos** (original 98/100), **KLD 0,0465**; Q4_K_M 15,7 GB |
| `Unb0rn/Qwen3.8-27B-Heretic-Uncensored-MTP-GGUF` | Heretic | **Sí** (dice el nombre); el buscador habla de cabezal fijado a Q8_0 | Q8_0/Q6_K/Q5_K_M |
| `hotdogs/Qwen3.8-27B-abliterated-MTP-GGUF` | Abliteration | **Sí** | KLD 0,0066 en una prueba de la ficha del modelo base del mismo autor |
| `Blackfrost-AI/Qwen3.8-27B-ABLITERATED-GGUF` | Abliteration | **Sí** (incrustado) | — |
| `cygnal/Qwen3.8-27B-heretic-ara-Q4_K_M-MTP-GGUF` | Heretic (ARA) | **Sí** | Solo Q4_K_M |
| `mradermacher/Qwen3.8-27B-heretic-ara-i1-GGUF` | Heretic (ARA) | ¿? | Cuantizador muy conocido, cuantizaciones con *imatrix* |
| `0bserverx/Qwen3.8-27B-Heretic-GSQ-RCO-GGUF`, `RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored` | Heretic + GSQ-RCO | ¿? | La combinación ideal para 8 GB, **si** se verifica |
| ~~`huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF`~~ | Abliteration | **Roto** | Su discusión #4 documenta que la abliteration reescribió el cabezal MTP: **0 % de aceptación**. Puede haberse corregido después: hay que comprobarlo |

**Por qué se rompe el MTP.** Muchas herramientas de abliteration cargan el modelo con
`transformers` y lo vuelven a guardar. Por el camino tocan o pierden los pesos `mtp.*`. Si lo
haces tú, hay que **copiar el cabezal MTP original** antes de convertir a GGUF.

**Lo que dice la investigación sobre abliterar un agente:**

- El trabajo *"Abliteration Is Not a Scalpel"* (arXiv 2607.17427, jul-2026) midió 21.600
  decisiones bajo incertidumbre, una tarea que **no provoca ningún rechazo**.
- Compararon Gemma-4-26B-A4B y Qwen3-30B-A3B, no Qwen3.8. Los modelos abliterados salieron
  **más optimistas**: +12,2 puntos en Gemma y +7,4 en Qwen. También se justificaban más largo
  y usaban menos palabras de duda.
- Conclusión: un modelo sin censura **no es el original menos los rechazos, es otro que
  decide distinto.** Para un cerebro que orquesta, eso se mide (Fase 1), no se supone.

---

## 6. Cosas que no sabías y que mejoran el plan

1. **El cuello de botella es tu RAM, no tu GPU.** Cada GB que sacas del modelo vale más que
   cualquier truco del motor. De ahí GSQ-RCO.
2. **MTP viene gratis dentro del modelo:** +74 % medido en 8 GB, sin perder calidad. Siempre
   que la versión que elijas lo conserve.
3. **Windows desborda la VRAM en silencio.** Desde el driver 536.40, si la VRAM se llena, el
   driver usa RAM "compartida" sin avisar y la velocidad se hunde. Ajústalo en *Panel de
   control de NVIDIA → Administrar configuración 3D → Configuración de programa →
   llama-server.exe → "CUDA - Sysmem Fallback Policy" = "Prefer No Sysmem Fallback"*. Así
   falla con un error en vez de ir lento a escondidas. Hazlo solo para ese programa, no
   global, para no afectar a los juegos.
4. **Tu CPU tiene gráfica integrada.** Si conectas el monitor a la placa base (si tiene salida
   de vídeo), Windows, el navegador y las demás aplicaciones dejan de ocupar VRAM de la 4060. Eso libera
   ~0,5-1,5 GB para el modelo. Los juegos siguen usando la 4060 (Windows lo enruta), con una
   pequeña penalización. Es opcional y se prueba en la Fase 6.
5. **La GPU será compartida.** Con el cerebro cargado, la 4060 tiene ~7 GB ocupados. Si la usas
   para otra cosa (juegos, vídeo), hace falta un **"modo GPU ocupada"** que pare o descargue el
   cerebro (decisión D10).
6. **La caché de prompt de los modelos híbridos es frágil.** El prompt de Hermes debe crecer
   solo por el final: nada dinámico (hora, recuerdos) al principio. El kit de la Fase 0 lo
   detecta solo.
7. **Pensar cuesta minutos a tu velocidad.** Apagado por defecto y encendido por tarea.
8. **La plantilla de chat de un GGUF puede estar envenenada.** Pillar Security (2025) demostró
   puertas traseras escondidas en la plantilla de chat de archivos GGUF. En 18 modelos y 4
   motores consiguieron:
   - bajar la exactitud del 90 % al 15 %;
   - colar enlaces del atacante en >90 % de los casos.

   Para los modelos de terceros, **carga la plantilla oficial** (`--chat-template-file`).
9. **Solo `.gguf`.** Nada de `.bin`/`.pt` (pickle de PyTorch, pueden ejecutar código) ni
   `trust_remote_code`. Anota el SHA256 de cada archivo.
10. **El nivel del router.** El nombre de un GGUF local no casará con el ranking de Artificial
    Analysis. Hay que fijar su nivel a mano (`medio-alto`, como el Qwen3.8-27B de la nube):
    el router ya tiene `PUT /modelos/nivel`.
11. **El respaldo `ollama:gemma4:12b` competirá por la VRAM** con el cerebro local. Hay que
    decidir: quitarlo, pasarlo a CPU o dejar que el cerebro local sea el respaldo.
12. **LLM Guard está archivado.** Tenía un escáner *Anonymize* y otro *Deanonymize* que hacían
    justo lo de `[USUARIO]`. Ya no se mantiene: no lo uses. Para detectar nombres en textos de terceros
    sirve **Microsoft Presidio**, que sí se mantiene (MIT). Su propio README avisa de que
    **no garantiza encontrarlo todo**.
13. **Hacerlo tú es posible y lo más fiable:** Heretic sobre los pesos oficiales, en una GPU
    alquilada unas horas. No hay datos tuyos implicados: solo el modelo público.
14. **El hardware es el multiplicador.** Con una GPU de 16 GB, las referencias son ~40 tok/s;
    con una de 24 GB, ~53-76 tok/s. Eso es entre 3 y 10 veces más que con 8 GB, según la
    cuantización con la que se compare (Fase 6).

---

## 7. Configuración del motor y por qué cada opción

El kit genera este comando (`fase0/arrancar_cerebro.py --solo-mostrar` lo enseña sin
ejecutarlo):

```
llama-server -m <modelo.gguf> --host 127.0.0.1 --port 8080 -c 65536 -fa on -ctk q8_0 -ctv q8_0
  --fit on --fit-target 1024 -np 1 --jinja --reasoning-format deepseek --ctx-checkpoints 32
  --cache-ram 8192 --metrics --spec-type draft-mtp --spec-draft-n-max 2
```

| Opción | Por qué |
|---|---|
| `--host 127.0.0.1` | Solo tu PC puede hablar con el cerebro |
| `-c 65536` | Los 64K que pide Hermes; en este modelo el contexto es barato (solo 16 capas guardan caché KV) |
| `-fa on`, `-ctk/-ctv q8_0` | Caché KV a 8 bits: ~la mitad de memoria que f16 y pérdida despreciable |
| `--fit on --fit-target 1024` | llama.cpp decide cuántas capas caben en la GPU dejando 1 GB libre. Si el monitor va por la integrada, prueba 512 |
| `-np 1` | La especulativa rinde con una petición a la vez; con varias se pierde la ventaja |
| `--spec-type draft-mtp --spec-draft-n-max 2` | MTP con 2 tokens de borrador. En las tablas de terceros, 2-3 es lo que mejor rinde en GPUs pequeñas; con 8 casi siempre pierde. La Fase 0 prueba 2 y 3 |
| `--ctx-checkpoints 32 --cache-ram 8192` | Puntos de control y caché en RAM para reutilizar el prompt en el modelo híbrido |
| `--jinja --reasoning-format deepseek` | Plantilla del modelo (herramientas en XML) y razonamiento aparte, en `reasoning_content` |
| Opcionales | `--sin-pensar`; `--mmproj` + `--vision-en-cpu` (visión sin gastar VRAM); `--plantilla` (plantilla oficial); `--dflash`; `--sin-op-offload` (a probar) |

Todas estas opciones las he comprobado en el README actual de `llama-server`. El valor
`deepseek` de `--reasoning-format` es el habitual. Si tu versión no lo acepta, usa
`--formato-razonamiento auto`.

---

## 8. Privacidad: lo que hay, por dónde se escapa y la frontera nueva

### 8.1 Lo que ya existe en JADIS (según las sesiones)

- **Proxy de redacción de Hindsight (`:8900`).** Hermes escribe en la memoria a través de él y
  **los secretos se redactan** antes de guardarse.
- **La marca `privado` de los perfiles del router.** Excluye a los proveedores que entrenan con
  tus datos (`entrena_si`; por ejemplo los `:free` de OpenRouter). La llevan `memoria` y
  `wiki`. **No** la llevan `principal` (el cerebro), `auxiliar`, `vision` ni `subagente`.
- **Lo que no he encontrado:** la seudonimización reversible (`[USUARIO]` ↔ `Javier`). Ver la
  sección 1.

### 8.2 Mapa de salidas: qué sale hoy de tu PC

| Salida | Qué lleva | Hoy | Propuesta |
|---|---|---|---|
| Perfil `principal` (cerebro) | **Todo**: cada conversación entera | Nube gratis (incluidos `:free` que pueden entrenar) | **Local, sin caer a la nube** (D1) |
| `auxiliar` (16 tareas de Hermes: títulos, compresión del contexto…) | La conversación, para resumirla | Nube | **Local** (D4) |
| `memoria` (extracción de recuerdos de Hindsight) | La conversación | Nube "privada" (no entrena, pero la lee) | **Local** (D4) |
| `wiki` | Tus notas | Nube "privada" | **Local** (D4) |
| `vision` | Tus capturas e imágenes | Nube | **Local**: Qwen3.8 ve imágenes; las imágenes no se pueden seudonimizar (D4) |
| `subagente` | La tarea delegada | Nube | **Nube seudonimizada + contexto mínimo**; las tareas privadas, a local (D5) |
| Voz (STT/TTS de Hermes) | Tu voz | OpenAI | Valorar local (D7) |
| Búsquedas web | Lo que buscas (también delata) | Buscador | Pasar las consultas por la frontera (Fase 5) |
| Avisos al móvil (ntfy) | El texto de la tarjeta de permiso | ntfy.sh público | Servidor propio si el texto es sensible (`JADIS_NTFY_SERVIDOR`) (D8) |
| Conectores MCP (Notion, Spotify…), Discord/WhatsApp | Lo que cada uno necesite | Cada servicio | Inventario en la Fase 5 |

### 8.3 Diseño: la frontera de privacidad (en el router)

**Por qué en el router.** Hermes, Hindsight y la wiki ya llaman a los modelos **solo** a través
de él. Es la única puerta de salida de texto hacia modelos. Si se controla ahí, no hay forma de
saltársela por despiste.

1. **Marca `local` por proveedor.** Se calcula sola: un servidor en `localhost` o `127.0.0.1`
   es local. "Sin clave" **no** significa local: Kilo o LLM7 no piden clave y están en
   Internet.
2. **Marca `solo_local` por perfil.** Un perfil así nunca usa un proveedor externo. Si el local
   no responde, devuelve un error claro y el HUD lo avisa en ámbar, como el aviso de "modelo
   rebajado". No cae a la nube en silencio.
3. **Seudonimizador** (solo cuando el destino es externo):
   - **Detección, por orden de fiabilidad:**
     1. Un **diccionario personal** cifrado en el vault que ya existe: tu nombre, apellidos y
        alias, tu usuario de Windows (las rutas `C:\Users\…` lo delatan), correos, teléfonos,
        direcciones, DNI, matrícula, empresa, y nombres de familia y amigos.
     2. **Patrones españoles**: correo, teléfono, DNI/NIE con su letra de control, IBAN,
        tarjeta (Luhn), IP, coordenadas y URLs con tokens. Más los patrones de secretos que
        ya usa el proxy de redacción.
     3. Opcional: **Presidio + spaCy en español**, para nombres de terceros dentro de correos
        o documentos.
   - **Marcadores con tipo y número**, estables durante toda la sesión del subagente (el router
     ya tiene sesiones "pegajosas"): `⟦PERSONA_1⟧`, `⟦LUGAR_1⟧`, `⟦EMAIL_1⟧`…
   - **Una línea de instrucción** al modelo externo: "los marcadores ⟦…⟧ son datos protegidos:
     cópialos tal cual".
4. **Comprobación de salida (DLP, "a prueba de fallos").** Justo antes de enviar, se busca cada
   término del diccionario en el JSON final, sin distinguir mayúsculas ni acentos. **Si
   aparece alguno, no se envía:** queda registrado el incidente, sin el valor.
5. **Reversión**, en tres sitios:
   - en el texto;
   - en los **argumentos de las llamadas a herramientas** (`tool_calls`), para que tus
     herramientas reciban los datos reales;
   - en *streaming*, con un búfer pequeño hasta que se cierra cada `⟧`.
6. **Auditoría local.** Se anota qué tipos se sustituyeron, cuántos y a qué proveedor. **Nunca
   los valores.**
7. **Panel.** Una sección "Privacidad" en el widget Router con el diccionario, los contadores y
   los incidentes.

### 8.4 Tu ejemplo, de ida y vuelta

```
Tú (HUD) ──► cerebro LOCAL: "Yo Javier, necesito que me digas cómo llegar a la Moncloa"
cerebro ──► delega en un subagente (perfil subagente → proveedor EXTERNO)
router  ──► envía:   "Yo ⟦PERSONA_1⟧, necesito que me digas cómo llegar a la Moncloa"
          (comprobación: "Javier" no aparece en el JSON → se envía)
nube    ──► responde: "⟦PERSONA_1⟧, coge la línea 3 hasta Moncloa…"
router  ──► revierte: "Javier, coge la línea 3 hasta Moncloa…" ──► cerebro ──► tú
```

**El matiz importante.** Si dijeras "desde mi casa en la calle X", la dirección se convertiría
en `⟦DIRECCION_1⟧`, y **con un marcador nadie puede calcularte la ruta**. Algunas tareas
**necesitan** el dato. Para eso está la minimización (Fase 4): el cerebro decide entre tres
caminos.

- **a)** La tarea se queda en local.
- **b)** Generaliza: "desde el barrio de…", "desde la estación de…".
- **c)** Te pide permiso para mandarlo.

### 8.5 Límites honestos

- **Seudonimizar no es anonimizar.** Para el RGPD, un dato seudonimizado sigue siendo un dato
  personal. El contenido puede delatarte: hábitos, horarios, lugares. La mejor protección es
  **mandar menos**, y por eso la Fase 4 importa tanto como la 3.
- **Hay falsos negativos:** apodos, nombres raros y datos dentro de imágenes o PDF. Lo
  compensan el diccionario, la comprobación de salida y que las imágenes y documentos
  personales se procesen en local.
- **Algunos modelos "tocan" los marcadores:** los traducen o les quitan los corchetes. Se
  prueba proveedor a proveedor y la reversión tolera variaciones menores.
- **La latencia añadida** es de milisegundos con diccionario y patrones; Presidio añade
  decenas de milisegundos.

---

## 9. Arquitectura objetivo

```
                    TU PC: zona de confianza (todo en claro)
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ HUD (Tauri) ─► Backend :8400 ─► Hermes (cerebro y agente) ──┐              │
 │                                 Hindsight y wiki ───────────┤              │
 │                                                             ▼              │
 │                       Router :8420 (única salida hacia modelos)            │
 │                  perfiles solo_local │        │ perfiles externos          │
 │       (principal, auxiliar, memoria, │        │ (subagentes)               │
 │        wiki, visión)                 ▼        ▼                            │
 │                   llama-server :8080    ┌─ FRONTERA DE PRIVACIDAD ─┐       │
 │                   Qwen3.8-27B local     │ seudonimiza → comprueba  │       │
 │                   (GPU 8 GB + RAM, MTP) │ revierte ← respuesta     │       │
 │                                         └────────────┬─────────────┘       │
 └──────────────────────────────────────────────────────┼─────────────────────┘
                                                        ▼
                                     Internet: solo texto seudonimizado y mínimo
                                     (OpenRouter, NVIDIA, Groq…)
```

---

## 10. Decisiones que necesito de ti

| # | Decisión | Opciones | Mi recomendación |
|---|---|---|---|
| D1 | Si el cerebro local no está disponible… | (a) JADIS espera o avisa; (b) usa la nube seudonimizada | **(a)**, con (b) como interruptor manual |
| D2 | Origen del modelo sin censura | (a) descargar uno de terceros verificado; (b) hacerlo tú con Heretic desde los pesos oficiales | **(a) para empezar**, con el checklist; **(b)** cuando lo demás funcione |
| D3 | Cuantización de partida | GSQ-RCO IQ3_S / IQ3_XXS / IQ4_XS | **IQ3_S-mtp**; IQ3_XXS si la Fase 0 va justa |
| D4 | Qué perfiles pasan a local | principal / +auxiliar / +memoria / +wiki / +visión | **Todos esos cinco**. Coste: comparten una única cola (el cerebro tiene prioridad) |
| D5 | Subagentes | externos seudonimizados / todo local | **Externos seudonimizados por defecto + contexto mínimo; las tareas con datos privados, a local** |
| D6 | Pensar | siempre / nunca / por tarea | **Apagado en conversación, encendido por tarea** |
| D7 | Voz (STT/TTS por OpenAI) | seguir / local | Decides tú. Si hablas mucho con JADIS, es la mayor fuga después del cerebro |
| D8 | Avisos al móvil | ntfy.sh / servidor propio | ntfy.sh vale si las tarjetas no llevan datos sensibles |
| D9 | Hardware | nada / RAM / GPU 16 GB / GPU 24 GB | Primero mide (Fase 0). Ampliar la RAM solo si tienes menos de 32 GB |
| D10 | Cuando uses la GPU para otra cosa (juegos…) | JADIS se pausa / usa la nube seudonimizada / se queda en CPU (muy lento) | Pausa con aviso + botón en el HUD |

**Datos que me faltan:**

1. RAM: GB, tipo y velocidad.
2. CPU exacta.
3. Espacio libre en disco: cada modelo ocupa 10-16 GB.
4. El enlace del motor dedicado que viste.
5. Si se puede, el tamaño real del prompt de sistema de Hermes. La Fase 0 lo mide con él si
   lo exportas a un archivo, que se queda en tu PC.

---

## 11. Plan por fases

Las fases 0 y 1 no tocan JADIS. Las 2-5 se hacen en una sesión de Claude Code **en tu PC**,
sobre `C:\J.A.D.I.S`: esta sesión en la nube no tiene acceso a ese código.

### Fase 0 — Medir en tu PC (sin tocar JADIS) · ~1-2 h

1. **Datos del equipo** y el ajuste **Sysmem Fallback** de NVIDIA (`fase0/README.md` trae los
   comandos).
2. **Instalar llama.cpp** desde la compilación oficial de Windows con CUDA.
3. **Descargar el modelo de referencia:** el modelo base de Qwen (con censura), cuantizado por
   ISTA-DASLab: `Qwen3.8-27B-GSQ-RCO-GGUF`, variante IQ3_S con MTP. Anota su SHA256.
4. **Arrancar** con `python fase0/arrancar_cerebro.py …`.
5. **Medir** con `python fase0/bench_cerebro.py --salida informe.json`, mejor con el prompt
   real de Hermes (`--sistema`).
6. **Variantes:** `--sin-mtp`, `--borrador-n 3`, `--sin-op-offload`, IQ3_XXS e IQ4_XS.

**Criterios de aceptación:**

- (a) ≥8 tok/s con MTP y sin pensar;
- (b) los turnos 2+ reutilizan ≥80 % del prompt;
- (c) el primer turno con el prompt grande tarda ≤60 s;
- (d) la llamada a la herramienta sale bien formada;
- (e) no hay "memoria compartida de GPU" en el Administrador de tareas.

**Si falla (b), es bloqueante:** se investiga la caché híbrida antes de seguir.

### Fase 1 — Elegir la versión sin censura · ~1 tarde

- **Opción A, descargar.** Candidatas de la tabla 5.7 que conserven el MTP. Checklist:
  1. Solo `.gguf`, con el SHA256 anotado.
  2. Plantilla de chat **oficial** (`--plantilla`).
  3. Aceptación del MTP en el kit parecida a la del oficial (≥0,6).
  4. A/B contra el oficial con la misma cuantización: 30-50 peticiones tuyas reales más la
     prueba de herramientas. Hay que mirar si decide distinto, no solo si responde.
  5. 10-20 peticiones que el oficial rechaza y tú quieres que conteste.
- **Opción B, hacerlo tú.**
  1. Heretic (`bnb_4bit`) sobre `Qwen/Qwen3.8-27B`, en una GPU alquilada.
  2. **Restaurar el cabezal MTP original**.
  3. `convert_hf_to_gguf.py`.
  4. Cuantizar.

  Es reproducible y no depende de nadie.
- **Entregable:** el GGUF elegido, su hash y el informe del A/B.

### Fase 2 — Integrar el cerebro local en JADIS · ~1-2 días

- **Supervisor (`supervisor.rs`).** La pieza nueva "Cerebro local" arranca y para
  `llama-server`, igual que hoy se asegura Ollama. Además, el "modo GPU ocupada" (D10).
- **Router:**
  - el proveedor `local-llamacpp` (compatible con OpenAI, sin clave; el router ya trata como
    gratis a un servidor local sin clave);
  - las marcas `local` y `solo_local`;
  - el nivel fijado a mano;
  - el fallo claro, sin caer a la nube;
  - una **cola con prioridad**: principal > auxiliar > memoria/wiki.
- **Perfiles según D4.** En Hermes: contexto de 64K y pensar según D6.
- **Ollama:** resolver el conflicto de VRAM del respaldo `gemma4:12b`.
- **Prompt de Hermes estable por el principio:** la caché depende de ello.
- **Pruebas** (router y backend) y prueba real en el HUD.
- **Criterio:** una conversación con herramientas en el HUD y **ninguna** petición de los
  perfiles `solo_local` fuera del PC, verificado en el registro del router.

### Fase 3 — Frontera de privacidad en el router · ~2-4 días

- **El módulo `privacidad`,** con todo lo de 8.3: diccionario en el vault, patrones españoles,
  Presidio opcional, marcadores, DLP, reversión (texto, `tool_calls` y streaming), auditoría y
  la sección en el panel.
- **Pruebas:**
  - ida y vuelta exacta;
  - **canarios** (un dato falso en el diccionario que nunca debe salir);
  - marcadores partidos en streaming;
  - argumentos de herramientas;
  - falsos positivos ("Moncloa" no es una persona);
  - un modelo externo que "toca" los marcadores.
- **Criterios:**
  - 0 apariciones del diccionario en un corpus de 200 mensajes de prueba;
  - reversión exacta;
  - menos de 50 ms añadidos por petición sin Presidio.

### Fase 4 — Mandar menos: minimización en la orquestación

Encaja con la "fase 2" ya aprobada del router: la herramienta de orquestación propia, con nivel
por tarea. Cada subtarea lleva:

- **nivel;**
- **clase de privacidad** (`local` / `externo-seudonimizado` / `externo-sin-datos`);
- **contexto mínimo**, no la conversación entera.

Por defecto, `externo-seudonimizado`. Si la tarea necesita un dato en claro, va a `local` o te
pide permiso.

### Fase 5 — El resto de salidas

Decidir sobre la voz (D7), las búsquedas web (pasar las consultas por la frontera), ntfy (D8),
los conectores MCP y Discord/WhatsApp, con un inventario de qué manda cada uno.

### Fase 6 — Optimizar y, si quieres, hardware (opcional)

- **Pruebas en el motor:**
  - DFlash 2 frente a MTP en 8 GB;
  - `-ot` (qué tensores van a la GPU);
  - el monitor en la gráfica integrada;
  - ik_llama.cpp.
- **Hardware:**
  - si tienes **<32 GB de RAM**, ampliarla es imprescindible;
  - con una **GPU de 16 GB**, la referencia es ~40 tok/s;
  - con una de **24 GB**, ~53-76 tok/s, y NInfer o Lucebox pasan a ser opciones reales.

  Los precios cambian mucho: los comprobamos cuando toque.

---

## 12. Riesgos y cómo se mitigan

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| La caché del modelo híbrido falla y cada turno relee todo | Media | **Alto** | Fase 0 bloqueante; prompt que solo crece por el final; `--ctx-checkpoints` |
| Demasiado lento para hablar con él | Media | Alto | IQ3_S/IQ3_XXS + MTP; pensar apagado; voz por frases; plan B con hardware |
| El modelo sin censura decide peor o distinto | Media | Medio | A/B en la Fase 1; conservar el oficial para volver atrás en un minuto |
| Más obediente = más vulnerable a instrucciones inyectadas (webs, correos) | Alta | **Alto** | Toda herramienta peligrosa detrás de ApprovalGate ("sin respuesta = no"); el contenido externo se trata como dato, no como orden; revisar que no quede ninguna herramienta sin tarjeta |
| Plantilla o archivo de terceros envenenado | Baja | Alto | Plantilla oficial, solo `.gguf` y hash anotado; la opción B quita la dependencia de terceros |
| Fugas por falsos negativos del seudonimizador | Media | Medio | Diccionario + DLP de salida + minimización + imágenes y documentos en local |
| Conflicto de VRAM con juegos o con Ollama | Alta | Medio | Modo GPU ocupada; decidir el respaldo de gemma |
| Drivers de NVIDIA (en sep-2026 ya hubo cuelgues) | Media | Medio | Fijar una versión que funcione; ajuste Sysmem Fallback |

---

## 13. Suposiciones explícitas

- **S1.** La RTX 4060 es de sobremesa: 8 GB, 272 GB/s, PCIe 4.0 x8. Si fuera de portátil
  cambia poco, porque el cuello de botella es la RAM.
- **S2.** La CPU es AMD con gráfica integrada. "AMD Radeon(TM) Graphics" aparece tanto en los
  Ryzen de AM5 (DDR5) como en las APU de AM4 (DDR4). **Sin confirmar:** por eso doy las dos
  columnas.
- **S3.** RAM ≥ 32 GB. **Sin confirmar.** Con 16 GB el plan se reduce a IQ3_XXS o menos.
- **S4.** Windows con Hermes nativo y Docker Desktop para Hindsight, según las sesiones.
- **S5.** Hermes necesita ≥64K de contexto (fuente secundaria).
- **S6.** Las velocidades de terceros son de otros equipos. Las mías son estimaciones con
  ±30 %.
- **S7.** Lo de Hugging Face sale del buscador y de webs secundarias. Hay que comprobar cada
  ficha antes de descargar.
- **S8.** No he leído el código de JADIS ni el ESTADO.md entero: están en tu PC.

---

## 14. Fuentes

**Modelo**

- Qwen3.8 (repo oficial): <https://github.com/QwenLM/Qwen3.8>
- Ficha en Hugging Face (no verificable desde aquí): <https://huggingface.co/Qwen/Qwen3.8-27B>
- Artificial Analysis, Qwen3.8-27B vs Qwen3.6-35B-A3B:
  <https://artificialanalysis.ai/models/comparisons/qwen3-8-27b-vs-qwen3-6-35b-a3b>

**Motor y aceleración**

- `llama-server`, opciones y `timings`:
  <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- MTP en llama.cpp (integrado el 16-may-2026): <https://github.com/ggml-org/llama.cpp/pull/22673>
- DFlash 2 en llama.cpp (integrado el 27-ago-2026): <https://github.com/ggml-org/llama.cpp/pull/27342>
- Mediciones de MTP por GPU, incluida la de 8 GB: <https://github.com/sudoingX/qwen38-mtp>
- DFlash 2 vs MTP y techo de ancho de banda: <https://github.com/hanxiao/Qwen3.8-27B-UD-Q4_K_XL-L4>
- Caché en modelos híbridos: <https://github.com/ggml-org/llama.cpp/issues/19794>
- Hermes + Ollama limitado a 4.096 tokens: <https://github.com/NousResearch/hermes-agent/issues/43900>
- Sysmem Fallback de NVIDIA:
  <https://runaihome.com/blog/shared-gpu-memory-slow-local-ai-sysmem-fallback-fix-2026/>
- RTX 4060 de 8 GB con Qwen3.8-27B, fuente secundaria:
  <https://x.com/xueyu1125/status/2089597987169476760>

**Carga por capas y motores dedicados**

- AirLLM: <https://github.com/lyogavin/airllm>
- Análisis de su velocidad: <https://runaihome.com/blog/airllm-70b-4gb-vram-inference-guide-2026/>
- NInfer-4090: <https://github.com/UDPSendToFailed/ninfer-4090>
- NInfer 16 GB:
  <https://github.com/Ryan-gsq/ninfer-16g-5070ti-5080-5090-qwen3.8-27b-gsq-rco>
- vinf: <https://github.com/andrem-eberle/vinf-3080ti>
- Lucebox: <https://github.com/Luce-Org/lucebox-hub>
- qengine: <https://github.com/Haru-neo/qengine>
- Qwen3.8-27B-in-C: <https://github.com/Julien-Bui/Qwen3.8-27B-in-C>
- Tema `qwen3-8-27b` en GitHub: <https://github.com/topics/qwen3-8-27b>

**Cuantizaciones**

- GSQ-RCO de ISTA-DASLab: <https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF>
- Unsloth Qwen3.8: <https://unsloth.ai/docs/models/qwen3.8>

**Sin censura y riesgos**

- Heretic: <https://github.com/p-e-w/heretic>
- MTP roto en huihui-ai:
  <https://huggingface.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF/discussions/4>
- "Abliteration Is Not a Scalpel": <https://arxiv.org/abs/2607.17427>
- Plantillas GGUF envenenadas (Pillar Security):
  - <https://www.pillar.security/blog/llm-backdoors-at-the-inference-level-the-threat-of-poisoned-templates>
  - <https://www.pillar.security/blog/from-discovery-to-large-scale-validation-chat-template-backdoors-across-18-models-and-4-engines>

**Privacidad**

- Microsoft Presidio: <https://github.com/microsoft/presidio>
- LLM Guard (archivado): <https://github.com/protectai/llm-guard>
- Política de datos de los modelos gratis de OpenRouter:
  <https://openrouter.ai/blog/tutorials/free-llm-apis-compared/>
