#!/bin/sh
# Arranque del contenedor de la Plataforma POA.
set -e
cd /app/servidor_poa

# La primera vez (volumen vacío) crea la base de datos y carga el catálogo POA
# y el personal. Si la BD ya existe, no la toca: el esquema se migra solo al
# arrancar la app (crear_esquema en app/main.py).
if [ ! -f datos/poa.db ]; then
  echo "Primer arranque: creando base de datos y cargando catálogo + personal..."
  python inicializar.py
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
