"""Interfaz de Videosyt. Corre solo en tu computadora; no necesita hosting.

Uso:  python3 servidor.py   (abre el navegador solo en http://localhost:8000)
Los videos se guardan en la carpeta salida/ y las claves de API en config.json.
"""
import json
import os
import queue
import re
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import videosyt

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "salida")
CONFIG = os.path.join(AQUI, "config.json")
PUERTO = int(os.environ.get("PORT", "8000"))
OPCIONALES = ["ELEVENLABS_VOICE_ID", "CLAUDE_MODEL"]

trabajos = {}
cola = queue.Queue()


# ---------- configuración (claves de API) ----------

def cargar_config():
    if os.path.exists(CONFIG):
        with open(CONFIG) as f:
            for k, v in json.load(f).items():
                if v:
                    os.environ[k] = v


def guardar_config(nuevas):
    actual = {}
    if os.path.exists(CONFIG):
        with open(CONFIG) as f:
            actual = json.load(f)
    for k in [*videosyt.CLAVES.values(), *OPCIONALES]:
        if k in nuevas:
            valor = nuevas[k].strip()
            actual[k] = valor
            if valor:
                os.environ[k] = valor
            else:
                os.environ.pop(k, None)
    with open(CONFIG, "w") as f:
        json.dump(actual, f, indent=2)


# ---------- trabajos en segundo plano ----------

def trabajador():
    while True:
        id_ = cola.get()
        t = trabajos[id_]
        t["estado"] = "generando"

        def avisar(pct, msg):
            t["progreso"], t["mensaje"] = pct, msg

        try:
            t["escenas"] = videosyt.crear_video(
                t["guion"], t["estilo"], os.path.join(SALIDA, f"{id_}.mp4"), avisar, t["clips"])
            t["estado"] = "listo"
        except Exception as e:  # se muestra en la interfaz
            traceback.print_exc()
            t["estado"], t["mensaje"] = "error", f"{type(e).__name__}: {e}"


def resumen(t):
    return {k: t[k] for k in ("id", "titulo", "estilo", "estado", "progreso", "mensaje", "creado", "clips")}


# ---------- HTTP ----------

class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer(self):
        largo = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(largo) or b"{}")

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta == "/":
            return self._archivo(os.path.join(AQUI, "web", "index.html"), "text/html; charset=utf-8")
        if ruta == "/api/estado":
            claves = {k: bool(os.environ.get(k)) for k in videosyt.CLAVES.values()}
            claves.update({k: os.environ.get(k, "") for k in OPCIONALES})
            return self._json({"estilos": videosyt.estilos(), "modo": videosyt.modo(), "claves": claves})
        if ruta == "/api/videos":
            lista = sorted(trabajos.values(), key=lambda t: t["creado"], reverse=True)
            return self._json([resumen(t) for t in lista])
        m = re.fullmatch(r"/api/videos/([a-f0-9]+)", ruta)
        if m and m.group(1) in trabajos:
            return self._json(resumen(trabajos[m.group(1)]))
        m = re.fullmatch(r"/videos/([a-f0-9]+)\.mp4", ruta)
        if m and os.path.exists(os.path.join(SALIDA, f"{m.group(1)}.mp4")):
            return self._archivo(os.path.join(SALIDA, f"{m.group(1)}.mp4"), "video/mp4")
        self._json({"error": "no encontrado"}, 404)

    def do_POST(self):
        if self.path == "/api/videos":
            datos = self._leer()
            texto = (datos.get("guion") or "").strip()
            if not texto:
                return self._json({"error": "El guion está vacío"}, 400)
            if datos.get("estilo") not in videosyt.estilos():
                return self._json({"error": "Estilo desconocido"}, 400)
            id_ = uuid.uuid4().hex[:12]
            primera = texto.splitlines()[0]
            trabajos[id_] = {
                "id": id_, "guion": texto, "estilo": datos["estilo"], "clips": bool(datos.get("clips")),
                "titulo": primera[:60] + ("…" if len(primera) > 60 else ""),
                "estado": "en cola", "progreso": 0, "mensaje": "Esperando turno", "creado": time.time(),
            }
            cola.put(id_)
            return self._json(resumen(trabajos[id_]), 201)
        if self.path == "/api/config":
            guardar_config(self._leer())
            return self._json({"ok": True})
        self._json({"error": "no encontrado"}, 404)

    def _archivo(self, ruta, tipo):
        tamano = os.path.getsize(ruta)
        inicio, fin = 0, tamano - 1
        rango = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("range", ""))
        if rango and (rango.group(1) or rango.group(2)):
            if rango.group(1):
                inicio = int(rango.group(1))
                fin = int(rango.group(2)) if rango.group(2) else fin
            else:
                inicio = max(0, tamano - int(rango.group(2)))
            fin = min(fin, tamano - 1)
            self.send_response(206)
            self.send_header("content-range", f"bytes {inicio}-{fin}/{tamano}")
        else:
            self.send_response(200)
        self.send_header("content-type", tipo)
        self.send_header("accept-ranges", "bytes")
        self.send_header("content-length", str(fin - inicio + 1))
        self.end_headers()
        with open(ruta, "rb") as f:
            f.seek(inicio)
            restante = fin - inicio + 1
            while restante > 0:
                bloque = f.read(min(65536, restante))
                if not bloque:
                    break
                self.wfile.write(bloque)
                restante -= len(bloque)


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    cargar_config()
    threading.Thread(target=trabajador, daemon=True).start()
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    direccion = f"http://localhost:{PUERTO}"
    print(f"Videosyt abierto en {direccion}  (cierra esta ventana para salir)")
    if not os.environ.get("VIDEOSYT_SIN_NAVEGADOR"):
        threading.Timer(1, webbrowser.open, [direccion]).start()
    servidor.serve_forever()
