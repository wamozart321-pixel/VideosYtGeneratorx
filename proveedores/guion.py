"""Paso 1: divide el guion en escenas, sin IA.

Pensado para guiones escritos en Scripzy u otra herramienta: cada párrafo es una
escena. Dentro de un párrafo se reconocen indicaciones visuales opcionales:

    Imagen: un niño mira el amanecer desde una ventana
    [plano general de una ciudad de noche]

Esas líneas se usan como descripción de la imagen y no se narran. Las etiquetas
como "Escena 3" se ignoran, y prefijos como "Narrador:" se quitan.
"""
import re

VISUAL = re.compile(r"^\s*(?:visual|imagen|image|prompt|toma|plano)\s*:\s*(.+)$", re.I)
CORCHETES = re.compile(r"^\s*[\[(](.+)[\])]\s*$")
ETIQUETA = re.compile(r"^\s*(?:escena|scene|parte|part)\s*\d+\s*[:.\-–—]?\s*$", re.I)
NARRADOR = re.compile(r"^\s*(?:narrador|narraci[oó]n|voz(?: en off)?|locutor|narrator)\s*:\s*", re.I)


def escenas(texto):
    resultado, visual_pendiente = [], None
    for parrafo in re.split(r"\n\s*\n", texto.strip()):
        narracion, visuales = [], []
        for linea in parrafo.splitlines():
            if not linea.strip() or ETIQUETA.match(linea):
                continue
            m = VISUAL.match(linea) or CORCHETES.match(linea)
            if m:
                visuales.append(m.group(1).strip())
            else:
                narracion.append(NARRADOR.sub("", linea).strip())
        if visual_pendiente:
            visuales.insert(0, visual_pendiente)
            visual_pendiente = None
        if not narracion:
            # Un párrafo solo con indicación visual describe la escena siguiente.
            visual_pendiente = " ".join(visuales) or None
            continue
        texto_escena = " ".join(narracion)
        resultado.append({
            "narracion": texto_escena,
            "prompt_visual": " ".join(visuales) or texto_escena,
            "visual_propio": bool(visuales),
        })
    return resultado
