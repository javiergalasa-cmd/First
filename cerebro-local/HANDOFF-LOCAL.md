# Handoff: cerebro local de JADIS (de la sesión en la nube a Claude Code en el PC)

> **Para la sesión de Claude Code que siga esto en `C:\J.A.D.I.S`.** Lee esto primero. Resume
> lo hecho del 5 al 9 de octubre de 2026 en una sesión en la nube (repo público `First`, rama
> `claude/magical-darwin-gcbo0m`). Javier quiere que todo siga **en local**.

## 1. Reglas de Javier que no se negocian

- **Precisión antes que rapidez.** Declarar las suposiciones, verificar los hechos y decir "no lo
  sé" cuando no se sepa.
- **Datos sensibles:** si se ven contraseñas, claves o datos personales, no se guardan, no se
  copian y no se mandan a ningún sitio.
- **Lo personal, solo JADIS; lo de fuera, los subagentes** (D5). Los correos, la memoria y la
  agenda nunca salen del PC.
- **Antes de usar la nube, preguntar:** si el cerebro local no responde, se pregunta a la vez en
  el PC (tarjeta de JADIS) y en el móvil (ntfy). Vale la primera respuesta. Sin respuesta = no (D1).

## 2. Qué se ha decidido, con medidas en este PC

PC: RTX 4060 de 8 GB, Ryzen 5 7600X, 32 GB de DDR5-5600 en **un solo módulo**, funcionando a 4800
(D.O.C.P. sin activar: pendiente de Javier). Placa ASUS TUF GAMING A620M-PLUS.

| Decisión | Valor | Por qué (medido) |
|---|---|---|
| **Modelo del cerebro** | **Qwen3.6-35B-A3B sin censura**, Heretic de llmfan46, cuantización `i1-IQ3_S` de mradermacher (14,2 GB). Está en `C:\jadis-cerebro\modelos\` | 32-35 tok/s y turnos de 1-2 s. Qwen3.8-27B (más listo) daba 2,4-3,1 tok/s y 13-25 s por turno con la RAM de un canal |
| **Motor** | llama.cpp `b11457` CUDA 12.4, en `C:\jadis-cerebro\llama.cpp\b11457-cuda-12.4\` (panel NVIDIA: "Prefer No Sysmem Fallback" para ese exe) | — |
| **Arranque** | `--sin-mtp --sin-mmap --ubatch 2048 --fit-target 512` (con `fase0/arrancar_cerebro.py`) | Sin mmap: lee el prompt un +46 %. Bloques de 2048: +84 %. MTP y DFlash no aceleran en este PC |
| **Pensar** | **Nunca.** En su lugar, el **bucle de revisión** (`fase1/bucle.py`) | Pensar: delegar 29 s de media, sin mejorar la calidad. Bucle: delegar 4,4 s y lo personal 2,1 s |
| **Personalidad** | `SOUL-JADIS.md` (texto literal): JARVIS en español de España, de usted, "señor", ironía seca y breve | Elegido por Javier el 9-oct |
| **Cuando llegue la RTX 5070 (16 GB)** | Volver a Qwen3.8-27B sin censura, entero en la GPU | Estimado: ~35-45 tok/s con más inteligencia (34 frente a 18 pensando en Artificial Analysis) |

Datos: `PLAN.md`, sección 4.0 y 4.0.1.

## 3. Calidad: batería de la Fase 1 (`fase1/calidad.py`)

23 casos con datos inventados, 3 repeticiones, último resultado con `--bucle`: **57/69**.

| Grupo | OK | Tiempo medio |
|---|---|---|
| charla | 12/15 | 1,3 s |
| delegar | 13/18 | 4,4 s |
| personal | 11/12 | 2,1 s |
| paso directo | 2/3 | 4,7 s |
| inyección | 6/6 | 2,1 s |
| sin censura | 10/12 | 2,5 s |

**Lo que queda por arreglar:**

1. **`correo-marta`:** sigue llamando a `enviar_correo` aunque Javier dijo "no lo envíes" (2 de 3
   veces, incluso tras 3 rondas). **Solución en código, no en prompt:** si `bucle.revisar` detecta
   una herramienta prohibida, JADIS no la ejecuta nunca (además de la tarjeta de permiso).
2. **Paso directo:** cuando un subagente entrega directamente a Javier, el código de JADIS cierra
   el turno **sin volver a llamar al cerebro** (ENCARGO, sección 3).
3. **Los fallos "breve"** son de topes de palabras estrictos en la batería; son menores.

## 4. Lo siguiente que pidió Javier: un mini equipo para tareas

Javier (9-oct): *"No es para proyectos, sino tareas. Un espacio con instrucciones para que funcione
como un mini equipo: JADIS entiende, un agente planifica y elige qué agentes orquestar y en qué
orden, y luego un arquitecto revisa el trabajo. Simple y rápido."*

Es distinto de **JADIS Office** (proyectos grandes; sesión "JADIS Phase 0 audit y setup"). Diseño
de partida que propongo, a validar con Javier:

1. **Entender (JADIS, local, sin pensar).**
   - Convierte la petición en un objetivo y un criterio de "hecho".
   - Separa lo personal, que se queda en local, de lo de fuera.
2. **Planificar (un agente planificador).**
   - Devuelve un plan corto en JSON: pasos, qué agente hace cada uno (de un catálogo fijo:
     buscador, redactor, programador, calculador…), el orden y qué pasos pueden ir en paralelo.
   - Tope: unos 5 pasos.
3. **Ejecutar.** Cada paso es una llamada rápida (`delegar` a la nube sin datos, o una
   herramienta local).
4. **Revisar ("arquitecto").**
   - Comprueba el resultado contra el criterio de "hecho".
   - Si falla, dice qué paso repetir y por qué. Máximo 2 vueltas.
   - Combina reglas de código (como `bucle.py`) con el juicio del revisor.

**Preguntas abiertas para Javier:**

- ¿El planificador y el revisor corren en local (rápidos, privados) o en la nube (más listos)?
- ¿Cuántas vueltas como máximo?
- ¿Qué catálogo de agentes?

## 5. Lo que sigue después (plan por fases, `PLAN.md` sección 11)

- **Fase 2:** integrar el cerebro en JADIS.
  - Proveedor `local-llamacpp` en el router.
  - Supervisor que arranca `llama-server`.
  - Prompt precalentado al arrancar, porque el primer turno lee unos 12.500 tokens (~15-30 s).
  - Perfiles.
  - D1 en el PC y el móvil.
  - Vigilar la RAM libre: sin mmap, el modelo deja ~9-10 GB fijos en la RAM.
- **Fase 3:** frontera de privacidad en el router (seudonimización, DLP, candado de procedencia).
- **Fase 4:** el cerebro dirige, según `ENCARGO-papel-del-cerebro.md` (herramienta `delegar`, paso
  directo, lectura de lo personal en dos pasos, bucle de revisión).

## 6. Archivos (esta carpeta)

| Archivo | Qué es |
|---|---|
| `PLAN.md` | Plan completo: investigación, medidas, decisiones (sección 10) y fases |
| `ENCARGO-papel-del-cerebro.md` | Qué construir en JADIS para el papel del cerebro (Fase 4) |
| `SOUL-JADIS.md` | El texto literal del cerebro (lo usan la batería y JADIS) |
| `ESTILO-JADIS.md` | Por qué habla así (JARVIS, brevedad) |
| `ESTADO-entrada.md` | Texto para añadir a `docs/ESTADO.md` de JADIS |
| `fase0/` | Inventario, descargas, pruebas de velocidad (`fase0.py`, `--exprimir`) y arranque (`arrancar_cerebro.py`). 64 pruebas |
| `fase1/` | Batería de calidad (`calidad.py`) y bucle de revisión (`bucle.py`). 24 pruebas |

**Pruebas:**

- En `fase0`: `python -m unittest discover -s tests`
- En `fase1`: lo mismo.

**Lanzar la batería** (con JADIS, Docker y WSL cerrados): `python fase1\calidad.py --repeticiones 3 --bucle`.

## 7. Pendiente de Javier

- **D.O.C.P. en la BIOS** (~+10 % de velocidad).
- **Decidir qué hacer con el repo público `First`:** hacerlo privado o borrar la rama de la nube.
- **¿Segundo módulo de RAM?** Doble canal y Q4.
- **Las preguntas del mini equipo** (sección 4).
