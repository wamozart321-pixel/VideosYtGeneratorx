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

1. Escribe o pega el guion. Cada párrafo es una escena.
2. Elige un estilo (cinemático, anime o shorts vertical).
3. Pulsa **Generar video**, mira el progreso y descarga el MP4.

Sin claves funciona en **modo demo** (tarjetas de color y voz en silencio) para probar el flujo.
En **Configurar IAs** pones tus claves y cada una activa la IA real de su paso:

| Clave       | Paso                         | Dónde se obtiene      |
|-------------|------------------------------|-----------------------|
| Claude      | Divide el guion en escenas   | console.anthropic.com |
| ElevenLabs  | Voz en off                   | elevenlabs.io         |
| fal.ai      | Imágenes (Flux) y video (Kling) | fal.ai             |

Las claves se guardan solo en tu equipo, en `config.json`.

## Flujo

```
guion + estilo
   │
   ▼
1. Escenas   (Claude)           narración + prompt visual por escena
   │
   ▼  por cada escena:
2. Voz       (ElevenLabs)       mp3; su duración marca la de la escena
3. Imagen    (Flux en fal.ai)   imagen con el prompt + el estilo
3b. Animar   (Kling en fal.ai)  opcional: convierte la imagen en un clip de video
4. Clip      (FFmpeg)           imagen con zoom lento (o el clip) + voz + subtítulos
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
- `servidor.py`: la app (interfaz en `web/index.html`). Los videos quedan en `salida/`.
- `videosyt.py`: el motor; también se puede usar por línea de comandos:
  `python3 videosyt.py ejemplos/guion.txt --estilo anime --salida video.mp4`
- `proveedores/`: un archivo por paso. Para cambiar de IA solo se toca ese archivo.
- `fuentes/`: tipografías DejaVu (licencia libre, ver `LICENCIA-DejaVu.txt`).

## Siguientes pasos sugeridos

1. Música de fondo (Suno o ElevenLabs Music) y subtítulos palabra por palabra (Whisper).
2. Editar escenas antes de generar (cambiar texto o regenerar una imagen).
3. Montaje con Remotion para transiciones y animaciones más ricas.
