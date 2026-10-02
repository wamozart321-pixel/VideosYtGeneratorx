"""Imágenes con OpenAI (los modelos de imagen de ChatGPT), como alternativa a Flux.

Necesita una clave de API de OpenAI (platform.openai.com), que se paga aparte del plan
ChatGPT Plus. OpenAI no acepta semilla ni tamaños libres: se pide 3:2 y el montaje recorta a
16:9. Devuelve la imagen en base64, así que se guarda directo en el disco.
"""
import base64
import json
import os
import urllib.error

from .http import post

# Del más nuevo al más viejo: si la cuenta aún no tiene acceso a uno, se prueba el siguiente.
MODELOS = ["gpt-image-2.5-flare", "gpt-image-2", "gpt-image-1.5", "gpt-image-1"]
TAMANOS = {"16:9": "1536x1024", "9:16": "1024x1536"}
URL = "https://api.openai.com/v1/images/generations"

_modelo_que_funciona = None


class Rechazada(Exception):
    """El filtro de contenido de OpenAI no quiso crear la imagen."""


class _ModeloNoDisponible(Exception):
    pass


def _modelos():
    if os.environ.get("OPENAI_IMAGE_MODEL"):
        return [os.environ["OPENAI_IMAGE_MODEL"]]
    return [_modelo_que_funciona] if _modelo_que_funciona else MODELOS


def _pedir(modelo, prompt, formato):
    try:
        return post(URL, {"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    {"model": modelo, "prompt": prompt, "size": TAMANOS[formato], "quality": "medium", "n": 1},
                    timeout=300)
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404):
            raise
        texto = e.read().decode(errors="replace")
        try:
            error = json.loads(texto).get("error") or {}
        except ValueError:
            error = {}
        codigo, mensaje = str(error.get("code") or ""), str(error.get("message") or texto)[:300]
        if "moderation" in codigo or "safety" in codigo:
            raise Rechazada(mensaje) from e
        if "model" in codigo or "model" in mensaje.lower():
            raise _ModeloNoDisponible(mensaje) from e
        raise ValueError(f"OpenAI respondió {e.code}: {mensaje}") from e


def generar(prompt, formato, destino):
    """Crea la imagen y la guarda en destino. Lanza Rechazada si el filtro de contenido la bloquea."""
    global _modelo_que_funciona
    error = None
    for modelo in _modelos():
        try:
            r = _pedir(modelo, prompt, formato)
        except _ModeloNoDisponible as e:
            error = e
            continue
        except Rechazada:
            _modelo_que_funciona = modelo  # el modelo existe; fue el contenido
            raise
        _modelo_que_funciona = modelo
        with open(destino, "wb") as f:
            f.write(base64.b64decode(r["data"][0]["b64_json"]))
        return
    raise ValueError(f"tu cuenta de OpenAI no tiene acceso a ningún modelo de imagen ({error})")
