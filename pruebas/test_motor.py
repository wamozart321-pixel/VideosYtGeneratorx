"""Pruebas del motor sin gastar créditos: las APIs se simulan.

Ejecutar:  python3 -m unittest discover pruebas
"""
import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from unittest import mock

import videosyt
from proveedores import clip_video, director, guion, imagen, openai_imagen, reintentos, voz

reintentos.time.sleep = lambda s: None  # sin esperas reales entre reintentos


def error_http(codigo, cuerpo=b"{}"):
    return urllib.error.HTTPError("https://api", codigo, "error", {}, io.BytesIO(cuerpo))


class Guion(unittest.TestCase):
    def test_formato_scripzy(self):
        texto = ("ESCENA 1\nNarrador: Hace mucho tiempo.\nImagen: an ancient ocean\n\n"
                 "[glowing cells]\n\nNacio la vida.\n\nEscena 3:\nHoy seguimos aqui.")
        e = guion.escenas(texto)
        self.assertEqual([x["narracion"] for x in e], ["Hace mucho tiempo.", "Nacio la vida.", "Hoy seguimos aqui."])
        self.assertEqual([x["prompt_visual"] for x in e], ["an ancient ocean", "glowing cells", "Hoy seguimos aqui."])


    def test_parrafo_largo_se_parte_en_varias_escenas(self):
        parrafo = " ".join(f"Esta es la oración número {n} del párrafo." for n in range(1, 13))  # 84 palabras
        normal, muchas = guion.escenas(parrafo), guion.escenas(parrafo, guion.RITMOS["muchas"])
        self.assertGreaterEqual(len(normal), 5)
        self.assertGreater(len(muchas), len(normal))
        self.assertEqual(" ".join(e["narracion"] for e in normal), parrafo)  # no se pierde ni repite texto
        self.assertTrue(all(len(e["narracion"].split()) <= 20 for e in normal))

    def test_indicacion_visual_solo_en_la_primera_escena_del_parrafo(self):
        parrafo = "Imagen: a stormy sea\n" + " ".join(f"Oración {n} con varias palabras más." for n in range(8))
        e = guion.escenas(parrafo)
        self.assertEqual(e[0]["prompt_visual"], "a stormy sea")
        self.assertEqual(e[1]["prompt_visual"], e[1]["narracion"])

    def test_subtitulos_cortos(self):
        trozos = guion.subtitulos("uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece", 7)
        self.assertEqual([len(t.split()) for t in trozos], [7, 6])


class Reintentos(unittest.TestCase):
    def test_reintenta_errores_temporales(self):
        f = mock.Mock(side_effect=[error_http(503), error_http(429), "ok"])
        self.assertEqual(reintentos.con_reintentos(f), "ok")
        self.assertEqual(f.call_count, 3)

    def test_se_rinde_con_el_error_original(self):
        f = mock.Mock(side_effect=error_http(500))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            reintentos.con_reintentos(f, intentos=3)
        self.assertEqual((ctx.exception.code, f.call_count), (500, 3))

    def test_no_reintenta_cuenta_sin_saldo(self):
        f = mock.Mock(side_effect=error_http(403, b'{"detail":"User is locked. Reason: TOP_UP."}'))
        with self.assertRaises(reintentos.ErrorDeCuenta):
            reintentos.con_reintentos(f)
        self.assertEqual(f.call_count, 1)


class Motor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.png = os.path.join(self.dir, "fuente.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1344x768",
                        "-frames:v", "1", self.png], check=True)
        self.entorno = mock.patch.dict(os.environ, {"FAL_KEY": "x"})
        self.entorno.start()
        self.sin_director = mock.patch.object(director, "post", side_effect=error_http(404))  # nunca a la red
        self.sin_director.start()
        self.texto = "Uno.\n\nDos.\n\nTres.\n\nCuatro."

    def tearDown(self):
        self.entorno.stop()
        self.sin_director.stop()

    def proyecto(self, **kw):
        return videosyt.nuevo_proyecto(self.texto, "cinematico", os.path.join(self.dir, "p"), **kw)

    def test_semilla_distinta_por_escena_y_biblia_al_final(self):
        cuerpos = []

        def post(url, cabeceras, cuerpo):
            cuerpos.append(cuerpo)
            return {"images": [{"url": "file://" + self.png}]}

        p = self.proyecto(biblia="a red robot")
        with mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        self.assertEqual(len({c["seed"] for c in cuerpos}), 4)
        self.assertTrue(all(c["prompt"].startswith("Scene illustrating:") for c in cuerpos))
        self.assertTrue(all("Recurring character: a red robot" in c["prompt"] for c in cuerpos))
        self.assertTrue(any("texto del guion" in a for a in p["avisos"]))  # el director falló: se avisa
        self.assertTrue(all(c["prompt"].endswith(imagen.SIN_TEXTO) for c in cuerpos))
        self.assertEqual({e["estado_imagen"] for e in p["escenas"]}, {"ia"})

    def test_director_describe_cada_escena_y_decide_el_personaje(self):
        self.texto = "Uno.\n\nImagen: un vinilo negro\nDos.\n\nTres.\n\nCuatro."
        pedidos, cuerpos = [], []

        def post_director(url, cabeceras, cuerpo, timeout=None):
            pedidos.append(cuerpo)
            return {"output": "```json\n" + json.dumps([
                {"n": 1, "imagen": "a smoky 1930s jazz club, wide shot", "personaje": False},
                {"n": 2, "imagen": "ignored because the script has its own visual", "personaje": False},
                {"n": 3, "imagen": "close-up of a pirate radio microphone", "personaje": True},
            ]) + "\n```"}

        def post(url, cabeceras, cuerpo):
            cuerpos.append(cuerpo["prompt"])
            return {"images": [{"url": "file://" + self.png}]}

        p = self.proyecto(biblia="a red robot")
        with mock.patch.object(director, "post", post_director), mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        self.assertEqual(len(pedidos), 1)
        self.assertIn("Full script", pedidos[0]["prompt"])
        visuales = [e["prompt_visual"] for e in p["escenas"]]
        self.assertEqual(visuales, ["a smoky 1930s jazz club, wide shot", "un vinilo negro",
                                    "close-up of a pirate radio microphone", "Cuatro."])  # la 4 no vino: queda el texto
        jazz = next(c for c in cuerpos if "jazz club" in c)
        radio = next(c for c in cuerpos if "pirate radio" in c)
        self.assertNotIn("red robot", jazz)
        self.assertIn("red robot", radio)
        self.assertTrue(p["dirigido"])
        videosyt.storyboard(p)  # no se vuelve a dirigir (ni a gastar) en el mismo proyecto
        self.assertEqual(len(pedidos), 1)

    def test_editar_la_descripcion_la_vuelve_propia(self):
        p = self.proyecto()
        videosyt.editar_escena(p, 0, prompt_visual="a burning vinyl record")
        self.assertTrue(p["escenas"][0]["visual_propio"])

    def test_imagen_en_negro_por_el_filtro_se_reintenta(self):
        cuerpos = []

        def post(url, cabeceras, cuerpo):
            cuerpos.append(dict(cuerpo))
            return {"images": [{"url": "file://" + self.png}], "has_nsfw_concepts": [len(cuerpos) == 1]}

        p = self.proyecto()
        with mock.patch.object(imagen, "post", post):
            videosyt.regenerar_escena(p, 0)
        self.assertEqual(len(cuerpos), 2)
        self.assertNotEqual(cuerpos[0]["seed"], cuerpos[1]["seed"])
        self.assertIn(imagen.SUAVE, cuerpos[1]["prompt"])
        self.assertEqual(p["escenas"][0]["estado_imagen"], "ia")

    def test_imagen_siempre_bloqueada_usa_respaldo(self):
        def post(url, cabeceras, cuerpo):
            bloqueada = "Dos" in cuerpo["prompt"]
            return {"images": [{"url": "file://" + self.png}], "has_nsfw_concepts": [bloqueada]}

        p = self.proyecto()
        with mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        e = p["escenas"][1]
        self.assertEqual(e["estado_imagen"], "respaldo")
        self.assertIn("filtro de contenido", e["aviso"])

    def openai(self, responder):
        """Simula la API de imágenes de OpenAI con la imagen de prueba en base64."""
        import base64
        with open(self.png, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        pedidos = []

        def post(url, cabeceras, cuerpo, timeout=None):
            pedidos.append(dict(cuerpo))
            error = responder(cuerpo, len(pedidos))
            if error:
                raise error
            return {"data": [{"b64_json": b64}]}

        openai_imagen._modelo_que_funciona = None
        return pedidos, mock.patch.object(openai_imagen, "post", post)

    def test_imagenes_con_openai_y_clip_con_el_archivo(self):
        pedidos, simulado = self.openai(lambda cuerpo, n: None)
        p = self.proyecto(biblia="a red robot", calidad="openai", clips=True)
        animados = []

        def animar(url, *_):
            animados.append(url)
            raise ValueError("sin red en las pruebas")  # el video sigue con la imagen
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}), simulado, \
                mock.patch.object(imagen, "post", side_effect=AssertionError("no debe usar fal")):
            videosyt.storyboard(p)
            with mock.patch.object(clip_video, "animar", animar):
                videosyt.renderizar(p, os.path.join(self.dir, "video.mp4"))
        self.assertEqual(len(pedidos), 4)
        self.assertEqual({c["size"] for c in pedidos}, {"1536x1024"})
        self.assertTrue(all("red robot" in c["prompt"] for c in pedidos))
        self.assertEqual({e["estado_imagen"] for e in p["escenas"]}, {"ia"})
        self.assertTrue(animados and all(u.startswith("data:image/png;base64,") for u in animados))

    def test_openai_prueba_el_siguiente_modelo_y_suaviza_si_lo_rechaza(self):
        def responder(cuerpo, n):
            if cuerpo["model"] == openai_imagen.MODELOS[0]:
                return error_http(404, b'{"error": {"code": "model_not_found", "message": "no model"}}')
            if n == 2:
                return error_http(400, b'{"error": {"code": "moderation_blocked", "message": "safety"}}')
        pedidos, simulado = self.openai(responder)
        p = self.proyecto(calidad="openai")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}), simulado:
            videosyt.regenerar_escena(p, 0)
        self.assertEqual([c["model"] for c in pedidos], [openai_imagen.MODELOS[0]] + [openai_imagen.MODELOS[1]] * 2)
        self.assertIn(imagen.SUAVE, pedidos[2]["prompt"])
        self.assertEqual(p["escenas"][0]["estado_imagen"], "ia")

    def test_si_openai_falla_se_hace_con_flux(self):
        pedidos, simulado = self.openai(lambda cuerpo, n: error_http(401, b'{"error": {"message": "bad key"}}'))
        modelos = []

        def post(url, cabeceras, cuerpo):
            modelos.append(url)
            return {"images": [{"url": "file://" + self.png}]}

        p = self.proyecto(calidad="openai")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}), simulado, mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        self.assertEqual(set(modelos), {"https://fal.run/fal-ai/flux/dev"})
        self.assertEqual({e["estado_imagen"] for e in p["escenas"]}, {"ia"})
        self.assertTrue(any("OpenAI" in a and "bad key" in a for a in p["avisos"]))
        self.assertLessEqual(len(pedidos), videosyt.LIMITES["openai"])  # la clave mala se deja de usar

    def test_leer_respuesta_del_director(self):
        self.assertEqual(director.leer_respuesta('Sure: [{"n": 2, "imagen": "x", "personaje": true}]', {1, 2}),
                         {2: ("x", True)})
        with self.assertRaises(ValueError):
            director.leer_respuesta("no puedo", {1})

    def test_escena_que_falla_usa_imagen_de_respaldo(self):
        def post(url, cabeceras, cuerpo):
            if "Scene illustrating: Tres" in cuerpo["prompt"]:
                raise error_http(500)
            return {"images": [{"url": "file://" + self.png}]}

        p = self.proyecto()
        with mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        e = p["escenas"][2]
        self.assertEqual(e["estado_imagen"], "respaldo")
        self.assertEqual(e["respaldo_de"], 2)
        self.assertTrue(os.path.exists(os.path.join(p["carpeta"], e["imagen"])))

    def test_cuenta_sin_saldo_bloquea_el_proveedor_y_el_video_termina(self):
        llamadas = []

        def post(url, cabeceras, cuerpo):
            llamadas.append(1)
            raise error_http(403, b'{"detail":"User is locked. Reason: TOP_UP."}')

        p = self.proyecto()
        with mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        self.assertLessEqual(len(llamadas), videosyt.LIMITES["imagen"])
        self.assertTrue(any("TOP_UP" in a for a in p["avisos"]))
        salida = os.path.join(self.dir, "video.mp4")
        videosyt.renderizar(p, salida)
        self.assertGreater(os.path.getsize(salida), 0)

    def test_voz_que_falla_queda_en_silencio(self):
        def post_voz(url, cabeceras, cuerpo, binario=False):
            raise error_http(500)

        p = self.proyecto()
        with mock.patch.object(imagen, "post", lambda *a: {"images": [{"url": "file://" + self.png}]}):
            videosyt.storyboard(p)
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "x"}), mock.patch.object(voz, "post", post_voz):
            videosyt.renderizar(p, os.path.join(self.dir, "video.mp4"))
        self.assertTrue(all(e.get("aviso_voz") for e in p["escenas"]))
        self.assertIn("sin voz", videosyt.resumen_respaldos(p))
        guardado = json.load(open(os.path.join(p["carpeta"], "proyecto.json")))
        self.assertEqual(len(guardado["escenas"]), 4)


if __name__ == "__main__":
    unittest.main()


class Estilos(unittest.TestCase):
    def test_catalogo_completo(self):
        catalogo = videosyt.estilos()
        self.assertEqual(len(catalogo), 20)
        for e in catalogo.values():
            self.assertTrue(os.path.exists(os.path.join(videosyt.AQUI, e["fuente"])), e["id"])
            self.assertRegex(e["fondo"], r"^#[0-9a-f]{6}$")
        self.assertTrue(any(e["personaje"] for e in catalogo.values()))
        self.assertTrue(any(not e["personaje"] for e in catalogo.values()))

    def test_formato_aparte_y_proyectos_antiguos(self):
        self.assertEqual(videosyt.estilo_de({"estilo": "anime", "formato": "9:16"})["formato"], "9:16")
        antiguo = videosyt.estilo_de({"estilo": "shorts"})  # "shorts" era un estilo vertical
        self.assertEqual((antiguo["id"], antiguo["formato"]), ("cinematico", "9:16"))

    def test_vista_previa_usa_el_personaje_del_estilo(self):
        enviado = {}
        def post(url, cabeceras, cuerpo):
            enviado.update(cuerpo)
            return {"images": [{"url": "https://x"}]}
        with mock.patch.dict(os.environ, {"FAL_KEY": "x"}), mock.patch.object(imagen, "post", post), \
                mock.patch.object(imagen, "descargar", lambda *a: None):
            videosyt.vista_previa("anime", "/tmp/no-importa.png")
        self.assertIn(videosyt.estilos()["anime"]["personaje"], enviado["prompt"])


class Actualizacion(unittest.TestCase):
    def respuesta(self, datos):
        r = mock.MagicMock()
        r.__enter__.return_value = io.BytesIO(json.dumps(datos).encode())
        return r

    def test_lee_la_version_publicada(self):
        import actualizar
        datos = {"name": "Videosyt para Windows · versión 42",
                 "assets": [{"name": "Videosyt.exe", "browser_download_url": "https://x/Videosyt.exe"}]}
        with mock.patch.object(actualizar, "_pedir", return_value=self.respuesta(datos)):
            self.assertEqual(actualizar.ultima_publicada(), (42, "https://x/Videosyt.exe"))

    def test_ofrece_actualizar_solo_si_hay_una_version_mayor(self):
        import actualizar
        datos = {"name": "Videosyt para Windows · versión 42",
                 "assets": [{"name": "Videosyt.exe", "browser_download_url": "https://x/Videosyt.exe"}]}
        for actual, esperado in [(41, 42), (42, 0)]:
            actualizar.estado["disponible"] = 0
            with mock.patch.object(actualizar, "_pedir", return_value=self.respuesta(datos)), \
                    mock.patch.object(actualizar, "version_actual", return_value=actual), \
                    mock.patch.object(actualizar.sys, "frozen", True, create=True):
                actualizar.comprobar()
            self.assertEqual(actualizar.estado["disponible"], esperado)
