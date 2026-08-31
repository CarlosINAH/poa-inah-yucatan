# Plan de mejoras — Plataforma POA (Centro INAH Yucatán)

> Basado en el análisis del grafo (`graphify-out/`), la lectura del código real de
> `servidor_poa/app/` y un **recorrido funcional en el navegador** con los datos reales
> (16 actividades, 38 fotos). La versión viva es el servidor FastAPI; `prototipo_poa/` y
> `vista_tema.html` son legado de la v2.0.
> Se avanza **por etapas**: cada una se puede hacer y verificar sola. No pasar a la
> siguiente sin terminar la anterior. Marcar `[x]` lo hecho.

---

## PRIORIDAD: Funcionamiento de la página

> Verificado el 2026-08-05: entrar, tablero, filtros, registrar, **no duplicar**,
> PDF individual y consolidado (con/sin fotos) **funcionan**. Sin errores de consola ni
> de servidor. Lo de abajo es lo que falta pulir en cómo se usa y se comporta la página.

### Etapa F1 — Terminar funciones que ya existen en el backend pero no en la pantalla ✅ (2026-08-05)
- [x] **Destacar foto**: se añadió el botón ★ (arriba-izquierda) en `actividad_detalle.html`,
      con marco dorado en la foto destacada. La ruta ya existía; el PDF ya la ordena primero.
- [x] **Pie de foto**: nueva ruta `POST /fotos/{id}/pie` (`main.py`) + campo de captura por
      foto. El PDF ya usa `pie` como leyenda (`pdf.py:210`). Verificado en navegador con datos
      reales y revertido lo de prueba.
- Nota (trampa verificada): el CSS se sirve con cache-busting `tema.css?v=N` en `base.html`.
  **Al cambiar `tema.css` hay que subir el número de versión** o el navegador sigue con la vieja.

### Etapa F2 — Captura de zona ✅ (2026-08-05)
- [x] **Causa encontrada**: la gente sí escribe el sitio, pero *dentro del título*
      («…nichos pintados en Mayapán», «Visita a la ZA Chichén Itzá»), y deja el campo vacío.
- [x] **Solución**: `app.js` detecta el sitio en el propio título y lo ofrece con un clic
      («¿La zona o sitio es **Mayapán**?»). No pisa lo que la persona ya escribió y no
      insiste cuando no hay sitio (ponencias, cursos). **No se inventó ningún catálogo de
      zonas**: el Excel del POA no trae columna de zona, así que la sugerencia sale siempre
      de las palabras del propio usuario.
- [x] Probado contra los 16 títulos reales: sugiere en 12, sin falsos positivos dañinos
      (el único discutible, «San Luis Potosí», se ignora con no hacer clic).
- [x] Se aclaró en la ayuda del campo que si no hubo sitio, se deja vacío.

---

## REDISEÑO DEL FLUJO (pedido el 2026-08-05)

> Objetivo: que lo use con comodidad alguien que **no usa mucho la computadora**.
> Principio rector: **una decisión por pantalla**, botones grandes, lenguaje llano, y
> desde cualquier lugar se puede volver al inicio sin miedo a perder lo hecho.

**Flujo pedido:** entrar → elegir *consultar* o *registrar* → periodo → formulario → fotos.

### Etapa G1 — Pantalla de Inicio y regreso siempre visible ✅ (2026-08-05)
- [x] Nueva pantalla `/inicio` (`inicio.html`): saluda por nombre y ofrece botones grandes
      con lenguaje llano y datos reales («Tienes N actividades registradas en 2026»).
      Coordinación ve además «Consolidado e informes» y «Personal».
- [x] Botón **«← Inicio»** en la barra superior de todas las pantallas (44 px, alcanzable
      con el dedo). No se muestra en la propia pantalla de inicio.
- [x] `/` ahora lleva a `/inicio` en vez de al tablero.

### Etapa G2 — Asistente por pasos para registrar 🔄 (pasos 1 y 2 hechos)
- [x] **Paso 1 (`/registrar`)**: sólo el periodo, en botones grandes de trimestre con sus
      meses. Indicador «Paso 1 de 3» y «← Volver al inicio».
- [x] **Paso 2 (`/actividades/nueva?anio=&trimestre=`)**: el formulario ya no vuelve a
      preguntar el periodo; lo confirma en una barra («Estás reportando el 2do Trimestre
      de 2026») con botón «Cambiar periodo». Secciones renumeradas.
- [x] Entrar a `/actividades/nueva` sin periodo **regresa al paso 1** en vez de mostrar el
      formulario a medias. La edición conserva su selector de periodo (ahí sí se puede mover).
- [ ] **Paso 3 (fotos)**: hoy al guardar cae en el detalle de la actividad, que ya permite
      subir fotos pero no se presenta como «Paso 3 de 3». Falta darle esa cara.

### Etapa G3 — Exportar a Excel y PDF desde la interfaz
- [ ] Exportar el consolidado a **Excel** con la forma del POA oficial (usar `openpyxl`,
      ya está en `requirements.txt`).
- [ ] Exponer en pantalla el PDF **sin fotos** (el parámetro `fotos=0` ya existe en la ruta).
- [ ] Botones de descarga claros, con nombre de archivo entendible.

### Etapa G4 — Importar Excel desde la web
- [ ] Subir un POA en Excel desde la interfaz (sólo coordinación), reutilizando
      `servidor_poa/importar_excel.py`, que ya lee hasta las fotos incrustadas y **no
      duplica** si se corre dos veces.
- [ ] Mostrar un resumen de lo importado antes/después (cuántas se cargaron, cuántas se
      saltaron por existir ya).

---

### Etapa F3 — Consolidado más útil
- [ ] Cuando no hay zonas capturadas, que la vista "por zona" avise o caiga por defecto a
      "por eje" (que sí tiene datos del catálogo).
- [ ] Exponer en la interfaz la opción de PDF **sin fotos** (el parámetro `fotos=0` ya
      existe en la ruta) para un envío más ligero.

### Etapa F4 — Robustez de las pantallas
- [ ] Revisar casos límite: actividad sin participantes, año sin actividades, foto cuyo
      archivo se borró del disco pero sigue en la base.
- [ ] Confirmar que el flujo de **primer PIN** de coordinación es claro (hoy ningún
      coordinador tiene PIN; Karla lo definirá en su primer ingreso).

---

## Más adelante: solidez interna (infraestructura)

> No es urgente para el funcionamiento diario, pero conviene tenerlo. Se aborda después
> de las etapas F.

## Diagnóstico rápido (qué está bien y qué falta)

**Sólido hoy:** el modelo de datos es correcto (una actividad = un hecho; cada quien suma
su participación; el POA cuenta 1). Las fotos se reprocesan en el servidor. El PIN de
coordinación usa Argon2. La normalización de zonas/títulos evita duplicados. El código
está bien comentado y es coherente.

**Lo que conviene mejorar (en orden de riesgo):**
1. **No hay respaldos ni pruebas.** Ya hay datos reales (actividades + 76 fotos). Hoy
   cualquier cambio se hace "a ciegas": no hay forma automática de saber si algo se rompió,
   ni de recuperar la base si se corrompe.
2. **`@app.on_event("startup")`** (`main.py:44`) está **deprecado** en FastAPI moderno.
   Funciona, pero es deuda que romperá en una futura actualización.
3. **Consultas N+1**: `buscar()`, `participaciones()` y `armar()` (`consolidado.py`) hacen
   una consulta por fila. Con la sección pequeña no se nota; crece linealmente con los datos.
4. **`main.py` (656 líneas)** repite el mismo diccionario de contexto del formulario en
   `nueva_form`, `crear` y `editar_form`. Un cambio hay que hacerlo en tres lugares.
5. **Operación manual**: se arranca con `iniciar_servidor.bat` a mano; sin arranque
   automático ni respaldo programado.
6. **Repo con legado mezclado**: `prototipo_poa/`, `vista_tema.html` y el README apuntan a
   la v2.0 obsoleta.

---

## Etapa 0 — Red de seguridad  *(hacer PRIMERO, no toca código de la app)*
- [ ] Script `scripts_apoyo/respaldar.py` (o `.bat`): copia fechada de `servidor_poa/datos/poa.db`
      + carpeta `fotos/` a `respaldos/AAAA-MM-DD/`. Correrlo **antes de cualquier otra etapa**.
- [ ] Generar `requirements.lock` (pip freeze) para poder reinstalar idéntico si algo falla.
- [ ] Verificar que `.venv` reinstala en limpio desde `requirements.txt` sin errores.

## Etapa 1 — Pruebas mínimas  *(la red que permite actualizar sin miedo)*
- [ ] Añadir `pytest` + `httpx` (TestClient de FastAPI) en un `requirements-dev.txt`.
- [ ] Base de datos temporal por prueba (no tocar `poa.db` real).
- [ ] Cubrir los flujos críticos:
      - entrar eligiendo nombre (sin PIN) y entrar como coordinación (con PIN)
      - crear actividad + validaciones (título corto, sin catálogo, sin trimestre)
      - **no duplicar**: sumarse a una existente en vez de crear otra (`sumar_participante` idempotente)
      - subir foto / tope de 4 / eliminar foto
      - generar PDF individual y consolidado (que no truene)
      - permisos: quien no es dueño no edita ni borra
- [ ] Meta: `pytest` corre en segundos y dice si algo se rompió.

## Etapa 2 — Modernizar FastAPI  *(con la Etapa 1 como red)*
- [ ] Reemplazar `@app.on_event("startup")` por el manejador `lifespan`.
- [ ] Revisar otras deprecaciones al iniciar (correr con warnings visibles).
- [ ] Actualizar dependencias a versiones vigentes, corriendo `pytest` después de cada salto.

## Etapa 3 — Rendimiento de consultas (N+1)
- [ ] Reescribir `buscar()` para traer participantes y conteo de fotos con una sola
      consulta agregada (JOIN + GROUP BY), no una por actividad.
- [ ] Igual para `armar()` / `participaciones()` en el consolidado.
- [ ] Confirmar índices necesarios (hoy existen `ix_act_*` y `ix_fotos_part`).

## Etapa 4 — Limpieza de `main.py`
- [ ] Extraer el contexto de formulario duplicado a un helper `_contexto_form(con, ...)`.
- [ ] Añadir logging básico (arranque, errores, acciones de coordinación).

## Etapa 5 — Operación y despliegue
- [ ] Arranque automático con el **Programador de tareas de Windows** (en vez del `.bat` a mano).
- [ ] Respaldo diario automático (reutiliza el script de la Etapa 0).
- [ ] (Opcional) HTTPS interno si la red del Centro lo permite.

## Etapa 6 — Limpieza del repositorio y documentación
- [ ] Mover `prototipo_poa/` y `vista_tema.html` a `_legado/` (o eliminarlos si ya no sirven).
- [ ] Actualizar `README.txt` para que deje de apuntar al prototipo v2.0.
- [ ] Documentar respaldo y arranque para quien opere la plataforma.

---

### Sugerencia de ritmo (para que alcancen los tokens)
Una etapa por sesión. Empezar por la **Etapa 0** (rápida y sin riesgo) y la **Etapa 1**
(la que más valor da: a partir de ahí todo lo demás se hace con red). Las etapas 3–6 son
mejoras, no urgencias.
