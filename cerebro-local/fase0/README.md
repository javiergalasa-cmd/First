# Fase 0: medir el cerebro local en tu PC (sin tocar JADIS)

**Objetivo:** saber, con números de **tu** equipo, si Qwen3.8-27B sirve como cerebro de JADIS
antes de cambiar nada. Tiempo: ~1-2 h, casi todo de descargas.

Contenido de esta carpeta:

| Archivo | Para qué |
|---|---|
| `arrancar_cerebro.py` | Lanza `llama-server` con la configuración del plan (PLAN.md §7) |
| `bench_cerebro.py` | Mide velocidad, primer turno, caché entre turnos, herramientas y pensar |
| `tests/` | Pruebas de los dos scripts contra un `llama-server` simulado (`python -m unittest discover -s tests`) |

Los dos scripts usan **solo la biblioteca estándar de Python** (3.9+) y **no hablan con
Internet**: el banco solo llama a la URL local que le des.

---

## 1. Datos de tu equipo (PowerShell)

```powershell
# RAM: capacidad por módulo, velocidad y tipo (SMBIOSMemoryType 26 = DDR4, 34 = DDR5)
Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, ConfiguredClockSpeed, SMBIOSMemoryType

# CPU
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

# GPU, VRAM y bus PCIe
nvidia-smi --query-gpu=name,memory.total,pcie.link.gen.max,pcie.link.width.max --format=csv

# Espacio libre en disco (cada modelo ocupa 10-16 GB)
Get-PSDrive -PSProvider FileSystem
```

Pásame lo que salga: sirve para ajustar las estimaciones de PLAN.md §4.

## 2. Ajuste de NVIDIA (evita que vaya lento a escondidas)

*Panel de control de NVIDIA → Administrar configuración 3D → Configuración de programa →*
añade `llama-server.exe` → **CUDA - Sysmem Fallback Policy = Prefer No Sysmem Fallback**.

Así, si la VRAM se llena, `llama-server` da un error en vez de usar RAM "compartida" y
hundirse. Hazlo solo para ese programa, no en la configuración global, para no afectar a los
juegos.

## 3. Instalar llama.cpp (compilación oficial para Windows con CUDA)

1. Entra en <https://github.com/ggml-org/llama.cpp/releases> (la última).
2. Descarga el zip `llama-…-bin-win-cuda-…-x64.zip` y el `cudart-llama-bin-win-cuda-…-x64.zip`
   de la **misma** versión de CUDA. El nombre exacto cambia con cada versión.
3. Descomprime los dos en la misma carpeta, por ejemplo `C:\llama\`.
4. Comprueba que tu versión tiene MTP:
   `C:\llama\llama-server.exe --help | Select-String "draft-mtp"`. Tiene que aparecer.

## 4. Descargar el modelo de referencia (el oficial, todavía con censura)

- Repo: **`ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`** en Hugging Face.
- Archivo: la variante **IQ3_S** que lleve **`mtp`** en el nombre (~12 GB). Descárgala desde
  la pestaña *Files* del navegador, o con `hf download <repo> <archivo> --local-dir D:\modelos`.
- Antes de descargar, comprueba en la ficha que de verdad es de ISTA-DASLab y que el archivo
  lleva el cabezal MTP.
- Anota el hash, para saber siempre qué archivo usaste:

  ```powershell
  Get-FileHash D:\modelos\<archivo>.gguf -Algorithm SHA256
  ```

  Compáralo con el SHA256 que muestra Hugging Face junto al archivo.

Empezamos por el oficial a propósito. Es la referencia con la que se compara después cada
versión sin censura (Fase 1).

## 5. Arrancar

```powershell
python arrancar_cerebro.py --llama-server C:\llama\llama-server.exe --modelo D:\modelos\<archivo>.gguf
```

- Para ver el comando sin ejecutarlo: añade `--solo-mostrar`.
- La primera carga tarda un poco: lee ~12 GB del disco.
- Deja esa ventana abierta.
- Para pararlo: `Ctrl+C`.

Mientras corre, mira el *Administrador de tareas → Rendimiento → GPU*. La **"Memoria de GPU
compartida"** no debería subir. Si sube, sube `--fit-target` (por ejemplo a 1536).

## 6. Medir (en otra ventana)

```powershell
python bench_cerebro.py --salida informe-iq3s-mtp.json
```

**Si puedes, usa el prompt de sistema REAL de Hermes.** Pide a la sesión de JADIS en tu PC que
lo vuelque a un archivo; se queda en tu PC. Luego:

```powershell
python bench_cerebro.py --sistema D:\pruebas\prompt_hermes.txt --salida informe-hermes.json
```

El banco hace, sin pensar y pensando:

1. **3 turnos de conversación** con un prompt de sistema grande. Mide cuánto tarda en leerlo,
   a cuántos tok/s genera y **si reutiliza la caché** en los turnos 2 y 3.
2. **Una llamada a herramienta.** Comprueba que pide `obtener_tiempo` con `{"ciudad": "Madrid"}`
   bien formado.

Al final imprime los **criterios de la Fase 0** con `[OK]` / `[NO]`.

**Aceptación del MTP.** Si el servidor la incluye en `timings`, el informe muestra
"MTP acepta X/Y". Si no sale, búscala en la ventana de `llama-server`: al terminar cada
petición con especulativa imprime una línea de *acceptance*. Sirve para comparar versiones en
la Fase 1, porque un MTP roto da ~0.

## 7. Variantes que conviene medir (una cada vez)

| Prueba | Cómo |
|---|---|
| Sin MTP (para ver cuánto aporta) | `arrancar_cerebro.py … --sin-mtp` |
| Borrador de 3 tokens | `… --borrador-n 3` |
| Sin subir capas al leer el prompt | `… --sin-op-offload` |
| Más pequeño y más rápido | el archivo IQ3_XXS-mtp del mismo repo |
| Cuantización clásica | Unsloth IQ4_XS (15,7 GB) |

Guarda cada informe con un nombre distinto y pásamelos: con eso se decide la D3 del plan.

## Criterios de aceptación (PLAN.md §11, Fase 0)

- (a) **≥ 8 tok/s** generando, con MTP y sin pensar.
- (b) Turnos 2+ que **reutilizan ≥ 80 %** del prompt. **Si falla, es bloqueante:** antes de
  integrar nada hay que resolver la caché del modelo híbrido.
- (c) Primer turno con el prompt grande en **≤ 60 s**.
- (d) Llamada a herramienta **bien formada**.
- (e) Sin "memoria de GPU compartida".

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| `llama-server` no arranca: "unknown argument" | Tu versión es más vieja que lo que pide el plan. Descarga la última release; o quita la opción con `--sin-mtp` / `--formato-razonamiento auto` |
| Error de memoria (OOM) al cargar | Sube `--fit-target` o baja `--contexto 32768` (solo para medir: Hermes necesita 64K) |
| Va muy lento y sube la memoria compartida | Revisa el paso 2 (Sysmem Fallback) y cierra lo que use la GPU (navegador, juegos) |
| `cache FALLO` en los turnos 2+ | Apunta el resultado y no sigas a la Fase 2: es el riesgo nº 1 del plan |
| Herramienta `FALLO` | Prueba la plantilla oficial con `--plantilla <archivo.jinja>` y repite |
