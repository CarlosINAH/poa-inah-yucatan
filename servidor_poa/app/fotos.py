# -*- coding: utf-8 -*-
"""Recepción y normalizado de la evidencia fotográfica.

El navegador ya manda la foto reducida, pero eso es una cortesía para la red:
aquí se vuelve a procesar siempre, porque un cliente puede mandar lo que quiera.
"""
from __future__ import annotations

import io
import secrets
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .db import FOTOS_DIR

MAX_BYTES_ENTRADA = 50 * 1024 * 1024   # lo que el usuario puede subir: 50 MB
LADO_MAXIMO = 2200                     # px del lado mayor, versión para ver en pantalla
CALIDAD_JPEG = 82
# En el PDF cada foto ocupa ~84 mm de ancho. A 1100 px eso son ~330 ppp, de sobra para
# imprimir. Incrustar la de 2200 px multiplicaba por diez el peso del consolidado.
LADO_IMPRESION = 1100
CALIDAD_IMPRESION = 78
MAX_FOTOS_POR_PARTICIPACION = 4
MAX_PIXELES = 80_000_000               # cota anti "bomba de descompresión"

Image.MAX_IMAGE_PIXELS = MAX_PIXELES


class FotoInvalida(Exception):
    pass


def _nombre_archivo(sufijo: str = "") -> str:
    hoy = datetime.now(timezone.utc).strftime("%Y%m")
    return f"{hoy}_{secrets.token_hex(8)}{sufijo}.jpg"


def _codificar(img: Image.Image, lado: int, calidad: int) -> tuple[bytes, int, int]:
    copia = img.copy()
    copia.thumbnail((lado, lado), Image.LANCZOS)
    salida = io.BytesIO()
    copia.save(salida, format="JPEG", quality=calidad, optimize=True, progressive=True)
    return salida.getvalue(), copia.width, copia.height


def procesar(datos: bytes, nombre_original: str) -> dict:
    """Valida, reorienta y guarda dos JPEG: uno para ver y otro, menor, para el PDF."""
    if not datos:
        raise FotoInvalida("El archivo llegó vacío.")
    if len(datos) > MAX_BYTES_ENTRADA:
        mb = len(datos) / 1024 / 1024
        raise FotoInvalida(
            f"«{nombre_original}» pesa {mb:.0f} MB y el máximo son 50 MB."
        )

    try:
        with Image.open(io.BytesIO(datos)) as img:
            img.verify()          # detecta archivos corruptos o que no son imagen
        with Image.open(io.BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img)   # respeta la rotación de la cámara
            img = img.convert("RGB")
            vista, ancho, alto = _codificar(img, LADO_MAXIMO, CALIDAD_JPEG)
            impresion, _, _ = _codificar(img, LADO_IMPRESION, CALIDAD_IMPRESION)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FotoInvalida(
            f"No pude leer «{nombre_original}» como imagen. ¿Es un JPG o PNG?"
        ) from exc

    archivo = _nombre_archivo()
    archivo_pdf = archivo.replace(".jpg", "_pdf.jpg")
    FOTOS_DIR.mkdir(parents=True, exist_ok=True)
    (FOTOS_DIR / archivo).write_bytes(vista)
    (FOTOS_DIR / archivo_pdf).write_bytes(impresion)

    return {
        "archivo": archivo,
        "archivo_pdf": archivo_pdf,
        "nombre_original": nombre_original[:180],
        "bytes": len(vista),
        "bytes_pdf": len(impresion),
        "bytes_original": len(datos),
        "ancho": ancho,
        "alto": alto,
    }


def eliminar(archivo: str) -> None:
    """Borra el JPEG y su versión de impresión. El nombre viene de la BD, pero se ancla igual."""
    for nombre in (archivo, archivo.replace(".jpg", "_pdf.jpg")):
        ruta = (FOTOS_DIR / Path(nombre).name).resolve()
        if ruta.is_relative_to(FOTOS_DIR.resolve()) and ruta.exists():
            ruta.unlink()
