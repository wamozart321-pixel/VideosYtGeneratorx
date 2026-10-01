"""Paso 4: une imagen + voz + subtítulos de cada escena y concatena el video final."""
import os
import subprocess
import textwrap

FPS = 25


def clip(imagen, audio, narracion, duracion, estilo, tamano, destino):
    ancho, alto = tamano
    sub = destino + ".txt"
    with open(sub, "w") as f:
        f.write(textwrap.fill(narracion, 22 if alto > ancho else 45))
    cuadros = int(duracion * FPS) + 1
    filtro = (
        f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,"
        f"crop={ancho * 2}:{alto * 2},"
        f"zoompan=z='min(zoom+{estilo['zoom']},1.3)':d={cuadros}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={FPS},"
        f"drawtext=fontfile={estilo['fuente']}:textfile={sub}:fontsize={min(ancho, alto) // 20}:"
        f"fontcolor={estilo['color_texto']}:box=1:boxcolor=black@0.55:boxborderw=14:"
        f"line_spacing=6:x=(w-tw)/2:y=h-th-h*0.08"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", imagen, "-i", audio,
         "-vf", filtro, "-t", f"{duracion:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", destino],
        check=True,
    )


def unir(clips, destino):
    lista = os.path.join(os.path.dirname(os.path.abspath(clips[0])), "lista.txt")
    with open(lista, "w") as f:
        f.writelines(f"file '{os.path.abspath(c)}'\n" for c in clips)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lista, "-c", "copy", destino],
        check=True,
    )
