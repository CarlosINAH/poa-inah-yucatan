# -*- coding: utf-8 -*-
"""Plataforma POA - Sección de Conservación y Restauración, Centro INAH Yucatán."""
from __future__ import annotations

import difflib
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, consolidado, fotos as fotos_mod, mapas, pdf
from .db import (FOTOS_DIR, PROGRAMAS_NACIONALES, TRIMESTRES, ahora, conectar,
                 crear_esquema, norm)

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Plataforma POA · Conservación · Centro INAH Yucatán")

# La llave firma la cookie de sesión. Si cambia, todos vuelven a entrar; por eso
# se guarda en disco en lugar de generarse en cada arranque.
_llave = BASE.parent / "datos" / "llave_sesion.txt"
_llave.parent.mkdir(parents=True, exist_ok=True)
if not _llave.exists():
    _llave.write_text(secrets.token_hex(32), encoding="utf-8")
    os.chmod(_llave, 0o600)
# En la red interna del Centro se sirve por HTTP, así que la cookie no puede exigir
# HTTPS. Cuando la plataforma se publica en línea (Fly.io, con HTTPS), se activa
# POA_COOKIE_SEGURA=1 para que la cookie de sesión sólo viaje cifrada.
_cookie_segura = os.environ.get("POA_COOKIE_SEGURA", "0") == "1"
app.add_middleware(
    SessionMiddleware,
    secret_key=_llave.read_text(encoding="utf-8").strip(),
    session_cookie="poa_sesion",
    max_age=12 * 60 * 60,
    same_site="lax",
    https_only=_cookie_segura,
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
plantillas = Jinja2Templates(directory=str(BASE / "templates"))


@app.on_event("startup")
def _preparar() -> None:
    con = conectar()
    crear_esquema(con)
    con.close()


# ----------------------------------------------------------------- infraestructura

def bd():
    con = conectar()
    try:
        yield con
    finally:
        con.close()


def usuario_actual(request: Request, con: sqlite3.Connection) -> sqlite3.Row | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    return con.execute(
        "SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)
    ).fetchone()


def exigir_sesion(request: Request, con: sqlite3.Connection = Depends(bd)) -> sqlite3.Row:
    u = usuario_actual(request, con)
    if u is None:
        raise HTTPException(status_code=307, headers={"Location": "/entrar"})
    return u


def exigir_admin(u: sqlite3.Row = Depends(exigir_sesion)) -> sqlite3.Row:
    if not u["es_admin"]:
        raise HTTPException(status_code=403, detail="Sólo la coordinación puede entrar aquí.")
    return u


def exigir_consolidado(u: sqlite3.Row = Depends(exigir_sesion)) -> sqlite3.Row:
    """El consolidado lo ven la coordinación y los responsables de proyecto.
    Los empleados sólo capturan y editan actividades; no ven el informe de la Sección."""
    if not (u["es_admin"] or u["es_responsable"]):
        raise HTTPException(
            status_code=403,
            detail="El consolidado es sólo para la coordinación y los responsables de proyecto.",
        )
    return u


@app.exception_handler(HTTPException)
async def _redirigir(request: Request, exc: HTTPException):
    if exc.status_code == 307 and "Location" in (exc.headers or {}):
        return RedirectResponse(exc.headers["Location"], status_code=303)
    con = conectar()
    try:
        u = usuario_actual(request, con)
        return plantillas.TemplateResponse(
            request, "error.html",
            {"u": u, "codigo": exc.status_code,
             "detalle": exc.detail or "Algo salió mal."},
            status_code=exc.status_code,
        )
    finally:
        con.close()


def vista(request: Request, nombre: str, ctx: dict[str, Any]) -> HTMLResponse:
    ctx.setdefault("aviso", request.session.pop("aviso", None))
    return plantillas.TemplateResponse(request, nombre, ctx)


def avisar(request: Request, texto: str) -> None:
    request.session["aviso"] = texto


# ------------------------------------------------------------------------ sesión

@app.get("/", response_class=HTMLResponse)
def raiz(request: Request, con: sqlite3.Connection = Depends(bd)):
    return RedirectResponse("/inicio" if usuario_actual(request, con) else "/entrar",
                            status_code=303)


@app.get("/inicio", response_class=HTMLResponse)
def inicio(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
           con: sqlite3.Connection = Depends(bd)):
    """El punto de partida: una decisión a la vez, con las palabras de la Sección.

    Antes se caía directo al tablero, que ya mezclaba consultar y registrar. Para quien
    no usa mucho la computadora, esa pantalla pedía entender la tabla antes de poder
    hacer nada.
    """
    anio = consolidado.anio_por_defecto(con)
    mias = len(consolidado.buscar(con, anio=anio, solo_de=u["id"]))
    return vista(request, "inicio.html", {
        "u": u, "anio": anio, "mias": mias,
        "total": consolidado.kpis(con, anio)["actividades"],
    })


@app.get("/entrar", response_class=HTMLResponse)
def entrar_form(request: Request, con: sqlite3.Connection = Depends(bd)):
    request.session.clear()
    return vista(request, "entrar.html", {"u": None, "personas": auth.seleccionables(con)})


@app.post("/entrar")
def entrar(request: Request, usuario_id: int = Form(...),
           con: sqlite3.Connection = Depends(bd)):
    fila = con.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1",
                       (usuario_id,)).fetchone()
    if fila is None:
        avisar(request, "Elige tu nombre de la lista.")
        return RedirectResponse("/entrar", status_code=303)

    request.session.clear()
    # Cada persona usa su PIN: la sesión no se abre hasta que el PIN esté puesto. Quien
    # aún no lo tiene lo define en su primer ingreso; quien ya lo tiene lo escribe.
    request.session["pin_pendiente"] = fila["id"]
    return RedirectResponse("/pin" if fila["pin_hash"] else "/definir-pin", status_code=303)


def _pendiente(request: Request, con: sqlite3.Connection) -> sqlite3.Row | None:
    uid = request.session.get("pin_pendiente")
    if not uid:
        return None
    return con.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)).fetchone()


@app.get("/pin", response_class=HTMLResponse)
def pin_form(request: Request, con: sqlite3.Connection = Depends(bd)):
    p = _pendiente(request, con)
    if p is None:
        return RedirectResponse("/entrar", status_code=303)
    return vista(request, "pin.html", {"u": None, "persona": p, "error": None})


@app.post("/pin", response_class=HTMLResponse)
def pin_verificar(request: Request, pin: str = Form(...),
                  con: sqlite3.Connection = Depends(bd)):
    p = _pendiente(request, con)
    if p is None:
        return RedirectResponse("/entrar", status_code=303)
    if not auth.verificar_pin(p["pin_hash"], pin):
        return vista(request, "pin.html",
                     {"u": None, "persona": p, "error": "Ese PIN no es correcto."})
    request.session.clear()
    request.session["uid"] = p["id"]
    return RedirectResponse("/tablero", status_code=303)


@app.get("/definir-pin", response_class=HTMLResponse)
def definir_pin_form(request: Request, con: sqlite3.Connection = Depends(bd)):
    p = _pendiente(request, con)
    if p is None or p["pin_hash"]:
        return RedirectResponse("/entrar", status_code=303)
    return vista(request, "definir_pin.html", {"u": None, "persona": p, "error": None})


@app.post("/definir-pin", response_class=HTMLResponse)
def definir_pin(request: Request, nuevo: str = Form(...), repetir: str = Form(...),
                con: sqlite3.Connection = Depends(bd)):
    p = _pendiente(request, con)
    if p is None or p["pin_hash"]:
        return RedirectResponse("/entrar", status_code=303)

    def fallo(msg):
        return vista(request, "definir_pin.html",
                     {"u": None, "persona": p, "error": msg})

    if nuevo != repetir:
        return fallo("El PIN y su repetición no coinciden.")
    if motivo := auth.validar_pin(nuevo):
        return fallo(motivo)

    con.execute("UPDATE usuarios SET pin_hash = ? WHERE id = ?",
                (auth.hash_pin(nuevo.strip()), p["id"]))
    con.commit()
    request.session.clear()
    request.session["uid"] = p["id"]
    avisar(request, "Tu PIN quedó guardado. Te lo pedirá cada vez que entres.")
    return RedirectResponse("/tablero", status_code=303)


@app.get("/mi-pin", response_class=HTMLResponse)
def mi_pin_form(request: Request, u: sqlite3.Row = Depends(exigir_sesion)):
    return vista(request, "mi_pin.html", {"u": u, "error": None})


@app.post("/mi-pin", response_class=HTMLResponse)
def mi_pin(request: Request, actual: str = Form(...), nuevo: str = Form(...),
           repetir: str = Form(...), u: sqlite3.Row = Depends(exigir_sesion),
           con: sqlite3.Connection = Depends(bd)):
    def fallo(msg):
        return vista(request, "mi_pin.html", {"u": u, "error": msg})

    if not auth.verificar_pin(u["pin_hash"], actual):
        return fallo("Tu PIN actual no es correcto.")
    if nuevo != repetir:
        return fallo("El PIN nuevo y su repetición no coinciden.")
    if motivo := auth.validar_pin(nuevo):
        return fallo(motivo)
    con.execute("UPDATE usuarios SET pin_hash = ? WHERE id = ?",
                (auth.hash_pin(nuevo.strip()), u["id"]))
    con.commit()
    avisar(request, "Tu PIN quedó actualizado.")
    return RedirectResponse("/tablero", status_code=303)


@app.post("/salir")
def salir(request: Request):
    request.session.clear()
    return RedirectResponse("/entrar", status_code=303)


# ----------------------------------------------------------------------- tablero

@app.get("/tablero", response_class=HTMLResponse)
def tablero(request: Request, anio: int | None = None, trimestre: int = 0, q: str = "",
            zona: str = "", ver: str = "mias",
            u: sqlite3.Row = Depends(exigir_sesion), con: sqlite3.Connection = Depends(bd)):
    """El tablero ES la lista de actividades: no hay una pantalla aparte que repita."""
    anio = anio or consolidado.anio_por_defecto(con)
    # Sólo coordinación y responsables ven las actividades de toda la Sección.
    # Un empleado siempre ve únicamente en las que participó, aunque escriba ?ver=todas.
    puede_todas = bool(u["es_admin"] or u["es_responsable"])
    ver = ver if ver in ("mias", "todas") else "mias"
    if not puede_todas:
        ver = "mias"
    filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre,
                               solo_de=u["id"] if ver == "mias" else None)
    return vista(request, "tablero.html", {
        "u": u, "anio": anio, "trimestre": trimestre, "q": q, "zona": zona, "ver": ver,
        "puede_todas": puede_todas,
        "anios": consolidado.anios_disponibles(con),
        "trimestres": TRIMESTRES,
        "zonas": consolidado.zonas_usadas(con),
        "kpis": consolidado.kpis(con, anio),
        "filas": filas,
    })


@app.get("/actividades")
def actividades_movido():
    """La pantalla «Actividades» se fundió con el tablero: mostraban lo mismo."""
    return RedirectResponse("/tablero?ver=todas", status_code=307)


@app.get("/registrar", response_class=HTMLResponse)
def registrar_periodo(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
                      con: sqlite3.Connection = Depends(bd)):
    """Paso 1 de 3: el periodo, solo. Elegir año y trimestre es una decisión chica y
    sin riesgo; ponerla sola de entrada evita la pantalla larga que espantaba."""
    return vista(request, "registrar_periodo.html", {
        "u": u,
        "anios": consolidado.anios_disponibles(con),
        "anio_defecto": consolidado.anio_por_defecto(con),
        "trimestres": TRIMESTRES,
    })


@app.get("/actividades/nueva", response_class=HTMLResponse)
def nueva_form(request: Request, anio: int = 0, trimestre: int = 0,
               u: sqlite3.Row = Depends(exigir_sesion),
               con: sqlite3.Connection = Depends(bd)):
    # Sin periodo no se puede empezar: se regresa al paso 1 en vez de mostrar el
    # formulario a medias.
    if trimestre not in (1, 2, 3, 4) or not anio:
        return RedirectResponse("/registrar", status_code=303)
    # `act` debe traer TODOS los campos que la plantilla lee: al venir del paso 1 sólo
    # se conoce el periodo, el resto va en blanco pero tiene que existir.
    vacia = {c: "" for c in ("titulo", "zona", "fechas_ejecucion", "observaciones",
                             "objetivo")}
    vacia.update({"id": None, "catalogo_id": 0, "responsable_id": None,
                  "programa_nacional": "Ninguno", "planeacion": "Si",
                  "planeado": 1, "realizado": 1, "mapa_lat": None, "mapa_lon": None,
                  "anio": anio, "trimestre": trimestre})
    return vista(request, "actividad_form.html", {
        "u": u, "act": vacia,
        "error": None, "editando": False, "paso": 2,
        "catalogo": consolidado.catalogo(con),
        "responsables": consolidado.responsables(con),
        "programas": PROGRAMAS_NACIONALES,
        "zonas": consolidado.zonas_usadas(con),
        "trimestres": TRIMESTRES,
        "anio_defecto": anio,
    })


def _leer_form_actividad(datos: dict) -> dict:
    def num(clave, defecto=0.0):
        try:
            return max(0.0, float(datos.get(clave) or defecto))
        except ValueError:
            return defecto
    try:
        trimestre = int(datos.get("trimestre") or 0)
    except ValueError:
        trimestre = 0
    campos = {
        "titulo": (datos.get("titulo") or "").strip(),
        "catalogo_id": int(datos.get("catalogo_id") or 0),
        "zona": (datos.get("zona") or "").strip(),
        "programa_nacional": (datos.get("programa_nacional") or "Ninguno").strip(),
        "anio": int(datos.get("anio") or 0),
        "trimestre": trimestre if trimestre in (1, 2, 3, 4) else 0,
        "planeado": num("planeado", 1.0),
        "realizado": num("realizado", 1.0),
        "planeacion": "Si" if (datos.get("planeacion") or "Si") == "Si" else "No",
        "objetivo": (datos.get("objetivo") or "").strip(),
        "observaciones": (datos.get("observaciones") or "").strip(),
        # Pin exacto de la ubicación: se pega un enlace de mapa o coordenadas. Si no
        # trae coordenadas válidas, queda NULL y el informe geocodifica el nombre.
        **dict(zip(("mapa_lat", "mapa_lon"),
                   mapas.parsear_coordenadas(datos.get("ubicacion_pin") or "") or (None, None))),
        "fechas_ejecucion": (datos.get("fechas_ejecucion") or "").strip(),
        "responsable_id": int(datos.get("responsable_id") or 0) or None,
    }
    return consolidado.expandir_periodo(campos)


@app.post("/actividades")
async def crear(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
                con: sqlite3.Connection = Depends(bd)):
    datos = _leer_form_actividad(dict(await request.form()))
    resumen = (dict(await request.form()).get("resumen") or "").strip()

    def fallo(msg):
        return vista(request, "actividad_form.html", {
            "u": u, "act": datos, "error": msg, "resumen": resumen, "editando": False,
            "catalogo": consolidado.catalogo(con),
            "responsables": consolidado.responsables(con),
            "programas": PROGRAMAS_NACIONALES,
            "zonas": consolidado.zonas_usadas(con),
            "trimestres": TRIMESTRES,
            "anio_defecto": consolidado.anio_por_defecto(con),
        })

    if len(datos["titulo"]) < 5:
        return fallo("Describe la actividad que realizaste (al menos 5 caracteres).")
    if not datos["catalogo_id"]:
        return fallo("Elige la Actividad POA con la que se alinea.")
    if not datos["anio"]:
        return fallo("Indica el año.")
    if not datos["trimestre"]:
        return fallo("Elige el trimestre al que pertenece la actividad.")

    datos["zona"] = consolidado.canonizar_zona(con, datos["zona"])
    act_id = consolidado.insertar_actividad(con, datos, u["id"])
    consolidado.sumar_participante(con, act_id, u["id"], resumen)
    con.commit()
    avisar(request, "Actividad registrada. Ahora puedes subir tus fotos.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.get("/actividades/{act_id}", response_class=HTMLResponse)
def detalle(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
            con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    partes = consolidado.participaciones(con, act_id)
    mi_parte = next((p for p in partes if p["usuario_id"] == u["id"]), None)
    # Puede sumar a otras personas quien ya participa (fue una labor compartida) o quien
    # puede editar la ficha (creador, responsable, coordinación). La lista para elegir
    # deja fuera a quienes ya están.
    puede_agregar = bool(mi_parte) or consolidado.puede_editar(u, act)
    ids_parte = {p["usuario_id"] for p in partes}
    agregables = ([r for r in auth.seleccionables(con) if r["id"] not in ids_parte]
                  if puede_agregar else [])
    return vista(request, "actividad_detalle.html", {
        "u": u, "act": act, "partes": partes,
        "mi_parte": mi_parte,
        "puede_editar": consolidado.puede_editar(u, act),
        "puede_agregar": puede_agregar, "agregables": agregables,
        "max_fotos": fotos_mod.MAX_FOTOS_POR_PARTICIPACION,
    })


@app.get("/actividades/{act_id}/editar", response_class=HTMLResponse)
def editar_form(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_editar(u, act):
        raise HTTPException(403, "Sólo quien creó la actividad, su responsable "
                                 "o la coordinación pueden editarla.")
    datos = dict(act)
    # El formulario habla de un solo periodo; la base guarda la rejilla de 4+4.
    t = datos["trimestre"] or 0
    datos["planeado"] = datos.get(f"plan_t{t}", 0) if t else 0
    datos["realizado"] = datos.get(f"inf_t{t}", 0) if t else 0
    return vista(request, "actividad_form.html", {
        "u": u, "act": datos, "error": None, "editando": True,
        "catalogo": consolidado.catalogo(con),
        "responsables": consolidado.responsables(con),
        "programas": PROGRAMAS_NACIONALES,
        "zonas": consolidado.zonas_usadas(con),
        "trimestres": TRIMESTRES,
        "anio_defecto": act["anio"],
    })


@app.post("/actividades/{act_id}/editar")
async def editar(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                 con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_editar(u, act):
        raise HTTPException(403, "No tienes permiso para editar esta actividad.")
    datos = _leer_form_actividad(dict(await request.form()))
    if len(datos["titulo"]) < 5 or not datos["catalogo_id"] or not datos["trimestre"]:
        raise HTTPException(400, "Faltan el título, la Actividad POA o el trimestre.")
    datos["zona"] = consolidado.canonizar_zona(con, datos["zona"])
    consolidado.actualizar_actividad(con, act_id, datos)
    con.commit()
    avisar(request, "Actividad actualizada.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.post("/actividades/{act_id}/sumarme")
def sumarme(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
            con: sqlite3.Connection = Depends(bd)):
    if consolidado.actividad(con, act_id) is None:
        raise HTTPException(404, "Esa actividad no existe.")
    consolidado.sumar_participante(con, act_id, u["id"], "")
    con.commit()
    avisar(request, "Te sumaste a la actividad. Escribe tu resumen y sube tus fotos.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.post("/actividades/{act_id}/participantes")
def agregar_participante(request: Request, act_id: int, usuario_id: int = Form(...),
                         u: sqlite3.Row = Depends(exigir_sesion),
                         con: sqlite3.Connection = Depends(bd)):
    """Sumar a OTRA persona a una actividad compartida.

    Lo puede hacer quien ya participa en ella o quien puede editar la ficha (creador,
    responsable, coordinación). La persona agregada entra después a escribir su propio
    resumen y subir sus fotos; la actividad sigue contando 1 para el POA.
    """
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    soy_parte = con.execute(
        "SELECT 1 FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
        (act_id, u["id"]),
    ).fetchone()
    if not (soy_parte or consolidado.puede_editar(u, act)):
        raise HTTPException(403, "Sólo quien participa en la actividad o la coordinación "
                                 "puede agregar a otras personas.")
    objetivo = con.execute("SELECT id, nombre FROM usuarios WHERE id = ? AND activo = 1",
                           (usuario_id,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no está en la lista.")
    consolidado.sumar_participante(con, act_id, objetivo["id"], "")
    con.commit()
    avisar(request, f"Agregaste a {objetivo['nombre']}. Cuando entre, podrá escribir su "
                    "resumen y subir sus fotos.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.post("/actividades/{act_id}/eliminar")
def eliminar_actividad(request: Request, act_id: int,
                       u: sqlite3.Row = Depends(exigir_admin),
                       con: sqlite3.Connection = Depends(bd)):
    # Sólo coordinación: eliminar arrastra los resúmenes y las fotos de TODOS los
    # participantes y no se deshace. Como entrar es sólo elegir un nombre de la lista,
    # dejar esto abierto significaría que un clic equivocado borra el trabajo de otro.
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    for archivo in consolidado.archivos_de_actividad(con, act_id):
        fotos_mod.eliminar(archivo)
    con.execute("DELETE FROM actividades WHERE id = ?", (act_id,))
    con.commit()
    avisar(request, f"Se eliminó «{act['titulo']}» y sus fotos.")
    return RedirectResponse("/actividades", status_code=303)


# ------------------------------------------------------------- participación

@app.post("/participaciones/{parte_id}/resumen")
def guardar_resumen(request: Request, parte_id: int, resumen: str = Form(""),
                    u: sqlite3.Row = Depends(exigir_sesion),
                    con: sqlite3.Connection = Depends(bd)):
    parte = consolidado.participacion(con, parte_id)
    if parte is None:
        raise HTTPException(404, "Esa participación no existe.")
    if parte["usuario_id"] != u["id"] and not u["es_admin"]:
        raise HTTPException(403, "Cada quien escribe su propio resumen.")
    con.execute(
        "UPDATE participaciones SET resumen = ?, actualizada_en = ? WHERE id = ?",
        (resumen.strip(), ahora(), parte_id),
    )
    con.commit()
    avisar(request, "Resumen guardado.")
    return RedirectResponse(f"/actividades/{parte['actividad_id']}", status_code=303)


@app.post("/participaciones/{parte_id}/fotos")
async def subir_fotos(request: Request, parte_id: int,
                      archivos: list[UploadFile] = [],
                      u: sqlite3.Row = Depends(exigir_sesion),
                      con: sqlite3.Connection = Depends(bd)):
    parte = consolidado.participacion(con, parte_id)
    if parte is None:
        raise HTTPException(404, "Esa participación no existe.")
    if parte["usuario_id"] != u["id"] and not u["es_admin"]:
        raise HTTPException(403, "Cada quien sube sus propias fotos.")

    ya = con.execute("SELECT COUNT(*) c FROM fotos WHERE participacion_id = ?",
                     (parte_id,)).fetchone()["c"]
    libres = fotos_mod.MAX_FOTOS_POR_PARTICIPACION - ya
    if libres <= 0:
        avisar(request, f"Ya tienes {fotos_mod.MAX_FOTOS_POR_PARTICIPACION} fotos. "
                        "Elimina alguna para subir otra.")
        return RedirectResponse(f"/actividades/{parte['actividad_id']}", status_code=303)

    guardadas, problemas = 0, []
    for archivo in archivos[:libres]:
        if not archivo.filename:
            continue
        try:
            meta = fotos_mod.procesar(await archivo.read(), archivo.filename)
        except fotos_mod.FotoInvalida as exc:
            problemas.append(str(exc))
            continue
        con.execute(
            """INSERT INTO fotos (participacion_id, archivo, archivo_pdf, nombre_original,
                                  bytes, bytes_pdf, bytes_original, ancho, alto,
                                  orden, creada_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (parte_id, meta["archivo"], meta["archivo_pdf"], meta["nombre_original"],
             meta["bytes"], meta["bytes_pdf"], meta["bytes_original"],
             meta["ancho"], meta["alto"], ya + guardadas, ahora()),
        )
        guardadas += 1
    con.commit()

    partes_msg = []
    if guardadas:
        partes_msg.append(f"{guardadas} foto{'s' if guardadas != 1 else ''} guardada"
                          f"{'s' if guardadas != 1 else ''}.")
    if len(archivos) > libres:
        partes_msg.append(f"Sólo caben {fotos_mod.MAX_FOTOS_POR_PARTICIPACION}; "
                          f"se ignoraron {len(archivos) - libres}.")
    partes_msg.extend(problemas)
    avisar(request, " ".join(partes_msg) or "No se subió ninguna foto.")
    return RedirectResponse(f"/actividades/{parte['actividad_id']}", status_code=303)


@app.post("/fotos/{foto_id}/eliminar")
def eliminar_foto(request: Request, foto_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    foto = consolidado.foto_con_dueno(con, foto_id)
    if foto is None:
        raise HTTPException(404, "Esa foto no existe.")
    if foto["usuario_id"] != u["id"] and not u["es_admin"]:
        raise HTTPException(403, "Cada quien administra sus propias fotos.")
    con.execute("DELETE FROM fotos WHERE id = ?", (foto_id,))
    con.commit()
    fotos_mod.eliminar(foto["archivo"])
    avisar(request, "Foto eliminada.")
    return RedirectResponse(f"/actividades/{foto['actividad_id']}", status_code=303)


@app.post("/fotos/{foto_id}/destacar")
def destacar_foto(request: Request, foto_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    foto = consolidado.foto_con_dueno(con, foto_id)
    if foto is None:
        raise HTTPException(404, "Esa foto no existe.")
    if foto["usuario_id"] != u["id"] and not u["es_admin"]:
        raise HTTPException(403, "No puedes destacar fotos de otra persona.")
    con.execute("UPDATE fotos SET destacada = 1 - destacada WHERE id = ?", (foto_id,))
    con.commit()
    return RedirectResponse(f"/actividades/{foto['actividad_id']}", status_code=303)


@app.post("/fotos/{foto_id}/pie")
def pie_foto(request: Request, foto_id: int, pie: str = Form(""),
             u: sqlite3.Row = Depends(exigir_sesion),
             con: sqlite3.Connection = Depends(bd)):
    """El pie es la leyenda que sale bajo la foto en el PDF (ver pdf.py)."""
    foto = consolidado.foto_con_dueno(con, foto_id)
    if foto is None:
        raise HTTPException(404, "Esa foto no existe.")
    if foto["usuario_id"] != u["id"] and not u["es_admin"]:
        raise HTTPException(403, "Cada quien pone el pie a sus propias fotos.")
    con.execute("UPDATE fotos SET pie = ? WHERE id = ?", (pie.strip()[:200], foto_id))
    con.commit()
    avisar(request, "Pie de foto guardado.")
    return RedirectResponse(f"/actividades/{foto['actividad_id']}", status_code=303)


@app.get("/foto/{archivo}")
def servir_foto(archivo: str, u: sqlite3.Row = Depends(exigir_sesion)):
    ruta = (FOTOS_DIR / Path(archivo).name).resolve()
    if not ruta.is_relative_to(FOTOS_DIR.resolve()) or not ruta.exists():
        raise HTTPException(404, "Esa foto no existe.")
    return Response(ruta.read_bytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------------- API

@app.get("/api/parecidas")
def api_parecidas(titulo: str = "", catalogo_id: int = 0, anio: int = 0,
                  u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    """Antes de crear un duplicado, ofrece sumarse a lo que ya existe."""
    objetivo = norm(titulo)
    if len(objetivo) < 5:
        return JSONResponse([])
    candidatas = con.execute(
        """SELECT a.id, a.titulo, a.zona, a.titulo_norm, a.anio,
                  c.actividad_poa,
                  (SELECT GROUP_CONCAT(us.nombre, ', ')
                     FROM participaciones p JOIN usuarios us ON us.id = p.usuario_id
                    WHERE p.actividad_id = a.id) AS participantes,
                  EXISTS(SELECT 1 FROM participaciones p
                          WHERE p.actividad_id = a.id AND p.usuario_id = ?) AS ya_estoy
             FROM actividades a JOIN catalogo_poa c ON c.id = a.catalogo_id
            WHERE a.anio = ?""",
        (u["id"], anio),
    ).fetchall()

    sugerencias = []
    for fila in candidatas:
        razon = difflib.SequenceMatcher(None, objetivo, fila["titulo_norm"]).ratio()
        # Alinear con la misma Actividad POA es señal fuerte de que es el mismo hecho.
        if catalogo_id and fila["actividad_poa"] and razon >= 0.45:
            razon += 0.15
        if razon >= 0.62:
            sugerencias.append({
                "id": fila["id"], "titulo": fila["titulo"], "zona": fila["zona"],
                "participantes": fila["participantes"] or "",
                "ya_estoy": bool(fila["ya_estoy"]),
                "parecido": round(min(razon, 1.0), 2),
            })
    sugerencias.sort(key=lambda s: -s["parecido"])
    return JSONResponse(sugerencias[:5])


@app.get("/api/mapa")
def api_mapa(zona: str = "", pin: str = "", u: sqlite3.Row = Depends(exigir_sesion),
            con: sqlite3.Connection = Depends(bd)):
    """Vista previa del mapa de una ubicación, para confirmar el punto al capturar.

    Usa el pin exacto (enlace/coordenadas) si viene; si no, geocodifica el nombre.
    Devuelve 404 si no se pudo ubicar, para que el formulario muestre el aviso.
    """
    coords = mapas.parsear_coordenadas(pin) if pin.strip() else None
    lat, lon = coords if coords else (None, None)
    ruta, _ = mapas.obtener_mapa(con, zona, lat, lon)
    if not ruta or not ruta.exists():
        raise HTTPException(404, "No se pudo ubicar.")
    return Response(ruta.read_bytes(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/catalogo/{cat_id}")
def api_catalogo(cat_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                 con: sqlite3.Connection = Depends(bd)):
    fila = con.execute("SELECT * FROM catalogo_poa WHERE id = ?", (cat_id,)).fetchone()
    if fila is None:
        raise HTTPException(404, "Actividad POA no encontrada.")
    return JSONResponse(dict(fila))


# ------------------------------------------------------------------ consolidado

@app.get("/consolidado", response_class=HTMLResponse)
def ver_consolidado(request: Request, anio: int | None = None, trimestre: int = 0,
                    agrupar: str = "zona", u: sqlite3.Row = Depends(exigir_consolidado),
                    con: sqlite3.Connection = Depends(bd)):
    anio = anio or consolidado.anio_por_defecto(con)
    agrupar = agrupar if agrupar in ("zona", "eje") else "zona"
    grupos = consolidado.armar(con, anio, trimestre, agrupar)
    return vista(request, "consolidado.html", {
        "u": u, "anio": anio, "trimestre": trimestre, "agrupar": agrupar,
        "anios": consolidado.anios_disponibles(con),
        "trimestres": TRIMESTRES,
        "grupos": grupos,
        "totales": consolidado.totales(grupos),
    })


@app.get("/pdf/consolidado")
def pdf_consolidado(anio: int | None = None, trimestre: int = 0, agrupar: str = "zona",
                    fotos: int = 1, u: sqlite3.Row = Depends(exigir_consolidado),
                    con: sqlite3.Connection = Depends(bd)):
    anio = anio or consolidado.anio_por_defecto(con)
    agrupar = agrupar if agrupar in ("zona", "eje") else "zona"
    grupos = consolidado.armar(con, anio, trimestre, agrupar)
    if not grupos:
        raise HTTPException(404, "No hay actividades reportadas en ese periodo.")
    contenido = pdf.consolidado(con, grupos, anio, trimestre, agrupar, con_fotos=bool(fotos))
    etiqueta = f"T{trimestre}" if trimestre else "anual"
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_consolidado_{anio}_{etiqueta}.pdf"'})


@app.get("/pdf/actividad/{act_id}")
def pdf_actividad(act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    # Un empleado sólo genera el PDF de actividades en las que participa; la
    # coordinación y los responsables pueden generar el de cualquiera (igual que
    # el tablero, donde ellos ven toda la Sección y el resto sólo lo suyo).
    if not (u["es_admin"] or u["es_responsable"]):
        parte = con.execute(
            "SELECT 1 FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
            (act_id, u["id"]),
        ).fetchone()
        if not parte:
            raise HTTPException(403, "Sólo puedes ver el PDF de tus propias actividades.")
    contenido = pdf.individual(con, act_id)
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_actividad_{act_id}.pdf"'})


# ----------------------------------------------------------------------- admin

@app.get("/admin/usuarios", response_class=HTMLResponse)
def admin_usuarios(request: Request, u: sqlite3.Row = Depends(exigir_admin),
                   con: sqlite3.Connection = Depends(bd)):
    return vista(request, "usuarios.html", {"u": u, "usuarios": consolidado.usuarios(con)})


@app.post("/admin/usuarios/{uid}/olvide-pin")
def olvide_pin(request: Request, uid: int, u: sqlite3.Row = Depends(exigir_admin),
               con: sqlite3.Connection = Depends(bd)):
    """Borra el PIN de una persona para que lo vuelva a definir en su próximo ingreso.
    Ahora todos tienen PIN, así que la coordinación puede reiniciar el de cualquiera
    que lo olvide."""
    objetivo = con.execute("SELECT nombre FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no existe.")
    con.execute("UPDATE usuarios SET pin_hash = '' WHERE id = ?", (uid,))
    con.commit()
    avisar(request, f"Se borró el PIN de {objetivo['nombre']}. La próxima vez que entre, "
                    "la plataforma le pedirá definir uno nuevo.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{uid}/activo")
def alternar_activo(request: Request, uid: int, u: sqlite3.Row = Depends(exigir_admin),
                    con: sqlite3.Connection = Depends(bd)):
    if uid == u["id"]:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    con.execute("UPDATE usuarios SET activo = 1 - activo WHERE id = ?", (uid,))
    con.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)
