# Videosyt

App para crear videos a partir de un guion, con estilos. Corre en tu propia computadora:
no necesita hosting, dominio ni servidor pagado. Solo pagas las IAs que actives con tu clave.

## Descargas

- **Windows:** `Videosyt.exe` en la sección *Releases* del repositorio. Doble clic y listo
  (FFmpeg ya viene incluido). Videos y claves se guardan en la carpeta `Videosyt` de tu usuario.
- **Android:** `Videosyt.apk` en *Releases*. Ábrelo en el teléfono y permite instalar apps de
  fuentes desconocidas. El video se crea dentro del teléfono; mantén la app abierta mientras se monta.

GitHub compila ambos gratis cada vez que se actualiza `main` (`.github/workflows/`).

## Cómo abrirla desde el código (Windows, Mac o Linux)

1. Instala **Python 3** (python.org) y **FFmpeg**:
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
2. Descarga este repositorio (botón verde **Code → Download ZIP**) y descomprímelo.
3. Doble clic en el lanzador de tu sistema:
   - Windows: `iniciar-windows.bat`
   - Mac: `iniciar-mac.command`
   - Linux: `iniciar-linux.sh`

Se abre una ventana del navegador en `http://localhost:8000`. Esa dirección es tu propia computadora,
nada se publica en internet. Para cerrar la app, cierra la ventana negra de la terminal.

## Cómo se usa

1. Pega el guion (por ejemplo, de Scripzy). Cada párrafo es una escena.
2. Opcional: en **Personajes y estilo fijo** describe al protagonista y la paleta (mejor en inglés).
   Se agrega igual a todas las imágenes, junto con la misma semilla, para que no cambien de una escena a otra.
3. Elige un estilo (cinemático, anime o shorts vertical) y pulsa **Crear storyboard**.
4. Revisa las imágenes: puedes corregir el texto de cada escena, cambiar su descripción y **Regenerar imagen**.
5. Pulsa **Crear video**: recién ahí se generan las voces y se monta el MP4.

### Formato del guion

```
Escena 1
Narrador: Hace millones de años, el océano cubría casi todo el planeta.
Imagen: a vast primordial ocean under a red sky

[glowing single cells under a microscope]
En sus aguas apareció la vida.
```

- Una línea `Imagen:` (también `Visual:`, `Prompt:`, `Toma:`, `Plano:`) o entre `[...]` describe la imagen
  y no se lee en voz alta. Sin ella, la imagen se crea a partir de la narración.
- Las etiquetas como `Escena 3` se ignoran y prefijos como `Narrador:` se quitan.
- Un párrafo que solo tiene la línea visual se aplica a la escena siguiente.

Sin claves funciona en **modo demo** (tarjetas de color y voz en silencio) para probar el flujo.
En **Configurar IAs** pones tus claves y cada una activa la IA real de su paso:

| Clave       | Paso                            | Dónde se obtiene |
|-------------|---------------------------------|------------------|
| ElevenLabs  | Voz en off                      | elevenlabs.io    |
| fal.ai      | Imágenes (Flux) y video (Kling) | fal.ai           |

Las claves se guardan solo en tu equipo (`config.json`) o en el teléfono.

### Si una IA falla

- Errores pasajeros (429, 5xx, cortes de red) se reintentan solos, con esperas crecientes.
- Si la cuenta no puede seguir (401/402/403, por ejemplo sin saldo), no se reintenta: esa IA se deja de
  usar en el resto del video y la app avisa qué revisar.
- El video siempre termina: una escena sin imagen usa la imagen IA más cercana con el zoom al revés
  (marcada como **Respaldo** en el storyboard), una sin voz queda en silencio y una sin clip usa la imagen.

## Flujo

```
guion + estilo + personajes fijos
   │
   ▼
1. Escenas   (local, sin IA)    narración + descripción visual por escena
2. Imágenes  (Flux en fal.ai)   4 a la vez, misma semilla y misma "biblia" visual
   │
   ▼  storyboard: revisar, editar, regenerar
   │
3. Voz       (ElevenLabs)       3 a la vez; su duración marca la de la escena
3b. Animar   (Kling en fal.ai)  opcional, 2 a la vez: convierte la imagen en un clip
4. Clips     (FFmpeg)           imagen con zoom lento (o el clip) + voz + subtítulos, en paralelo
   │
   ▼
5. Unir      (FFmpeg)           concatena los clips → MP4
```

## Estilos

Cada estilo es un JSON en `estilos/`: sufijo de prompt para las imágenes, formato (16:9 o 9:16),
fuente y color de subtítulos y velocidad del zoom. Para crear uno nuevo, copia un JSON y cambia valores;
aparece solo en la app.

## Archivos

- `app.py`: versión de escritorio (ventana propia); es lo que se empaqueta en el .exe.
- `android/`: la app de Android (Capacitor). `www/motor.js` hace todo el flujo en el teléfono.
- `servidor.py`: la app (interfaz en `web/index.html`). Los proyectos quedan en `proyectos/` y los videos en `salida/`.
- `videosyt.py`: el motor; también se puede usar por línea de comandos:
  `python3 videosyt.py ejemplos/guion.txt --estilo anime --salida video.mp4`
- `proveedores/`: un archivo por paso (y `reintentos.py`). Para cambiar de IA solo se toca ese archivo.
- `pruebas/`: pruebas del motor con las APIs simuladas (no gastan créditos):
  `python3 -m unittest discover pruebas`
- `fuentes/`: tipografías DejaVu (licencia libre, ver `LICENCIA-DejaVu.txt`).

## Siguientes pasos sugeridos

1. Música de fondo (Suno o ElevenLabs Music) y subtítulos palabra por palabra (Whisper).
2. Montaje con Remotion para transiciones y animaciones más ricas.
