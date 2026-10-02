"""Director de arte: convierte cada trozo del guion en una descripción visual distinta.

Sin esto, la imagen de cada escena se pedía con el texto narrado tal cual (un fragmento en
español, a veces abstracto) y con el personaje delante en todas: Flux repetía el mismo
personaje en el mismo tipo de lugar. Aquí un modelo de texto barato (vía fal, con la misma
FAL_KEY) lee el guion completo y propone, por escena, qué se ve: lugar, época, objetos y tipo
de plano, y si el personaje aparece o no. Si falla, las escenas conservan el texto del guion.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from .http import post
from .reintentos import con_reintentos

MODELOS = ["google/gemini-2.5-flash", "openai/gpt-4.1-mini"]
POR_LOTE = 25  # escenas por llamada: respuestas cortas y en paralelo
MAX_GUION = 12000  # caracteres del guion completo que se envían como contexto

INSTRUCCIONES = """You are the art director of a faceless YouTube channel. You receive a narration script split into numbered scenes. For each scene write one prompt for an AI image model that shows what that part of the script is actually about: the concrete subject, place, era, objects and action.
Rules:
- English, 20 to 45 words per scene.
- Neighbouring scenes must look different: change the setting, the subject and the shot (wide establishing shot, close-up of an object, crowd, aerial view, detail of hands, silhouette, over-the-shoulder...).
- Follow the eras and places of the story (for example a smoky 1930s jazz club, a 1960s pirate radio ship, a modern phone screen).
- Turn abstract ideas and metaphors into concrete visual symbols.
- Never ask for written words, letters, logos, captions or readable signs.
- Show violent, cruel or tragic events symbolically (shadows, empty places, meaningful objects, faces reacting), never graphic violence, bodies, blood or nudity: the image model blacks those images out.
- Do not describe the art style; it is added later.
- If there is a recurring character, it is the protagonist of the video: put it in about three of every four scenes, acting out or reacting to what that scene is about, inside that scene's own setting and era. Start those prompts with the character's full description and set "personaje" to true. Leave it out (false) only for establishing shots, close-ups of objects or scenes about specific real people. If there is no recurring character, "personaje" is always false.
Reply only with a JSON array, one object per scene with the same numbers: [{"n": 1, "imagen": "...", "personaje": false}]"""


def _pedido(guion, lote, personaje):
    escenas = "\n".join(f"{n}. {texto}" for n, texto in lote)
    return (f"Recurring character: {personaje or 'none'}\n\n"
            f"Full script (context):\n{guion[:MAX_GUION]}\n\n"
            f"Scenes to describe:\n{escenas}")


def leer_respuesta(texto, numeros):
    """Extrae {n: (descripción, personaje)} de la respuesta; tolera ```json y texto alrededor."""
    m = re.search(r"\[.*\]", texto or "", re.S)
    if not m:
        raise ValueError("el director no devolvió una lista")
    resultado = {}
    for item in json.loads(m.group(0)):
        if isinstance(item, dict) and item.get("n") in numeros and str(item.get("imagen", "")).strip():
            resultado[item["n"]] = (str(item["imagen"]).strip(), bool(item.get("personaje")))
    if not resultado:
        raise ValueError("el director no describió ninguna escena")
    return resultado


def _llamar_modelo(modelo, pedido):
    r = post("https://fal.run/openrouter/router", {"authorization": f"Key {os.environ['FAL_KEY']}"},
             {"model": modelo, "system_prompt": INSTRUCCIONES, "prompt": pedido, "temperature": 0.8},
             timeout=120)
    if r.get("error"):
        raise ValueError(r["error"])
    return r.get("output", "")


def _describir_lote(guion, lote, personaje):
    pedido, numeros = _pedido(guion, lote, personaje), {n for n, _ in lote}
    modelos = [os.environ["FAL_LLM_MODEL"]] if os.environ.get("FAL_LLM_MODEL") else MODELOS
    error = None
    for modelo in modelos:  # si un modelo no está disponible, se prueba el siguiente
        try:
            return leer_respuesta(con_reintentos(_llamar_modelo, modelo, pedido, intentos=3), numeros)
        except Exception as e:  # noqa: BLE001
            error = e
    raise error


def describir(guion, narraciones, personaje=""):
    """Devuelve {número de escena (desde 1): (descripción en inglés, aparece el personaje)}.

    Las escenas que el modelo no describió no aparecen; lanza la excepción si no describió ninguna."""
    numeradas = list(enumerate(narraciones, 1))
    lotes = [numeradas[i:i + POR_LOTE] for i in range(0, len(numeradas), POR_LOTE)]
    resultado, error = {}, None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for futuro in [pool.submit(_describir_lote, guion, lote, personaje) for lote in lotes]:
            try:
                resultado.update(futuro.result())
            except Exception as e:  # noqa: BLE001
                error = e
    if not resultado:
        raise error or ValueError("sin escenas")
    return resultado
