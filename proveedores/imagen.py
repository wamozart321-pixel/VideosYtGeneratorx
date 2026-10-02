"""Paso 3: imagen por escena. Flux (fal.ai) si hay clave; si no, una tarjeta de color.

Devuelve la URL de la imagen generada (o None en modo demo) para poder animarla después."""
import os
import textwrap

from . import ejecutar
from .http import descargar, post
from .montaje import ruta_filtro


SIN_TEXTO = "purely visual scene, no written words, no captions, no signs, no lettering anywhere"


def componer_prompt(prompt, estilo, biblia=""):
    """Primero lo que pasa en la escena, luego el estilo y al final el personaje fijo (si sale).

    Antes la biblia iba primero e idéntica en todas las escenas, y Flux dibujaba siempre el mismo
    personaje en el mismo lugar. El texto de la escena va como algo a ilustrar, no a escribir:
    si no, Flux tiende a dibujar letras inventadas en carteles, libros o pantallas."""
    escena = prompt.strip().strip('"«»“”')
    partes = [f"Scene illustrating: {escena}" if escena else "", estilo["prompt_imagen"],
              f"Recurring character: {biblia.strip()}" if biblia.strip() else "", SIN_TEXTO]
    return ". ".join(p for p in partes if p)


def generar(prompt, estilo, destino, biblia="", semilla=None):
    """Genera la imagen con Flux y devuelve su URL. Requiere FAL_KEY."""
    cuerpo = {
        "prompt": componer_prompt(prompt, estilo, biblia),
        "image_size": "portrait_16_9" if estilo["formato"] == "9:16" else "landscape_16_9",
    }
    if semilla is not None:
        cuerpo["seed"] = semilla  # semilla propia por escena: varía la composición
    modelo = os.environ.get("FAL_IMAGE_MODEL") or estilo.get("modelo") or "fal-ai/flux/dev"
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
