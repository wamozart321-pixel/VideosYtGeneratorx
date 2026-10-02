"""Paso 2: narración. ElevenLabs si hay clave; si no, silencio con la duración estimada."""
import os
import re

from . import ejecutar
from .http import post


def narrar(texto, destino):
    clave = os.environ.get("ELEVENLABS_API_KEY")
    if clave:
        voz = os.environ.get("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
        audio = post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voz}",
            {"xi-api-key": clave, "accept": "audio/mpeg"},
            {"text": texto, "model_id": "eleven_multilingual_v2"},
            binario=True,
        )
        with open(destino, "wb") as f:
            f.write(audio)
        return duracion(destino)
    return silencio(texto, destino)


def silencio(texto, destino):
    """Audio en silencio con la duración que tendría la narración (~150 palabras por minuto)."""
    segundos = max(3.0, len(texto.split()) / 2.5)
    ejecutar.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{segundos:.2f}", destino],
        check=True,
    )
    return duracion(destino)


def duracion(archivo):
    # Se lee de la salida de FFmpeg para no depender de ffprobe.
    salida = ejecutar.run(["ffmpeg", "-hide_banner", "-i", archivo], capture_output=True, text=True)
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", salida.stderr).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)
