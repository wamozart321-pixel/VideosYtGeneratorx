"""Videosyt: de un guion a un video con estilo.

Uso:  python3 videosyt.py ejemplos/guion.txt --estilo cinematico --salida video.mp4
Sin claves de API funciona en modo demo (tarjetas de color y voz en silencio).
"""
import argparse
import json
import os
import tempfile

from proveedores import guion, imagen, montaje, voz

TAMANOS = {"16:9": (1280, 720), "9:16": (720, 1280)}
AQUI = os.path.dirname(os.path.abspath(__file__))


def crear_video(ruta_guion, nombre_estilo, salida):
    with open(os.path.join(AQUI, "estilos", f"{nombre_estilo}.json")) as f:
        estilo = json.load(f)
    with open(ruta_guion) as f:
        texto = f.read()
    tamano = TAMANOS[estilo["formato"]]

    print(f"Estilo: {estilo['nombre']} ({estilo['formato']})")
    lista = guion.escenas(texto, estilo)
    print(f"{len(lista)} escenas")

    trabajo = tempfile.mkdtemp(prefix="videosyt-")
    clips = []
    for i, escena in enumerate(lista, 1):
        base = os.path.join(trabajo, f"escena{i:02d}")
        dur = voz.narrar(escena["narracion"], base + ".mp3")
        imagen.generar(escena["prompt_visual"], estilo, tamano, base + ".png", i)
        montaje.clip(base + ".png", base + ".mp3", escena["narracion"], dur, estilo, tamano, base + ".mp4")
        clips.append(base + ".mp4")
        print(f"  escena {i}: {dur:.1f}s")

    montaje.unir(clips, salida)
    print(f"Listo: {salida}")


def modo():
    claves = {"guion": "ANTHROPIC_API_KEY", "voz": "ELEVENLABS_API_KEY", "imagen": "FAL_KEY"}
    return ", ".join(f"{p}={'real' if os.environ.get(k) else 'demo'}" for p, k in claves.items())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea un video a partir de un guion.")
    p.add_argument("guion")
    p.add_argument("--estilo", default="cinematico")
    p.add_argument("--salida", default="video.mp4")
    a = p.parse_args()
    print("Modo:", modo())
    crear_video(a.guion, a.estilo, a.salida)
