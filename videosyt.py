"""Videosyt: de un guion a un video con estilo.

Uso:  python3 videosyt.py ejemplos/guion.txt --estilo cinematico --salida video.mp4
Interfaz web:  python3 servidor.py  (y abre http://localhost:8000)
Sin claves de API funciona en modo demo (tarjetas de color y voz en silencio).
"""
import argparse
import json
import os
import tempfile

from proveedores import clip_video, guion, imagen, montaje, voz

TAMANOS = {"16:9": (1280, 720), "9:16": (720, 1280)}
AQUI = os.path.dirname(os.path.abspath(__file__))
CLAVES = {"guion": "ANTHROPIC_API_KEY", "voz": "ELEVENLABS_API_KEY", "imagen": "FAL_KEY"}


def estilos():
    carpeta = os.path.join(AQUI, "estilos")
    resultado = {}
    for archivo in sorted(os.listdir(carpeta)):
        if archivo.endswith(".json"):
            with open(os.path.join(carpeta, archivo)) as f:
                resultado[archivo[:-5]] = json.load(f)
    return resultado


def crear_video(texto, nombre_estilo, salida, avisar=print, usar_clips=False):
    """Genera el video. `avisar(porcentaje, mensaje)` informa el progreso."""
    estilo = estilos()[nombre_estilo]
    tamano = TAMANOS[estilo["formato"]]
    usar_clips = usar_clips and bool(os.environ.get("FAL_KEY"))

    avisar(2, "Dividiendo el guion en escenas")
    lista = guion.escenas(texto, estilo)

    trabajo = tempfile.mkdtemp(prefix="videosyt-")
    clips = []
    for i, escena in enumerate(lista, 1):
        avance = 5 + int(85 * (i - 1) / len(lista))
        base = os.path.join(trabajo, f"escena{i:02d}")
        avisar(avance, f"Escena {i} de {len(lista)}: narrando")
        dur = voz.narrar(escena["narracion"], base + ".mp3")
        avisar(avance, f"Escena {i} de {len(lista)}: creando imagen")
        url = imagen.generar(escena["prompt_visual"], estilo, tamano, base + ".png", i)
        animado = None
        if usar_clips and url:
            avisar(avance, f"Escena {i} de {len(lista)}: animando (puede tardar unos minutos)")
            clip_video.animar(url, escena["prompt_visual"], estilo, base + "_clip.mp4")
            animado = base + "_clip.mp4"
        avisar(avance, f"Escena {i} de {len(lista)}: montando")
        montaje.clip(base + ".png", base + ".mp3", escena["narracion"], dur, estilo, tamano,
                     base + ".mp4", video=animado)
        clips.append(base + ".mp4")

    avisar(95, "Uniendo escenas")
    montaje.unir(clips, salida)
    avisar(100, "Listo")
    return len(lista)


def modo():
    return {paso: bool(os.environ.get(k)) for paso, k in CLAVES.items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea un video a partir de un guion.")
    p.add_argument("guion")
    p.add_argument("--estilo", default="cinematico")
    p.add_argument("--salida", default="video.mp4")
    p.add_argument("--clips", action="store_true", help="anima cada escena con Kling (requiere FAL_KEY)")
    a = p.parse_args()
    print("Modo:", ", ".join(f"{k}={'real' if v else 'demo'}" for k, v in modo().items()))
    with open(a.guion) as f:
        crear_video(f.read(), a.estilo, a.salida, lambda pct, msg: print(f"[{pct:3d}%] {msg}"), a.clips)
    print(f"Listo: {a.salida}")
