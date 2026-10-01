"""Paso 3: imagen por escena. Flux (fal.ai) si hay clave; si no, una tarjeta de color.

Devuelve la URL de la imagen generada (o None en modo demo) para poder animarla después."""
import os
import subprocess
import textwrap

from .http import descargar, post
from .montaje import ruta_filtro

def generar(prompt, estilo, tamano, destino, numero):
    clave = os.environ.get("FAL_KEY")
    if clave:
        modelo = os.environ.get("FAL_IMAGE_MODEL", "fal-ai/flux/schnell")
        r = post(
            f"https://fal.run/{modelo}",
            {"authorization": f"Key {clave}"},
            {"prompt": f"{prompt}, {estilo['prompt_imagen']}",
             "image_size": "portrait_16_9" if estilo["formato"] == "9:16" else "landscape_16_9"},
        )
        url = r["images"][0]["url"]
        descargar(url, destino)
        return url
    _tarjeta_demo(prompt, estilo, tamano, destino, numero)
    return None


def _tarjeta_demo(prompt, estilo, tamano, destino, numero):
    ancho, alto = tamano
    lado = min(ancho, alto)
    texto = destino + ".txt"
    with open(texto, "w") as f:
        f.write(textwrap.fill(prompt, 30))
    fuente = ruta_filtro(estilo["fuente"])
    texto_f = ruta_filtro(texto)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c={estilo['fondo_demo']}:s={ancho}x{alto}", "-frames:v", "1",
         "-vf",
         f"drawtext=fontfile='{fuente}':text='ESCENA {numero}':fontsize={lado // 8}:"
         f"fontcolor=white@0.35:x=(w-tw)/2:y=h*0.15,"
         f"drawtext=fontfile='{fuente}':textfile='{texto_f}':fontsize={lado // 28}:"
         f"fontcolor=white@0.5:x=(w-tw)/2:y=h*0.45:line_spacing=8",
         destino],
        check=True,
    )
