"""Actualización automática del .exe desde la descarga publicada en GitHub.

Al abrir, la app compara su número de versión (version.txt, lo escribe GitHub al
compilar) con el de la última publicación. Si hay una nueva, la interfaz ofrece
"Actualizar": se descarga el .exe nuevo, la app se cierra, se reemplaza el archivo
y se vuelve a abrir. Las claves y los proyectos están en la carpeta de datos del
usuario, así que se conservan.
"""
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

REPO = "wamozart321-pixel/VideosYtGeneratorx"
ETIQUETA = "windows-ultima"
AQUI = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

estado = {"actual": 0, "disponible": 0, "descargando": False, "progreso": 0, "error": ""}
_url = None


def version_actual():
    try:
        with open(os.path.join(AQUI, "version.txt")) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0  # ejecutado desde el código: no se actualiza solo


def _pedir(url):
    req = urllib.request.Request(url, headers={"user-agent": "Videosyt", "accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=30)


def ultima_publicada():
    """Devuelve (versión, url del .exe) de la última publicación, o (0, None)."""
    with _pedir(f"https://api.github.com/repos/{REPO}/releases/tags/{ETIQUETA}") as r:
        datos = json.load(r)
    m = re.search(r"versi[oó]n (\d+)", datos.get("name") or "")
    exe = next((a["browser_download_url"] for a in datos.get("assets", []) if a["name"].endswith(".exe")), None)
    return (int(m.group(1)), exe) if m and exe else (0, None)


def comprobar():
    global _url
    estado["actual"] = version_actual()
    if not estado["actual"] or not getattr(sys, "frozen", False):
        return
    try:
        version, _url = ultima_publicada()
        if version > estado["actual"]:
            estado["disponible"] = version
    except Exception:  # noqa: BLE001  (sin internet o GitHub no responde: se intenta en la próxima apertura)
        pass


def comprobar_en_segundo_plano():
    threading.Thread(target=comprobar, daemon=True).start()


def _descargar(destino):
    with _pedir(_url) as r, open(destino, "wb") as f:
        total = int(r.headers.get("content-length") or 0)
        hecho = 0
        while bloque := r.read(1 << 16):
            f.write(bloque)
            hecho += len(bloque)
            if total:
                estado["progreso"] = int(100 * hecho / total)


def _reemplazar_y_reiniciar(nuevo):
    """Un PowerShell oculto espera a que la app se cierre, cambia el .exe y la vuelve a abrir."""
    actual = sys.executable.replace("'", "''")  # comillas escapadas para PowerShell
    nuevo = nuevo.replace("'", "''")
    pids = ",".join(str(p) for p in {os.getpid(), os.getppid()})  # el .exe de un archivo usa dos procesos
    script = (
        f"Wait-Process -Id {pids} -ErrorAction SilentlyContinue; "
        f"for ($i = 0; $i -lt 20; $i++) {{ try {{ Move-Item -Force -LiteralPath '{nuevo}' '{actual}' -ErrorAction Stop; break }} "
        f"catch {{ Start-Sleep -Milliseconds 500 }} }}; "
        f"Start-Process -FilePath '{actual}'"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
                     close_fds=True)
    threading.Timer(1.0, os._exit, [0]).start()


def instalar():
    if estado["descargando"] or not estado["disponible"] or not _url:
        return
    estado.update(descargando=True, progreso=0, error="")
    nuevo = os.path.join(os.path.dirname(sys.executable), "Videosyt.nuevo.exe")
    try:
        _descargar(nuevo)
        _reemplazar_y_reiniciar(nuevo)
    except Exception as e:  # noqa: BLE001  (se muestra en la interfaz)
        estado.update(descargando=False, error=f"No se pudo actualizar: {e}")


def instalar_en_segundo_plano():
    threading.Thread(target=instalar, daemon=True).start()
