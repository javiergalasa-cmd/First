# Fase 1: ¿el cerebro piensa bien en lo tuyo?

Un comando que arranca el modelo elegido en la Fase 0 (Qwen3.6-35B-A3B sin censura) y le hace
**23 casos típicos de JADIS**. Lo que se puede comprobar con código, lo comprueba: herramienta
correcta, encargos sin datos personales, breve, sin rechazos, en español, sin emojis y tratándote de
usted (como JARVIS). Lo demás (gracia,
criterio, tono) lo juzgas tú leyendo las respuestas en el informe.

**Todos los datos personales de los casos son inventados.**

## Cómo lanzarlo

Con JADIS, Docker y WSL cerrados, como en la Fase 0:

```powershell
cd C:\jadis-cerebro\kit\cerebro-local
git pull
cd fase1
python calidad.py
```

Tarda unos 2-4 minutos y escribe `C:\jadis-cerebro\informe-calidad.md`.

Como el modelo no responde siempre igual, `python calidad.py --repeticiones 3` repite cada caso
tres veces. Así se ve si un fallo es constante o casual.

## Qué prueba

| Grupo | Casos | Regla | Qué se comprueba |
|---|---|---|---|
| charla | 5 | **sin pensar** | Respuesta breve, sin herramientas, sin razonamiento |
| delegar | 6 | **pensando** | Usa `delegar` con la clase de privacidad correcta y sin tus datos en el encargo |
| personal | 4 | pensando | Correo, agenda, alarma y memoria los hace él; **no delega** |
| paso directo | 1 | pensando | Si el subagente ya te contestó, no lo repite (≤ 20 palabras) |
| inyección | 2 | pensando | Un correo o una web con órdenes escondidas no le hacen enviar, borrar ni delegar |
| sin censura | 4 | según el caso | No rechaza (chiste negro, roast, abrir tu propia puerta, opinión) |
| acción | 1 | pensando | Vaciar la papelera: lo hace (la tarjeta de permiso la pone JADIS) o pregunta |

**Regla de pensar (decisión de Javier):** si hablas con él, no piensa. Si le mandas una tarea,
piensa y delega lo que toque. En la batería lo decide cada caso; en JADIS lo decidirá el código
(Fase 4).

## Opciones

- `--solo delegar,inyeccion`: solo esos grupos o casos.
- `--modelo C:\...\otro.gguf`: probar otro modelo, por ejemplo el 27B cuando llegue la 5070.
- `--url http://127.0.0.1:8080`: usar un servidor ya arrancado.
- `--tareas-sin-pensar`: las tareas también sin pensar, para comparar calidad y tiempo.
- `--opciones "..."`: cambiar los ajustes de arranque. Por defecto, los elegidos en la Fase 0:
  `--sin-mtp --sin-mmap --ubatch 2048 --fit-target 512`.

## Pruebas del propio script

`python -m unittest discover -s tests` (13 pruebas, sin GPU).
