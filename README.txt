Plataforma POA - Sección de Conservación y Restauración, Centro INAH Yucatán
Versión 3.0 (servidor en red interna)

==============================================================================
QUÉ CAMBIÓ RESPECTO DE LA VERSIÓN 2.0
==============================================================================
La 2.0 era un archivo HTML local que se abría con doble clic y guardaba en el
navegador. Se cambió a un servidor para NO DUPLICAR ACTIVIDADES: si varias
personas participan en la misma actividad, el POA debe contarla UNA vez, y para
que el sistema sepa que dos reportes son el mismo hecho tiene que verlos a la
vez. Con archivos locales cada quien captura a ciegas y los títulos escritos a
mano nunca coinciden.

El prototipo 2.0 sigue en prototipo_poa/index.html como referencia. La versión
que se usa es la de servidor_poa/.

==============================================================================
CÓMO SE ENTRA (no hay contraseñas)
==============================================================================
La plataforma abre con una lista de nombres: cada quien elige el suyo y entra.
Nada que teclear, nada que olvidar.

Lo que eso implica, dicho claro: cualquiera en la red interna puede elegir
cualquier nombre. Es una decisión consciente de la Sección, a cambio de que
capturar no cueste fricción. Por eso lo delicado está acotado:

- El Consolidado y el panel de Personal piden un PIN. Sólo la coordinación
  (Karla Martínez y Carlos Gálvez) lo tiene.
- ELIMINAR una actividad es sólo de coordinación, porque arrastra los resúmenes
  y las fotos de todos sus participantes y no se deshace.
- Todo lo demás (capturar, sumarse, escribir el propio resumen, subir fotos)
  está abierto a quien elija su nombre.

PRIMER DÍA - IMPORTANTE:
La coordinación arranca SIN PIN. La primera vez que Karla y Carlos elijan su
nombre, la plataforma les pedirá crearlo. Háganlo de inmediato: mientras un PIN
esté vacío, cualquiera que elija ese nombre puede ponerle uno y quedarse con el
acceso a la coordinación.

Si alguien de coordinación olvida su PIN, la otra persona de coordinación lo
borra desde Personal ("Olvidó su PIN") y así puede definir uno nuevo.

==============================================================================
INSTALACIÓN (una sola vez, en el equipo que hará de servidor)
==============================================================================
Requiere Python 3.12 o superior.

  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r servidor_poa\requirements.txt
  .venv\Scripts\python.exe servidor_poa\inicializar.py

El último comando crea la base, carga el catálogo POA (67 actividades) y da de
alta a las 14 personas de la Sección. No genera contraseñas: no hay.

==============================================================================
CARGAR UN POA DESDE EXCEL
==============================================================================
  .venv\Scripts\python.exe servidor_poa\importar_excel.py "C:\ruta\archivo.xlsx"

Lee la hoja "Actividades" desde la fila 3, incluidas las fotos "imagen en celda"
de Excel 365 (que openpyxl no ve: la celda sólo guarda #VALUE! y hay que seguir a
mano la cadena vm -> metadata -> richValue -> rel -> media).

Se puede correr dos veces sin duplicar: si una actividad con el mismo título y año
ya existe, la salta. Al terminar reporta lo que hay que revisar.

Ya se cargaron las 16 actividades del 2do trimestre 2026 con sus 38 fotos.
La columna Zona / Sitio quedó VACÍA porque el Excel no la tiene: hay que llenarla
en cada actividad desde la plataforma para que el consolidado por zona sirva.

==============================================================================
ENCENDER LA PLATAFORMA
==============================================================================
Doble clic en:  servidor_poa\iniciar_servidor.bat

La ventana muestra la dirección para los demás (algo como http://10.131.2.24:8000)
y debe quedarse abierta: mientras esté abierta, la plataforma está encendida.

Si tus compañeros no logran entrar desde sus equipos, es el Firewall de Windows.
Abre el puerto una vez, en PowerShell como administrador:

  New-NetFirewallRule -DisplayName "Plataforma POA" -Direction Inbound `
    -LocalPort 8000 -Protocol TCP -Action Allow -Profile Domain,Private

==============================================================================
CÓMO SE USA
==============================================================================
Al entrar, cada quien ve DIRECTAMENTE la lista de sus actividades (el tablero es
la lista; no hay una pantalla aparte que muestre lo mismo). Un conmutador
"Mías / Todas" cambia entre lo propio y lo de toda la Sección, y se filtra por
año, trimestre y zona.

EL TRIMESTRE ES LA CATEGORÍA. Al registrar una actividad lo primero que se elige
es Año + Trimestre (con los meses a la vista: 2do Trimestre = abril a junio, para
no confundirlo con semestres). Después sólo se capturan "Planeado" y "Realizado"
de ese trimestre. Por dentro la base conserva la rejilla de 4+4 del POA oficial,
que es la que sale en el PDF, pero nadie tiene que llenar ocho casillas.

LO IMPORTANTE - cuando varios trabajaron en lo mismo:
  Al escribir el título, si ya existe algo parecido la plataforma avisa y ofrece
  "Sumarme a ésta". Al sumarte NO se crea otra actividad: es la misma, cuenta 1
  para el POA, y tú escribes tu propio resumen y subes tus propias fotos (hasta
  4). En el consolidado sale una sola actividad con todos los participantes.

Fotos: se aceptan hasta 50 MB por foto. El navegador y el servidor las reducen
automáticamente (una versión para ver y otra, menor, para el PDF). Una foto de
10 MB termina ocupando unos 2 MB.

Zonas: se escribe la que sea. Si ya existe una parecida, se guarda con la
escritura canónica, para que el consolidado no la parta en varios renglones
("chichen itza" se guarda como "Chichén Itzá").

==============================================================================
PERMISOS
==============================================================================
- Cualquier empleado: registra actividades, se suma a las existentes, escribe su
  resumen y sube sus fotos. Sólo puede tocar LO SUYO.
- Quien creó la actividad, y el responsable de proyecto asignado: además pueden
  editar su ficha POA (cifras, alineación).
- Coordinación (con PIN): además ve el Consolidado, genera el PDF de la Sección,
  elimina actividades, y administra el personal (activar/desactivar, borrar el
  PIN de la otra persona de coordinación).

Coordinación actual: Karla Martínez López y Carlos Alberto Gálvez Valencia.
Para cambiarlo, edita la columna es_admin en la tabla usuarios.

==============================================================================
INFORMES
==============================================================================
- PDF individual: en cada actividad, botón "Ver PDF". Reemplaza a la hoja
  "Reporte de actividades" del Excel, sin tener que escribir el número de fila.
- PDF consolidado: pestaña Consolidado (sólo coordinación). Se elige año,
  trimestre y si se agrupa por zona o por eje. Sale con portada, resumen
  ejecutivo, una ficha por actividad y bloque de firmas (Elaboró / Revisó /
  Vo. Bo. coordinación). Hay versión con fotos y sin fotos.

==============================================================================
RESPALDO
==============================================================================
Todo vive en la carpeta servidor_poa\datos\:
  poa.db          la base de datos completa
  fotos\          las fotos
Copia esa carpeta entera y tienes todo. Hazlo con el servidor apagado.

==============================================================================
CONTENIDO DEL PROYECTO
==============================================================================
servidor_poa\
  app\main.py           rutas web y permisos
  app\db.py             esquema de la base
  app\consolidado.py    consultas y armado del consolidado
  app\pdf.py            generación de los PDF
  app\fotos.py          validación y reducción de imágenes
  app\auth.py           lista de nombres y PIN de coordinación (Argon2)
  app\templates\        páginas
  app\static\           tema Liquid Glass, JavaScript y logos
  datos\                base de datos y fotos (respaldar esto)
  inicializar.py        crea la base y da de alta al personal
  iniciar_servidor.bat  encender la plataforma
prototipo_poa\          versión 2.0 anterior, de referencia
datos_extraidos\        catálogo POA y análisis del Excel de origen
scripts_apoyo\          scripts de inspección del Excel

NOTA sobre el catálogo: el Excel de origen escribe "Corservación" en los siete
Programas Nacionales de Conservación. En la plataforma está corregido.
