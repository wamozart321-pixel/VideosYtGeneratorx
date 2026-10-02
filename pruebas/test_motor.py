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
from proveedores import guion, imagen, reintentos, voz

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
        self.texto = "Uno.\n\nDos.\n\nTres.\n\nCuatro."

    def tearDown(self):
        self.entorno.stop()

    def proyecto(self, **kw):
        return videosyt.nuevo_proyecto(self.texto, "cinematico", os.path.join(self.dir, "p"), **kw)

    def test_misma_semilla_y_biblia_en_todas_las_escenas(self):
        cuerpos = []

        def post(url, cabeceras, cuerpo):
            cuerpos.append(cuerpo)
            return {"images": [{"url": "file://" + self.png}]}

        p = self.proyecto(biblia="a red robot")
        with mock.patch.object(imagen, "post", post):
            videosyt.storyboard(p)
        self.assertEqual(len({c["seed"] for c in cuerpos}), 1)
        self.assertTrue(all(c["prompt"].startswith("a red robot") for c in cuerpos))
        self.assertEqual({e["estado_imagen"] for e in p["escenas"]}, {"ia"})

    def test_escena_que_falla_usa_imagen_de_respaldo(self):
        def post(url, cabeceras, cuerpo):
            if cuerpo["prompt"].startswith("Tres"):
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
