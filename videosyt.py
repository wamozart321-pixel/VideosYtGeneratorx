"""Videosyt: de un guion a un video con estilo.

Uso:  python3 videosyt.py ejemplos/guion.txt --estilo cinematico --salida video.mp4
Interfaz:  python3 servidor.py  (o app.py para la ventana de escritorio)

El trabajo se hace en dos fases:
  1. storyboard(): divide el guion y genera solo las imágenes (lo barato). Se puede
     revisar, editar y regenerar escenas sueltas.
  2. renderizar(): genera voces y clips (lo caro) y monta el MP4.
Todo se guarda en la carpeta del proyecto (proyecto.json + archivos), así que se puede
retomar sin repetir llamadas pagadas. Si una IA falla en una escena, se reintenta y,
si sigue fallando, se usa un respaldo para que el video siempre termine.
"""
import argparse
import json
import os
import random
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from proveedores import clip_video, director, guion, imagen, montaje, openai_imagen, voz
from proveedores.reintentos import ErrorDeCuenta, Proveedores, con_reintentos

TAMANOS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}  # 1080p
AQUI = os.path.dirname(os.path.abspath(__file__))
CLAVES = {"voz": "ELEVENLABS_API_KEY", "imagen": "FAL_KEY"}
NOMBRES = {"imagen": "fal.ai (imágenes)", "openai": "OpenAI (imágenes)", "voz": "ElevenLabs (voz)",
           "video": "fal.ai (Kling)"}
# Cuántas llamadas simultáneas acepta cada API sin devolver 429.
LIMITES = {"imagen": 4, "openai": 3, "voz": 2, "video": 2}  # el plan gratis de ElevenLabs admite 2 a la vez
MONTAJES_A_LA_VEZ = max(1, min(4, (os.cpu_count() or 2) // 2))


FUENTES = {"sans": "fuentes/DejaVuSans-Bold.ttf", "serif": "fuentes/DejaVuSerif-Bold.ttf"}
FORMATOS = ("16:9", "9:16")
# Calidad de imagen → modelo de fal.ai, u OpenAI (precio aproximado por imagen en la descripción de la interfaz).
CALIDADES = {"rapida": "fal-ai/flux/schnell", "buena": "fal-ai/flux/dev", "maxima": "fal-ai/flux-pro/v1.1",
             "openai": "openai"}
ESCENA_DE_MUESTRA = ("sitting at a desk late at night, focused and determined",
                     "a desk with an open notebook and a warm lamp late at night")


def estilos():
    """Catálogo compartido con la app de Android (estilos/estilos.json)."""
    with open(os.path.join(AQUI, "estilos", "estilos.json"), encoding="utf-8") as f:
        lista = json.load(f)
    return {e["id"]: {**e, "fondo_demo": "0x" + e["fondo"].lstrip("#"), "fuente": FUENTES[e["fuente"]],
                      "color_texto": "0x" + e["color_texto"].lstrip("#"), "formato": "16:9"}
            for e in lista}


def estilo_de(proyecto):
    """El estilo visual del proyecto con su formato (el formato se elige aparte del estilo)."""
    catalogo = estilos()
    nombre = proyecto["estilo"]
    formato = proyecto.get("formato") or ("9:16" if nombre == "shorts" else "16:9")  # "shorts" era un estilo antes
    return {**catalogo.get(nombre, catalogo["cinematico"]), "formato": formato,
            "modelo": CALIDADES.get(proyecto.get("calidad"), CALIDADES["rapida"]),
            "subtitulos": proyecto.get("subtitulos", True)}


def vista_previa(id_estilo, destino):
    """Imagen de muestra de un estilo para el selector (una llamada a Flux). Requiere FAL_KEY."""
    estilo = {**estilos()[id_estilo], "modelo": CALIDADES["buena"]}
    escena = ESCENA_DE_MUESTRA[0] if estilo["personaje"] else ESCENA_DE_MUESTRA[1]
    return con_reintentos(imagen.generar, escena, estilo, destino, estilo["personaje"], 7, intentos=2)


def modo():
    activos = {paso: bool(os.environ.get(k)) for paso, k in CLAVES.items()}
    activos["imagen"] = activos["imagen"] or bool(os.environ.get("OPENAI_API_KEY"))
    return activos


def _con_openai(estilo):
    return estilo["modelo"] == "openai" and bool(os.environ.get("OPENAI_API_KEY"))


# ---------- proyecto ----------

def nuevo_proyecto(texto, nombre_estilo, carpeta, biblia="", clips=False, formato="16:9", ritmo="normal",
                   calidad="buena", subtitulos=True):
    escenas = guion.escenas(texto, guion.RITMOS[ritmo])
    if not escenas:
        raise ValueError("El guion no tiene texto para narrar")
    semilla = random.randint(0, 2**31 - 1)
    proyecto = {
        "carpeta": carpeta, "estilo": nombre_estilo, "formato": formato, "biblia": biblia.strip(), "clips": bool(clips),
        "ritmo": ritmo, "calidad": calidad, "subtitulos": bool(subtitulos),
        "semilla": semilla, "guion": texto, "avisos": [],
        "escenas": [{**e, "imagen": f"escena{i:02d}.png", "url": None, "estado_imagen": "pendiente",
                     "semilla": (semilla + i) % 2**31, "personaje": True, "version": 0}
                    for i, e in enumerate(escenas, 1)],
    }
    os.makedirs(carpeta, exist_ok=True)
    guardar(proyecto)
    return proyecto


def guardar(proyecto):
    ruta = os.path.join(proyecto["carpeta"], "proyecto.json")
    with open(ruta + ".tmp", "w") as f:
        json.dump(proyecto, f, ensure_ascii=False, indent=1)
    os.replace(ruta + ".tmp", ruta)


def cargar(carpeta):
    with open(os.path.join(carpeta, "proyecto.json")) as f:
        proyecto = json.load(f)
    proyecto["carpeta"] = carpeta
    return proyecto


class _Progreso:
    """Contador seguro entre hilos: avisa del avance según las tareas terminadas."""

    def __init__(self, avisar, desde, hasta, total, texto):
        self.avisar, self.desde, self.hasta, self.total, self.texto = avisar, desde, hasta, max(total, 1), texto
        self.hechas, self._lock = 0, threading.Lock()
        avisar(desde, f"{texto} (0 de {total})")

    def una_mas(self):
        with self._lock:
            self.hechas += 1
            pct = self.desde + int((self.hasta - self.desde) * self.hechas / self.total)
            self.avisar(pct, f"{self.texto} ({self.hechas} de {self.total})")


def _llamar(tipo, proveedores, semaforos, funcion, *args, intentos=4):
    """Llama a una API respetando su límite y con reintentos. Si la cuenta falla, bloquea el proveedor."""
    with semaforos[tipo]:
        motivo = proveedores.motivo(tipo)  # se mira al tener turno: otra llamada pudo bloquearlo mientras esperaba
        if motivo:
            raise ErrorDeCuenta(motivo)
        try:
            return con_reintentos(funcion, *args, intentos=intentos)
        except ErrorDeCuenta as e:
            proveedores.bloquear(tipo, str(e))
            raise


def _semaforos():
    return {k: threading.Semaphore(v) for k, v in LIMITES.items()}


def _avisar_bloqueos(proyecto, proveedores):
    for tipo, nombre in NOMBRES.items():
        motivo = proveedores.motivo(tipo)
        if motivo:
            aviso = f"{nombre} rechazó la cuenta ({motivo}). Se usó un respaldo."
            if aviso not in proyecto["avisos"]:
                proyecto["avisos"].append(aviso)


# ---------- fase 1: storyboard ----------

def _imagen_openai(prompt, estilo, destino, biblia):
    """Como imagen.generar pero con OpenAI; si su filtro la rechaza, se pide una versión más suave."""
    texto = imagen.componer_prompt(prompt, estilo, biblia)
    try:
        openai_imagen.generar(texto, estilo["formato"], destino)
    except openai_imagen.Rechazada:
        try:
            openai_imagen.generar(f"{texto}. {imagen.SUAVE}", estilo["formato"], destino)
        except openai_imagen.Rechazada as e:
            raise imagen.ImagenBloqueada(f"el filtro de contenido de OpenAI la rechazó ({e}); "
                                         "prueba a cambiar la descripción") from e


def _imagen_escena(proyecto, i, estilo, proveedores, semaforos, semilla=None):
    e = proyecto["escenas"][i]
    destino = os.path.join(proyecto["carpeta"], e["imagen"])
    e["aviso"] = None
    biblia = proyecto["biblia"] if e.get("personaje", True) else ""
    fallo_openai = None
    if _con_openai(estilo):
        try:
            _llamar("openai", proveedores, semaforos, _imagen_openai, e["prompt_visual"], estilo, destino, biblia)
            e.update(url=None, estado_imagen="ia")  # sin URL: si se anima, se envía el archivo
            e["version"] += 1
            return
        except Exception as error:  # noqa: BLE001  (si hay clave de fal, se intenta con Flux)
            fallo_openai = f"OpenAI no pudo crear la imagen: {error}"
    if estilo["modelo"] == "openai":  # sin clave de OpenAI o si falló: Flux dev
        estilo = {**estilo, "modelo": CALIDADES["buena"]}
    if os.environ.get("FAL_KEY"):
        try:
            if semilla is None:  # proyectos anteriores no guardaban una semilla por escena
                semilla = e.get("semilla", (proyecto["semilla"] + i + 1) % 2**31)
            e["url"] = _llamar("imagen", proveedores, semaforos, imagen.generar, e["prompt_visual"], estilo,
                               destino, biblia, semilla)
            e.update(estado_imagen="ia", aviso=fallo_openai and f"{fallo_openai}. Se hizo con Flux.")
        except Exception as error:  # noqa: BLE001  (cualquier fallo de la API → respaldo)
            e.update(url=None, estado_imagen="fallida", aviso=fallo_openai or f"No se pudo crear la imagen: {error}")
    elif fallo_openai:
        e.update(url=None, estado_imagen="fallida", aviso=fallo_openai)
    else:
        imagen.tarjeta_demo(e["prompt_visual"], estilo, TAMANOS[estilo["formato"]], destino, i + 1)
        e.update(url=None, estado_imagen="demo")
    e["version"] += 1


def _resolver_respaldos(proyecto, estilo):
    """Las escenas cuya imagen falló reutilizan la imagen IA más cercana (preferentemente la anterior)."""
    escenas = proyecto["escenas"]
    buenas = [j for j, e in enumerate(escenas) if e["estado_imagen"] == "ia"]
    for i, e in enumerate(escenas):
        if e["estado_imagen"] not in ("fallida", "respaldo"):
            continue
        destino = os.path.join(proyecto["carpeta"], e["imagen"])
        if buenas:
            origen = min(buenas, key=lambda j: (abs(j - i), j > i))
            shutil.copyfile(os.path.join(proyecto["carpeta"], escenas[origen]["imagen"]), destino)
            e.update(estado_imagen="respaldo", url=escenas[origen]["url"], respaldo_de=origen + 1)
        else:
            imagen.tarjeta_demo(e["prompt_visual"], estilo, TAMANOS[estilo["formato"]], destino, i + 1)
            e.update(estado_imagen="respaldo", url=None, respaldo_de=None)
        e["version"] += 1


def dirigir(proyecto, avisar=lambda *_: None):
    """Cambia el texto narrado de cada escena por una descripción visual propia (una vez por proyecto).

    Las escenas con indicación visual escrita en el guion (Imagen: ...) se respetan."""
    if proyecto.get("dirigido") or not os.environ.get("FAL_KEY"):
        return
    avisar(1, "Pensando qué mostrar en cada escena")
    escenas = proyecto["escenas"]
    try:
        descripciones = director.describir(proyecto["guion"], [e["narracion"] for e in escenas], proyecto["biblia"])
    except Exception as error:  # noqa: BLE001  (sin director, las imágenes usan el texto del guion)
        proyecto["avisos"].append(f"No se pudo describir cada escena con IA ({error}); "
                                  "las imágenes se basan en el texto del guion.")
        return
    for n, e in enumerate(escenas, 1):
        if n in descripciones and not e.get("visual_propio"):
            e["prompt_visual"], e["personaje"] = descripciones[n]
    proyecto["dirigido"] = True
    guardar(proyecto)


def storyboard(proyecto, avisar=lambda *_: None):
    """Genera en paralelo las imágenes de todas las escenas."""
    estilo = estilo_de(proyecto)
    dirigir(proyecto, avisar)
    proveedores, semaforos = Proveedores(), _semaforos()
    escenas = proyecto["escenas"]
    progreso = _Progreso(avisar, 2, 98, len(escenas), "Creando imágenes")

    def tarea(i):
        _imagen_escena(proyecto, i, estilo, proveedores, semaforos)
        progreso.una_mas()

    with ThreadPoolExecutor(max_workers=LIMITES["imagen"] + 2) as pool:
        list(pool.map(tarea, range(len(escenas))))
    _resolver_respaldos(proyecto, estilo)
    _avisar_bloqueos(proyecto, proveedores)
    guardar(proyecto)
    avisar(100, "Storyboard listo")


def editar_escena(proyecto, i, narracion=None, prompt_visual=None):
    e = proyecto["escenas"][i]
    if narracion is not None and narracion.strip():
        e["narracion"] = narracion.strip()
    if prompt_visual is not None and prompt_visual.strip() and prompt_visual.strip() != e["prompt_visual"]:
        e["prompt_visual"] = prompt_visual.strip()
        e["visual_propio"] = True
    guardar(proyecto)


def regenerar_escena(proyecto, i, nueva_semilla=True):
    """Vuelve a crear la imagen de una escena. Con nueva_semilla sale una variación distinta."""
    estilo = estilo_de(proyecto)
    e = proyecto["escenas"][i]
    if nueva_semilla:
        e["semilla"] = random.randint(0, 2**31 - 1)
    _imagen_escena(proyecto, i, estilo, Proveedores(), _semaforos(), e.get("semilla"))
    if e["estado_imagen"] == "fallida":
        _resolver_respaldos(proyecto, estilo)
    guardar(proyecto)


# ---------- fase 2: render ----------

def renderizar(proyecto, salida, avisar=lambda *_: None):
    estilo = estilo_de(proyecto)
    tamano = TAMANOS[estilo["formato"]]
    carpeta, escenas = proyecto["carpeta"], proyecto["escenas"]
    proveedores, semaforos = Proveedores(), _semaforos()
    usar_clips = proyecto["clips"] and bool(os.environ.get("FAL_KEY"))
    duraciones, animados = [0.0] * len(escenas), [None] * len(escenas)

    # Voces y clips de todas las escenas a la vez (cada API con su límite).
    tareas = len(escenas) * (2 if usar_clips else 1)
    progreso = _Progreso(avisar, 2, 70, tareas, "Generando voces y clips" if usar_clips else "Generando voces")

    def tarea_voz(i):
        e, audio = escenas[i], os.path.join(carpeta, f"escena{i + 1:02d}.mp3")
        try:
            if os.environ.get("ELEVENLABS_API_KEY"):
                duraciones[i] = _llamar("voz", proveedores, semaforos, voz.narrar, e["narracion"], audio)
            else:
                duraciones[i] = voz.narrar(e["narracion"], audio)
        except Exception as error:  # noqa: BLE001  (respaldo: silencio con la duración estimada)
            e["aviso_voz"] = f"Voz no disponible: {error}"
            duraciones[i] = voz.silencio(e["narracion"], audio)
        progreso.una_mas()

    def tarea_clip(i):
        e, destino = escenas[i], os.path.join(carpeta, f"escena{i + 1:02d}_clip.mp4")
        fuente = e.get("url")
        if not fuente and (e["estado_imagen"] == "ia" or e.get("respaldo_de")):
            fuente = clip_video.como_dato(os.path.join(carpeta, e["imagen"]))  # imagen de OpenAI: no tiene URL
        if fuente:
            try:
                _llamar("video", proveedores, semaforos, clip_video.animar, fuente, e["prompt_visual"],
                        estilo, destino, intentos=2)
                animados[i] = destino
            except Exception as error:  # noqa: BLE001  (respaldo: imagen con zoom)
                e["aviso_clip"] = f"Clip no disponible: {error}"
        progreso.una_mas()

    with ThreadPoolExecutor(max_workers=sum(LIMITES.values())) as pool:
        trabajos = [pool.submit(tarea_voz, i) for i in range(len(escenas))]
        if usar_clips:
            trabajos += [pool.submit(tarea_clip, i) for i in range(len(escenas))]
        for t in trabajos:
            t.result()

    # Montaje de cada escena en paralelo según los núcleos del equipo.
    progreso = _Progreso(avisar, 70, 96, len(escenas), "Montando escenas")
    clips = [os.path.join(carpeta, f"escena{i + 1:02d}.mp4") for i in range(len(escenas))]

    def montar(i):
        e = escenas[i]
        montaje.clip(os.path.join(carpeta, e["imagen"]), os.path.join(carpeta, f"escena{i + 1:02d}.mp3"),
                     e["narracion"], duraciones[i], estilo, tamano, clips[i], video=animados[i],
                     zoom_inverso=e["estado_imagen"] == "respaldo")
        progreso.una_mas()

    with ThreadPoolExecutor(max_workers=MONTAJES_A_LA_VEZ) as pool:
        list(pool.map(montar, range(len(escenas))))

    avisar(97, "Uniendo escenas")
    montaje.unir(clips, salida)
    _avisar_bloqueos(proyecto, proveedores)
    guardar(proyecto)
    avisar(100, "Listo")


def resumen_respaldos(proyecto):
    """Texto corto para el usuario con lo que no salió con IA."""
    escenas = proyecto["escenas"]
    respaldo = [i + 1 for i, e in enumerate(escenas) if e["estado_imagen"] == "respaldo"]
    sin_voz = [i + 1 for i, e in enumerate(escenas) if e.get("aviso_voz")]
    sin_clip = [i + 1 for i, e in enumerate(escenas) if e.get("aviso_clip")]
    partes = []
    if respaldo:
        partes.append(f"imagen de respaldo en escena(s) {', '.join(map(str, respaldo))}")
    if sin_voz:
        motivo = escenas[sin_voz[0] - 1]["aviso_voz"]  # dice qué arreglar (cuota, demasiadas a la vez...)
        partes.append(f"sin voz en escena(s) {', '.join(map(str, sin_voz))} ({motivo})")
    if sin_clip:
        partes.append(f"sin clip animado en escena(s) {', '.join(map(str, sin_clip))}")
    return "; ".join(partes)


def crear_video(texto, nombre_estilo, salida, avisar=print, usar_clips=False, biblia="", formato="16:9", **opciones):
    """Flujo completo sin pausa para revisar (línea de comandos y prueba del .exe)."""
    proyecto = nuevo_proyecto(texto, nombre_estilo, tempfile.mkdtemp(prefix="videosyt-"), biblia, usar_clips,
                              formato, **opciones)
    storyboard(proyecto, lambda pct, msg: avisar(pct // 3, msg))
    renderizar(proyecto, salida, lambda pct, msg: avisar(33 + pct * 2 // 3, msg))
    return proyecto


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea un video a partir de un guion.")
    p.add_argument("guion")
    p.add_argument("--estilo", default="cinematico")
    p.add_argument("--formato", default="16:9", choices=FORMATOS)
    p.add_argument("--ritmo", default="normal", choices=guion.RITMOS, help="cuántas escenas por minuto")
    p.add_argument("--calidad", default="buena", choices=CALIDADES, help="modelo de imagen")
    p.add_argument("--sin-subtitulos", action="store_true")
    p.add_argument("--salida", default="video.mp4")
    p.add_argument("--biblia", default="", help="personajes y estilo fijos para todas las escenas")
    p.add_argument("--clips", action="store_true", help="anima cada escena con Kling (requiere FAL_KEY)")
    a = p.parse_args()
    print("Modo:", ", ".join(f"{k}={'real' if v else 'demo'}" for k, v in modo().items()))
    inicio = time.time()
    with open(a.guion) as f:
        proyecto = crear_video(f.read(), a.estilo, a.salida, lambda pct, msg: print(f"[{pct:3d}%] {msg}"),
                               a.clips, a.biblia, a.formato, ritmo=a.ritmo, calidad=a.calidad,
                               subtitulos=not a.sin_subtitulos)
    for aviso in proyecto["avisos"]:
        print("Aviso:", aviso)
    if resumen_respaldos(proyecto):
        print("Respaldos:", resumen_respaldos(proyecto))
    print(f"Listo: {a.salida} ({time.time() - inicio:.1f} s)")
