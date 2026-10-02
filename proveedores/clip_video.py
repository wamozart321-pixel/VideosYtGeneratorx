"""Paso 3b (opcional): anima la imagen de la escena con Kling en fal.ai."""
import base64
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


def como_dato(ruta):
    """La imagen como data URI: fal la acepta en lugar de una URL (las de OpenAI no tienen URL)."""
    with open(ruta, "rb") as f:
        datos = f.read()
    tipo = "image/png" if datos[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{tipo};base64,{base64.b64encode(datos).decode()}"
