# -*- coding: utf-8 -*-
"""Identificación de usuarios.

No hay contraseñas: la plataforma vive en la red interna del Centro INAH y cada quien
entra eligiendo su nombre de una lista. Es una decisión consciente de la Sección, a
cambio de que capturar no cueste ni un teclazo.

Lo único protegido es la coordinación (Consolidado y panel de Personal), con un PIN.
Eso evita que un clic en el nombre equivocado termine generando el informe firmado de
la Sección o desactivando a alguien.
"""
from __future__ import annotations

import sqlite3
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()

LONGITUD_MINIMA_PIN = 4


def hash_pin(pin: str) -> str:
    return _ph.hash(pin)


def verificar_pin(hash_guardado: str, pin: str) -> bool:
    if not hash_guardado:
        return False
    try:
        return _ph.verify(hash_guardado, pin)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validar_pin(pin: str) -> str | None:
    """Devuelve el motivo del rechazo, o None si el PIN sirve."""
    pin = pin.strip()
    if len(pin) < LONGITUD_MINIMA_PIN:
        return f"El PIN debe tener al menos {LONGITUD_MINIMA_PIN} caracteres."
    if len(set(pin)) == 1:
        return "El PIN no puede ser el mismo carácter repetido."
    if pin in ("1234", "0000", "1111", "12345", "123456"):
        return "Ese PIN es demasiado fácil de adivinar."
    return None


def usuario_desde_nombre(nombre: str, tomados: set[str]) -> str:
    """'Carlos Alberto Gálvez Valencia' -> 'carlos.galvez'

    El identificador ya no se teclea al entrar, pero sigue sirviendo para referirse a
    una persona sin depender de acentos ni de cómo se escriba su nombre completo.
    """
    limpio = unicodedata.normalize("NFD", nombre)
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    partes = [p for p in limpio.lower().split() if p.isalpha()]
    if not partes:
        base = "usuario"
    elif len(partes) == 1:
        base = partes[0]
    else:
        # nombre de pila + primer apellido. Con 4 palabras (2 nombres + 2 apellidos)
        # el apellido es la penúltima; con 3 es la segunda.
        apellido = partes[2] if len(partes) >= 4 else partes[1]
        base = f"{partes[0]}.{apellido}"
    candidato, n = base, 2
    while candidato in tomados:
        candidato, n = f"{base}{n}", n + 1
    tomados.add(candidato)
    return candidato


def seleccionables(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Las personas que aparecen en la lista de la pantalla de entrada."""
    return con.execute(
        """SELECT id, nombre, cargo, grupo, es_admin, pin_hash <> '' AS tiene_pin
             FROM usuarios WHERE activo = 1
            ORDER BY es_responsable DESC, nombre"""
    ).fetchall()
