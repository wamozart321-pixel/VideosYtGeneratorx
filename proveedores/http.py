import json
import urllib.request


def post(url, headers, cuerpo, binario=False, timeout=300):
    """POST con JSON usando solo la librería estándar."""
    req = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode(),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        datos = r.read()
    return datos if binario else json.loads(datos)


def descargar(url, destino):
    with urllib.request.urlopen(url, timeout=300) as r, open(destino, "wb") as f:
        f.write(r.read())
