# Videosyt: arquitectura

## Flujo

```
guion.txt + estilo
   │
   ▼
1. Escenas    (Claude)        divide el guion: narración + prompt visual por escena
   │
   ▼  por cada escena:
2. Voz        (ElevenLabs)    narración en mp3; su duración marca la duración de la escena
3. Imagen     (Flux en fal.ai) imagen con el prompt + el estilo
4. Clip       (FFmpeg)        imagen con zoom lento + voz + subtítulos
   │
   ▼
5. Unir       (FFmpeg)        concatena los clips → video.mp4
```

## Estilos

Cada estilo es un JSON en `estilos/`: sufijo de prompt para las imágenes, formato (16:9 o 9:16),
fuente y color de subtítulos, velocidad del zoom y descripción de la voz.
Crear un estilo nuevo es copiar un JSON y cambiar valores. Vienen tres: `cinematico`, `anime`, `shorts`.

## Cómo usarlo

Requisitos: Python 3.9+ y FFmpeg. No hace falta instalar librerías.

```
python3 videosyt.py ejemplos/guion.txt --estilo cinematico --salida video.mp4
```

Sin claves funciona en **modo demo**: un párrafo por escena, voz en silencio y tarjetas de color.
Cada clave que agregues activa la IA real de ese paso, de forma independiente:

| Variable              | Paso    | Dónde se obtiene        |
|-----------------------|---------|-------------------------|
| `ANTHROPIC_API_KEY`   | Escenas | console.anthropic.com   |
| `ELEVENLABS_API_KEY`  | Voz     | elevenlabs.io           |
| `FAL_KEY`             | Imagen  | fal.ai                  |

Opcionales: `CLAUDE_MODEL`, `ELEVENLABS_VOICE_ID`, `FAL_IMAGE_MODEL` (por ejemplo `fal-ai/flux/dev`).

## Archivos

- `videosyt.py`: orquesta el flujo.
- `proveedores/guion.py`, `voz.py`, `imagen.py`, `montaje.py`: un archivo por paso.
  Para cambiar de IA (por ejemplo OpenAI TTS en vez de ElevenLabs) solo se toca ese archivo.

## Siguientes pasos sugeridos

1. Clips de video reales por escena (Kling, Veo o Wan en fal.ai) en lugar de imagen con zoom.
2. Música de fondo y subtítulos sincronizados palabra por palabra (Whisper).
3. Montaje con Remotion para plantillas con animaciones, transiciones y marca.
4. Interfaz web: subir guion, elegir estilo, ver progreso y descargar.
5. Cola de trabajos y almacenamiento (los videos tardan minutos y cuestan por generación).
