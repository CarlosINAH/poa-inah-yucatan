# -*- coding: utf-8 -*-
"""Crea la base de datos, carga el catálogo POA y da de alta al personal.

Se puede volver a correr sin miedo: no pisa usuarios ni actividades existentes.

    .venv\\Scripts\\python.exe servidor_poa\\inicializar.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import auth, db  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO_JSON = RAIZ / "datos_extraidos" / "poa_catalog.json"

# nombre, cargo, grupo, es_responsable, es_admin
# Lista confirmada por Carlos Gálvez el 14/07/2026. Ojo: el Excel de origen escribe
# «Claudia Garcia» en las 5 filas de Restaurador responsable; el apellido correcto es
# Gracia Solís.
PERSONAL = [
    ("Diana Elizabeth Arano Recio", "Restauradora", "Responsables de proyecto", 1, 0),
    ("Natalia Hernández Tangarife", "Restauradora", "Responsables de proyecto", 1, 0),
    ("Claudia Angélica Ocampo Flores", "Restauradora", "Responsables de proyecto", 1, 0),
    ("Karla Martínez López", "Restauradora · Coordinadora de la Sección de Conservación",
     "Responsables de proyecto", 1, 1),
    ("Claudia A. Gracia Solís", "Restauradora", "Responsables de proyecto", 1, 0),
    ("Carlos Alberto Gálvez Valencia", "Técnico / Programador", "Empleados", 0, 1),
    ("César Téllez Castro", "Restaurador", "Empleados", 0, 0),
    ("Martha Angélica Soto Velázquez", "Restauradora", "Empleados", 0, 0),
    ("Margarita Alicia Alcántara Mejorada", "Restauradora", "Empleados", 0, 0),
    ("Vidaura Anamari Cardos Ramírez", "Arquitecta", "Empleados", 0, 0),
    ("Jareth Anuar Guadarrama Moreno", "Químico", "Empleados", 0, 0),
    ("Luz Fabiola González Juárez", "Restauradora", "Empleados", 0, 0),
    ("Helga Zelezny Geovannini Acuña", "Arqueóloga", "Empleados", 0, 0),
    ("Gerardo Magallón Calderón", "Restaurador", "Empleados", 0, 0),
]


def texto(valor) -> str:
    """El Excel deja 0 donde no hay línea de acción; en la plataforma eso es vacío."""
    if valor is None or valor == 0:
        return ""
    return str(valor).strip()


def cargar_catalogo(con) -> int:
    if not CATALOGO_JSON.exists():
        sys.exit(f"No encuentro el catálogo POA en {CATALOGO_JSON}")
    datos = json.loads(CATALOGO_JSON.read_text(encoding="utf-8"))
    nuevos = 0
    for act in datos["activities"]:
        cur = con.execute(
            """INSERT INTO catalogo_poa
                 (actividad_poa, unidad_medida, programa_operativo, eje,
                  linea_accion_enc, eje_estrategico_enc)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(actividad_poa) DO UPDATE SET
                 unidad_medida       = excluded.unidad_medida,
                 programa_operativo  = excluded.programa_operativo,
                 eje                 = excluded.eje,
                 linea_accion_enc    = excluded.linea_accion_enc,
                 eje_estrategico_enc = excluded.eje_estrategico_enc""",
            (
                texto(act["Actividad POA"]),
                texto(act["Unidad de Medida"]),
                texto(act["Programa Operativo"]),
                texto(act["Eje"]),
                texto(act["Línea de acción ENC"]),
                texto(act["Eje estratégico ENC"]),
            ),
        )
        nuevos += cur.rowcount
    con.commit()
    return nuevos


def cargar_personal(con) -> list[tuple[str, str, str]]:
    tomados = {f["usuario"] for f in con.execute("SELECT usuario FROM usuarios")}
    credenciales = []
    for nombre, cargo, grupo, responsable, admin in PERSONAL:
        ya = con.execute("SELECT id FROM usuarios WHERE nombre = ?", (nombre,)).fetchone()
        if ya:
            continue
        usuario = auth.usuario_desde_nombre(nombre, tomados)
        # Sin contraseña: se entra eligiendo el nombre. La coordinación define su PIN
        # la primera vez que entra.
        con.execute(
            """INSERT INTO usuarios
                 (usuario, nombre, cargo, grupo, es_responsable, es_admin,
                  pin_hash, activo, creado_en)
               VALUES (?, ?, ?, ?, ?, ?, '', 1, ?)""",
            (usuario, nombre, cargo, grupo, responsable, admin, db.ahora()),
        )
        credenciales.append((nombre, usuario, ""))
    con.commit()
    return credenciales


def main() -> None:
    con = db.conectar()
    db.crear_esquema(con)

    nuevos_cat = cargar_catalogo(con)
    total_cat = con.execute("SELECT COUNT(*) c FROM catalogo_poa").fetchone()["c"]
    print(f"Catálogo POA: {total_cat} actividades ({nuevos_cat} nuevas).")

    credenciales = cargar_personal(con)
    total_usr = con.execute("SELECT COUNT(*) c FROM usuarios").fetchone()["c"]
    print(f"Personal: {total_usr} usuarios ({len(credenciales)} nuevos).")

    print("\nNo hay contraseñas: cada quien entra eligiendo su nombre de la lista.")

    admins = [f["nombre"] for f in con.execute(
        "SELECT nombre FROM usuarios WHERE es_admin = 1 AND pin_hash = '' ORDER BY nombre")]
    if admins:
        print("\nCOORDINACIÓN - definan su PIN cuanto antes:")
        for a in admins:
            print(f"  - {a}")
        print("\nEntra a la plataforma, elige tu nombre y te pedirá crearlo. Mientras esté\n"
              "vacío, cualquiera que elija ese nombre puede ponerle uno y quedarse con el\n"
              "acceso al Consolidado y al panel de Personal.")
    con.close()


if __name__ == "__main__":
    main()
