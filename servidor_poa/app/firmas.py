# -*- coding: utf-8 -*-
"""Firmas dibujadas por cada persona.

Cada quien traza su firma una sola vez (con el dedo o el mouse) en /mi-firma. El
navegador manda un PNG del trazo; aquí se valida, se recorta el espacio en blanco y se
guarda como PNG con fondo transparente. Luego pdf.py la estampa sobre la línea de firma
en cada hoja del informe donde esa persona figura como ejecutante o responsable.
"""
from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from .db import FIRMAS_DIR

MAX_BYTES = 3 * 1024 * 1024      # una firma dibujada no debería pesar más que esto
MAX_BYTES_SUBIDA = 15 * 1024 * 1024   # una firma subida (escaneo/foto) puede pesar más
LADO_MAXIMO = 1000               # px del lado mayor; de sobra para imprimirla nítida
UMBRAL_FONDO = 205               # claridad a partir de la cual se considera «papel» (se vuelve transparente)


class FirmaInvalida(Exception):
    pass


def _nombre_archivo() -> str:
    hoy = datetime.now(timezone.utc).strftime("%Y%m")
    return f"firma_{hoy}_{secrets.token_hex(8)}.png"


def _decodificar(data_url: str) -> bytes:
    """Extrae los bytes de un data URL «data:image/png;base64,…» (o base64 pelón)."""
    texto = (data_url or "").strip()
    if not texto:
        raise FirmaInvalida("No recibí ningún trazo de firma.")
    if texto.startswith("data:"):
        _, _, texto = texto.partition(",")
    try:
        return base64.b64decode(texto, validate=False)
    except (ValueError, base64.binascii.Error) as exc:
        raise FirmaInvalida("La firma llegó en un formato que no pude leer.") from exc


def _recortar(img: Image.Image) -> Image.Image:
    """Recorta el rectángulo con trazo, para que la firma no salga perdida en un lienzo grande."""
    caja = img.split()[-1].getbbox()   # límites de lo no transparente (canal alfa)
    return img.crop(caja) if caja else img


def procesar(data_url: str) -> str:
    """Valida y guarda la firma; devuelve el nombre del archivo PNG en firmas/."""
    datos = _decodificar(data_url)
    if len(datos) > MAX_BYTES:
        raise FirmaInvalida("La firma pesa demasiado. Vuelve a trazarla más simple.")
    try:
        with Image.open(io.BytesIO(datos)) as img:
            img = img.convert("RGBA")
            recorte = _recortar(img)
    except (OSError, ValueError) as exc:
        raise FirmaInvalida("No pude leer la firma como imagen.") from exc

    if recorte.width < 2 or recorte.height < 2:
        raise FirmaInvalida("La firma quedó vacía. Traza tu firma antes de guardar.")

    recorte.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
    salida = io.BytesIO()
    recorte.save(salida, format="PNG", optimize=True)

    FIRMAS_DIR.mkdir(parents=True, exist_ok=True)
    archivo = _nombre_archivo()
    (FIRMAS_DIR / archivo).write_bytes(salida.getvalue())
    return archivo


def procesar_subida(datos: bytes) -> str:
    """Procesa una firma SUBIDA como imagen (escaneo o foto de la firma sobre papel):
    quita el fondo claro para dejarla transparente, la recorta y la guarda como PNG.

    Sirve cuando la persona no puede firmar en pantalla (p. ej. por incapacidad médica) y
    la coordinación carga su firma a partir de un archivo. Devuelve el nombre del PNG.
    """
    if not datos:
        raise FirmaInvalida("El archivo llegó vacío.")
    if len(datos) > MAX_BYTES_SUBIDA:
        raise FirmaInvalida("La imagen de la firma pesa demasiado (máximo 15 MB).")
    try:
        with Image.open(io.BytesIO(datos)) as im:
            im = ImageOps.exif_transpose(im).convert("RGBA")
    except (OSError, ValueError) as exc:
        raise FirmaInvalida(
            "No pude leer el archivo como imagen. Sube un PNG o JPG de la firma."
        ) from exc

    # El fondo (papel) se vuelve transparente y la tinta se conserva: entre más oscuro el
    # trazo, más opaco queda, para que se estampe limpio sobre la línea de firma.
    gris = im.convert("L")
    alfa = gris.point(lambda p: 0 if p >= UMBRAL_FONDO
                      else min(255, round((UMBRAL_FONDO - p) * 255 / UMBRAL_FONDO)))
    im.putalpha(alfa)
    recorte = _recortar(im)
    if recorte.width < 3 or recorte.height < 3:
        raise FirmaInvalida("No se distingue la firma en la imagen (¿quedó casi todo en "
                            "blanco?). Usa una foto nítida del trazo sobre papel claro.")

    recorte.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
    salida = io.BytesIO()
    recorte.save(salida, format="PNG", optimize=True)

    FIRMAS_DIR.mkdir(parents=True, exist_ok=True)
    archivo = _nombre_archivo()
    (FIRMAS_DIR / archivo).write_bytes(salida.getvalue())
    return archivo


def eliminar(archivo: str) -> None:
    """Borra el PNG de una firma reemplazada. El nombre viene de la BD, pero se ancla igual."""
    if not archivo:
        return
    ruta = (FIRMAS_DIR / Path(archivo).name).resolve()
    if ruta.is_relative_to(FIRMAS_DIR.resolve()) and ruta.exists():
        ruta.unlink()
