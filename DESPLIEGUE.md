# Guía de despliegue — Plataforma POA en línea

Objetivo: dejar la plataforma **en línea para consulta** corriendo en una **PC de la
Sección**, publicada con **Cloudflare Tunnel** (URL HTTPS, sin abrir puertos del
firewall), y con el código respaldado en **GitHub (privado)**.

> **Los datos del personal (base y fotos) nunca salen de la PC del INAH ni se suben a
> GitHub.** El `.gitignore` ya los excluye. Sólo el código va al repositorio.

---

## 1. Subir el código a GitHub (privado)

Requiere **GitHub CLI**: `winget install GitHub.cli` (reabre la terminal después).

```bash
git add -A
git commit -m "Despliegue con Docker + Cloudflare Tunnel"
gh auth login
gh repo create poa-inah-yucatan --private --source=. --push
```

Esto crea el repo **privado** y sube el código. (Alternativa manual: crear el repo
vacío en github.com, `git remote add origin <URL>`, `git push -u origin main`.)

---

## 2. Correr la plataforma en la PC de la Sección

Elige **una** de las dos opciones. La **A** es la más simple y no necesita Docker.

### Opción A — Nativa (recomendada en Windows, ya funciona hoy)

Es como ya la usas en la red interna. Doble clic en:

```
servidor_poa\iniciar_servidor.bat
```

Queda escuchando en `http://localhost:8000`. Deja esa ventana abierta. (Para que
arranque sola al prender la PC, se puede poner un acceso directo del `.bat` en la
carpeta de Inicio de Windows.)

### Opción B — En contenedor

En Windows, **Docker Desktop requiere licencia de pago** para instituciones grandes
como el INAH. Usa en su lugar **Rancher Desktop** o **Podman Desktop** (gratuitos), que
entienden el mismo `docker-compose.yml`. Luego:

```bash
docker compose up -d          # levanta la plataforma en http://localhost:8000
```

El contenedor reutiliza `servidor_poa/datos`, así que ve las actividades y fotos que ya
tienes. (En un NAS Linux, Docker es gratuito y esta opción es la ideal.)

---

## 3. Publicarla en línea con Cloudflare Tunnel

El túnel toma lo que corre en `http://localhost:8000` y le da una URL pública HTTPS,
sin exponer la PC ni tocar el firewall del INAH.

**Necesitas una vez:** una cuenta gratuita en Cloudflare y un **dominio agregado a
Cloudflare** (si el INAH no te da uno, un dominio propio barato sirve). Sin dominio,
existe el modo de prueba del paso 3.d.

**a.** Entra a **Cloudflare Zero Trust** → **Networks → Tunnels → Create a tunnel**
   → tipo *Cloudflared* → ponle nombre (p. ej. `poa-inah`).

**b.** Copia el **token** que te muestra (empieza con `eyJ...`).

**c.** En **Public Hostname** del túnel, define:
   - *Subdomain/Domain*: el que quieras, p. ej. `poa.tudominio.mx`
   - *Service*: `http://localhost:8000` (Opción A nativa) **o** `http://poa:8000`
     (Opción B en contenedor).

**d.** Ejecuta el túnel en la PC:

   - **Nativa:** descarga `cloudflared` para Windows
     (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/),
     y corre:
     ```bash
     cloudflared.exe tunnel run --token eyJ...
     ```
     (o instálalo como servicio: `cloudflared.exe service install eyJ...`, así arranca solo).

   - **En contenedor:** copia `.env.example` a `.env`, pega el token en `TUNNEL_TOKEN`, y:
     ```bash
     docker compose --profile online up -d
     ```

   - **Modo de prueba (sin dominio ni cuenta), URL temporal:**
     ```bash
     cloudflared.exe tunnel --url http://localhost:8000
     ```
     Te da una URL `https://xxxxx.trycloudflare.com` que cambia en cada arranque. Sirve
     para probar; no para el uso diario.

**e.** Cuando ya todos entren por la URL HTTPS del túnel, sube la seguridad de la cookie:
   - **Nativa:** antes de arrancar el `.bat`, en esa terminal: `set POA_COOKIE_SEGURA=1`
   - **Contenedor:** cambia `POA_COOKIE_SEGURA=0` a `=1` en `docker-compose.yml`.
   > No lo pongas en `1` si alguien sigue entrando por `http://IP:8000` sin cifrar: con la
   > cookie "segura", esos no podrían iniciar sesión.

Comparte la URL del túnel con las 14 personas. Listo: la plataforma está en línea.

---

## 4. Seguridad — importante al pasar a internet

- **Ahora todos entran con PIN.** La primera vez, cada persona **define su PIN**. Avísales
  para que las 14 lo hagan pronto (idealmente el mismo día): mientras alguien no tenga
  PIN, cualquiera que elija su nombre podría ponérselo y entrar por esa persona.
- Si alguien lo olvida, la **coordinación** lo reinicia desde **Personal** y esa persona
  define uno nuevo al siguiente ingreso.
- **Eliminar una actividad** sigue siendo exclusivo de la coordinación.
- El **token del túnel** es un secreto: vive en `.env` (nunca en GitHub).

---

## Alternativa en la nube (si algún día no hay PC siempre encendida)

El repo también trae `fly.toml` para desplegar en **Fly.io** (que por debajo usa el
mismo `Dockerfile`). Los datos irían a un volumen en la nube en vez de quedarse en el
INAH. Pídeme la guía si llegas a necesitarla.
