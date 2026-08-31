# -*- coding: utf-8 -*-
"""Mapa de ubicación para el informe.

Convierte el nombre de una zona (p. ej. «Chichén Itzá») en una imagen de mapa con un
marcador, para que la hoja del informe muestre dónde ocurrió la actividad.

Todo es best-effort y con respaldo: si no hay internet, si el sitio no se puede ubicar,
o si el servidor de mapas no responde, se devuelve None y el PDF muestra sólo el nombre
del lugar. Nada de esto debe tumbar la generación del informe.

Se cachea con fuerza: las coordenadas quedan en la tabla `zonas` (una geocodificación
por zona en toda la vida) y la imagen del mapa en `datos/mapas/<zona>.png`. Así el
informe no vuelve a salir a la red por una zona ya resuelta, y funciona sin internet una
vez que la imagen existe.

El mapa se arma juntando teselas (tiles) de OpenStreetMap y dibujando el marcador con
Pillow. Se eligió sobre los servicios de «static map» con API key (no queremos claves) y
sobre los agregadores sin key (poco fiables: el que probamos ni siquiera resolvía DNS).
"""
from __future__ import annotations

import math
import sqlite3
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from .db import DATOS_DIR, norm

MAPAS_DIR = DATOS_DIR / "mapas"

# OSM pide identificar la app con un User-Agent real y no abusar del servicio. Con el
# caché por zona el volumen es mínimo.
_UA = "PlataformaPOA-INAH-Yucatan/1.0 (informe interno de la Seccion de Conservacion)"
_TIMEOUT = 6  # segundos por petición: si tarda más, mejor el respaldo que colgar el PDF
_SESGO = ", Yucatán, México"   # los sitios de la Sección están todos en Yucatán

_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_ZOOM = 14
_ANCHO, _ALTO = 640, 360


def _geocodificar(con: sqlite3.Connection, zona: str, clave: str):
    """Devuelve (lat, lon) para la zona, o None. Cachea el resultado en `zonas`."""
    fila = con.execute("SELECT lat, lon FROM zonas WHERE nombre_norm = ?", (clave,)).fetchone()
    if fila and fila["lat"] is not None:
        return fila["lat"], fila["lon"]

    consulta = urllib.parse.urlencode({
        "q": zona + _SESGO, "format": "json", "limit": 1, "countrycodes": "mx",
    })
    url = "https://nominatim.openstreetmap.org/search?" + consulta
    peticion = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(peticion, timeout=_TIMEOUT) as r:
        import json
        datos = json.load(r)
    if not datos:
        return None
    lat, lon = float(datos[0]["lat"]), float(datos[0]["lon"])
    con.execute("UPDATE zonas SET lat = ?, lon = ? WHERE nombre_norm = ?", (lat, lon, clave))
    con.commit()
    return lat, lon


def _tesela_fraccional(lat: float, lon: float, z: int) -> tuple[float, float]:
    """(x, y) de tesela en coordenadas fraccionales (Web Mercator)."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _descargar_tesela(z: int, x: int, y: int) -> Image.Image:
    url = _TILE_URL.format(z=z, x=x, y=y)
    peticion = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(peticion, timeout=_TIMEOUT) as r:
        return Image.open(BytesIO(r.read())).convert("RGB")


def _dibujar_mapa(lat: float, lon: float) -> Image.Image | None:
    """Une las teselas alrededor del punto y dibuja el marcador. None si no baja nada."""
    xf, yf = _tesela_fraccional(lat, lon, _ZOOM)
    cx, cy = xf * 256.0, yf * 256.0                 # píxel-mundo del centro
    izq, arriba = cx - _ANCHO / 2, cy - _ALTO / 2   # esquina sup-izq del recorte
    tx0, ty0 = int(izq // 256), int(arriba // 256)
    tx1, ty1 = int((izq + _ANCHO) // 256), int((arriba + _ALTO) // 256)

    lienzo = Image.new("RGB", (_ANCHO, _ALTO), (232, 232, 226))
    exitos = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            try:
                tesela = _descargar_tesela(_ZOOM, tx, ty)
            except Exception:
                continue  # una tesela caída deja un hueco gris, no tumba el mapa
            lienzo.paste(tesela, (int(tx * 256 - izq), int(ty * 256 - arriba)))
            exitos += 1
    if exitos == 0:
        return None

    d = ImageDraw.Draw(lienzo)
    mx, my = _ANCHO // 2, _ALTO // 2
    d.ellipse([mx - 9, my - 9, mx + 9, my + 9], fill=(198, 40, 52), outline=(255, 255, 255), width=3)
    d.ellipse([mx - 3, my - 3, mx + 3, my + 3], fill=(255, 255, 255))
    return lienzo


def obtener_mapa(con: sqlite3.Connection, zona: str) -> tuple[Path | None, str]:
    """(ruta_de_la_imagen | None, nombre_del_lugar).

    La ruta es None cuando no se pudo dibujar el mapa; el segundo valor es siempre el
    nombre del lugar (el «título del punto geográfico») para el respaldo en texto.
    """
    zona = (zona or "").strip()
    if not zona:
        return None, ""
    clave = norm(zona)
    cache = MAPAS_DIR / f"{clave}.png"
    if cache.exists():
        return cache, zona

    try:
        coords = _geocodificar(con, zona, clave)
        if not coords:
            return None, zona
        img = _dibujar_mapa(*coords)
        if img is None:
            return None, zona
        MAPAS_DIR.mkdir(parents=True, exist_ok=True)
        img.save(cache, "PNG")
        return cache, zona
    except Exception:
        # Sin internet, timeout, sitio no ubicable, servicio caído: respaldo en texto.
        return None, zona
