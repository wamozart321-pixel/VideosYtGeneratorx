"""Paso 3b (opcional): anima la imagen de la escena con Kling en fal.ai."""
import os

from .http import descargar, post


def animar(url_imagen, prompt, estilo, destino):
    modelo = os.environ.get("FAL_VIDEO_MODEL") or "fal-ai/kling-video/v2.1/standard/image-to-video"
    r = post(
        f"https://fal.run/{modelo}",
        {"authorization": f"Key {os.environ['FAL_KEY']}"},
        {"prompt": f"{prompt}, {estilo['prompt_imagen']}, smooth camera motion",
         "image_url": url_imagen, "duration": "5"},
        timeout=900,
    )
    descargar(r["video"]["url"], destino)
