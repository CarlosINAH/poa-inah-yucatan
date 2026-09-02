# -*- coding: utf-8 -*-
"""Generación de los PDF: ficha individual y consolidado de la Sección.

La ficha individual reproduce la hoja «Reporte de actividades» del Excel, pero sin
tener que escribir a mano el número de fila: se arma para la actividad pedida.
El consolidado hace lo mismo para todas las actividades del periodo, agrupadas.
"""
from __future__ import annotations

import io
import sqlite3
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .consolidado import armar, participaciones
from .db import FOTOS_DIR, TRIMESTRES
from .mapas import obtener_mapa

# Los logos del membrete viven junto a la app (app/static), la misma carpeta que usa
# la interfaz web. Antes se leían de prototipo_poa/assets, que el .dockerignore excluye
# de la imagen: en el contenedor los PDF salían sin los logos de Cultura e INAH.
ASSETS = Path(__file__).resolve().parent / "static"
TINTA = colors.HexColor("#1f2933")
ACENTO = colors.HexColor("#2d6396")
SUAVE = colors.HexColor("#eef4f8")
BORDE = colors.HexColor("#c7d4de")

INSTITUCION = "Sección de Conservación y Restauración · Centro INAH Yucatán"

_ss = getSampleStyleSheet()
E = {
    "titulo": ParagraphStyle("titulo", parent=_ss["Title"], fontSize=15, leading=19,
                             textColor=TINTA, spaceAfter=2),
    "sub": ParagraphStyle("sub", parent=_ss["Normal"], fontSize=9, leading=12,
                          textColor=colors.HexColor("#5b6b7a"), alignment=TA_CENTER),
    "seccion": ParagraphStyle("seccion", parent=_ss["Heading2"], fontSize=11.5, leading=14,
                              textColor=ACENTO, spaceBefore=10, spaceAfter=5),
    "grupo": ParagraphStyle("grupo", parent=_ss["Heading1"], fontSize=13, leading=16,
                            textColor=colors.white, spaceBefore=0, spaceAfter=0),
    "etiqueta": ParagraphStyle("etiqueta", parent=_ss["Normal"], fontSize=8, leading=10,
                               textColor=colors.HexColor("#5b6b7a"), fontName="Helvetica-Bold"),
    "valor": ParagraphStyle("valor", parent=_ss["Normal"], fontSize=9, leading=12,
                            textColor=TINTA),
    "cuerpo": ParagraphStyle("cuerpo", parent=_ss["Normal"], fontSize=9, leading=13,
                             textColor=TINTA, alignment=TA_JUSTIFY),
    "pie_foto": ParagraphStyle("pie_foto", parent=_ss["Normal"], fontSize=7, leading=9,
                               textColor=colors.HexColor("#5b6b7a"), alignment=TA_CENTER),
    "celda": ParagraphStyle("celda", parent=_ss["Normal"], fontSize=8, leading=10,
                            textColor=TINTA),
    "th": ParagraphStyle("th", parent=_ss["Normal"], fontSize=7.5, leading=9,
                         textColor=colors.white, fontName="Helvetica-Bold",
                         alignment=TA_CENTER),
    # --- Hoja por actividad (v3.5) ---
    "titulo_act": ParagraphStyle("titulo_act", parent=_ss["Title"], fontSize=16, leading=20,
                                 textColor=TINTA, alignment=TA_LEFT, spaceAfter=1),
    "meta_act": ParagraphStyle("meta_act", parent=_ss["Normal"], fontSize=9, leading=12,
                               textColor=colors.HexColor("#5b6b7a"), spaceAfter=6),
    "et_seccion": ParagraphStyle("et_seccion", parent=_ss["Normal"], fontSize=8.5, leading=11,
                                 textColor=ACENTO, fontName="Helvetica-Bold",
                                 spaceBefore=9, spaceAfter=3),
    "cap_mapa": ParagraphStyle("cap_mapa", parent=_ss["Normal"], fontSize=9.5, leading=12,
                               textColor=TINTA, alignment=TA_CENTER, fontName="Helvetica-Bold",
                               spaceBefore=3, spaceAfter=2),
}

_MAPA_ANCHO = 140 * mm            # ancho del mapa en la hoja (centrado)
_MAPA_ALTO = _MAPA_ANCHO * 360 / 640   # el servicio devuelve 640x360 fijo


def _esc(texto) -> str:
    return (str(texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _periodo(anio: int, trimestre: int) -> str:
    return f"{TRIMESTRES[trimestre]} de {anio}" if trimestre in TRIMESTRES else f"Ejercicio {anio}"


# ------------------------------------------------------------- encabezado / pie

def _membrete(canvas, doc):
    canvas.saveState()
    ancho, alto = letter
    y = alto - 16 * mm
    for nombre, x in (("logo-cultura.png", 18 * mm), ("logo-inah.png", ancho - 42 * mm)):
        ruta = ASSETS / nombre
        if ruta.exists():
            try:
                canvas.drawImage(str(ruta), x, y - 4 * mm, height=11 * mm, width=24 * mm,
                                 preserveAspectRatio=True, anchor="sw", mask="auto")
            except Exception:
                pass  # un logo ilegible no debe tumbar el informe
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#5b6b7a"))
    canvas.drawCentredString(ancho / 2, y, INSTITUCION)
    canvas.setStrokeColor(BORDE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, alto - 20 * mm, ancho - 18 * mm, alto - 20 * mm)

    canvas.line(18 * mm, 14 * mm, ancho - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 10 * mm, f"Generado el {date.today():%d/%m/%Y}")
    canvas.drawRightString(ancho - 18 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


def _documento(buffer) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=24 * mm, bottomMargin=18 * mm,
        title="Informe POA", author=INSTITUCION,
    )


# ------------------------------------------------------------------- fragmentos

def _campo(etiqueta: str, valor: str) -> Table:
    t = Table([[Paragraph(_esc(etiqueta), E["etiqueta"])],
               [Paragraph(_esc(valor) or "—", E["valor"])]], colWidths=[174 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SUAVE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _rejilla(pares: list[tuple[str, str]]) -> Table:
    """Dos columnas de etiqueta/valor."""
    filas, buf = [], []
    for etiqueta, valor in pares:
        buf.append(Table([[Paragraph(_esc(etiqueta), E["etiqueta"])],
                          [Paragraph(_esc(valor) or "—", E["valor"])]], colWidths=[84 * mm]))
        if len(buf) == 2:
            filas.append(buf)
            buf = []
    if buf:
        buf.append("")
        filas.append(buf)
    t = Table(filas, colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _tabla_cifras(act: dict) -> Table:
    cab = ["", "Anual", "1er T", "2do T", "3er T", "4to T", "Total"]
    plan = ["Planeado", act["planeado_anual"], act["plan_t1"], act["plan_t2"],
            act["plan_t3"], act["plan_t4"], act["total_planeado"]]
    inf = ["Informado", "—", act["inf_t1"], act["inf_t2"], act["inf_t3"],
           act["inf_t4"], act["total_informado"]]

    def limpio(v):
        if isinstance(v, float):
            return str(int(v)) if v == int(v) else f"{v:g}"
        return str(v)

    datos = [[Paragraph(_esc(c), E["th"]) for c in cab],
             [limpio(v) for v in plan], [limpio(v) for v in inf]]
    t = Table(datos, colWidths=[26 * mm, *[24.6 * mm] * 6])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACENTO),
        ("BACKGROUND", (0, 1), (0, -1), SUAVE),
        ("BACKGROUND", (-1, 1), (-1, -1), colors.HexColor("#f5faf6")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (-1, 1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _banda_participante(parte: dict) -> Table:
    """Nombre y cargo de quien aportó, como banda de encabezado."""
    t = Table([[Paragraph(f"<b>{_esc(parte['nombre'])}</b>", E["valor"]),
                Paragraph(_esc(parte["cargo"]), E["etiqueta"])]],
              colWidths=[110 * mm, 64 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SUAVE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _fotos_de(parte: dict, limite: int) -> list[dict]:
    orden = sorted(parte["fotos"], key=lambda f: (-f["destacada"], f["orden"], f["id"]))
    return orden[:limite]


def _tira_fotos(fotos_lista: list[dict], autor: str = "") -> list:
    """Fotos en filas de dos, escaladas para no deformarse."""
    if not fotos_lista:
        return []
    celdas = []
    for foto in fotos_lista:
        # La versión de impresión pesa ~10 veces menos que la de pantalla y a este
        # tamaño se ve idéntica; sin esto el consolidado sale de cientos de MB.
        ruta = FOTOS_DIR / (foto["archivo_pdf"] or foto["archivo"])
        if not ruta.exists():
            ruta = FOTOS_DIR / foto["archivo"]
        if not ruta.exists():
            continue
        ancho_max, alto_max = 84 * mm, 60 * mm
        escala = min(ancho_max / max(foto["ancho"], 1), alto_max / max(foto["alto"], 1))
        try:
            img = Image(str(ruta), width=foto["ancho"] * escala, height=foto["alto"] * escala)
        except Exception:
            continue
        pie = foto["pie"] or foto["nombre_original"]
        if autor:
            pie = f"{pie} · {autor}" if pie else autor
        celdas.append([img, Paragraph(_esc(pie), E["pie_foto"])])
    if not celdas:
        return []

    filas = []
    for i in range(0, len(celdas), 2):
        par = celdas[i:i + 2]
        filas.append([
            Table([[c[0]], [c[1]]], colWidths=[85 * mm]) for c in par
        ] + ([""] if len(par) == 1 else []))
    t = Table(filas, colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [t]


def _firmas() -> list:
    encabezados = ["Elaboró", "Revisó", "Vo. Bo. Coordinación"]
    t = Table([
        [Paragraph(f"<b>{h}</b>", E["pie_foto"]) for h in encabezados],
        ["", "", ""],
        [Paragraph("_" * 28, E["pie_foto"]) for _ in encabezados],
        [Paragraph("Nombre y firma", E["pie_foto"]) for _ in encabezados],
    ], colWidths=[58 * mm] * 3, rowHeights=[6 * mm, 12 * mm, 5 * mm, 5 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [Spacer(1, 10 * mm), t]


def _etiqueta_seccion(texto: str) -> Paragraph:
    return Paragraph(_esc(texto).upper(), E["et_seccion"])


def _fotos_ordenadas(fotos: list) -> list:
    return sorted(fotos, key=lambda f: (-f["destacada"], f["orden"], f["id"]))


def _bloque_ubicacion(con, act: dict) -> list:
    """Etiqueta «Ubicación» + mapa con el nombre del sitio, o respaldo en texto."""
    zona = act.get("zona") or ""
    lat, lon = act.get("mapa_lat"), act.get("mapa_lon")
    piezas: list = [_etiqueta_seccion("Ubicación")]
    if not zona and lat is None:
        piezas.append(_campo("Sitio", "Sin ubicación registrada"))
        return piezas
    ruta, nombre = obtener_mapa(con, zona, lat, lon)
    if ruta and ruta.exists():
        try:
            img = Image(str(ruta), width=_MAPA_ANCHO, height=_MAPA_ALTO)
            img.hAlign = "CENTER"
            piezas += [img, Paragraph(_esc(nombre), E["cap_mapa"])]
            return piezas
        except Exception:
            pass  # imagen ilegible: cae al respaldo de texto
    piezas.append(_campo("Sitio", nombre or "Sin ubicación registrada"))
    return piezas


def _cuadricula_fotos(pares: list) -> list:
    """Hasta 4 fotos en cuadrícula 2×2. `pares`: lista de (foto, autor)."""
    celdas = []
    for foto, autor in pares:
        ruta = FOTOS_DIR / (foto["archivo_pdf"] or foto["archivo"])
        if not ruta.exists():
            ruta = FOTOS_DIR / foto["archivo"]
        if not ruta.exists():
            continue
        escala = min(82 * mm / max(foto["ancho"], 1), 58 * mm / max(foto["alto"], 1))
        try:
            img = Image(str(ruta), width=foto["ancho"] * escala, height=foto["alto"] * escala)
        except Exception:
            continue
        pie = foto["pie"] or foto["nombre_original"]
        leyenda = f"{pie} · {autor}" if pie else autor
        celdas.append(Table([[img], [Paragraph(_esc(leyenda), E["pie_foto"])]],
                            colWidths=[84 * mm]))
    if not celdas:
        return []
    filas = [celdas[i:i + 2] for i in range(0, len(celdas), 2)]
    for fila in filas:
        if len(fila) == 1:
            fila.append("")
    t = Table(filas, colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [t]


def _hoja_actividad(con, act: dict, con_fotos: bool = True) -> list:
    """Una actividad = una hoja: título, ubicación (mapa), objetivo y resumen.

    Las fotos van al final; si no caben en la hoja, cada grupo de 4 (cuadrícula 2×2)
    salta a la hoja siguiente en bloque, sin partirse.
    """
    piezas: list = [
        Paragraph(_esc(act["titulo"]), E["titulo_act"]),
        Paragraph(_esc(f'{act.get("eje", "")}  ·  {_periodo(act["anio"], act.get("trimestre", 0))}'),
                  E["meta_act"]),
    ]
    piezas += _bloque_ubicacion(con, act)

    piezas.append(_etiqueta_seccion("Objetivo"))
    piezas.append(Paragraph(_esc(act.get("objetivo")) or "—", E["cuerpo"]))

    piezas.append(_etiqueta_seccion("Resumen"))
    partes = act.get("participaciones") or []
    if partes:
        for parte in partes:
            piezas.append(_banda_participante(parte))
            piezas.append(Spacer(1, 2))
            piezas.append(Paragraph(_esc(parte["resumen"]) or "<i>Sin resumen capturado.</i>",
                                    E["cuerpo"]))
            piezas.append(Spacer(1, 4))
    else:
        piezas.append(Paragraph("<i>Sin resumen capturado.</i>", E["cuerpo"]))

    if con_fotos:
        todas = [(f, parte["nombre"]) for parte in partes
                 for f in _fotos_ordenadas(parte["fotos"])]
        for i in range(0, len(todas), 4):
            grupo = _cuadricula_fotos(todas[i:i + 4])
            if grupo:
                piezas.append(KeepTogether([_etiqueta_seccion("Evidencia fotográfica"), *grupo]))
    return piezas


# ------------------------------------------------------------------- individual

def individual(con: sqlite3.Connection, act_id: int) -> bytes:
    from .consolidado import actividad as leer
    fila = leer(con, act_id)
    act = dict(fila)
    act["participaciones"] = participaciones(con, act_id)

    buffer = io.BytesIO()
    doc = _documento(buffer)
    doc.build(_hoja_actividad(con, act, con_fotos=True),
              onFirstPage=_membrete, onLaterPages=_membrete)
    return buffer.getvalue()


# ------------------------------------------------------------------ consolidado

def _portada(anio: int, trimestre: int, agrupar: str, tot: dict, grupos: list[dict]) -> list:
    resumen = [[Paragraph(_esc(c), E["th"]) for c in
                ("Zona" if agrupar == "zona" else "Eje", "Actividades",
                 "Informado", "Personas")]]
    for g in grupos:
        resumen.append([
            Paragraph(_esc(g["nombre"]), E["celda"]),
            str(len(g["actividades"])),
            f"{g['informado']:g}",
            str(g["personas"]),
        ])
    resumen.append([Paragraph("<b>Total de la Sección</b>", E["celda"]),
                    str(tot["actividades"]), f"{tot['informado']:g}", str(tot["personas"])])

    t = Table(resumen, colWidths=[90 * mm, 28 * mm, 28 * mm, 28 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACENTO),
        ("BACKGROUND", (0, -1), (-1, -1), SUAVE),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    nota = ("Cada actividad se cuenta una sola vez, sin importar cuántas personas hayan "
            "participado en ella. La columna «Personas» indica cuántos servidores públicos "
            "intervinieron en el grupo.")
    return [
        Spacer(1, 14 * mm),
        Paragraph("INFORME CONSOLIDADO", E["titulo"]),
        Paragraph("PROGRAMA OPERATIVO ANUAL", E["titulo"]),
        Spacer(1, 2),
        Paragraph(INSTITUCION, E["sub"]),
        Paragraph(_periodo(anio, trimestre), E["sub"]),
        Spacer(1, 10 * mm),
        Paragraph("Resumen ejecutivo", E["seccion"]),
        t,
        Spacer(1, 4),
        Paragraph(nota, E["pie_foto"]),
        *_firmas(),
    ]


def consolidado(con: sqlite3.Connection, grupos: list[dict], anio: int, trimestre: int,
                agrupar: str, con_fotos: bool = True) -> bytes:
    from .consolidado import totales
    tot = totales(grupos)

    # Una actividad por hoja: se aplanan los grupos conservando su orden (por zona/eje).
    actividades = [a for g in grupos for a in g["actividades"]]

    buffer = io.BytesIO()
    doc = _documento(buffer)
    piezas: list = _portada(anio, trimestre, agrupar, tot, grupos)
    for act in actividades:
        piezas.append(PageBreak())
        piezas += _hoja_actividad(con, act, con_fotos=con_fotos)

    doc.build(piezas, onFirstPage=_membrete, onLaterPages=_membrete)
    return buffer.getvalue()
