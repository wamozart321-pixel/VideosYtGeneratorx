"""Paso 3: imagen por escena. Flux (fal.ai) si hay clave; si no, una tarjeta de color.

Devuelve la URL de la imagen generada (o None en modo demo) para poder animarla después."""
import os
import textwrap

from . import ejecutar
from .http import descargar, post
from .montaje import ruta_filtro


def componer_prompt(prompt, estilo, biblia=""):
    """La biblia visual va primero y es idéntica en todas las escenas; así se mantiene el estilo."""
    partes = [biblia.strip(), prompt.strip(), estilo["prompt_imagen"], "no text, no letters, no watermark"]
    return ". ".join(p for p in partes if p)


def generar(prompt, estilo, destino, biblia="", semilla=None):
    """Genera la imagen con Flux y devuelve su URL. Requiere FAL_KEY."""
    cuerpo = {
        "prompt": componer_prompt(prompt, estilo, biblia),
        "image_size": "portrait_16_9" if estilo["formato"] == "9:16" else "landscape_16_9",
    }
    if semilla is not None:
        cuerpo["seed"] = semilla  # misma semilla en todo el video = estilo más estable
    modelo = os.environ.get("FAL_IMAGE_MODEL") or "fal-ai/flux/schnell"
    r = post(f"https://fal.run/{modelo}", {"authorization": f"Key {os.environ['FAL_KEY']}"}, cuerpo)
    url = r["images"][0]["url"]
    descargar(url, destino)
    return url


def tarjeta_demo(prompt, estilo, tamano, destino, numero):
    ancho, alto = tamano
    lado = min(ancho, alto)
    texto = destino + ".txt"
    with open(texto, "w") as f:
        f.write(textwrap.fill(prompt, 30))
    fuente = ruta_filtro(estilo["fuente"])
    texto_f = ruta_filtro(texto)
    ejecutar.run(
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
