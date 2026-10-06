# Fase 0: medir el cerebro local en tu PC (sin tocar JADIS)

**Objetivo:** saber, con números de **tu** equipo, a qué velocidad va Qwen3.8-27B y si sirve
como cerebro de JADIS. Así las decisiones de PLAN.md se toman con datos y no con
estimaciones.

**Lo que no hace:**
- no toca JADIS;
- no cambia la configuración del sistema;
- no instala nada en Windows: todo queda en una carpeta (`C:\jadis-cerebro`) que se puede
  borrar entera al terminar.

| Archivo | Para qué |
|---|---|
| `fase0.py` | **Todo en un comando:** mira el equipo, descarga (preguntando antes), prueba y deja el informe |
| `arrancar_cerebro.py` | Lanza `llama-server` con la configuración del plan (PLAN.md §7); también sirve suelto |
| `bench_cerebro.py` | Mide la velocidad, el primer turno, la caché entre turnos, las herramientas y el pensar; también sirve suelto |
| `tests/` | 49 pruebas de los tres scripts con un `llama-server` simulado (`python -m unittest discover -s tests`) |

Los scripts solo usan la **biblioteca estándar de Python** (3.9 o superior). Solo se conectan
a Internet para descargar:
- `github.com`: la versión oficial de llama.cpp;
- `huggingface.co`: el modelo.

Las pruebas hablan únicamente con `127.0.0.1`.

---

## Antes de empezar (5 minutos)

1. **Cierra lo que use la GPU:** JADIS, Ollama, juegos y el navegador si tiene muchas pestañas.
   El script avisa si encuentra a Ollama o JADIS abiertos, o la VRAM ocupada.
2. **Ajuste de NVIDIA** (evita que vaya lento sin avisar): *Panel de control de NVIDIA →
   Administrar configuración 3D → Configuración de programa*.
   - Añade `llama-server.exe` cuando lo hayas descargado; lo encontrarás en
     `C:\jadis-cerebro\llama.cpp\...`.
   - Pon **CUDA - Sysmem Fallback Policy = Prefer No Sysmem Fallback**.
   - Hazlo solo para ese programa, no en la configuración global.
   - Si te lo saltas, el informe lo deja ver igualmente, pero las medidas pueden salir peores.
3. **Comprueba que tienes Python:** `python --version` debe dar 3.9 o más.
4. **Espacio:** ~25 GB libres. Los dos modelos de prueba ocupan 21 GB; llama.cpp, menos de 1 GB.

## Opción A: un solo comando (recomendada)

En PowerShell:

```powershell
git clone -b claude/magical-darwin-gcbo0m https://github.com/javiergalasa-cmd/First C:\jadis-cerebro\kit
cd C:\jadis-cerebro\kit\cerebro-local\fase0

python fase0.py --solo-inventario   # ~10 s, no descarga nada
python fase0.py                     # todo; antes de descargar enseña qué y cuánto, y pregunta
```

Si no quieres usar git, descarga el zip de la rama, descomprímelo y entra en
`cerebro-local\fase0`:
<https://github.com/javiergalasa-cmd/First/archive/refs/heads/claude/magical-darwin-gcbo0m.zip>

**Qué hace `python fase0.py`:**

1. **Inventario.** Mira la GPU y la VRAM, la CPU y la RAM: GB, **DDR4 o DDR5**, velocidad,
   **cuántos módulos y si va en uno o dos canales**. También el disco y si hay programas que
   estorben.

   Avisa también si tu RAM **va más lenta de lo que pone en el módulo**. Pasa mucho: falta
   activar el perfil XMP/EXPO, que en placas ASUS se llama DOCP, en la BIOS. Activarlo es gratis
   y acelera la parte del modelo que va en la CPU.
2. **Descarga, preguntando antes:**
   - la última compilación oficial de llama.cpp para Windows con CUDA, eligiendo la versión de
     CUDA que admite tu driver;
   - Qwen3.8-27B GSQ-RCO de ISTA-DASLab en dos tamaños, los dos **con cabezal MTP**: **IQ3_S**
     (11,8 GB) e **IQ2_S** (9,3 GB).

   Comprueba el SHA256 de cada archivo contra el que publica Hugging Face. Si se corta,
   **vuelve a lanzar el mismo comando y reanuda** donde se quedó.
3. **Pruebas.** Cada modelo se prueba **con MTP** (sin pensar y pensando) y **sin MTP**, para
   saber cuánto aporta. Cada prueba arranca `llama-server`, espera a que cargue, ejecuta el banco
   y lo para.
4. **Informe.** Deja `C:\jadis-cerebro\informe-fase0.md` (y `.json`). **Pásamelo.** No lleva:
   - el nombre del equipo;
   - el usuario;
   - rutas;
   - números de serie.

**Duración:** la descarga depende de tu conexión (21 GB: ~10 min a 300 Mb/s). Las pruebas
tardan ~1-1,5 h. Puedes dejarlo trabajando; mientras tanto, mejor no usar la GPU.

**Variantes útiles:**

| Quiero… | Comando |
|---|---|
| Solo el de 3,5 bits (12 GB) | `python fase0.py --variantes iq3_s` |
| Una prueba rápida (2 turnos, sin pensar) | `python fase0.py --rapido` |
| Usar el prompt real de Hermes | `python fase0.py --sistema D:\pruebas\prompt_hermes.txt` |
| Probar también 3 tokens de borrador | `python fase0.py --configs mtp2,mtp3,sin-mtp` |
| Otra carpeta u otro disco | `python fase0.py --carpeta D:\jadis-cerebro` |
| Ya tengo llama.cpp y el modelo | `python fase0.py --sin-descargas --llama-server C:\llama\llama-server.exe --modelo D:\m.gguf` |
| Sin preguntar (lo lanza otro programa) | añade `--si` |

## Opción B: paso a paso, a mano

Si prefieres hacerlo tú, o algo falla en la opción A:

1. **llama.cpp.** Entra en <https://github.com/ggml-org/llama.cpp/releases> y descarga de la
   **misma** versión de CUDA:
   - el zip `llama-…-bin-win-cuda-…-x64.zip`;
   - el zip `cudart-llama-bin-win-cuda-…-x64.zip`.

   Descomprime los dos en `C:\llama\`. Comprueba que tiene MTP: en
   `C:\llama\llama-server.exe --help | Select-String "draft-mtp"` tiene que salir algo.
2. **Modelo.** Repo `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`: el archivo IQ3_S que lleve `mtp` en
   el nombre. Anota su hash con `Get-FileHash <archivo> -Algorithm SHA256`.
3. **Arrancar:**
   `python arrancar_cerebro.py --llama-server C:\llama\llama-server.exe --modelo D:\modelos\<archivo>.gguf`
   (con `--solo-mostrar` enseña el comando sin ejecutarlo).
4. **Medir, en otra ventana:** `python bench_cerebro.py --salida informe.json`.

## Qué se mide y cuándo se da por buena la Fase 0

| Criterio | Umbral | Por qué |
|---|---|---|
| (a) Velocidad al generar, con MTP y sin pensar | ≥ 8 tok/s | Por debajo, una respuesta con herramientas se hace larga |
| (b) Caché de prompt entre turnos | reutiliza ≥ 80 % | **Bloqueante**: si falla, cada turno relee todo el prompt (25-50 s) |
| (c) Primer turno con el prompt grande | ≤ 60 s | Es lo que tarda en "leerse" a Hermes al empezar |
| (d) Llamada a herramienta | bien formada | El cerebro de un agente vive de esto |
| (e) Memoria de GPU compartida | sin desbordar | Si la VRAM se desborda a la RAM, todo va a la mitad |

**Aceptación del MTP.** Si el servidor la incluye en `timings`, el banco muestra "MTP acepta
X/Y". Si no, `fase0.py` la lee del registro de `llama-server`. Un MTP roto da ~0, y eso es lo que
habrá que vigilar con los modelos sin censura de la Fase 1.

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| "unknown argument" al arrancar | Tu `llama-server` es más viejo que lo que pide el plan: deja que `fase0.py` baje el último, o quita la opción (`--sin-mtp`, `--formato-razonamiento auto`) |
| Error de memoria (out of memory) al cargar | Sube el margen (`arrancar_cerebro.py --fit-target 1536`) o cierra lo que use la GPU |
| Va muy lento y sube la "memoria de GPU compartida" | Revisa el ajuste de NVIDIA del paso 2 y cierra el navegador o los juegos |
| `cache FALLO` en los turnos 2+ | Apunta el resultado y no sigas a la Fase 2: es el riesgo nº 1 del plan |
| Herramienta `FALLO` | Prueba la plantilla oficial con `arrancar_cerebro.py --plantilla <archivo.jinja>` |
| La descarga se corta | Vuelve a lanzar el mismo comando: reanuda y comprueba el SHA256 al acabar |
| "pide iniciar sesión o aceptar condiciones" | El repo de Hugging Face es privado o restringido: avísame y busco otro |
