"""Interfaz de Videosyt. Corre solo en tu computadora; no necesita hosting.

Uso:  python3 servidor.py   (abre el navegador solo en http://localhost:8000)
Los proyectos se guardan en proyectos/, los videos terminados en salida/ y las
claves de API en config.json.
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import actualizar
import videosyt

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.environ.get("VIDEOSYT_DATOS") or AQUI  # donde se guardan proyectos, videos y claves
SALIDA = os.path.join(DATOS, "salida")
PROYECTOS = os.path.join(DATOS, "proyectos")
VISTAS = os.path.join(DATOS, "vistas")  # imágenes de muestra de cada estilo
CONFIG = os.path.join(DATOS, "config.json")
PUERTO = int(os.environ.get("PORT", "8000"))
OPCIONALES = ["ELEVENLABS_VOICE_ID"]
SECRETAS = [*videosyt.CLAVES.values(), "OPENAI_API_KEY"]  # la interfaz solo sabe si están puestas
OCUPADO = {"en cola", "storyboard", "render"}

proyectos = {}
cola = queue.Queue()
vistas = {"generando": False, "error": ""}


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
    for k in [*SECRETAS, *OPCIONALES]:
        if k in nuevas:
            valor = nuevas[k].strip()
            actual[k] = valor
            if valor:
                os.environ[k] = valor
            else:
                os.environ.pop(k, None)
    with open(CONFIG, "w") as f:
        json.dump(actual, f, indent=2)


# ---------- proyectos y trabajos en segundo plano ----------

def cargar_proyectos():
    if not os.path.isdir(PROYECTOS):
        return
    for id_ in os.listdir(PROYECTOS):
        try:
            p = videosyt.cargar(os.path.join(PROYECTOS, id_))
        except (OSError, ValueError):
            continue
        if p.get("fase") in OCUPADO:  # la app se cerró a mitad de un trabajo
            p.update(fase="error" if not p.get("escenas_listas") else "storyboard_listo",
                     mensaje="Se interrumpió al cerrar la app. Puedes volver a intentarlo.")
        proyectos[id_] = p


def trabajador():
    while True:
        id_, tarea = cola.get()
        p = proyectos[id_]

        def avisar(pct, msg):
            p["progreso"], p["mensaje"] = pct, msg

        try:
            if tarea == "storyboard":
                p["fase"] = "storyboard"
                videosyt.storyboard(p, avisar)
                p.update(fase="storyboard_listo", escenas_listas=True, mensaje="Revisa las escenas")
            elif tarea == "render":
                p["fase"] = "render"
                destino = os.path.join(SALIDA, f"videosyt-{id_}.mp4")
                videosyt.renderizar(p, destino, avisar)
                p.update(fase="listo", video=destino, mensaje=videosyt.resumen_respaldos(p) or "Listo")
        except Exception as e:  # se muestra en la interfaz
            traceback.print_exc()
            p.update(fase="error" if not p.get("escenas_listas") else "storyboard_listo",
                     mensaje=f"No se pudo terminar: {type(e).__name__}: {e}")
        videosyt.guardar(p)


def regenerar(p, i):
    try:
        videosyt.regenerar_escena(p, i)
    except Exception:  # noqa: BLE001  (el estado de la escena ya refleja el fallo)
        traceback.print_exc()
    finally:
        p["escenas"][i]["regenerando"] = False


def vistas_listas():
    return {id_: int(os.path.getmtime(os.path.join(VISTAS, f"{id_}.png")))
            for id_ in videosyt.estilos() if os.path.exists(os.path.join(VISTAS, f"{id_}.png"))}


def crear_vistas():
    """Genera en segundo plano las muestras de los estilos que aún no tienen."""
    faltan = [id_ for id_ in videosyt.estilos() if id_ not in vistas_listas()]
    vistas["error"] = ""
    try:
        with ThreadPoolExecutor(videosyt.LIMITES["imagen"]) as grupo:
            for futuro in [grupo.submit(videosyt.vista_previa, id_, os.path.join(VISTAS, f"{id_}.png"))
                           for id_ in faltan]:
                try:
                    futuro.result()
                except Exception as e:  # noqa: BLE001  (se muestra en la interfaz)
                    vistas["error"] = f"No se pudieron crear algunas vistas previas: {e}"
    finally:
        vistas["generando"] = False


def resumen(p):
    return {"id": p["id"], "titulo": p["titulo"], "estilo": p["estilo"], "fase": p.get("fase"),
            "progreso": p.get("progreso", 0), "mensaje": p.get("mensaje", ""), "creado": p["creado"]}


def detalle(p):
    datos = resumen(p)
    datos.update(formato=videosyt.estilo_de(p)["formato"], biblia=p["biblia"], clips=p["clips"], avisos=p["avisos"], tiene_video=bool(p.get("video")),
                 escenas=[{"narracion": e["narracion"], "prompt_visual": e["prompt_visual"],
                           "estado": e["estado_imagen"], "respaldo_de": e.get("respaldo_de"),
                           "aviso": e.get("aviso"), "regenerando": e.get("regenerando", False),
                           "imagen": f"/archivos/{p['id']}/{e['imagen']}?v={e['version']}"}
                          for e in p["escenas"]])
    return datos


def abrir_carpeta(ruta):
    if sys.platform == "win32":
        os.startfile(ruta)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])


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

    def _proyecto(self, id_):
        p = proyectos.get(id_)
        if not p:
            self._json({"error": "Proyecto no encontrado"}, 404)
        return p

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta == "/":
            return self._archivo(os.path.join(AQUI, "web", "index.html"), "text/html; charset=utf-8")
        if ruta == "/api/estado":
            claves = {k: bool(os.environ.get(k)) for k in SECRETAS}
            claves.update({k: os.environ.get(k, "") for k in OPCIONALES})
            return self._json({"estilos": videosyt.estilos(), "modo": videosyt.modo(), "claves": claves,
                               "vistas": vistas_listas(), "vistas_estado": vistas,
                               "actualizacion": actualizar.estado})
        if ruta == "/api/proyectos":
            lista = sorted(proyectos.values(), key=lambda p: p["creado"], reverse=True)
            return self._json([resumen(p) for p in lista])
        m = re.fullmatch(r"/api/proyectos/([a-f0-9]+)", ruta)
        if m:
            p = self._proyecto(m.group(1))
            return p and self._json(detalle(p))
        m = re.fullmatch(r"/archivos/([a-f0-9]+)/(escena\d+\.png)", ruta)
        if m and m.group(1) in proyectos:
            archivo = os.path.join(proyectos[m.group(1)]["carpeta"], m.group(2))
            if os.path.exists(archivo):
                return self._archivo(archivo, "image/png")
        m = re.fullmatch(r"/vistas/([a-z0-9-]+)\.png", ruta)
        if m and os.path.exists(os.path.join(VISTAS, m.group(1) + ".png")):
            return self._archivo(os.path.join(VISTAS, m.group(1) + ".png"), "image/png")
        m = re.fullmatch(r"/videos/([a-f0-9]+)\.mp4", ruta)
        if m and proyectos.get(m.group(1), {}).get("video") and os.path.exists(proyectos[m.group(1)]["video"]):
            return self._archivo(proyectos[m.group(1)]["video"], "video/mp4")
        self._json({"error": "no encontrado"}, 404)

    def do_POST(self):
        ruta = self.path.split("?")[0]
        if ruta == "/api/proyectos":
            return self._crear(self._leer())
        m = re.fullmatch(r"/api/proyectos/([a-f0-9]+)/(render|escenas/(\d+)(/regenerar)?)", ruta)
        if m:
            p = self._proyecto(m.group(1))
            if not p:
                return
            if p.get("fase") in OCUPADO:
                return self._json({"error": "Espera a que termine el trabajo en curso"}, 409)
            if m.group(2) == "render":
                p.update(fase="en cola", progreso=0, mensaje="Esperando turno")
                cola.put((p["id"], "render"))
                return self._json(resumen(p))
            i = int(m.group(3)) - 1
            if not 0 <= i < len(p["escenas"]):
                return self._json({"error": "Escena inexistente"}, 404)
            if m.group(4):
                p["escenas"][i]["regenerando"] = True
                threading.Thread(target=regenerar, args=(p, i), daemon=True).start()
            else:
                datos = self._leer()
                videosyt.editar_escena(p, i, datos.get("narracion"), datos.get("prompt_visual"))
            return self._json(detalle(p))
        if ruta == "/api/actualizar":
            actualizar.instalar_en_segundo_plano()
            return self._json(actualizar.estado)
        if ruta == "/api/vistas":
            if not os.environ.get("FAL_KEY"):
                return self._json({"error": "Configura la clave de fal.ai para crear las vistas previas"}, 400)
            if not vistas["generando"]:
                vistas["generando"] = True
                threading.Thread(target=crear_vistas, daemon=True).start()
            return self._json(vistas)
        if ruta == "/api/abrir-carpeta":
            os.makedirs(SALIDA, exist_ok=True)
            abrir_carpeta(SALIDA)
            return self._json({"ok": True})
        if ruta == "/api/config":
            guardar_config(self._leer())
            return self._json({"ok": True})
        self._json({"error": "no encontrado"}, 404)

    def _crear(self, datos):
        texto = (datos.get("guion") or "").strip()
        if not texto:
            return self._json({"error": "El guion está vacío"}, 400)
        if datos.get("estilo") not in videosyt.estilos():
            return self._json({"error": "Estilo desconocido"}, 400)
        formato, ritmo, calidad = datos.get("formato") or "16:9", datos.get("ritmo") or "normal", datos.get("calidad") or "buena"
        if formato not in videosyt.FORMATOS or ritmo not in videosyt.guion.RITMOS or calidad not in videosyt.CALIDADES:
            return self._json({"error": "Opción desconocida"}, 400)
        id_ = uuid.uuid4().hex[:12]
        try:
            p = videosyt.nuevo_proyecto(texto, datos["estilo"], os.path.join(PROYECTOS, id_),
                                        datos.get("biblia") or "", datos.get("clips"), formato,
                                        ritmo, calidad, datos.get("subtitulos", True))
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        primera = next(e["narracion"] for e in p["escenas"])
        p.update(id=id_, titulo=primera[:60] + ("…" if len(primera) > 60 else ""), creado=time.time(),
                 fase="en cola", progreso=0, mensaje="Esperando turno")
        proyectos[id_] = p
        videosyt.guardar(p)
        cola.put((id_, "storyboard"))
        return self._json(resumen(p), 201)

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


def iniciar(puerto=PUERTO):
    """Arranca el servidor en segundo plano y devuelve su dirección."""
    os.makedirs(SALIDA, exist_ok=True)
    os.makedirs(PROYECTOS, exist_ok=True)
    os.makedirs(VISTAS, exist_ok=True)
    cargar_config()
    cargar_proyectos()
    actualizar.comprobar_en_segundo_plano()
    threading.Thread(target=trabajador, daemon=True).start()
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return f"http://localhost:{servidor.server_address[1]}", servidor


if __name__ == "__main__":
    direccion, servidor = iniciar()
    print(f"Videosyt abierto en {direccion}  (cierra esta ventana para salir)")
    if not os.environ.get("VIDEOSYT_SIN_NAVEGADOR"):
        threading.Timer(1, webbrowser.open, [direccion]).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
