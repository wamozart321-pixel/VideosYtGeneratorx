"""Ejecuta FFmpeg sin abrir ventanas de consola en Windows."""
import subprocess
import sys

SIN_VENTANA = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def run(args, **kwargs):
    return subprocess.run(args, **SIN_VENTANA, **kwargs)
