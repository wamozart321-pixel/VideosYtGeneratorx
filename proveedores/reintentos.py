"""Reintentos con espera exponencial para las llamadas a las APIs de IA.

Solo se reintenta lo que puede arreglarse esperando (límite de tasa, caídas del
servidor, red). Los errores de cuenta (clave mala, sin saldo) se cortan al instante
y bloquean ese proveedor para el resto del video, para no gastar tiempo en él.
"""
import random
import threading
import time
import urllib.error

CODIGOS_DE_CUENTA = {401, 402, 403}


class ErrorDeCuenta(Exception):
    """La API rechazó la cuenta (clave inválida, sin saldo...). Reintentar no sirve."""


class Proveedores:
    """Recuerda qué proveedores fallaron por la cuenta durante un video."""

    def __init__(self):
        self._bloqueados = {}
        self._lock = threading.Lock()

    def bloquear(self, nombre, motivo):
        with self._lock:
            self._bloqueados.setdefault(nombre, motivo)

    def motivo(self, nombre):
        with self._lock:
            return self._bloqueados.get(nombre)


def _detalle(e):
    try:
        return e.read().decode(errors="replace")[:300]
    except Exception:
        return ""


def con_reintentos(funcion, *args, intentos=4, espera_base=1.0, **kwargs):
    for n in range(intentos):
        try:
            return funcion(*args, **kwargs)
        except urllib.error.HTTPError as e:
            if e.code in CODIGOS_DE_CUENTA:
                raise ErrorDeCuenta(f"{e.code}: {_detalle(e)}") from e
            if e.code != 429 and e.code < 500:
                raise
            espera = float(e.headers.get("retry-after") or espera_base * 2 ** n)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            espera = espera_base * 2 ** n
        if n == intentos - 1:
            raise
        time.sleep(min(espera, 30) + random.uniform(0, espera_base / 2))
