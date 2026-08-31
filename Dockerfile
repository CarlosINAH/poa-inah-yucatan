# Plataforma POA — Sección de Conservación y Restauración, Centro INAH Yucatán
# Imagen para correr el servidor FastAPI en Docker (p. ej. en el NAS Synology).
FROM python:3.12-slim

# Salida sin buffer (logs en vivo) y zona horaria de Yucatán para fechas correctas.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Merida

# tzdata para que TZ tenga efecto; ca-certificates por si se necesitan salidas TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependencias primero (capa cacheable: no se reinstalan si sólo cambia el código).
COPY servidor_poa/requirements.txt servidor_poa/requirements.txt
RUN pip install --no-cache-dir -r servidor_poa/requirements.txt

# 2) Código de la aplicación y el catálogo POA que necesita inicializar.py
#    (datos_extraidos/poa_catalog.json). La carpeta servidor_poa/datos NO se copia
#    a propósito: vive en un volumen para que la BD y las fotos persistan.
COPY servidor_poa/ servidor_poa/
COPY datos_extraidos/ datos_extraidos/

# 3) Arranque: siembra la BD la primera vez y luego levanta el servidor.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /app/servidor_poa
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
