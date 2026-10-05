# -*- coding: utf-8 -*-
"""Plataforma POA - Sección de Conservación y Restauración, Centro INAH Yucatán."""
from __future__ import annotations

import difflib
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import (auth, consolidado, firmas as firmas_mod, fotos as fotos_mod,
               importador, lugares, mapas, pdf)
from .db import (FIRMAS_DIR, FOTOS_DIR, PROGRAMAS_NACIONALES, TRIMESTRES, ahora,
                 conectar, crear_esquema, norm)

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


def _fecha_hora(iso: str | None) -> str:
    """Sello ISO (2026-09-30T14:05:…) → «30/09/2026 14:05». Vacío → «Nunca»."""
    from datetime import datetime
    if not iso:
        return "Nunca"
    try:
        return f"{datetime.fromisoformat(iso):%d/%m/%Y %H:%M}"
    except (ValueError, TypeError):
        return str(iso)


plantillas.env.filters["fecha_hora"] = _fecha_hora


@app.on_event("startup")
def _preparar() -> None:
    con = conectar()
    crear_esquema(con)
    _purgar_papelera(con)   # limpia lo que ya cumplió 30 días en la papelera
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
    mias = len(consolidado.buscar(con, anio=anio, solo_de=u["id"], relacion="mias"))
    return vista(request, "inicio.html", {
        "u": u, "anio": anio, "mias": mias,
        "total": consolidado.kpis(con, anio)["actividades"],
        "compartidas": consolidado.cuenta_compartidas(con, u["id"], anio),
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
    con.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE id = ?", (ahora(), p["id"]))
    con.commit()
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

    con.execute("UPDATE usuarios SET pin_hash = ?, ultimo_ingreso = ? WHERE id = ?",
                (auth.hash_pin(nuevo.strip()), ahora(), p["id"]))
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


@app.get("/mi-firma", response_class=HTMLResponse)
def mi_firma_form(request: Request, u: sqlite3.Row = Depends(exigir_sesion)):
    return vista(request, "mi_firma.html", {"u": u, "error": None})


@app.post("/mi-firma", response_class=HTMLResponse)
def mi_firma(request: Request, firma: str = Form(""),
             u: sqlite3.Row = Depends(exigir_sesion),
             con: sqlite3.Connection = Depends(bd)):
    try:
        archivo = firmas_mod.procesar(firma)
    except firmas_mod.FirmaInvalida as exc:
        return vista(request, "mi_firma.html", {"u": u, "error": str(exc)})
    anterior = u["firma"]
    con.execute("UPDATE usuarios SET firma = ? WHERE id = ?", (archivo, u["id"]))
    con.commit()
    if anterior and anterior != archivo:
        firmas_mod.eliminar(anterior)   # el PNG viejo ya no lo usa nadie
    avisar(request, "Tu firma quedó guardada. Aparecerá en cada hoja del informe que firmes.")
    return RedirectResponse("/mi-firma", status_code=303)


@app.post("/mi-firma/borrar")
def borrar_firma(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
                 con: sqlite3.Connection = Depends(bd)):
    if u["firma"]:
        firmas_mod.eliminar(u["firma"])
    con.execute("UPDATE usuarios SET firma = '' WHERE id = ?", (u["id"],))
    con.commit()
    avisar(request, "Se borró tu firma. Las hojas saldrán con la línea en blanco para firmar a mano.")
    return RedirectResponse("/mi-firma", status_code=303)


@app.get("/firma/{archivo}")
def servir_firma(archivo: str, u: sqlite3.Row = Depends(exigir_sesion)):
    ruta = (FIRMAS_DIR / Path(archivo).name).resolve()
    if not ruta.is_relative_to(FIRMAS_DIR.resolve()) or not ruta.exists():
        raise HTTPException(404, "Esa firma no existe.")
    return Response(ruta.read_bytes(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


@app.post("/salir")
def salir(request: Request):
    request.session.clear()
    return RedirectResponse("/entrar", status_code=303)


# ----------------------------------------------------------------------- tablero

@app.get("/tablero", response_class=HTMLResponse)
def tablero(request: Request, anio: int | None = None, trimestre: int = 0, q: str = "",
            zona: str = "", ver: str = "mias", empleado: int = 0,
            u: sqlite3.Row = Depends(exigir_sesion), con: sqlite3.Connection = Depends(bd)):
    """El tablero ES la lista de actividades: no hay una pantalla aparte que repita.

    Pestañas: «mis actividades» (donde ya confirmé que participé), «actividades
    compartidas» (donde alguien me etiquetó y falta que confirme) y, para la
    coordinación y los responsables, «todas» las de la Sección y «por empleado» (la
    coordinación no participa: revisa y descarga lo de cada quien).
    """
    anio = anio or consolidado.anio_por_defecto(con)
    puede_todas = bool(u["es_admin"] or u["es_responsable"])
    ver = ver if ver in ("mias", "compartidas", "todas", "empleado", "a_cargo") else "mias"
    if ver == "todas" and not puede_todas:
        ver = "mias"
    # «A mi cargo» (actividades donde soy el responsable de proyecto) es del responsable.
    if ver == "a_cargo" and not u["es_responsable"]:
        ver = "mias"
    # «Por empleado» (ver el perfil de cada quien y descargar su PDF) es de la coordinación:
    # ve los resúmenes de todas las actividades de la persona.
    if ver == "empleado" and not u["es_admin"]:
        ver = "todas" if puede_todas else "mias"
    empleado = empleado if (ver == "empleado" and u["es_admin"]) else 0

    empleado_nombre = ""
    if ver == "empleado":
        if empleado:
            fila = con.execute("SELECT nombre FROM usuarios WHERE id = ?", (empleado,)).fetchone()
            empleado_nombre = fila["nombre"] if fila else ""
            filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre,
                                       solo_de=empleado, relacion="participa") if fila else []
            # Para que la coordinación revise: el resumen de esa persona en cada actividad.
            for f in filas:
                pr = con.execute(
                    """SELECT p.id, p.resumen FROM participaciones p
                        WHERE p.actividad_id = ? AND p.usuario_id = ?
                          AND p.estado = 'confirmada'""", (f["id"], empleado)).fetchone()
                f["emp_parte_id"] = pr["id"] if pr else None
                f["emp_resumen"] = pr["resumen"] if pr else ""
        else:
            filas = []
    elif ver == "compartidas":
        filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre,
                                   solo_de=u["id"], relacion="compartidas")
        info = consolidado.mis_compartidas_info(con, u["id"], anio)
        for f in filas:
            datos = info.get(f["id"], {})
            f["mi_parte_id"] = datos.get("parte_id")
            f["etiquetada_por"] = datos.get("por")
            f["mi_estado"] = datos.get("estado")
    elif ver == "a_cargo":
        filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre,
                                   solo_de=u["id"], relacion="a_cargo")
    elif ver == "mias":
        filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre,
                                   solo_de=u["id"], relacion="mias")
    else:  # todas
        filas = consolidado.buscar(con, anio=anio, texto=q, zona=zona, trimestre=trimestre)

    return vista(request, "tablero.html", {
        "u": u, "anio": anio, "trimestre": trimestre, "q": q, "zona": zona, "ver": ver,
        "puede_todas": puede_todas,
        "empleado": empleado, "empleado_nombre": empleado_nombre,
        "empleados": consolidado.usuarios(con) if u["es_admin"] else [],
        "n_compartidas": consolidado.cuenta_compartidas(con, u["id"], anio),
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
    vacia = {c: "" for c in ("titulo", "zona", "municipio", "fechas_ejecucion",
                             "observaciones", "objetivo")}
    vacia.update({"id": None, "catalogo_id": 0, "responsable_id": None,
                  "programa_nacional": "Ninguno", "planeacion": "Si",
                  "planeado": 1, "realizado": 1, "mapa_lat": None, "mapa_lon": None,
                  "fuera_estado": 0, "anio": anio, "trimestre": trimestre})
    return vista(request, "actividad_form.html", {
        "u": u, "act": vacia,
        "error": None, "editando": False, "paso": 2,
        "catalogo": consolidado.catalogo(con),
        "responsables": consolidado.responsables(con),
        "programas": PROGRAMAS_NACIONALES,
        "zonas": consolidado.zonas_usadas(con),
        "municipios": lugares.MUNICIPIOS_YUCATAN,
        "comisarias": lugares.COMISARIAS,
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
        # Fuera de Yucatán: el lugar se escribe a mano y no aplica el municipio de la lista.
        "fuera_estado": 1 if datos.get("fuera_estado") else 0,
        "municipio": "" if datos.get("fuera_estado") else (datos.get("municipio") or "").strip(),
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
            "municipios": lugares.MUNICIPIOS_YUCATAN,
            "comisarias": lugares.COMISARIAS,
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
    consolidado.sumar_participante(con, act_id, u["id"], resumen,
                                   estado="confirmada", agregada_por=u["id"])
    con.commit()
    avisar(request, "Actividad registrada. Ahora puedes subir tus fotos.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.get("/actividades/{act_id}", response_class=HTMLResponse)
def detalle(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
            con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    partes = consolidado.participaciones(con, act_id)   # todos los estados, para mostrarlos
    mi_parte = next((p for p in partes if p["usuario_id"] == u["id"]), None)
    # En la ficha, el resumen y las firmas son de los confirmados; los pendientes y
    # rechazados se muestran aparte con su estado.
    confirmados = [p for p in partes if p["estado"] == "confirmada"]
    # Puede sumar a otras personas quien ya participa (confirmado) o quien puede editar
    # la ficha (creador, responsable, coordinación). La lista para elegir deja fuera a
    # quienes ya están (en cualquier estado): a los rechazados se les re-etiqueta con su
    # propio botón, sólo la coordinación.
    puede_agregar = bool(mi_parte and mi_parte["estado"] == "confirmada") \
        or consolidado.puede_editar(u, act)
    ids_parte = {p["usuario_id"] for p in partes}
    agregables = ([r for r in auth.seleccionables(con) if r["id"] not in ids_parte]
                  if puede_agregar else [])
    return vista(request, "actividad_detalle.html", {
        "u": u, "act": act, "partes": partes, "confirmados": confirmados,
        "mi_parte": mi_parte,
        # Resúmenes en la ficha: cada quien ve el suyo; el RESPONSABLE de proyecto de esta
        # actividad ve los de todos (para revisar y firmar). La coordinación (aunque sea
        # admin) NO los ve aquí: los revisa en «Actividades → Por empleado».
        "ver_resumenes": bool(act["responsable_id"] and act["responsable_id"] == u["id"]),
        "puede_editar": consolidado.puede_editar(u, act),
        "puede_agregar": puede_agregar, "agregables": agregables,
        "max_fotos": fotos_mod.MAX_FOTOS_POR_PARTICIPACION,
        # Autorización por firma: quién puede pedirla, quién puede firmarla y su estado.
        "puede_autorizar": consolidado.puede_autorizar(u, act),
        "esta_autorizada": consolidado.esta_autorizada(act),
        "soy_participante": mi_parte is not None and mi_parte["estado"] == "confirmada",
        "tengo_firma": bool(u["firma"]),
        "puede_borrar": consolidado.puede_borrar(u, act),
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
        "municipios": lugares.MUNICIPIOS_YUCATAN,
        "comisarias": lugares.COMISARIAS,
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
    # Quien se suma solo confirma su propia participación de una vez.
    consolidado.sumar_participante(con, act_id, u["id"], "",
                                   estado="confirmada", agregada_por=u["id"])
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
    estado = consolidado.estado_participacion(con, act_id, objetivo["id"])
    if estado == "rechazada":
        # Ya dijo que no participó: sólo la coordinación puede volver a etiquetarlo.
        if not u["es_admin"]:
            raise HTTPException(403, f"{objetivo['nombre']} indicó que no participó en esta "
                                     "actividad. Sólo la coordinación puede volver a etiquetarlo.")
        consolidado.reetiquetar_participacion(con, act_id, objetivo["id"], u["id"])
        con.commit()
        avisar(request, f"Volviste a etiquetar a {objetivo['nombre']}. Le aparecerá en "
                        "«Actividades compartidas» para que confirme.")
        return RedirectResponse(f"/actividades/{act_id}", status_code=303)
    # Etiquetar a alguien más deja su participación pendiente: contará en el informe
    # cuando esa persona confirme que sí participó.
    consolidado.sumar_participante(con, act_id, objetivo["id"], "",
                                   estado="pendiente", agregada_por=u["id"])
    con.commit()
    avisar(request, f"Etiquetaste a {objetivo['nombre']}. Le aparecerá en «Actividades "
                    "compartidas» para confirmar su participación.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


def _destino_seguro(volver: str, alterno: str) -> str:
    """Sólo se acepta un redirect interno (evita mandar a un sitio externo)."""
    return volver if volver.startswith("/") and not volver.startswith("//") else alterno


@app.post("/participaciones/{parte_id}/confirmar")
def confirmar_participacion(request: Request, parte_id: int, volver: str = Form(""),
                            u: sqlite3.Row = Depends(exigir_sesion),
                            con: sqlite3.Connection = Depends(bd)):
    """El empleado confirma que sí participó en una actividad donde lo etiquetaron."""
    parte = consolidado.participacion(con, parte_id)
    if parte is None:
        raise HTTPException(404, "Esa participación no existe.")
    if parte["usuario_id"] != u["id"]:
        raise HTTPException(403, "Sólo tú puedes confirmar tu propia participación.")
    consolidado.confirmar_participacion(con, parte_id)
    con.commit()
    avisar(request, "Confirmaste tu participación. Ya cuenta y puedes subir tu evidencia.")
    return RedirectResponse(_destino_seguro(volver, f"/actividades/{parte['actividad_id']}"),
                            status_code=303)


@app.post("/participaciones/{parte_id}/rechazar")
def rechazar_participacion(request: Request, parte_id: int, volver: str = Form(""),
                           u: sqlite3.Row = Depends(exigir_sesion),
                           con: sqlite3.Connection = Depends(bd)):
    """El empleado indica que NO participó: deja de contar y sólo la coordinación puede
    volver a etiquetarlo."""
    parte = consolidado.participacion(con, parte_id)
    if parte is None:
        raise HTTPException(404, "Esa participación no existe.")
    if parte["usuario_id"] != u["id"]:
        raise HTTPException(403, "Sólo tú puedes responder por tu propia participación.")
    consolidado.rechazar_participacion(con, parte_id)
    con.commit()
    avisar(request, "Registramos que no participaste. Si fue un error, la coordinación "
                    "puede volver a etiquetarte.")
    return RedirectResponse(_destino_seguro(volver, "/tablero?ver=compartidas"),
                            status_code=303)


def _es_revisor(u: sqlite3.Row, act) -> bool:
    """Quién revisa una actividad: la coordinación o el responsable de proyecto de ESA
    actividad. Son los que ven los resúmenes de todos."""
    resp = act["responsable_id"] if not isinstance(act, dict) else act.get("responsable_id")
    return bool(u["es_admin"] or (resp and resp == u["id"]))


def _borrar_definitivo(con: sqlite3.Connection, act_id: int) -> None:
    """Borra la actividad y sus fotos de disco. Irreversible; sólo desde la papelera."""
    for archivo in consolidado.archivos_de_actividad(con, act_id):
        fotos_mod.eliminar(archivo)
    con.execute("DELETE FROM actividades WHERE id = ?", (act_id,))


def _purgar_papelera(con: sqlite3.Connection) -> None:
    """Elimina del todo lo que ya cumplió 30 días en la papelera."""
    vencidas = consolidado.vencidas(con)
    for aid in vencidas:
        _borrar_definitivo(con, aid)
    if vencidas:
        con.commit()


@app.post("/actividades/{act_id}/eliminar")
def eliminar_actividad(request: Request, act_id: int,
                       u: sqlite3.Row = Depends(exigir_sesion),
                       con: sqlite3.Connection = Depends(bd)):
    """Manda la actividad a la papelera (borrado suave, reversible por 30 días).

    Cada quien puede mandar a la papelera las actividades que registró; la coordinación,
    las de cualquiera. No se pierde nada de inmediato: vive 30 días en la papelera.
    """
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_borrar(u, act):
        raise HTTPException(403, "Sólo puedes enviar a la papelera las actividades que "
                                 "registraste (o la coordinación).")
    consolidado.enviar_a_papelera(con, act_id, u["id"])
    con.commit()
    avisar(request, f"«{act['titulo']}» se envió a la papelera. Puedes restaurarla "
                    f"durante {consolidado.DIAS_PAPELERA} días.")
    return RedirectResponse("/tablero", status_code=303)


@app.get("/papelera", response_class=HTMLResponse)
def papelera(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
             con: sqlite3.Connection = Depends(bd)):
    """La papelera: cada quien ve la suya; la coordinación, la de todos."""
    _purgar_papelera(con)   # aprovecha la visita para limpiar lo vencido
    items = consolidado.papelera(con, uid=None if u["es_admin"] else u["id"])
    return vista(request, "papelera.html", {
        "u": u, "items": items, "dias": consolidado.DIAS_PAPELERA,
    })


@app.post("/actividades/{act_id}/restaurar")
def restaurar_actividad(request: Request, act_id: int,
                        u: sqlite3.Row = Depends(exigir_sesion),
                        con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_borrar(u, act):
        raise HTTPException(403, "No puedes restaurar esta actividad.")
    consolidado.restaurar(con, act_id)
    con.commit()
    avisar(request, f"«{act['titulo']}» se restauró.")
    return RedirectResponse("/papelera", status_code=303)


@app.post("/actividades/{act_id}/eliminar-definitivo")
def eliminar_definitivo(request: Request, act_id: int,
                        u: sqlite3.Row = Depends(exigir_admin),
                        con: sqlite3.Connection = Depends(bd)):
    """Elimina del todo una actividad de la papelera. Irreversible; sólo coordinación."""
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    _borrar_definitivo(con, act_id)
    con.commit()
    avisar(request, f"Se eliminó definitivamente «{act['titulo']}» y sus fotos.")
    return RedirectResponse("/papelera", status_code=303)


# ------------------------------------------------------- autorización por firma

@app.post("/actividades/{act_id}/firmar")
async def firmar_actividad(request: Request, act_id: int,
                           u: sqlite3.Row = Depends(exigir_sesion),
                           con: sqlite3.Connection = Depends(bd)):
    """Paso 4 del registro: el empleado firma su actividad y la envía al responsable.

    La firma se dibuja aquí mismo (o se reutiliza la ya registrada). Queda guardada en el
    perfil para reutilizarla en las siguientes actividades. Firmar deja la actividad lista
    y solicita la autorización del responsable de proyecto.
    """
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    soy = con.execute("SELECT 1 FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
                      (act_id, u["id"])).fetchone()
    if not (soy or consolidado.puede_editar(u, act)):
        raise HTTPException(403, "Sólo quien participa en la actividad puede firmarla.")
    if consolidado.esta_autorizada(act):
        avisar(request, "Esa actividad ya está autorizada.")
        return RedirectResponse(f"/actividades/{act_id}", status_code=303)
    if not act["responsable_id"]:
        avisar(request, "Primero asigna un responsable de proyecto a la actividad (Editar ficha).")
        return RedirectResponse(f"/actividades/{act_id}", status_code=303)

    # Firma dibujada en el momento (opcional): si viene, se guarda y reemplaza la anterior.
    trazo = ((await request.form()).get("firma") or "").strip()
    if trazo:
        try:
            archivo = firmas_mod.procesar(trazo)
        except firmas_mod.FirmaInvalida as exc:
            avisar(request, str(exc))
            return RedirectResponse(f"/actividades/{act_id}", status_code=303)
        anterior = u["firma"]
        con.execute("UPDATE usuarios SET firma = ? WHERE id = ?", (archivo, u["id"]))
        if anterior and anterior != archivo:
            firmas_mod.eliminar(anterior)
    elif not u["firma"]:
        avisar(request, "Dibuja tu firma para poder firmar la actividad.")
        return RedirectResponse(f"/actividades/{act_id}", status_code=303)

    consolidado.solicitar_autorizacion(con, act_id)
    con.commit()
    avisar(request, "Firmaste la actividad. Se envió al responsable para su autorización.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.post("/actividades/{act_id}/autorizar")
def autorizar_una(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    """El responsable de la actividad la firma y autoriza."""
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_autorizar(u, act):
        raise HTTPException(403, "Sólo el responsable de proyecto de esta actividad puede firmarla.")
    if not u["firma"]:
        avisar(request, "Registra tu firma en «Mi firma» antes de autorizar.")
        return RedirectResponse("/mi-firma", status_code=303)
    consolidado.autorizar(con, act_id, u["id"])
    con.commit()
    avisar(request, "Actividad autorizada con tu firma. Ya se puede ver el PDF.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.post("/actividades/{act_id}/revocar-firma")
def revocar_firma(request: Request, act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    """Quita la autorización (el responsable o la coordinación); el PDF vuelve a ocultarse."""
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    if not consolidado.puede_autorizar(u, act):
        raise HTTPException(403, "Sólo el responsable de proyecto o la coordinación puede revocar.")
    consolidado.revocar_autorizacion(con, act_id)
    con.commit()
    avisar(request, "Se revocó la autorización. El PDF deja de estar disponible hasta firmar de nuevo.")
    return RedirectResponse(f"/actividades/{act_id}", status_code=303)


@app.get("/autorizaciones", response_class=HTMLResponse)
def autorizaciones(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
                   con: sqlite3.Connection = Depends(bd)):
    """Bandeja del responsable: solicitudes de firma agrupadas por quién las pidió.
    Para la coordinación, además, el resumen de qué responsables faltan por firmar."""
    grupos = consolidado.pendientes_para(con, u["id"])
    por_responsable = consolidado.pendientes_por_responsable(con) if u["es_admin"] else []
    huerfanas = consolidado.sin_responsable(con) if u["es_admin"] else []
    return vista(request, "autorizaciones.html", {
        "u": u, "grupos": grupos, "tengo_firma": bool(u["firma"]),
        "por_responsable": por_responsable,
        "huerfanas": huerfanas,
        "responsables": consolidado.responsables(con) if u["es_admin"] else [],
        "trimestres": TRIMESTRES,
    })


@app.post("/autorizaciones/asignar-responsable")
async def asignar_responsable(request: Request, u: sqlite3.Row = Depends(exigir_admin),
                              con: sqlite3.Connection = Depends(bd)):
    """La coordinación enlaza o corrige el responsable de proyecto de una actividad."""
    form = await request.form()
    try:
        act_id = int(form.get("act_id") or 0)
        resp_id = int(form.get("responsable_id") or 0)
    except (TypeError, ValueError):
        act_id = resp_id = 0
    volver = _destino_seguro(str(form.get("volver") or ""), "/autorizaciones")
    if act_id and resp_id and consolidado.asignar_responsable(con, act_id, resp_id):
        con.commit()
        avisar(request, "Responsable asignado a la actividad.")
    else:
        avisar(request, "No se pudo asignar: elige un responsable válido.")
    return RedirectResponse(volver, status_code=303)


@app.get("/responsables", response_class=HTMLResponse)
def revision_responsables(request: Request, anio: int | None = None, resp: int = -1,
                          u: sqlite3.Row = Depends(exigir_admin),
                          con: sqlite3.Connection = Depends(bd)):
    """Revisión manual del enlace actividad ↔ responsable: la coordinación ve todas las
    actividades del año con su responsable actual y corrige las que quedaron mal. `resp`
    separa por responsable: -1 todas, 0 sin responsable, un id esa persona."""
    anio = anio or consolidado.anio_por_defecto(con)
    filtro = None if resp < 0 else resp
    filas = consolidado.revision_responsables(con, anio, filtro)
    sin = len(consolidado.sin_responsable(con, anio))
    return vista(request, "responsables.html", {
        "u": u, "anio": anio, "resp": resp, "filas": filas, "sin_responsable": sin,
        "responsables": consolidado.responsables(con),
        "anios": consolidado.anios_disponibles(con),
        "trimestres": TRIMESTRES,
    })


@app.post("/autorizaciones/autorizar")
async def autorizar_lote(request: Request, u: sqlite3.Row = Depends(exigir_sesion),
                         con: sqlite3.Connection = Depends(bd)):
    """El responsable firma y autoriza varias actividades de una sola vez."""
    if not u["firma"]:
        avisar(request, "Registra tu firma en «Mi firma» antes de autorizar.")
        return RedirectResponse("/mi-firma", status_code=303)
    ids = (await request.form()).getlist("act_ids")
    n = 0
    for sid in ids:
        try:
            aid = int(sid)
        except (TypeError, ValueError):
            continue
        act = consolidado.actividad(con, aid)
        if act and consolidado.puede_autorizar(u, act) and not consolidado.esta_autorizada(act):
            consolidado.autorizar(con, aid, u["id"])
            n += 1
    con.commit()
    if n:
        avisar(request, f"Firmaste y autorizaste {n} actividad{'es' if n != 1 else ''}.")
    else:
        avisar(request, "No se autorizó ninguna actividad. Marca al menos una.")
    return RedirectResponse("/autorizaciones", status_code=303)


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
            WHERE a.anio = ? AND a.eliminada_en = ''""",
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


@app.get("/api/buscar-lugar")
def api_buscar_lugar(q: str = "", municipio: str = "", fuera: str = "",
                     u: sqlite3.Row = Depends(exigir_sesion)):
    """Busca lugares por nombre en OpenStreetMap para ubicar el punto en el mapa.

    Dentro de Yucatán: si viene `municipio`, se acota la búsqueda a ese municipio.
    Fuera de Yucatán (`fuera=1`): se busca en todo el mundo (otro estado o país), sin
    acotar a Yucatán ni a México. Devuelve hasta 6 candidatos {nombre, lat, lon}.
    Best-effort: [] si no hay internet o el servicio falla.
    """
    consulta = (q or "").strip()
    if fuera:
        return JSONResponse(mapas.buscar_lugares(consulta, solo_mexico=False))
    muni = (municipio or "").strip()
    if muni and consulta:
        consulta = f"{consulta}, {muni}, Yucatán, México"
    elif muni:
        consulta = f"{muni}, Yucatán, México"
    return JSONResponse(mapas.buscar_lugares(consulta))


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
                    fotos: int = 1, act_ids: list[int] | None = Query(None),
                    u: sqlite3.Row = Depends(exigir_consolidado),
                    con: sqlite3.Connection = Depends(bd)):
    """El consolidado se arma solo con todas las actividades del periodo. Si la coordinación
    marcó cuáles incluir (`act_ids`), sólo salen ésas."""
    anio = anio or consolidado.anio_por_defecto(con)
    agrupar = agrupar if agrupar in ("zona", "eje") else "zona"
    grupos = consolidado.armar(con, anio, trimestre, agrupar)
    if act_ids:
        elegidas = set(act_ids)
        grupos = [{**g, "actividades": [a for a in g["actividades"] if a["id"] in elegidas]}
                  for g in grupos]
        grupos = [g for g in grupos if g["actividades"]]
    if not grupos:
        raise HTTPException(404, "No hay actividades para incluir en el consolidado.")
    contenido = pdf.consolidado(con, grupos, anio, trimestre, agrupar, con_fotos=bool(fotos))
    etiqueta = f"T{trimestre}" if trimestre else "anual"
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_consolidado_{anio}_{etiqueta}.pdf"'})


@app.get("/pdf/mias/vista-previa")
def pdf_mias_vista_previa(anio: int | None = None, trimestre: int = 0,
                         u: sqlite3.Row = Depends(exigir_sesion),
                         con: sqlite3.Connection = Depends(bd)):
    """Borrador para que el empleado revise que firmó TODAS sus actividades.

    A diferencia del PDF oficial, NO exige la autorización del responsable: incluye todas
    sus actividades del periodo (firmadas o no), con la marca «VISTA PREVIA» y el aviso de
    cuáles le falta firmar."""
    anio = anio or consolidado.anio_por_defecto(con)
    trimestre = trimestre if trimestre in (1, 2, 3, 4) else 0
    actividades = consolidado.actividades_de(con, u["id"], anio, trimestre)
    if not actividades:
        raise HTTPException(404, "Aún no tienes actividades capturadas en ese periodo.")
    contenido = pdf.vista_previa(con, actividades, solo_usuario=u["id"])
    etiqueta = f"T{trimestre}" if trimestre else "anual"
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_vista_previa_{anio}_{etiqueta}.pdf"'})


@app.get("/pdf/mias")
def pdf_mias(anio: int | None = None, trimestre: int = 0,
             u: sqlite3.Row = Depends(exigir_sesion),
             con: sqlite3.Connection = Depends(bd)):
    """El PDF de las actividades que capturó quien lo pide: una hoja por actividad, con
    su hoja de fotos, y firmadas. Cada quien descarga lo suyo."""
    anio = anio or consolidado.anio_por_defecto(con)
    trimestre = trimestre if trimestre in (1, 2, 3, 4) else 0
    actividades = consolidado.actividades_de(con, u["id"], anio, trimestre)
    # Sólo se muestran las actividades ya firmadas por su responsable.
    actividades = [a for a in actividades if consolidado.esta_autorizada(a)]
    if not actividades:
        raise HTTPException(404, "Aún no tienes actividades autorizadas por el responsable "
                                 "en ese periodo. El PDF se habilita cuando firman tus actividades.")
    contenido = pdf.de_actividades(con, actividades, con_fotos=True, solo_usuario=u["id"])
    etiqueta = f"T{trimestre}" if trimestre else "anual"
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_mis_actividades_{anio}_{etiqueta}.pdf"'})


@app.get("/pdf/empleado/{uid}")
def pdf_empleado(uid: int, anio: int | None = None, trimestre: int = 0,
                 u: sqlite3.Row = Depends(exigir_admin),
                 con: sqlite3.Connection = Depends(bd)):
    """La coordinación descarga el PDF de un empleado: sus actividades del periodo con su
    resumen y su evidencia, una hoja por actividad."""
    persona = con.execute("SELECT id, nombre FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if persona is None:
        raise HTTPException(404, "Esa persona no existe.")
    anio = anio or consolidado.anio_por_defecto(con)
    trimestre = trimestre if trimestre in (1, 2, 3, 4) else 0
    actividades = consolidado.actividades_de(con, uid, anio, trimestre)
    if not actividades:
        raise HTTPException(404, f"{persona['nombre']} no tiene actividades confirmadas en "
                                 "ese periodo.")
    contenido = pdf.de_actividades(con, actividades, con_fotos=True, solo_usuario=uid)
    etiqueta = f"T{trimestre}" if trimestre else "anual"
    apellido = norm(persona["nombre"]).replace(" ", "_")
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="POA_{apellido}_{anio}_{etiqueta}.pdf"'})


@app.get("/pdf/actividad/{act_id}")
def pdf_actividad(act_id: int, u: sqlite3.Row = Depends(exigir_sesion),
                  con: sqlite3.Connection = Depends(bd)):
    act = consolidado.actividad(con, act_id)
    if act is None:
        raise HTTPException(404, "Esa actividad no existe.")
    # ¿Quien lo pide participa en la actividad? Su ficha muestra sólo su resumen y su
    # evidencia. Quien no participa (coordinación/responsable) recibe el compilado: un
    # único resumen, el más extenso.
    participa = con.execute(
        "SELECT 1 FROM participaciones WHERE actividad_id = ? AND usuario_id = ?",
        (act_id, u["id"]),
    ).fetchone()
    # El compilado (con los resúmenes) lo generan quien participa, la coordinación y el
    # responsable de proyecto de ESA actividad. Un responsable de otra actividad no ve los
    # resúmenes ajenos.
    if not participa and not _es_revisor(u, act):
        raise HTTPException(403, "Sólo puedes ver el PDF de tus propias actividades.")
    # El PDF se habilita cuando el responsable firma y autoriza. La coordinación puede
    # verlo antes (supervisión); el resto, sólo una vez autorizada.
    if not consolidado.esta_autorizada(act) and not u["es_admin"]:
        raise HTTPException(403, "El PDF estará disponible cuando el responsable de "
                                 "proyecto firme y autorice esta actividad.")
    if participa:
        contenido = pdf.individual(con, act_id, solo_usuario=u["id"])
    else:
        contenido = pdf.individual(con, act_id, compilado=True)
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


@app.post("/admin/usuarios/{uid}/pin")
def admin_cambiar_pin(request: Request, uid: int, nuevo: str = Form(...),
                      u: sqlite3.Row = Depends(exigir_admin),
                      con: sqlite3.Connection = Depends(bd)):
    """La coordinación fija un PIN nuevo a una persona desde el panel de Personal.
    A diferencia de «Olvidó su PIN» (que lo borra para que lo defina al entrar), aquí se
    establece uno de inmediato, útil para dejarle un PIN provisional."""
    objetivo = con.execute("SELECT nombre FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no existe.")
    if motivo := auth.validar_pin(nuevo):
        avisar(request, motivo)
        return RedirectResponse("/admin/usuarios", status_code=303)
    con.execute("UPDATE usuarios SET pin_hash = ? WHERE id = ?",
                (auth.hash_pin(nuevo.strip()), uid))
    con.commit()
    avisar(request, f"Se definió un PIN nuevo para {objetivo['nombre']}.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{uid}/activo")
def alternar_activo(request: Request, uid: int, u: sqlite3.Row = Depends(exigir_admin),
                    con: sqlite3.Connection = Depends(bd)):
    if uid == u["id"]:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    con.execute("UPDATE usuarios SET activo = 1 - activo WHERE id = ?", (uid,))
    con.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/nueva")
def crear_usuario(request: Request, nombre: str = Form(...), cargo: str = Form(""),
                  es_responsable: int = Form(0), es_admin: int = Form(0),
                  u: sqlite3.Row = Depends(exigir_admin),
                  con: sqlite3.Connection = Depends(bd)):
    """Alta de personal desde el panel. Entra sin PIN: lo define en su primer ingreso."""
    if len(nombre.strip()) < 3:
        avisar(request, "Escribe el nombre completo de la persona.")
        return RedirectResponse("/admin/usuarios", status_code=303)
    consolidado.crear_usuario(con, nombre, cargo, bool(es_responsable), bool(es_admin))
    con.commit()
    avisar(request, f"Se agregó a {nombre.strip()}. Aparecerá en la lista de entrada y "
                    "definirá su PIN la primera vez que entre.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{uid}/editar")
def editar_usuario(request: Request, uid: int, nombre: str = Form(...),
                   cargo: str = Form(""), es_responsable: int = Form(0),
                   es_admin: int = Form(0), u: sqlite3.Row = Depends(exigir_admin),
                   con: sqlite3.Connection = Depends(bd)):
    objetivo = con.execute("SELECT id FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no existe.")
    if len(nombre.strip()) < 3:
        avisar(request, "El nombre no puede quedar vacío.")
        return RedirectResponse("/admin/usuarios", status_code=303)
    # Nadie puede quitarse a sí mismo la coordinación (evita quedarse sin acceso admin).
    es_admin = 1 if uid == u["id"] else es_admin
    consolidado.editar_usuario(con, uid, nombre, cargo, bool(es_responsable), bool(es_admin))
    con.commit()
    avisar(request, "Datos actualizados.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{uid}/eliminar")
def eliminar_usuario(request: Request, uid: int, u: sqlite3.Row = Depends(exigir_admin),
                     con: sqlite3.Connection = Depends(bd)):
    """Borra a una persona SÓLO si no tiene datos ligados; si los tiene, se desactiva para
    no perder sus participaciones ni sus actividades."""
    objetivo = con.execute("SELECT nombre FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no existe.")
    if uid == u["id"]:
        raise HTTPException(400, "No puedes eliminar tu propia cuenta.")
    if consolidado.referencias_usuario(con, uid) > 0:
        con.execute("UPDATE usuarios SET activo = 0 WHERE id = ?", (uid,))
        con.commit()
        avisar(request, f"{objetivo['nombre']} tiene actividades o participaciones ligadas, "
                        "así que no se puede borrar sin perder esos datos. Se desactivó en su "
                        "lugar (deja de aparecer en la lista).")
        return RedirectResponse("/admin/usuarios", status_code=303)
    consolidado.eliminar_usuario(con, uid)
    con.commit()
    avisar(request, f"Se eliminó a {objetivo['nombre']}.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@app.post("/admin/usuarios/{uid}/firma")
async def admin_cargar_firma(request: Request, uid: int, archivo: UploadFile,
                             u: sqlite3.Row = Depends(exigir_admin),
                             con: sqlite3.Connection = Depends(bd)):
    """La coordinación carga la firma de una persona a partir de una imagen (escaneo o
    foto), para quien no puede firmar en pantalla. Se limpia el fondo y se guarda igual que
    una firma dibujada, así que sirve para autorizar y se estampa en los PDF."""
    objetivo = con.execute("SELECT id, nombre, firma FROM usuarios WHERE id = ?",
                           (uid,)).fetchone()
    if objetivo is None:
        raise HTTPException(404, "Esa persona no existe.")
    datos = await archivo.read()
    try:
        nombre_archivo = firmas_mod.procesar_subida(datos)
    except firmas_mod.FirmaInvalida as exc:
        avisar(request, str(exc))
        return RedirectResponse("/admin/usuarios", status_code=303)
    anterior = objetivo["firma"]
    con.execute("UPDATE usuarios SET firma = ? WHERE id = ?", (nombre_archivo, uid))
    con.commit()
    if anterior:
        firmas_mod.eliminar(anterior)
    avisar(request, f"Se cargó la firma de {objetivo['nombre']}. Ya puede usarse para "
                    "autorizar y aparecerá en los PDF.")
    return RedirectResponse("/admin/usuarios", status_code=303)


# ------------------------------------------------------- importar históricos (Excel)

@app.get("/admin/importar", response_class=HTMLResponse)
def importar_form(request: Request, u: sqlite3.Row = Depends(exigir_admin)):
    return vista(request, "importar.html", {"u": u, "resultado": None})


@app.post("/admin/importar", response_class=HTMLResponse)
async def importar_post(request: Request, archivo: UploadFile,
                        anio: str = Form(""),
                        u: sqlite3.Row = Depends(exigir_admin),
                        con: sqlite3.Connection = Depends(bd)):
    def pantalla(resultado):
        return vista(request, "importar.html", {"u": u, "resultado": resultado})

    nombre = archivo.filename or ""
    if not nombre.lower().endswith(".xlsx"):
        avisar(request, "El archivo debe ser un Excel .xlsx (el mismo formato del POA trimestral).")
        return RedirectResponse("/admin/importar", status_code=303)

    # Año: lo que escriba la coordinación manda; si lo deja vacío, se adivina del nombre.
    anio_texto = (anio or "").strip()
    if anio_texto:
        try:
            anio_final = int(anio_texto)
        except ValueError:
            avisar(request, "El año debe ser un número, por ejemplo 2024.")
            return RedirectResponse("/admin/importar", status_code=303)
    else:
        anio_final = importador.detectar_anio(nombre) or 0
    if not (2000 <= anio_final <= 2100):
        avisar(request, "No pude determinar el año. Escríbelo en el campo (por ejemplo 2024).")
        return RedirectResponse("/admin/importar", status_code=303)

    contenido = await archivo.read()
    if len(contenido) > importador.MAX_BYTES_ARCHIVO:
        resultado = importador.Resultado(
            anio=anio_final,
            error=f"El archivo pesa más de {importador.MAX_BYTES_ARCHIVO // (1024 * 1024)} MB.")
        return pantalla(resultado)

    resultado = importador.importar(con, contenido, anio_final)
    return pantalla(resultado)
