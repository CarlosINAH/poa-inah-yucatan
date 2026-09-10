# -*- coding: utf-8 -*-
"""Catálogo de lugares para la ubicación de actividades.

Nivel 1: los 106 municipios de Yucatán (lista fija y confiable).
Nivel 2: comisarías/localidades. Se incluyen las de MÉRIDA (curadas); para el resto
de municipios el campo acepta escribir libremente y el buscador de mapa (OpenStreetMap)
ayuda a ubicar el punto exacto. La lista de comisarías es una SUGERENCIA (datalist),
no una restricción: si falta alguna, se puede teclear igual.
"""
from __future__ import annotations

# Los 106 municipios del estado de Yucatán (orden alfabético).
MUNICIPIOS_YUCATAN = [
    "Abalá", "Acanceh", "Akil", "Baca", "Bokobá", "Buctzotz", "Cacalchén",
    "Calotmul", "Cansahcab", "Cantamayec", "Celestún", "Cenotillo", "Conkal",
    "Cuncunul", "Cuzamá", "Chacsinkín", "Chankom", "Chapab", "Chemax",
    "Chicxulub Pueblo", "Chichimilá", "Chikindzonot", "Chocholá", "Chumayel",
    "Dzán", "Dzemul", "Dzidzantún", "Dzilam de Bravo", "Dzilam González",
    "Dzitás", "Dzoncauich", "Espita", "Halachó", "Hocabá", "Hoctún", "Homún",
    "Huhí", "Hunucmá", "Ixil", "Izamal", "Kanasín", "Kantunil", "Kaua",
    "Kinchil", "Kopomá", "Mama", "Maní", "Maxcanú", "Mayapán", "Mérida",
    "Mocochá", "Motul", "Muna", "Muxupip", "Opichén", "Oxkutzcab", "Panabá",
    "Peto", "Progreso", "Quintana Roo", "Río Lagartos", "Sacalum", "Samahil",
    "Sanahcat", "San Felipe", "Santa Elena", "Seyé", "Sinanché", "Sotuta",
    "Sucilá", "Sudzal", "Suma", "Tahdziú", "Tahmek", "Teabo", "Tecoh",
    "Tekal de Venegas", "Tekantó", "Tekax", "Tekit", "Tekom", "Telchac Pueblo",
    "Telchac Puerto", "Temax", "Temozón", "Tepakán", "Tetiz", "Teya", "Ticul",
    "Timucuy", "Tinum", "Tixcacalcupul", "Tixkokob", "Tixmehuac", "Tixpéhual",
    "Tizimín", "Tunkás", "Tzucacab", "Uayma", "Ucú", "Umán", "Valladolid",
    "Xocchel", "Yaxcabá", "Yaxkukul", "Yobaín",
]

# Comisarías y localidades por municipio. Sólo Mérida por ahora (las más conocidas);
# el resto se completa escribiendo o con el buscador del mapa.
COMISARIAS = {
    "Mérida": [
        "Caucel", "Cholul", "Chablekal", "Chalmuch", "Cheumán", "Chichí Suárez",
        "Cosgaya", "Dzityá", "Dzoyaxché", "Dzununcán", "Hunxectamán", "Komchén",
        "Molas", "Noc Ac", "Sac-Nicté", "San Antonio Hool", "San José Tzal",
        "San Pedro Chimay", "Santa Cruz Palomeque", "Santa Gertrudis Copó",
        "Sierra Papacal", "Sitpach", "Suytunchén", "Tahdzibichén", "Tamanché",
        "Texán Cámara", "Tixcacal", "Xcanatún", "Xcunyá", "Xmatkuil",
        "Yaxché Casares", "Yaxnic",
    ],
}
