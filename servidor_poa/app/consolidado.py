# -*- coding: utf-8 -*-
"""Consultas y armado del consolidado.

Regla que gobierna todo este módulo: las cifras POA (planeado e informado) se leen
de la ACTIVIDAD, nunca se suman por participante. Si tres personas intervinieron el
mismo mural, el POA reporta 1, y las tres aparecen como participantes.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from .db import ahora, norm

CAMPOS_ACTIVIDAD = (
    "titulo", "catalogo_id", "zona", "programa_nacional", "anio", "trimestre",
    "planeado_anual",
    "plan_t1", "plan_t2", "plan_t3", "plan_t4",
    "inf_t1", "inf_t2", "inf_t3", "inf_t4",
    "planeacion", "observaciones", "fechas_ejecucion", "responsable_id",
)


def expandir_periodo(datos: dict) -> dict:
    """De «trimestre + planeado + realizado» a la rejilla de 4+4 del POA.

    El formulario pide un solo periodo; la base y el PDF conservan la rejilla porque es
    la forma del informe oficial. Aquí se traduce una en la otra.
    """
    trimestre = datos.get("trimestre") or 0
    for n in (1, 2, 3, 4):
        datos[f"plan_t{n}"] = 0.0
        datos[f"inf_t{n}"] = 0.0
    if trimestre in (1, 2, 3, 4):
        datos[f"plan_t{trimestre}"] = datos.get("planeado", 0.0)
        datos[f"inf_t{trimestre}"] = datos.get("realizado", 0.0)
    datos["planeado_anual"] = datos.get("planeado", 0.0)
    return datos

_SELECT_ACTIVIDAD = """
SELECT a.*,
       c.actividad_poa, c.unidad_medida, c.programa_operativo, c.eje,
       c.linea_accion_enc, c.eje_estrategico_enc,
       r.nombre AS responsable_nombre, r.cargo AS responsable_cargo,
       cr.nombre AS creador_nombre,
       (a.inf_t1 + a.inf_t2 + a.inf_t3 + a.inf_t4) AS total_informado,
       (a.plan_t1 + a.plan_t2 + a.plan_t3 + a.plan_t4) AS total_planeado
  FROM actividades a
  JOIN catalogo_poa c  ON c.id = a.catalogo_id
  LEFT JOIN usuarios r ON r.id = a.responsable_id
  JOIN usuarios cr     ON cr.id = a.creada_por
"""


# ------------------------------------------------------------------ referencias

def catalogo(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM catalogo_poa ORDER BY actividad_poa").fetchall()


def responsables(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT id, nombre, cargo FROM usuarios WHERE es_responsable = 1 AND activo = 1 "
        "ORDER BY nombre"
    ).fetchall()


def usuarios(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        """SELECT u.*, (SELECT COUNT(*) FROM participaciones p WHERE p.usuario_id = u.id)
                       AS participaciones
             FROM usuarios u ORDER BY u.es_responsable DESC, u.nombre"""
    ).fetchall()


def zonas_usadas(con: sqlite3.Connection) -> list[str]:
    return [f["nombre"] for f in con.execute(
        "SELECT nombre FROM zonas ORDER BY usos DESC, nombre")]


def canonizar_zona(con: sqlite3.Connection, zona: str) -> str:
    """Aprende la zona y devuelve SIEMPRE su forma canónica.

    Quien escriba 'chichen  itza' termina guardando 'Chichén Itzá' si esa zona ya
    existía. Es lo que hace que el consolidado agrupe una sola vez: si se guardara el
    texto tal cual se tecleó, la misma zona saldría partida en varios renglones.
    """
    zona = " ".join((zona or "").split())
    if not zona:
        return ""
    clave = norm(zona)
    fila = con.execute("SELECT id, nombre FROM zonas WHERE nombre_norm = ?",
                       (clave,)).fetchone()
    if fila:
        con.execute("UPDATE zonas SET usos = usos + 1 WHERE id = ?", (fila["id"],))
        return fila["nombre"]
    con.execute("INSERT INTO zonas (nombre, nombre_norm, usos) VALUES (?, ?, 1)",
                (zona, clave))
    return zona


def anios_disponibles(con: sqlite3.Connection) -> list[int]:
    filas = [f["anio"] for f in con.execute(
        "SELECT DISTINCT anio FROM actividades ORDER BY anio DESC")]
    hoy = date.today().year
    if hoy not in filas:
        filas.insert(0, hoy)
    return filas


def anio_por_defecto(con: sqlite3.Connection) -> int:
    fila = con.execute("SELECT MAX(anio) a FROM actividades").fetchone()
    return fila["a"] or date.today().year


# ------------------------------------------------------------------ actividades

def insertar_actividad(con: sqlite3.Connection, datos: dict, uid: int) -> int:
    columnas = ", ".join(CAMPOS_ACTIVIDAD)
    marcas = ", ".join("?" for _ in CAMPOS_ACTIVIDAD)
    cur = con.execute(
        f"""INSERT INTO actividades ({columnas}, titulo_norm, zona_norm,
                                      creada_por, creada_en, actualizada_en)
            VALUES ({marcas}, ?, ?, ?, ?, ?)""",
        (*(datos[c] for c in CAMPOS_ACTIVIDAD), norm(datos["titulo"]),
         norm(datos["zona"]), uid, ahora(), ahora()),
    )
    return int(cur.lastrowid)


def actualizar_actividad(con: sqlite3.Connection, act_id: int, datos: dict) -> None:
    asignaciones = ", ".join(f"{c} = ?" for c in CAMPOS_ACTIVIDAD)
    con.execute(
        f"""UPDATE actividades SET {asignaciones}, titulo_norm = ?, zona_norm = ?,
                                   actualizada_en = ?
             WHERE id = ?""",
        (*(datos[c] for c in CAMPOS_ACTIVIDAD), norm(datos["titulo"]),
         norm(datos["zona"]), ahora(), act_id),
    )


def actividad(con: sqlite3.Connection, act_id: int) -> sqlite3.Row | None:
    return con.execute(_SELECT_ACTIVIDAD + " WHERE a.id = ?", (act_id,)).fetchone()


def puede_editar(u: sqlite3.Row, act: sqlite3.Row) -> bool:
    """La ficha POA la toca quien la creó, su responsable de proyecto o la coordinación.
    El resumen y las fotos de cada quien son otra cosa: eso siempre es del dueño."""
    return bool(u["es_admin"] or act["creada_por"] == u["id"]
                or (act["responsable_id"] and act["responsable_id"] == u["id"]))


def buscar(con: sqlite3.Connection, anio: int, texto: str = "", zona: str = "",
           trimestre: int = 0, solo_de: int | None = None) -> list[dict]:
    """La lista del tablero. `solo_de` limita a las actividades de una persona."""
    condiciones, params = ["a.anio = ?"], [anio]
    if texto.strip():
        condiciones.append("(a.titulo_norm LIKE ? OR c.actividad_poa LIKE ?)")
        params += [f"%{norm(texto)}%", f"%{texto.strip()}%"]
    if zona.strip():
        condiciones.append("a.zona_norm = ?")
        params.append(norm(zona))
    if trimestre in (1, 2, 3, 4):
        condiciones.append("a.trimestre = ?")
        params.append(trimestre)
    if solo_de:
        condiciones.append("EXISTS (SELECT 1 FROM participaciones p "
                           "WHERE p.actividad_id = a.id AND p.usuario_id = ?)")
        params.append(solo_de)

    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY a.trimestre, a.actualizada_en DESC", params).fetchall()

    salida = []
    for f in filas:
        act = dict(f)
        resumen = con.execute(
            """SELECT u.nombre,
                      (SELECT COUNT(*) FROM fotos x WHERE x.participacion_id = p.id) nf
                 FROM participaciones p JOIN usuarios u ON u.id = p.usuario_id
                WHERE p.actividad_id = ? ORDER BY p.creada_en""", (f["id"],)).fetchall()
        act["participantes"] = [r["nombre"] for r in resumen]
        act["n_fotos"] = sum(r["nf"] for r in resumen)
        salida.append(act)
    return salida


def archivos_de_actividad(con: sqlite3.Connection, act_id: int) -> list[str]:
    return [f["archivo"] for f in con.execute(
        """SELECT f.archivo FROM fotos f
             JOIN participaciones p ON p.id = f.participacion_id
            WHERE p.actividad_id = ?""", (act_id,))]


# --------------------------------------------------------------- participación

def sumar_participante(con: sqlite3.Connection, act_id: int, uid: int,
                       resumen: str = "") -> int:
    """Alta idempotente: volver a sumarse no duplica ni pisa el resumen ya escrito."""
    con.execute(
        """INSERT INTO participaciones (actividad_id, usuario_id, resumen,
                                        creada_en, actualizada_en)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (actividad_id, usuario_id) DO NOTHING""",
        (act_id, uid, resumen, ahora(), ahora()),
    )
    fila = con.execute(
        "SELECT id FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
        (act_id, uid),
    ).fetchone()
    return int(fila["id"])


def participacion(con: sqlite3.Connection, parte_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM participaciones WHERE id = ?", (parte_id,)).fetchone()


def participaciones(con: sqlite3.Connection, act_id: int) -> list[dict]:
    filas = con.execute(
        """SELECT p.*, u.nombre, u.cargo, u.grupo
             FROM participaciones p JOIN usuarios u ON u.id = p.usuario_id
            WHERE p.actividad_id = ?
            ORDER BY p.creada_en""", (act_id,)).fetchall()
    salida = []
    for f in filas:
        parte = dict(f)
        parte["fotos"] = [dict(x) for x in con.execute(
            "SELECT * FROM fotos WHERE participacion_id = ? ORDER BY orden, id",
            (f["id"],))]
        salida.append(parte)
    return salida


def foto_con_dueno(con: sqlite3.Connection, foto_id: int) -> sqlite3.Row | None:
    return con.execute(
        """SELECT f.*, p.usuario_id, p.actividad_id
             FROM fotos f JOIN participaciones p ON p.id = f.participacion_id
            WHERE f.id = ?""", (foto_id,)).fetchone()


# ------------------------------------------------------------------- consolidado

def kpis(con: sqlite3.Connection, anio: int) -> dict:
    # Lo planeado se toma del mayor entre la casilla anual y la suma de los trimestres:
    # en el POA de origen es común llenar sólo los trimestres y dejar el anual vacío, y
    # entonces el avance saldría 0% aunque todo esté reportado.
    fila = con.execute(
        """SELECT COUNT(*) actividades,
                  COALESCE(SUM(MAX(planeado_anual,
                                   plan_t1 + plan_t2 + plan_t3 + plan_t4)), 0) planeado,
                  COALESCE(SUM(inf_t1 + inf_t2 + inf_t3 + inf_t4), 0) informado
             FROM actividades WHERE anio = ?""", (anio,)).fetchone()
    personas = con.execute(
        """SELECT COUNT(DISTINCT p.usuario_id) c
             FROM participaciones p JOIN actividades a ON a.id = p.actividad_id
            WHERE a.anio = ?""", (anio,)).fetchone()["c"]
    colaborativas = con.execute(
        """SELECT COUNT(*) c FROM (
              SELECT p.actividad_id FROM participaciones p
                JOIN actividades a ON a.id = p.actividad_id
               WHERE a.anio = ?
               GROUP BY p.actividad_id HAVING COUNT(*) > 1)""", (anio,)).fetchone()["c"]
    planeado, informado = fila["planeado"], fila["informado"]
    return {
        "actividades": fila["actividades"],
        "planeado": planeado,
        "informado": informado,
        "avance": round(informado / planeado * 100) if planeado else 0,
        "personas": personas,
        "colaborativas": colaborativas,
    }


def armar(con: sqlite3.Connection, anio: int, trimestre: int, agrupar: str) -> list[dict]:
    """Agrupa las actividades del periodo por zona o por eje, con sus participantes."""
    condiciones, params = ["a.anio = ?"], [anio]
    if trimestre in (1, 2, 3, 4):
        condiciones.append("a.trimestre = ?")
        params.append(trimestre)
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY a.zona, c.eje, a.titulo", params).fetchall()

    grupos: dict[str, list[dict]] = {}
    for f in filas:
        act = dict(f)
        act["participaciones"] = participaciones(con, f["id"])
        act["participantes"] = ", ".join(p["nombre"] for p in act["participaciones"])
        act["informado_periodo"] = (
            act[f"inf_t{trimestre}"] if trimestre in (1, 2, 3, 4) else act["total_informado"]
        )
        clave = (act["zona"] or "Sin zona especificada") if agrupar == "zona" else act["eje"]
        grupos.setdefault(clave, []).append(act)

    return [
        {
            "nombre": nombre,
            "actividades": acts,
            "informado": sum(a["informado_periodo"] for a in acts),
            "personas": len({p["usuario_id"] for a in acts for p in a["participaciones"]}),
        }
        for nombre, acts in sorted(grupos.items())
    ]


def totales(grupos: list[dict]) -> dict:
    actividades = [a for g in grupos for a in g["actividades"]]
    return {
        "grupos": len(grupos),
        "actividades": len(actividades),
        "informado": sum(a["informado_periodo"] for a in actividades),
        "personas": len({p["usuario_id"] for a in actividades
                         for p in a["participaciones"]}),
        "fotos": sum(len(p["fotos"]) for a in actividades for p in a["participaciones"]),
    }
