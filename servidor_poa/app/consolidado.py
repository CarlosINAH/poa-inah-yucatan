# -*- coding: utf-8 -*-
"""Consultas y armado del consolidado.

Regla que gobierna todo este módulo: las cifras POA (planeado e informado) se leen
de la ACTIVIDAD, nunca se suman por participante. Si tres personas intervinieron el
mismo mural, el POA reporta 1, y las tres aparecen como participantes.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from .db import ahora, norm

DIAS_PAPELERA = 30   # días que una actividad vive en la papelera antes de borrarse del todo

CAMPOS_ACTIVIDAD = (
    "titulo", "catalogo_id", "zona", "municipio", "fuera_estado",
    "programa_nacional", "anio", "trimestre",
    "planeado_anual",
    "plan_t1", "plan_t2", "plan_t3", "plan_t4",
    "inf_t1", "inf_t2", "inf_t3", "inf_t4",
    "planeacion", "objetivo", "mapa_lat", "mapa_lon",
    "observaciones", "fechas_ejecucion", "responsable_id",
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
       r.firma AS responsable_firma,
       cr.nombre AS creador_nombre,
       au.nombre AS autorizada_por_nombre,
       (a.inf_t1 + a.inf_t2 + a.inf_t3 + a.inf_t4) AS total_informado,
       (a.plan_t1 + a.plan_t2 + a.plan_t3 + a.plan_t4) AS total_planeado
  FROM actividades a
  JOIN catalogo_poa c  ON c.id = a.catalogo_id
  LEFT JOIN usuarios r  ON r.id = a.responsable_id
  LEFT JOIN usuarios au ON au.id = a.autorizada_por
  JOIN usuarios cr      ON cr.id = a.creada_por
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


# ------------------------------------------------------------- alta/edición de personal

def crear_usuario(con: sqlite3.Connection, nombre: str, cargo: str,
                  es_responsable: bool, es_admin: bool, email: str = "") -> int:
    """Da de alta a una persona. El identificador (para referirse a ella sin acentos) se
    deriva del nombre y se hace único."""
    from .auth import usuario_desde_nombre
    tomados = {r["usuario"] for r in con.execute("SELECT usuario FROM usuarios")}
    usuario = usuario_desde_nombre(nombre, tomados)
    cur = con.execute(
        """INSERT INTO usuarios (usuario, nombre, cargo, email, es_responsable, es_admin,
                                 activo, creado_en)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
        (usuario, nombre.strip(), cargo.strip(), email.strip(),
         int(es_responsable), int(es_admin), ahora()))
    return int(cur.lastrowid)


def editar_usuario(con: sqlite3.Connection, uid: int, nombre: str, cargo: str,
                   es_responsable: bool, es_admin: bool) -> None:
    con.execute(
        "UPDATE usuarios SET nombre = ?, cargo = ?, es_responsable = ?, es_admin = ? "
        "WHERE id = ?",
        (nombre.strip(), cargo.strip(), int(es_responsable), int(es_admin), uid))


def referencias_usuario(con: sqlite3.Connection, uid: int) -> int:
    """Cuántos datos dependen de la persona (participaciones o actividades). Si hay alguno,
    no se puede borrar sin perder información: se desactiva en su lugar."""
    p = con.execute("SELECT COUNT(*) c FROM participaciones WHERE usuario_id = ?",
                    (uid,)).fetchone()["c"]
    a = con.execute(
        """SELECT COUNT(*) c FROM actividades
            WHERE creada_por = ? OR responsable_id = ? OR autorizada_por = ?
               OR eliminada_por = ?""", (uid, uid, uid, uid)).fetchone()["c"]
    return p + a


def eliminar_usuario(con: sqlite3.Connection, uid: int) -> None:
    con.execute("DELETE FROM usuarios WHERE id = ?", (uid,))


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
        "SELECT DISTINCT anio FROM actividades WHERE eliminada_en = '' ORDER BY anio DESC")]
    hoy = date.today().year
    if hoy not in filas:
        filas.insert(0, hoy)
    return filas


def anio_por_defecto(con: sqlite3.Connection) -> int:
    fila = con.execute("SELECT MAX(anio) a FROM actividades WHERE eliminada_en = ''").fetchone()
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
    """La ficha POA sólo la edita quien la registró (el empleado). La coordinación y los
    responsables de proyecto no ingresan ni editan actividades: observan y, si algo debe
    corregirse, lo piden con una nota. El resumen y las fotos siempre son del dueño."""
    creador = act["creada_por"] if not isinstance(act, dict) else act.get("creada_por")
    return bool(creador == u["id"])


# ------------------------------------------------------------------------- papelera

def puede_borrar(u: sqlite3.Row, act) -> bool:
    """A la papelera la manda quien creó la actividad; la coordinación, cualquiera."""
    creador = act["creada_por"] if not isinstance(act, dict) else act.get("creada_por")
    return bool(u["es_admin"] or creador == u["id"])


def _dias_restantes(eliminada_en: str) -> int:
    """Días que faltan para la eliminación definitiva (0 si ya venció)."""
    try:
        t = datetime.fromisoformat(eliminada_en)
    except (ValueError, TypeError):
        return DIAS_PAPELERA
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    faltan = (t + timedelta(days=DIAS_PAPELERA) - datetime.now(timezone.utc)).days
    return max(faltan, 0)


def enviar_a_papelera(con: sqlite3.Connection, act_id: int, uid: int) -> None:
    con.execute(
        "UPDATE actividades SET eliminada_en = ?, eliminada_por = ? "
        "WHERE id = ? AND eliminada_en = ''", (ahora(), uid, act_id))


def restaurar(con: sqlite3.Connection, act_id: int) -> None:
    con.execute(
        "UPDATE actividades SET eliminada_en = '', eliminada_por = NULL WHERE id = ?",
        (act_id,))


def papelera(con: sqlite3.Connection, uid: int | None = None) -> list[dict]:
    """Actividades en la papelera. Con `uid`, sólo las que esa persona creó o mandó
    (cada quien ve su propia papelera; la coordinación, la de todos)."""
    cond, params = ["a.eliminada_en != ''"], []
    if uid is not None:
        cond.append("(a.creada_por = ? OR a.eliminada_por = ?)")
        params += [uid, uid]
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(cond)
        + " ORDER BY a.eliminada_en DESC", params).fetchall()
    salida = []
    for f in filas:
        act = dict(f)
        act["dias_restantes"] = _dias_restantes(act["eliminada_en"])
        salida.append(act)
    return salida


def vencidas(con: sqlite3.Connection) -> list[int]:
    """IDs de las actividades que ya cumplieron 30 días en la papelera (a borrar del todo)."""
    limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_PAPELERA)).isoformat(timespec="seconds")
    return [f["id"] for f in con.execute(
        "SELECT id FROM actividades WHERE eliminada_en != '' AND eliminada_en <= ?", (limite,))]


# --------------------------------------------------------------- autorización por firma

def puede_autorizar(u: sqlite3.Row, act) -> bool:
    """Firma y autoriza el responsable de proyecto de esa actividad (o la coordinación)."""
    resp = act["responsable_id"] if not isinstance(act, dict) else act.get("responsable_id")
    return bool(u["es_admin"] or (resp and resp == u["id"]))


def esta_autorizada(act) -> bool:
    valor = act["autorizada_en"] if not isinstance(act, dict) else act.get("autorizada_en")
    return bool(valor)


def solicitar_autorizacion(con: sqlite3.Connection, act_id: int) -> None:
    """El empleado pide la firma del responsable. No repite fecha si ya está autorizada."""
    con.execute(
        "UPDATE actividades SET autorizacion_solicitada = ? "
        "WHERE id = ? AND autorizada_en = ''", (ahora(), act_id))


def autorizar(con: sqlite3.Connection, act_id: int, uid: int) -> None:
    """El responsable firma y autoriza: a partir de aquí el PDF se puede ver."""
    con.execute(
        "UPDATE actividades SET autorizada_en = ?, autorizada_por = ? WHERE id = ?",
        (ahora(), uid, act_id))


def revocar_autorizacion(con: sqlite3.Connection, act_id: int) -> None:
    """Quita la firma/autorización (por si el responsable se equivocó o hubo un cambio)."""
    con.execute(
        "UPDATE actividades SET autorizada_en = '', autorizada_por = NULL WHERE id = ?",
        (act_id,))


def pendientes_para(con: sqlite3.Connection, uid: int, anio: int | None = None) -> list[dict]:
    """Solicitudes de firma dirigidas a un responsable, agrupadas por quien las pidió.

    Devuelve, p. ej.: «Jareth solicitó firma de 3 actividades de las que eres responsable».
    """
    condiciones = ["a.responsable_id = ?", "a.autorizacion_solicitada != ''",
                   "a.autorizada_en = ''", "a.eliminada_en = ''"]
    params: list = [uid]
    if anio:
        condiciones.append("a.anio = ?")
        params.append(anio)
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY cr.nombre, a.autorizacion_solicitada", params).fetchall()

    grupos: dict[int, dict] = {}
    for f in filas:
        act = dict(f)
        g = grupos.setdefault(act["creada_por"], {
            "solicitante_id": act["creada_por"],
            "solicitante_nombre": act["creador_nombre"],
            "actividades": [],
        })
        g["actividades"].append(act)
    return list(grupos.values())


def cuenta_pendientes(con: sqlite3.Connection, uid: int) -> int:
    return con.execute(
        "SELECT COUNT(*) c FROM actividades "
        "WHERE responsable_id = ? AND autorizacion_solicitada != '' AND autorizada_en = '' "
        "AND eliminada_en = ''",
        (uid,)).fetchone()["c"]


def pendientes_por_responsable(con: sqlite3.Connection,
                               anio: int | None = None) -> list[dict]:
    """Por responsable de proyecto, cuántas actividades esperan su firma (ya se solicitó y
    aún no autoriza). Para que la coordinación vea quién falta por firmar."""
    cond = ["a.autorizacion_solicitada != ''", "a.autorizada_en = ''",
            "a.eliminada_en = ''", "a.responsable_id IS NOT NULL"]
    params: list = []
    if anio:
        cond.append("a.anio = ?")
        params.append(anio)
    filas = con.execute(
        "SELECT r.id, r.nombre, r.cargo, COUNT(*) AS pendientes "
        "FROM actividades a JOIN usuarios r ON r.id = a.responsable_id "
        "WHERE " + " AND ".join(cond) +
        " GROUP BY r.id, r.nombre, r.cargo ORDER BY pendientes DESC, r.nombre",
        params).fetchall()
    return [dict(f) for f in filas]


def sin_responsable(con: sqlite3.Connection, anio: int | None = None) -> list[dict]:
    """Actividades que quedaron sin responsable de proyecto enlazado. Pasa cuando el
    importador no reconoció el nombre del Excel o cuando se registró una sin elegirlo:
    nadie las ve en «A mi cargo» ni en Autorizaciones, así que a su responsable nunca se
    le pide firmar. Las junta para que la coordinación las enlace."""
    cond = ["a.responsable_id IS NULL", "a.eliminada_en = ''"]
    params: list = []
    if anio:
        cond.append("a.anio = ?")
        params.append(anio)
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(cond)
        + " ORDER BY a.anio DESC, cr.nombre, a.titulo", params).fetchall()
    return [dict(f) for f in filas]


def asignar_responsable(con: sqlite3.Connection, act_id: int, resp_id: int) -> bool:
    """Enlaza una actividad con su responsable de proyecto. Sólo admite a quien está
    marcado como responsable y activo; devuelve False si el destino no califica."""
    ok = con.execute(
        "SELECT 1 FROM usuarios WHERE id = ? AND es_responsable = 1 AND activo = 1",
        (resp_id,)).fetchone()
    if not ok:
        return False
    con.execute("UPDATE actividades SET responsable_id = ? WHERE id = ? AND eliminada_en = ''",
                (resp_id, act_id))
    return True


def buscar(con: sqlite3.Connection, anio: int, texto: str = "", zona: str = "",
           trimestre: int = 0, solo_de: int | None = None,
           relacion: str | None = None) -> list[dict]:
    """La lista del tablero. `solo_de` limita a las actividades de una persona y
    `relacion` dice de qué tipo, según QUIÉN creó la actividad (fiable también para los
    datos previos, que no guardaban quién etiquetó):
      - 'mias': actividades que creó esa persona (donde participa confirmada).
      - 'compartidas': actividades creadas por otra persona en las que aparece (no
        rechazadas); ahí confirma si participó.
    Sin `relacion`, cualquier actividad en la que aparezca (para conteos internos)."""
    condiciones, params = ["a.anio = ?", "a.eliminada_en = ''"], [anio]
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
        if relacion == "mias":
            # Las que creó esta persona (donde participa confirmada).
            condiciones.append(
                "a.creada_por = ? AND EXISTS (SELECT 1 FROM participaciones p "
                "WHERE p.actividad_id = a.id AND p.usuario_id = ? AND p.estado = 'confirmada')")
            params += [solo_de, solo_de]
        elif relacion == "compartidas":
            # Creadas por OTRA persona pero donde ésta aparece sin haber rechazado.
            condiciones.append(
                "a.creada_por <> ? AND EXISTS (SELECT 1 FROM participaciones p "
                "WHERE p.actividad_id = a.id AND p.usuario_id = ? AND p.estado <> 'rechazada')")
            params += [solo_de, solo_de]
        elif relacion == "participa":
            # Todas en las que esa persona participa confirmada (la vista por empleado de
            # la coordinación, que no participa pero revisa lo de cada quien).
            condiciones.append(
                "EXISTS (SELECT 1 FROM participaciones p WHERE p.actividad_id = a.id "
                "AND p.usuario_id = ? AND p.estado = 'confirmada')")
            params.append(solo_de)
        elif relacion == "a_cargo":
            # Todas las actividades de las que esa persona es el responsable de proyecto,
            # sin importar si ya se le pidió la firma (el panel del responsable).
            condiciones.append("a.responsable_id = ?")
            params.append(solo_de)
        else:
            condiciones.append("EXISTS (SELECT 1 FROM participaciones p "
                               "WHERE p.actividad_id = a.id AND p.usuario_id = ?)")
            params.append(solo_de)

    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY a.trimestre, a.actualizada_en DESC", params).fetchall()

    salida = []
    for f in filas:
        act = dict(f)
        # En el tablero, «quién participa» y el conteo de fotos son los confirmados.
        resumen = con.execute(
            """SELECT u.nombre,
                      (SELECT COUNT(*) FROM fotos x WHERE x.participacion_id = p.id) nf
                 FROM participaciones p JOIN usuarios u ON u.id = p.usuario_id
                WHERE p.actividad_id = ? AND p.estado = 'confirmada'
                ORDER BY p.creada_en""", (f["id"],)).fetchall()
        act["participantes"] = [r["nombre"] for r in resumen]
        act["n_fotos"] = sum(r["nf"] for r in resumen)
        salida.append(act)
    return salida


def cuenta_compartidas(con: sqlite3.Connection, uid: int, anio: int) -> int:
    """Cuántas actividades tienen a esta persona etiquetada y PENDIENTE de confirmar
    (es lo que se muestra como aviso en la pestaña «Actividades compartidas»)."""
    return con.execute(
        """SELECT COUNT(*) c FROM participaciones p
             JOIN actividades a ON a.id = p.actividad_id
            WHERE p.usuario_id = ? AND p.estado = 'pendiente'
              AND a.creada_por <> ?
              AND a.anio = ? AND a.eliminada_en = ''""", (uid, uid, anio)).fetchone()["c"]


def mis_compartidas_info(con: sqlite3.Connection, uid: int,
                         anio: int) -> dict[int, dict]:
    """Por actividad compartida (creada por otra persona), la participación de ésta, quién
    la etiquetó y su estado. Alimenta los botones «Sí participé / No participé»."""
    filas = con.execute(
        """SELECT p.id AS parte_id, p.actividad_id, p.estado, ag.nombre AS por
             FROM participaciones p
             JOIN actividades a ON a.id = p.actividad_id
        LEFT JOIN usuarios ag ON ag.id = p.agregada_por
            WHERE p.usuario_id = ? AND p.estado <> 'rechazada'
              AND a.creada_por <> ?
              AND a.anio = ? AND a.eliminada_en = ''""", (uid, uid, anio)).fetchall()
    return {f["actividad_id"]: {"parte_id": f["parte_id"], "por": f["por"],
                                "estado": f["estado"]} for f in filas}


def actividades_de(con: sqlite3.Connection, uid: int, anio: int,
                   trimestre: int = 0) -> list[dict]:
    """Las actividades en las que participó una persona, con sus participaciones cargadas.

    Es lo que alimenta la descarga «mis actividades»: cada quien se lleva en un PDF todo
    lo que capturó, con la hoja por actividad del informe individual.
    """
    condiciones = ["a.anio = ?", "a.eliminada_en = ''",
                   "EXISTS (SELECT 1 FROM participaciones p "
                   "WHERE p.actividad_id = a.id AND p.usuario_id = ? "
                   "AND p.estado = 'confirmada')"]
    params: list = [anio, uid]
    if trimestre in (1, 2, 3, 4):
        condiciones.append("a.trimestre = ?")
        params.append(trimestre)
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY a.trimestre, a.zona, a.titulo", params).fetchall()
    salida = []
    for f in filas:
        act = dict(f)
        act["participaciones"] = participaciones(con, f["id"], solo_confirmadas=True)
        salida.append(act)
    return salida


def archivos_de_actividad(con: sqlite3.Connection, act_id: int) -> list[str]:
    return [f["archivo"] for f in con.execute(
        """SELECT f.archivo FROM fotos f
             JOIN participaciones p ON p.id = f.participacion_id
            WHERE p.actividad_id = ?""", (act_id,))]


# --------------------------------------------------------------- participación

def sumar_participante(con: sqlite3.Connection, act_id: int, uid: int,
                       resumen: str = "", estado: str = "confirmada",
                       agregada_por: int | None = None) -> int:
    """Alta idempotente: volver a sumar no duplica ni pisa el resumen ni el estado ya
    guardados. `estado`: 'confirmada' cuando la persona se registra a sí misma; 'pendiente'
    cuando otra la etiqueta y falta que confirme. `agregada_por` guarda quién etiquetó."""
    con.execute(
        """INSERT INTO participaciones (actividad_id, usuario_id, resumen, estado,
                                        agregada_por, creada_en, actualizada_en)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (actividad_id, usuario_id) DO NOTHING""",
        (act_id, uid, resumen, estado, agregada_por, ahora(), ahora()),
    )
    fila = con.execute(
        "SELECT id FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
        (act_id, uid),
    ).fetchone()
    return int(fila["id"])


def estado_participacion(con: sqlite3.Connection, act_id: int, uid: int) -> str | None:
    """El estado de la participación de una persona en una actividad, o None si no está."""
    fila = con.execute(
        "SELECT estado FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
        (act_id, uid)).fetchone()
    return fila["estado"] if fila else None


def confirmar_participacion(con: sqlite3.Connection, parte_id: int) -> None:
    """El empleado confirma que sí participó: la participación pasa a contar en el informe."""
    con.execute("UPDATE participaciones SET estado = 'confirmada', actualizada_en = ? "
                "WHERE id = ?", (ahora(), parte_id))


def rechazar_participacion(con: sqlite3.Connection, parte_id: int) -> None:
    """El empleado dice que NO participó: deja de contar y sólo la coordinación puede
    volver a etiquetarlo."""
    con.execute("UPDATE participaciones SET estado = 'rechazada', actualizada_en = ? "
                "WHERE id = ?", (ahora(), parte_id))


def guardar_nota(con: sqlite3.Connection, parte_id: int, nota: str, por: int) -> None:
    """El responsable de proyecto o la coordinación deja una nota/observación al empleado
    sobre su resumen (corregir redacción, etc.). Vaciarla la quita."""
    con.execute(
        "UPDATE participaciones SET nota = ?, nota_por = ?, nota_en = ? WHERE id = ?",
        (nota.strip(), por if nota.strip() else None,
         ahora() if nota.strip() else "", parte_id))


def reetiquetar_participacion(con: sqlite3.Connection, act_id: int, uid: int,
                              por: int) -> None:
    """La coordinación vuelve a etiquetar a alguien que había rechazado: regresa a
    'pendiente' para que confirme de nuevo."""
    con.execute(
        "UPDATE participaciones SET estado = 'pendiente', agregada_por = ?, "
        "actualizada_en = ? WHERE actividad_id = ? AND usuario_id = ?",
        (por, ahora(), act_id, uid))


def participacion(con: sqlite3.Connection, parte_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM participaciones WHERE id = ?", (parte_id,)).fetchone()


def participaciones(con: sqlite3.Connection, act_id: int,
                    solo_confirmadas: bool = False) -> list[dict]:
    """Participaciones de una actividad. Con `solo_confirmadas` deja fuera las pendientes
    de confirmar y las rechazadas: es lo que va al informe y a los conteos."""
    cond = "p.actividad_id = ?"
    if solo_confirmadas:
        cond += " AND p.estado = 'confirmada'"
    filas = con.execute(
        f"""SELECT p.*, u.nombre, u.cargo, u.grupo, u.firma, u.es_responsable,
                   nb.nombre AS nota_por_nombre
             FROM participaciones p JOIN usuarios u ON u.id = p.usuario_id
        LEFT JOIN usuarios nb ON nb.id = p.nota_por
            WHERE {cond}
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
             FROM actividades WHERE anio = ? AND eliminada_en = ''""", (anio,)).fetchone()
    personas = con.execute(
        """SELECT COUNT(DISTINCT p.usuario_id) c
             FROM participaciones p JOIN actividades a ON a.id = p.actividad_id
            WHERE a.anio = ? AND a.eliminada_en = '' AND p.estado = 'confirmada'""",
        (anio,)).fetchone()["c"]
    colaborativas = con.execute(
        """SELECT COUNT(*) c FROM (
              SELECT p.actividad_id FROM participaciones p
                JOIN actividades a ON a.id = p.actividad_id
               WHERE a.anio = ? AND a.eliminada_en = '' AND p.estado = 'confirmada'
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
    condiciones, params = ["a.anio = ?", "a.eliminada_en = ''"], [anio]
    if trimestre in (1, 2, 3, 4):
        condiciones.append("a.trimestre = ?")
        params.append(trimestre)
    filas = con.execute(
        _SELECT_ACTIVIDAD + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY a.zona, c.eje, a.titulo", params).fetchall()

    grupos: dict[str, list[dict]] = {}
    for f in filas:
        act = dict(f)
        act["participaciones"] = participaciones(con, f["id"], solo_confirmadas=True)
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
