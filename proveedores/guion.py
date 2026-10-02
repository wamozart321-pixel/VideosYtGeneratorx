"""Paso 1: divide el guion en escenas, sin IA.

Pensado para guiones escritos en Scripzy u otra herramienta: cada párrafo es una
escena. Dentro de un párrafo se reconocen indicaciones visuales opcionales:

    Imagen: un niño mira el amanecer desde una ventana
    [plano general de una ciudad de noche]

Esas líneas se usan como descripción de la imagen y no se narran. Las etiquetas
como "Escena 3" se ignoran, y prefijos como "Narrador:" se quitan.

Los párrafos largos se parten por oraciones en varias escenas de unas
`palabras_por_escena` palabras, para que la imagen cambie seguido.
"""
import re

VISUAL = re.compile(r"^\s*(?:visual|imagen|image|prompt|toma|plano)\s*:\s*(.+)$", re.I)
CORCHETES = re.compile(r"^\s*[\[(](.+)[\])]\s*$")
ETIQUETA = re.compile(r"^\s*(?:escena|scene|parte|part)\s*\d+\s*[:.\-–—]?\s*$", re.I)
ORACION = re.compile(r"(?<=[.!?…])[\"'»”)]*\s+")
PAUSA = re.compile(r"(?<=[,;:])\s+")
# Ritmo: palabras por escena (a ~2,5 palabras por segundo).
RITMOS = {"pocas": 25, "normal": 12, "muchas": 8}
NARRADOR = re.compile(r"^\s*(?:narrador|narraci[oó]n|voz(?: en off)?|locutor|narrator)\s*:\s*", re.I)


def _palabras(t):
    return len(t.split())


def partir(texto, objetivo):
    """Divide la narración en trozos de unas `objetivo` palabras sin cortar oraciones si se puede."""
    piezas = []
    for oracion in ORACION.split(texto.strip()):
        # Una oración muy larga se corta en comas; si aún es larga, por palabras.
        if _palabras(oracion) > objetivo * 1.6:
            for parte in PAUSA.split(oracion):
                palabras = parte.split()
                while len(palabras) > objetivo * 1.6:
                    piezas.append(" ".join(palabras[:objetivo]))
                    palabras = palabras[objetivo:]
                piezas.append(" ".join(palabras))
        else:
            piezas.append(oracion)
    trozos, actual = [], ""
    for pieza in filter(None, (p.strip() for p in piezas)):
        n, junto = _palabras(actual), _palabras(actual) + _palabras(pieza)
        # Se une la pieza si deja el trozo más cerca del objetivo (o si el trozo aún es muy corto).
        if n >= objetivo * 0.6 and abs(junto - objetivo) > abs(n - objetivo):
            trozos.append(actual)
            actual = pieza
        else:
            actual = f"{actual} {pieza}".strip()
    if actual:
        # Un resto muy corto se une al trozo anterior.
        if trozos and _palabras(actual) < objetivo * 0.4:
            trozos[-1] += " " + actual
        else:
            trozos.append(actual)
    return trozos


def subtitulos(texto, max_palabras):
    """Trozos cortos para mostrar de a uno mientras se narra (como en los Shorts)."""
    palabras = texto.split()
    n = max(1, -(-len(palabras) // max_palabras))  # partes iguales, sin un último trozo de 1 palabra
    tam = -(-len(palabras) // n)
    return [" ".join(palabras[i:i + tam]) for i in range(0, len(palabras), tam)]


def escenas(texto, palabras_por_escena=RITMOS["normal"]):
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
        visual = " ".join(visuales)
        for n, trozo in enumerate(partir(" ".join(narracion), palabras_por_escena)):
            # La indicación visual del párrafo es para su primera escena; las demás usan su texto.
            resultado.append({
                "narracion": trozo,
                "prompt_visual": visual if visual and n == 0 else trozo,
                "visual_propio": bool(visual) and n == 0,
            })
    return resultado
