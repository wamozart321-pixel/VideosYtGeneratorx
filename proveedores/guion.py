"""Paso 1: convierte el guion en escenas (texto narrado + prompt visual)."""
import json
import os

from .http import post

INSTRUCCIONES = """Divide este guion en escenas para un video.
Estilo visual: {estilo}
Devuelve SOLO un JSON: una lista de objetos con
"narracion" (texto que se lee en voz alta, en el idioma del guion) y
"prompt_visual" (descripción en inglés de la imagen de esa escena, sin texto escrito en la imagen).

Guion:
{guion}"""


def escenas(guion, estilo):
    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        return _escenas_demo(guion)
    r = post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": clave, "anthropic-version": "2023-06-01"},
        {
            "model": os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5-5",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": INSTRUCCIONES.format(
                estilo=estilo["prompt_imagen"], guion=guion)}],
        },
    )
    # La respuesta puede traer varios bloques (por ejemplo de razonamiento); se usan solo los de texto.
    texto = "".join(b["text"] for b in r.get("content", []) if b.get("type") == "text")
    inicio, fin = texto.find("["), texto.rfind("]")
    if inicio < 0 or fin < inicio:
        raise ValueError("Claude no devolvió la lista de escenas. Intenta de nuevo.")
    return json.loads(texto[inicio: fin + 1])


def _escenas_demo(guion):
    # Sin API: un párrafo = una escena.
    parrafos = [p.strip() for p in guion.split("\n\n") if p.strip()]
    return [{"narracion": p, "prompt_visual": p} for p in parrafos]
