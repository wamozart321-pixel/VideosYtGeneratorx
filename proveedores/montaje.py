"""Paso 4: une imagen + voz + subtítulos de cada escena y concatena el video final."""
import os
import textwrap

from . import ejecutar
from .guion import subtitulos

FPS = 25
AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_filtro(ruta):
    """Ruta absoluta escapada para usarla dentro de un filtro de FFmpeg (también en Windows)."""
    ruta = os.path.abspath(os.path.join(AQUI, ruta)).replace("\\", "/")
    return ruta.replace(":", "\\:").replace("'", "\\'")


# Imágenes casi fijas: preset rápido y ajuste para imagen estática; calidad visual casi igual.
CODIFICAR = ["-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "23", "-pix_fmt", "yuv420p"]


def clip(imagen, audio, narracion, duracion, estilo, tamano, destino, video=None, zoom_inverso=False):
    """Si hay `video` (clip animado) se usa en bucle; si no, la imagen con zoom lento.

    `zoom_inverso` aleja en vez de acercar: se usa cuando la imagen es de respaldo
    (reutilizada de otra escena) para que no se vea repetida."""
    ancho, alto = tamano
    cuadros = int(duracion * FPS) + 1
    if video:
        entrada = ["-stream_loop", "-1", "-i", video]
        mover = (f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,"
                 f"crop={ancho}:{alto},fps={FPS},")
    else:
        # Una sola imagen de entrada: zoompan genera todos los cuadros a partir de ella,
        # así la imagen se escala una vez y no en cada cuadro.
        entrada = ["-i", imagen]
        z = (f"if(eq(on,0),1.3,max(zoom-{estilo['zoom']},1.0))" if zoom_inverso
             else f"min(zoom+{estilo['zoom']},1.3)")
        mover = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,"
                 f"crop={ancho * 2}:{alto * 2},"
                 f"zoompan=z='{z}':d={cuadros}:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={FPS},")
    filtro = mover + (textos(narracion, duracion, estilo, tamano, destino) if estilo.get("subtitulos", True)
                      else "null")
    ejecutar.run(
        ["ffmpeg", "-y", "-loglevel", "error", *entrada, "-i", audio,
         "-map", "0:v", "-map", "1:a", "-vf", filtro, "-t", f"{duracion:.2f}", *CODIFICAR,
         "-c:a", "aac", "-ar", "44100", "-ac", "2", destino],
        check=True,
    )


def textos(narracion, duracion, estilo, tamano, destino):
    """Subtítulos en trozos cortos (máximo 2 líneas) que cambian al ritmo de la voz."""
    ancho, alto = tamano
    vertical = alto > ancho
    trozos = subtitulos(narracion, 5 if vertical else 7)
    total = sum(len(t) for t in trozos)
    filtros, inicio = [], 0.0
    for n, trozo in enumerate(trozos):
        # Cada trozo dura en proporción a sus letras, que es más o menos lo que tarda en leerse.
        fin = duracion if n == len(trozos) - 1 else inicio + duracion * len(trozo) / total
        archivo = f"{destino}.{n}.txt"
        with open(archivo, "w", encoding="utf-8") as f:
            f.write(textwrap.fill(trozo, 18 if vertical else 32))
        filtros.append(
            f"drawtext=fontfile='{ruta_filtro(estilo['fuente'])}':textfile='{ruta_filtro(archivo)}':"
            f"fontsize={min(ancho, alto) // 16}:fontcolor={estilo['color_texto']}:"
            f"borderw=3:bordercolor=black@0.85:box=1:boxcolor=black@0.35:boxborderw=10:line_spacing=6:"
            f"x=(w-tw)/2:y=h-th-h*{0.18 if vertical else 0.07}:enable='between(t,{inicio:.3f},{fin:.3f})'")
        inicio = fin
    return ",".join(filtros)


def unir(clips, destino):
    lista = os.path.join(os.path.dirname(os.path.abspath(clips[0])), "lista.txt")
    with open(lista, "w") as f:
        f.writelines(f"file '{os.path.abspath(c)}'\n" for c in clips)
    ejecutar.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lista, "-c", "copy", destino],
        check=True,
    )
