"""Videosyt como programa de escritorio (es lo que se empaqueta en Videosyt.exe).

Abre la interfaz en una ventana propia. Los videos y las claves se guardan en la
carpeta Videosyt dentro de tu carpeta de usuario.
"""
import os
import sys

if getattr(sys, "frozen", False):
    # Dentro del .exe: FFmpeg viene incluido junto al programa.
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("VIDEOSYT_DATOS", os.path.join(os.path.expanduser("~"), "Videosyt"))

import servidor  # noqa: E402  (necesita el PATH y la carpeta de datos de arriba)
import videosyt  # noqa: E402


def prueba():
    """Genera un video demo sin abrir ventanas; lo usa GitHub para verificar el .exe."""
    os.makedirs(servidor.SALIDA, exist_ok=True)
    destino = os.path.join(servidor.SALIDA, "prueba.mp4")
    videosyt.crear_video("Primera escena de prueba.\n\nSegunda escena de prueba.", "cinematico",
                         destino, lambda *_: None)
    print("OK", destino, os.path.getsize(destino))


def main():
    if os.environ.get("VIDEOSYT_PRUEBA"):
        return prueba()
    direccion, _ = servidor.iniciar(0)
    try:
        import webview
    except ImportError:
        import threading
        import webbrowser
        webbrowser.open(direccion)
        threading.Event().wait()
        return
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window("Videosyt", direccion, width=1280, height=860, min_size=(420, 600))
    webview.start()


if __name__ == "__main__":
    main()
