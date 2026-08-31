/* Plataforma POA · Sección de Conservación y Restauración · Centro INAH Yucatán */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------------------------------------------------------------- tema */
  const segTema = $('#segTema');
  if (segTema) {
    const aplicar = (pref) => {
      const oscuro = pref === 'dark' ||
        (pref === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.dataset.theme = oscuro ? 'dark' : 'light';
      $$('button', segTema).forEach(b => {
        const elegido = b.dataset.tema === pref;
        b.classList.toggle('on', elegido);
        // Sin esto el lector de pantalla no puede saber qué tema está puesto:
        // la única señal era el color de fondo.
        b.setAttribute('aria-pressed', String(elegido));
      });
    };
    aplicar(localStorage.getItem('poa_tema') || 'auto');
    segTema.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      localStorage.setItem('poa_tema', b.dataset.tema);
      aplicar(b.dataset.tema);
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if ((localStorage.getItem('poa_tema') || 'auto') === 'auto') aplicar('auto');
    });
  }

  /* ------------------------------------------------------------- avisos */
  $$('#toasts .toast').forEach(t => {
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, 6000);
  });

  /* ------------------------------- contador de palabras (límite del POA) */
  const contar = (texto) => (texto.trim().match(/\S+/g) || []).length;
  $$('textarea[name="resumen"]').forEach(ta => {
    const salida = ta.parentElement.querySelector('.char-count');
    if (!salida) return;
    const pintar = () => {
      const n = contar(ta.value);
      salida.textContent = `${n} / 300 palabras`;
      salida.style.color = n > 300 ? 'var(--rose)' : '';
    };
    ta.addEventListener('input', pintar);
    pintar();
  });

  /* ---------------------- campos derivados de la Actividad POA (VLOOKUP) */
  const selCatalogo = $('#catalogo');
  if (selCatalogo) {
    const destinos = {
      unidad_medida: $('#d_unidad'), programa_operativo: $('#d_programa'),
      eje: $('#d_eje'), linea_accion_enc: $('#d_linea'),
      eje_estrategico_enc: $('#d_ejeenc'),
    };
    const derivar = async () => {
      const id = selCatalogo.value;
      if (!id) {
        Object.values(destinos).forEach(o => {
          if (o) { o.textContent = '—'; o.closest('.dfield').classList.remove('filled'); }
        });
        return;
      }
      try {
        const r = await fetch(`/api/catalogo/${id}`);
        if (!r.ok) return;
        const d = await r.json();
        Object.entries(destinos).forEach(([clave, salida]) => {
          if (!salida) return;
          salida.textContent = d[clave] || '—';
          salida.closest('.dfield').classList.toggle('filled', Boolean(d[clave]));
        });
      } catch { /* sin conexión: los campos se llenan igual en el servidor al guardar */ }
    };
    selCatalogo.addEventListener('change', derivar);
    derivar();
  }

  /* ------------- ¿ya existe esta actividad? Sumarse en vez de duplicar */
  const inTitulo = $('#titulo');
  const aviso = $('#avisoParecidas');
  // Al editar una actividad que ya existe no tiene sentido ofrecer sumarse a ella.
  const editando = $('#formActividad')?.dataset.editando === 'si';
  if (inTitulo && aviso && !editando) {
    let temporizador;
    const consultar = async () => {
      const titulo = inTitulo.value.trim();
      // Sin selector de etiqueta: el año es un <select>, no un <input>.
      const anio = $('[name="anio"]')?.value || '';
      if (titulo.length < 5 || !anio) { aviso.hidden = true; return; }
      try {
        const params = new URLSearchParams({
          titulo, anio, catalogo_id: $('#catalogo')?.value || '0',
        });
        const r = await fetch(`/api/parecidas?${params}`);
        if (!r.ok) return;
        const encontradas = await r.json();
        if (!encontradas.length) { aviso.hidden = true; return; }
        aviso.innerHTML = `
          <div class="edit-banner">
            <div>
              <b>Puede que esto ya esté registrado</b>
              <div class="section-desc">Si es la misma actividad, súmate: contará
                <b>1</b> para el POA y tú escribes tu propio resumen.</div>
              <div class="stack" style="margin-top:10px">
                ${encontradas.map(a => `
                  <div class="rep-card">
                    <div class="rc-top">
                      <strong>${escapar(a.titulo)}</strong>
                      <span class="tag">${escapar(a.zona || 'Sin zona')}</span>
                    </div>
                    <div class="mini">${escapar(a.participantes || 'Sin participantes')}</div>
                    <div class="actions">
                      <a class="btn sm" href="/actividades/${a.id}">Verla</a>
                      ${a.ya_estoy
                        ? '<span class="muted" style="font-size:12px">Ya estás en ésta</span>'
                        : `<button class="btn sm primary" type="button"
                                   data-sumarme="${a.id}">Sumarme a ésta</button>`}
                    </div>
                  </div>`).join('')}
              </div>
            </div>
          </div>`;
        aviso.hidden = false;
      } catch { /* si falla, el usuario sigue capturando normal */ }
    };
    const agendar = () => { clearTimeout(temporizador); temporizador = setTimeout(consultar, 450); };
    inTitulo.addEventListener('input', agendar);
    $('#catalogo')?.addEventListener('change', agendar);
    // El parecido se busca dentro del mismo año: si cambia, hay que volver a mirar.
    $('[name="anio"]')?.addEventListener('change', agendar);

    // El aviso vive dentro del formulario de alta, y los <form> no pueden anidarse:
    // el navegador descarta el interno. Por eso se envía con fetch.
    aviso.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-sumarme]');
      if (!b) return;
      b.disabled = true;
      b.textContent = 'Sumándote…';
      const id = b.dataset.sumarme;
      try {
        const r = await fetch(`/actividades/${id}/sumarme`, { method: 'POST' });
        if (!r.ok) throw new Error(r.status);
        location.href = `/actividades/${id}`;
      } catch {
        b.disabled = false;
        b.textContent = 'Sumarme a ésta';
        alert('No pude sumarte. Abre la actividad con «Verla» e inténtalo desde ahí.');
      }
    });
  }

  const escapar = (s) => String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* --------------------------- la zona que ya viene escrita dentro del título

     Nadie llenaba «Zona / Sitio»: el sitio se escribe dentro del título
     («…nichos pintados en Mayapán»). En vez de pedir que lo teclee otra vez, se
     le ofrece lo que él mismo ya escribió. Es una sugerencia: si se equivoca, la
     ignora. No hay catálogo oficial de zonas, así que no se inventa ninguna. */
  const inZona = $('#zonaSitio');
  const sugZona = $('#sugerenciaZona');
  if (inZona && sugZona && $('#titulo')) {
    const NOMBRE = '[A-ZÁÉÍÓÚÑ][\\wáéíóúñ]*';
    const FRASE = `${NOMBRE}(?:\\s+(?:de\\s+|del\\s+|la\\s+|las\\s+|los\\s+)?${NOMBRE})*`;
    // Ni el artículo ni «ZA»/«Zona Arqueológica» son parte del nombre del sitio.
    const ART = '(?:el\\s+|la\\s+|las\\s+|los\\s+)?(?:ZA\\s+|Zona\\s+Arqueológica\\s+)?';
    const PATRONES = [
      // «… en Mayapán», «… en la Iglesia de San Juan», «Visita a la ZA Chichén Itzá»
      new RegExp(`\\b(?:en|a)\\s+${ART}(${FRASE})`, 'g'),
      // «Restauración de ancla histórica – Progreso»
      new RegExp(`[–—-]\\s*(${FRASE})\\s*$`, 'g'),
      // «Intervención de remoción de graffitis (Gotas Doradas)»
      new RegExp(`\\((${FRASE})\\)`, 'g'),
      // «… de la colección de Xuenkal» (el sitio cierra el título)
      new RegExp(`\\bde\\s+(${FRASE})\\s*$`, 'g'),
    ];

    const candidata = (titulo) => {
      for (const re of PATRONES) {
        re.lastIndex = 0;
        let m, ultima = null;
        // La última coincidencia: el sitio suele ir al final del título.
        while ((m = re.exec(titulo)) !== null) ultima = m[1];
        if (ultima) {
          const limpia = ultima.trim().replace(/\s+/g, ' ');
          if (limpia.length >= 4 && limpia.length <= 60) return limpia;
        }
      }
      return null;
    };

    const proponer = () => {
      // Sólo se ofrece si la persona no escribió ya su zona: no se pisa lo suyo.
      if (inZona.value.trim()) { sugZona.hidden = true; return; }
      const z = candidata($('#titulo').value || '');
      if (!z) { sugZona.hidden = true; return; }
      sugZona.innerHTML = `¿La zona o sitio es <b>${escapar(z)}</b>?
        <button type="button" class="btn sm" data-usar-zona>Sí, usarla</button>`;
      sugZona.hidden = false;
    };

    sugZona.addEventListener('click', (e) => {
      if (!e.target.closest('[data-usar-zona]')) return;
      inZona.value = sugZona.querySelector('b').textContent;
      sugZona.hidden = true;
      inZona.focus();
    });

    let tZona;
    $('#titulo').addEventListener('input', () => {
      clearTimeout(tZona);
      tZona = setTimeout(proponer, 450);
    });
    inZona.addEventListener('input', proponer);
    proponer();
  }

  /* ------------------------------------------- fotos: arrastrar y reducir */
  const LADO_MAXIMO = 2200;
  const CALIDAD = 0.82;
  const MAX_BYTES = 50 * 1024 * 1024;

  /* Reduce en el navegador para no mandar 50 MB por la red interna.
     El servidor vuelve a procesar de todas formas: esto es velocidad, no confianza. */
  async function reducir(file) {
    if (!file.type.startsWith('image/')) return null;
    if (file.size > MAX_BYTES) {
      alert(`«${file.name}» pesa ${(file.size / 1048576).toFixed(0)} MB y el máximo son 50 MB.`);
      return null;
    }
    try {
      const bitmap = await createImageBitmap(file);
      const escala = Math.min(1, LADO_MAXIMO / Math.max(bitmap.width, bitmap.height));
      if (escala === 1 && file.size < 2 * 1024 * 1024) { bitmap.close(); return file; }
      const w = Math.round(bitmap.width * escala);
      const h = Math.round(bitmap.height * escala);
      const lienzo = Object.assign(document.createElement('canvas'), { width: w, height: h });
      lienzo.getContext('2d').drawImage(bitmap, 0, 0, w, h);
      bitmap.close();
      const blob = await new Promise(res => lienzo.toBlob(res, 'image/jpeg', CALIDAD));
      if (!blob || blob.size >= file.size) return file;
      return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
    } catch {
      return file;   // si el navegador no puede, que lo reduzca el servidor
    }
  }

  $$('.form-fotos').forEach(form => {
    const zona = $('[data-zona]', form);
    const input = $('input[type="file"]', form);
    const boton = $('button[type="submit"]', form);
    if (!zona || !input) return;

    const hint = $('.dz-hint', zona);
    const textoInicial = hint ? hint.textContent : '';
    const pintar = () => {
      const n = input.files.length;
      if (!hint) return;
      hint.textContent = n
        ? `${n} foto${n !== 1 ? 's' : ''} lista${n !== 1 ? 's' : ''} para subir`
        : textoInicial;
    };

    // El input ya no está [hidden] (así se alcanza con el tabulador), de modo que
    // el clic sobre él llega hasta aquí: sin este filtro se reabriría el diálogo.
    zona.addEventListener('click', (e) => { if (e.target !== input) input.click(); });
    zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('drag'); });
    zona.addEventListener('dragleave', () => zona.classList.remove('drag'));
    zona.addEventListener('drop', e => {
      e.preventDefault();
      zona.classList.remove('drag');
      const dt = new DataTransfer();
      Array.from(e.dataTransfer.files).forEach(f => dt.items.add(f));
      input.files = dt.files;
      pintar();
    });
    input.addEventListener('change', pintar);

    let reduciendo = false;
    form.addEventListener('submit', async (e) => {
      if (reduciendo || !input.files.length) return;
      e.preventDefault();
      reduciendo = true;
      if (boton) { boton.disabled = true; boton.textContent = 'Preparando fotos…'; }
      const dt = new DataTransfer();
      for (const file of Array.from(input.files)) {
        const listo = await reducir(file);
        if (listo) dt.items.add(listo);
      }
      input.files = dt.files;
      if (!dt.files.length) {
        reduciendo = false;
        if (boton) { boton.disabled = false; boton.textContent = 'Subir fotos'; }
        return;
      }
      if (boton) boton.textContent = 'Subiendo…';
      form.submit();
    });
  });
})();
