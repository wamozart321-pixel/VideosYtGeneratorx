"""Paso 2: narración. ElevenLabs si hay clave; si no, silencio con la duración estimada."""
import os
import subprocess

from .http import post

VOZ = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")


def narrar(texto, destino):
    clave = os.environ.get("ELEVENLABS_API_KEY")
    if clave:
        audio = post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}",
            {"xi-api-key": clave, "accept": "audio/mpeg"},
            {"text": texto, "model_id": "eleven_multilingual_v2"},
            binario=True,
        )
        with open(destino, "wb") as f:
            f.write(audio)
    else:
        segundos = max(3.0, len(texto.split()) / 2.5)  # ~150 palabras por minuto
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{segundos:.2f}", destino],
            check=True,
        )
    return duracion(destino)


def duracion(archivo):
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", archivo],
        capture_output=True, text=True, check=True,
    )
    return float(salida.stdout.strip())
