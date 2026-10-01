"""Paso 4: une imagen + voz + subtítulos de cada escena y concatena el video final."""
import os
import textwrap

from . import ejecutar

FPS = 25
AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_filtro(ruta):
    """Ruta absoluta escapada para usarla dentro de un filtro de FFmpeg (también en Windows)."""
    ruta = os.path.abspath(os.path.join(AQUI, ruta)).replace("\\", "/")
    return ruta.replace(":", "\\:").replace("'", "\\'")


def clip(imagen, audio, narracion, duracion, estilo, tamano, destino, video=None):
    """Si hay `video` (clip animado) se usa en bucle; si no, la imagen con zoom lento."""
    ancho, alto = tamano
    sub = destino + ".txt"
    with open(sub, "w") as f:
        f.write(textwrap.fill(narracion, 22 if alto > ancho else 45))
    cuadros = int(duracion * FPS) + 1
    if video:
        entrada = ["-stream_loop", "-1", "-i", video]
        mover = (f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,"
                 f"crop={ancho}:{alto},fps={FPS},")
    else:
        entrada = ["-loop", "1", "-i", imagen]
        mover = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,"
                 f"crop={ancho * 2}:{alto * 2},"
                 f"zoompan=z='min(zoom+{estilo['zoom']},1.3)':d={cuadros}:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={FPS},")
    filtro = (
        mover +
        f"drawtext=fontfile='{ruta_filtro(estilo['fuente'])}':textfile='{ruta_filtro(sub)}':fontsize={min(ancho, alto) // 20}:"
        f"fontcolor={estilo['color_texto']}:box=1:boxcolor=black@0.55:boxborderw=14:"
        f"line_spacing=6:x=(w-tw)/2:y=h-th-h*0.08"
    )
    ejecutar.run(
        ["ffmpeg", "-y", "-loglevel", "error", *entrada, "-i", audio,
         "-map", "0:v", "-map", "1:a", "-vf", filtro, "-t", f"{duracion:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", destino],
        check=True,
    )


def unir(clips, destino):
    lista = os.path.join(os.path.dirname(os.path.abspath(clips[0])), "lista.txt")
    with open(lista, "w") as f:
        f.writelines(f"file '{os.path.abspath(c)}'\n" for c in clips)
    ejecutar.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lista, "-c", "copy", destino],
        check=True,
    )
