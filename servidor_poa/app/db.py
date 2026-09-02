# -*- coding: utf-8 -*-
"""Esquema y acceso a datos de la Plataforma POA.

El modelo central: una ACTIVIDAD es un hecho del mundo real y existe una sola vez.
Cada empleado que trabajó en ella agrega su PARTICIPACION (su resumen y sus fotos).
Por eso el conteo POA de la actividad se toma de la actividad, no de las
participaciones: si tres personas intervinieron el mismo mural, el POA cuenta 1.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATOS_DIR = BASE_DIR / "datos"
FOTOS_DIR = DATOS_DIR / "fotos"
DB_PATH = DATOS_DIR / "poa.db"

ESQUEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- No hay contraseñas: cada quien entra eligiendo su nombre de la lista. Sólo la
-- coordinación tiene un PIN, y sólo para el Consolidado y el panel de Personal.
CREATE TABLE IF NOT EXISTS usuarios (
  id                     INTEGER PRIMARY KEY,
  usuario                TEXT NOT NULL UNIQUE,
  nombre                 TEXT NOT NULL,
  cargo                  TEXT NOT NULL DEFAULT '',
  grupo                  TEXT NOT NULL DEFAULT '',
  email                  TEXT NOT NULL DEFAULT '',   -- correo Microsoft (login Entra ID y match de invitados del calendario)
  es_responsable         INTEGER NOT NULL DEFAULT 0,
  es_admin               INTEGER NOT NULL DEFAULT 0,
  pin_hash               TEXT NOT NULL DEFAULT '',
  activo                 INTEGER NOT NULL DEFAULT 1,
  creado_en              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalogo_poa (
  id                   INTEGER PRIMARY KEY,
  actividad_poa        TEXT NOT NULL UNIQUE,
  unidad_medida        TEXT NOT NULL DEFAULT '',
  programa_operativo   TEXT NOT NULL DEFAULT '',
  eje                  TEXT NOT NULL DEFAULT '',
  linea_accion_enc     TEXT NOT NULL DEFAULT '',
  eje_estrategico_enc  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS zonas (
  id          INTEGER PRIMARY KEY,
  nombre      TEXT NOT NULL,
  nombre_norm TEXT NOT NULL UNIQUE,
  usos        INTEGER NOT NULL DEFAULT 0,
  -- Coordenadas geocodificadas una sola vez (Nominatim) para dibujar el mapa del
  -- informe. NULL mientras no se hayan resuelto o si el sitio no se pudo ubicar.
  lat         REAL,
  lon         REAL
);

CREATE TABLE IF NOT EXISTS actividades (
  id                 INTEGER PRIMARY KEY,
  titulo             TEXT NOT NULL,
  titulo_norm        TEXT NOT NULL,
  catalogo_id        INTEGER NOT NULL REFERENCES catalogo_poa(id),
  zona               TEXT NOT NULL DEFAULT '',
  zona_norm          TEXT NOT NULL DEFAULT '',
  programa_nacional  TEXT NOT NULL DEFAULT 'Ninguno',
  anio               INTEGER NOT NULL,
  -- Trimestre al que pertenece la actividad (1..4). Es la categoría que se elige al
  -- capturar; plan_tN e inf_tN se llenan en ese trimestre y los demás quedan en 0.
  -- La rejilla de 4+4 se conserva porque es la forma del POA oficial y del PDF.
  trimestre          INTEGER NOT NULL DEFAULT 0,
  planeado_anual     REAL NOT NULL DEFAULT 0,
  plan_t1            REAL NOT NULL DEFAULT 0,
  plan_t2            REAL NOT NULL DEFAULT 0,
  plan_t3            REAL NOT NULL DEFAULT 0,
  plan_t4            REAL NOT NULL DEFAULT 0,
  inf_t1             REAL NOT NULL DEFAULT 0,
  inf_t2             REAL NOT NULL DEFAULT 0,
  inf_t3             REAL NOT NULL DEFAULT 0,
  inf_t4             REAL NOT NULL DEFAULT 0,
  planeacion         TEXT NOT NULL DEFAULT 'Si',
  objetivo           TEXT NOT NULL DEFAULT '',
  -- Pin exacto de la ubicación (lo confirma quien captura). Si está, el mapa del
  -- informe usa este punto; si es NULL, se geocodifica el nombre de la zona.
  mapa_lat           REAL,
  mapa_lon           REAL,
  observaciones      TEXT NOT NULL DEFAULT '',
  fechas_ejecucion   TEXT NOT NULL DEFAULT '',
  responsable_id     INTEGER REFERENCES usuarios(id),
  creada_por         INTEGER NOT NULL REFERENCES usuarios(id),
  creada_en          TEXT NOT NULL,
  actualizada_en     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_act_anio       ON actividades(anio);
CREATE INDEX IF NOT EXISTS ix_act_titulonorm ON actividades(titulo_norm);
CREATE INDEX IF NOT EXISTS ix_act_zona       ON actividades(zona_norm);

CREATE TABLE IF NOT EXISTS participaciones (
  id            INTEGER PRIMARY KEY,
  actividad_id  INTEGER NOT NULL REFERENCES actividades(id) ON DELETE CASCADE,
  usuario_id    INTEGER NOT NULL REFERENCES usuarios(id),
  resumen       TEXT NOT NULL DEFAULT '',
  creada_en     TEXT NOT NULL,
  actualizada_en TEXT NOT NULL,
  UNIQUE (actividad_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS fotos (
  id                INTEGER PRIMARY KEY,
  participacion_id  INTEGER NOT NULL REFERENCES participaciones(id) ON DELETE CASCADE,
  archivo           TEXT NOT NULL,
  archivo_pdf       TEXT NOT NULL DEFAULT '',
  nombre_original   TEXT NOT NULL DEFAULT '',
  bytes             INTEGER NOT NULL DEFAULT 0,
  bytes_pdf         INTEGER NOT NULL DEFAULT 0,
  bytes_original    INTEGER NOT NULL DEFAULT 0,
  ancho             INTEGER NOT NULL DEFAULT 0,
  alto              INTEGER NOT NULL DEFAULT 0,
  pie               TEXT NOT NULL DEFAULT '',
  destacada         INTEGER NOT NULL DEFAULT 0,
  orden             INTEGER NOT NULL DEFAULT 0,
  creada_en         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fotos_part ON fotos(participacion_id);
"""

TRIMESTRES = {1: "1er Trimestre", 2: "2do Trimestre", 3: "3er Trimestre", 4: "4to Trimestre"}

# El Excel de origen escribe "Corservación" en los siete programas. Se corrige aquí.
PROGRAMAS_NACIONALES = [
    "Ninguno",
    "Programa Nacional de Conservación de Patrimonio Arqueológico",
    "Programa Nacional de Conservación de Patrimonio Histórico",
    "Programa Nacional de Conservación de Patrimonio Gráfico-rupestre",
    "Programa Nacional de Conservación de Patrimonio Paleontológico",
    "Programa Nacional de Conservación de Patrimonio en Museos",
    "Programa Nacional de Conservación de Acervos Documentales",
]


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(texto: str | None) -> str:
    """Minúsculas sin acentos ni puntuación, para comparar sin depender de cómo se escribió.

    'Chichén Itzá' y 'chichen  itza.' colapsan al mismo valor.
    """
    s = unicodedata.normalize("NFD", str(texto or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())
    return " ".join(s.split())


def conectar() -> sqlite3.Connection:
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    FOTOS_DIR.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False porque las rutas async abren la conexión en un hilo del
    # pool y la usan en el event loop. Es seguro: cada petición tiene la suya y no se
    # comparte entre peticiones (ver la dependencia bd() en main.py).
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def crear_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    _migrar(con)
    con.commit()


def _migrar(con: sqlite3.Connection) -> None:
    """Lleva una base ya existente al esquema actual, sin tocar los datos."""
    columnas = {f["name"] for f in con.execute("PRAGMA table_info(usuarios)")}

    # v3.1: se quitaron las contraseñas. Sólo la coordinación tiene PIN.
    if "pin_hash" not in columnas:
        con.execute("ALTER TABLE usuarios ADD COLUMN pin_hash TEXT NOT NULL DEFAULT ''")

    # v3.3: correo Microsoft para el login con Entra ID y para casar los invitados
    # del calendario de Outlook con cada persona de la Sección.
    if "email" not in columnas:
        con.execute("ALTER TABLE usuarios ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    for obsoleta in ("password_hash", "debe_cambiar_password"):
        if obsoleta in columnas:
            con.execute(f"ALTER TABLE usuarios DROP COLUMN {obsoleta}")

    fotos_cols = {f["name"] for f in con.execute("PRAGMA table_info(fotos)")}
    if "archivo_pdf" not in fotos_cols:
        con.execute("ALTER TABLE fotos ADD COLUMN archivo_pdf TEXT NOT NULL DEFAULT ''")
        con.execute("ALTER TABLE fotos ADD COLUMN bytes_pdf INTEGER NOT NULL DEFAULT 0")

    act_cols = {f["name"] for f in con.execute("PRAGMA table_info(actividades)")}
    if "trimestre" not in act_cols:
        con.execute("ALTER TABLE actividades ADD COLUMN trimestre INTEGER NOT NULL DEFAULT 0")
        _asignar_trimestre(con)

    # v3.5: objetivo de la actividad (encabeza cada hoja del informe nuevo).
    if "objetivo" not in act_cols:
        con.execute("ALTER TABLE actividades ADD COLUMN objetivo TEXT NOT NULL DEFAULT ''")

    # v3.5: pin exacto de la ubicación por actividad (confirmado al capturar).
    if "mapa_lat" not in act_cols:
        con.execute("ALTER TABLE actividades ADD COLUMN mapa_lat REAL")
        con.execute("ALTER TABLE actividades ADD COLUMN mapa_lon REAL")

    # v3.5: coordenadas de cada zona para el mapa del informe.
    zona_cols = {f["name"] for f in con.execute("PRAGMA table_info(zonas)")}
    if "lat" not in zona_cols:
        con.execute("ALTER TABLE zonas ADD COLUMN lat REAL")
        con.execute("ALTER TABLE zonas ADD COLUMN lon REAL")


def _asignar_trimestre(con: sqlite3.Connection) -> None:
    """Deduce el trimestre de las actividades que venían de la rejilla de 4+4.

    Manda lo informado: una actividad pertenece al trimestre en que se ejecutó. Lo
    planeado se recoge de donde estuviera y se concentra en ese mismo trimestre, que es
    lo que ahora captura el formulario (en el POA de origen era común planear en un
    trimestre y ejecutar en otro; al colapsar, gana el de ejecución).
    """
    for f in con.execute("SELECT * FROM actividades"):
        informados = [n for n in (1, 2, 3, 4) if (f[f"inf_t{n}"] or 0) > 0]
        planeados = [n for n in (1, 2, 3, 4) if (f[f"plan_t{n}"] or 0) > 0]
        trimestre = (informados or planeados or [0])[0]
        if not trimestre:
            continue
        total_plan = sum(f[f"plan_t{n}"] or 0 for n in (1, 2, 3, 4))
        total_inf = sum(f[f"inf_t{n}"] or 0 for n in (1, 2, 3, 4))
        con.execute(
            f"""UPDATE actividades
                   SET trimestre = ?,
                       plan_t1 = 0, plan_t2 = 0, plan_t3 = 0, plan_t4 = 0,
                       inf_t1 = 0, inf_t2 = 0, inf_t3 = 0, inf_t4 = 0,
                       plan_t{trimestre} = ?, inf_t{trimestre} = ?
                 WHERE id = ?""",
            (trimestre, total_plan, total_inf, f["id"]),
        )
