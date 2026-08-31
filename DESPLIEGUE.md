# Guía de despliegue — Plataforma POA en línea

Esta guía lleva la plataforma de la red interna a una URL en línea (Fly.io), con el
código respaldado en GitHub. Está pensada para hacerse una sola vez.

> **Antes que nada:** la base de datos y las fotos del personal **no** se suben a
> GitHub (el `.gitignore` ya las excluye). Sólo viaja el código. Los datos reales
> viven en el volumen persistente del servidor.

---

## 1. Requisitos (instalar una vez)

- **Git** — ya está instalado.
- **GitHub CLI (`gh`)** — para crear el repositorio y autenticarte:
  https://cli.github.com/  → o en PowerShell: `winget install GitHub.cli`
- **Fly CLI (`flyctl`)** — para desplegar:
  En PowerShell: `iwr https://fly.io/install.ps1 -useb | iex`
  (necesitas una cuenta en https://fly.io — el plan tiene una capa gratuita).

Cierra y reabre la terminal después de instalarlas para que queden en el PATH.

---

## 2. Subir el código a GitHub (repositorio privado)

Desde la carpeta del proyecto:

```bash
git add -A
git commit -m "Plataforma POA lista para desplegar"
gh auth login
gh repo create poa-inah-yucatan --private --source=. --push
```

Esto crea el repositorio **privado** `poa-inah-yucatan` en tu cuenta y sube el código.
(Si prefieres hacerlo a mano: crea el repo vacío en github.com, luego
`git remote add origin <URL>` y `git push -u origin main`.)

---

## 3. Desplegar en Fly.io

1. Edita `fly.toml` y cambia la línea `app = "poa-inah-yucatan"` por un nombre único
   (si ese ya está tomado, Fly te avisará).

2. Inicia sesión y crea la app + el volumen persistente:

   ```bash
   fly auth login
   fly apps create poa-inah-yucatan          # usa el mismo nombre del fly.toml
   fly volumes create poa_datos --region qro --size 1
   ```

3. Despliega:

   ```bash
   fly deploy
   ```

La primera vez, el contenedor crea la base de datos y carga el catálogo POA y el
personal automáticamente (paso `inicializar.py`). Al terminar, `fly deploy` te da la
URL pública (algo como `https://poa-inah-yucatan.fly.dev`).

Para actualizar en el futuro (tras cambiar código): `git push` y luego `fly deploy`.

---

## 4. (Opcional) Llevar los datos actuales a la versión en línea

El despliegue arranca con la base **recién sembrada** (personal y catálogo, sin
actividades). Si quieres que las 16 actividades y las fotos que ya tienes en la PC
interna aparezcan en línea, hay que copiar `servidor_poa/datos` al volumen:

```bash
# Con la app ya desplegada y encendida:
tar -C servidor_poa/datos -czf - poa.db fotos | \
  fly ssh console -C "tar -C /app/servidor_poa/datos -xzf -"
fly apps restart poa-inah-yucatan
```

> Este paso sobrescribe la base en línea con la local. Hazlo sólo la primera vez, o
> perderás lo que se haya capturado en línea. Si tienes dudas, pídeme ayuda antes de
> correrlo.

---

## 5. Notas de seguridad (importante al pasar a internet)

- **Ahora todos entran con PIN.** La primera vez que cada persona entre, la plataforma
  le pedirá **definir su PIN**. Avísales para que lo hagan pronto: mientras alguien no
  tenga PIN, cualquiera que elija su nombre podría ponérselo y entrar por esa persona
  (ventana de "primer día"). Idealmente que las 14 personas entren y definan su PIN el
  mismo día.
- Si alguien olvida su PIN, la **coordinación** lo reinicia desde **Personal** y esa
  persona define uno nuevo en su siguiente ingreso.
- La cookie de sesión ya va **sólo por HTTPS** en línea (`POA_COOKIE_SEGURA=1` en
  `fly.toml`).
- **Eliminar una actividad** sigue siendo exclusivo de la coordinación.
