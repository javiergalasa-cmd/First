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
| `tests/` | 58 pruebas de los tres scripts con un `llama-server` simulado (`python -m unittest discover -s tests`) |

Los scripts solo usan la **biblioteca estándar de Python** (3.9 o superior). Solo se conectan
a Internet para descargar:
- `github.com`: la versión oficial de llama.cpp;
- `huggingface.co`: el modelo.

Las pruebas hablan únicamente con `127.0.0.1`.

---

## Antes de empezar (5 minutos)

1. **Cierra lo que use la GPU:** JADIS, Ollama, juegos y el navegador si tiene muchas pestañas.
   El script avisa si encuentra a Ollama o JADIS abiertos, o la VRAM ocupada.
2. **Comprueba que tienes Python:** `python --version` debe dar 3.9 o más.
3. **Espacio:** ~25 GB libres. Los dos modelos de prueba ocupan 21 GB; llama.cpp, menos de 1 GB.

El ajuste de NVIDIA va **después de descargar** (paso intermedio de la opción A): el programa
que hay que elegir en el panel, `llama-server.exe`, todavía no existe en tu PC hasta entonces.

## Opción A: un solo comando (recomendada)

En PowerShell:

```powershell
git clone -b claude/magical-darwin-gcbo0m https://github.com/javiergalasa-cmd/First C:\jadis-cerebro\kit
cd C:\jadis-cerebro\kit\cerebro-local\fase0

python fase0.py --solo-inventario   # ~10 s, no descarga nada
python fase0.py --solo-descargar    # baja todo y te dice la ruta de llama-server.exe
#   -> aquí haces el ajuste de NVIDIA de abajo, con esa ruta
python fase0.py                     # pruebas (ya no descarga nada)
```

Si ya lo clonaste antes, actualízalo con `git pull` dentro de `C:\jadis-cerebro\kit`.

Si no quieres usar git, descarga el zip de la rama, descomprímelo y entra en
`cerebro-local\fase0`:
<https://github.com/javiergalasa-cmd/First/archive/refs/heads/claude/magical-darwin-gcbo0m.zip>

### El ajuste de NVIDIA, paso a paso

Hazlo cuando `--solo-descargar` te haya dado la ruta. Será algo como
`C:\jadis-cerebro\llama.cpp\b…-cuda-…\llama-server.exe`.

1. *Panel de control de NVIDIA → Administrar la configuración 3D →* pestaña **Configuración de
   programa**.
2. En "1. Seleccione un programa para personalizar", pulsa **Agregar**. `llama-server.exe` no
   saldrá en la lista: pulsa **Examinar…**, ve a la ruta que te dio el script, elige
   **`llama-server.exe`** y pulsa **Agregar programa seleccionado**.
3. En "2. Especifique la configuración", busca la línea que empieza por **"CUDA -"** y habla de
   **Sysmem Fallback**. Según la versión puede salir traducida, como "memoria del sistema". Elige
   **Prefer No Sysmem Fallback**.
4. **Aplicar.**

Hazlo solo para ese programa, no en "Configuración global": así no afecta a los juegos ni a otras
aplicaciones.

**El ajuste va ligado a esa ruta.** El script reutiliza siempre el `llama-server.exe` que ya
tienes, para que no cambie. Solo baja otra versión si se lo pides con `--actualizar-llama`, y
entonces hay que repetir este ajuste con la ruta nueva.

**Para qué sirve:** si la VRAM se llena, `llama-server` dará un error en vez de seguir a la
mitad de velocidad sin avisar.

**Si te lía, sáltatelo.** `--fit` ya deja 1 GB libre de margen, así que es un seguro, no algo
imprescindible.

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

## Prueba de velocidad: ¿se puede sacar más?

### Primero, dos comprobaciones gratis (2 minutos, sin instalar nada)

1. **¿Tu RAM va a la velocidad para la que está hecha?**
   - Mira en *Administrador de tareas → Rendimiento → Memoria* la **"Velocidad"** y las
     **"Ranuras usadas"**.
   - Compárala con la del módulo, que viene en su etiqueta o en su referencia:

     | Referencia | Velocidad |
     |---|---|
     | `KF432…` | 3200 |
     | `KF436…` | 3600 |
     | `KF556…` | 5600 |
     | `KF560…` | 6000 |

   - Si Windows dice menos (por ejemplo 2133 o 2400 en un módulo de 3200, o 4800 en uno de
     6000), **falta activar el perfil en la BIOS**. En ASUS: al encender, pulsa *Supr* → en
     *EZ Mode* activa **D.O.C.P.** (o EXPO) → *F10* para guardar.
   - Es gratis y acelera justo la parte que frena al cerebro.
   - Si después el PC se cuelga o no arranca, desactívalo de nuevo. Muchas placas lo deshacen
     solas tras varios arranques fallidos.
   - `fase0.py --solo-inventario` también lo detecta y avisa.
2. **¿Cuánta VRAM se come el escritorio?**
   - Con todo cerrado, mira en *Administrador de tareas → Rendimiento → GPU (la NVIDIA)* la
     **"Memoria dedicada de GPU"**.
   - Si ya hay 1 GB o más ocupado, **conectar el monitor a la placa base** (la gráfica
     integrada del Ryzen) deja ese espacio al modelo.
   - Solo funciona si la placa tiene salida de vídeo y la integrada está activada en la BIOS.
   - **No hace falta cambiar el cable para jugar.** Con el monitor en la placa, Windows 11 puede
     hacer que el juego se calcule en la 4060 y solo la imagen pase por la placa:
     *Configuración → Sistema → Pantalla → Gráficos* → el juego → *Alto rendimiento*.
   - **El coste:** algún fotograma por segundo menos y algo más de latencia. Con algunas
     combinaciones, G-Sync/FreeSync deja de funcionar. Pruébalo con un juego y decide; si no te
     convence, conecta el monitor a la 4060 para jugar.

### Luego, la prueba automática

**Desde la carpeta del kit**, no desde la tuya de usuario. Si no, Python responde
`can't open file ... fase0.py`.

```powershell
cd C:\jadis-cerebro\kit\cerebro-local\fase0
git pull
python fase0.py --exprimir
```

- **Si `cd` dice que la carpeta no existe:** aún no has bajado el kit. Haz el `git clone` de
  arriba.
- **Antes de empezar:** el Administrador de tareas debería marcar **12 GB o más de RAM
  "Disponible"**. Es donde va la parte del modelo que no cabe en la GPU. Con menos, Windows tira
  del disco y las medidas salen mucho peores de lo real (el script avisa).

Sobre la variante IQ3_S (o la que digas con `--variantes iq2_s`) prueba **un ajuste cada vez**
frente a la configuración del plan, y mide cuánto genera y cuánto tarda en leer el prompt:

| Qué prueba | Ajustes |
|---|---|
| El borrador | MTP con 1, 2 o 3 tokens; o **DFlash 2**, un borrador aparte que baja ~1 GB más (`--sin-dflash` lo salta) |
| Los hilos de CPU | uno por núcleo, o la mitad |
| El margen de VRAM | 512 MiB libres en vez de 1024: caben más capas en la GPU |
| La lectura del prompt | bloques de 2048; sin subir capas a la GPU al leer |
| La caché KV a 4 bits | **esta sí cuesta algo de precisión**: sale en el informe, pero no la elige sola |

**Qué hace con los resultados:**
- Se queda con los ajustes que ganan sin coste de calidad: un 5 % o más al generar, o un 10 % o
  más al leer sin empeorar al generar.
- Prueba esos ganadores **combinados**.
- Te da el **comando recomendado** para arrancar el cerebro.

Tarda **~30-40 min** y deja `C:\jadis-cerebro\informe-velocidad.md`.

**Repítela después de cada cambio** (activar D.O.C.P., mover el monitor, un segundo módulo de
RAM) para ver el efecto real con tus números. Las diferencias de menos de ~5 % son ruido.

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
