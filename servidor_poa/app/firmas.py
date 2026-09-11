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

from PIL import Image

from .db import FIRMAS_DIR

MAX_BYTES = 3 * 1024 * 1024      # una firma no debería pesar más que esto
LADO_MAXIMO = 1000               # px del lado mayor; de sobra para imprimirla nítida


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


def eliminar(archivo: str) -> None:
    """Borra el PNG de una firma reemplazada. El nombre viene de la BD, pero se ancla igual."""
    if not archivo:
        return
    ruta = (FIRMAS_DIR / Path(archivo).name).resolve()
    if ruta.is_relative_to(FIRMAS_DIR.resolve()) and ruta.exists():
        ruta.unlink()
