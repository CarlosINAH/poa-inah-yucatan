# -*- coding: utf-8 -*-
"""Carga a la plataforma las actividades de un POA trimestral en Excel (CLI).

    .venv\\Scripts\\python.exe servidor_poa\\importar_excel.py "C:\\ruta\\archivo.xlsx" [AÑO]

El año es opcional: si no lo pones, se adivina del nombre del archivo (p. ej.
«POA 2024.xlsx» → 2024) y, si no aparece, se usa 2026.

La lógica vive en app/importador.py, compartida con la pantalla web
(Coordinación → Importar). Se puede correr dos veces sin duplicar: si ya existe
una actividad con el mismo título y año, se salta.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db, importador  # noqa: E402

ANIO_POR_DEFECTO = 2026


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    if not src.exists():
        sys.exit(f"No encuentro el archivo:\n  {src}")

    if len(sys.argv) >= 3:
        anio = int(sys.argv[2])
    else:
        anio = importador.detectar_anio(src.name) or ANIO_POR_DEFECTO

    con = db.conectar()
    db.crear_esquema(con)
    res = importador.importar(con, src, anio)
    con.close()

    if res.error:
        sys.exit(res.error)

    print(f"\nAño importado       : {res.anio}")
    print(f"Actividades creadas : {res.creadas}")
    if res.saltadas:
        print(f"Ya existían (saltadas): {res.saltadas}")
    print(f"Fotos importadas    : {res.fotos}")
    if res.avisos:
        print("\nRevisar:")
        for a in res.avisos:
            print(f"  - {a}")
    print("\nLa columna Zona / Sitio quedó vacía: el Excel no la tiene. "
          "Se llena desde la plataforma, en cada actividad.")


if __name__ == "__main__":
    main()
