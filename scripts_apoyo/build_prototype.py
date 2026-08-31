from pathlib import Path
import json

catalog_path = Path("work/excel_analysis/poa_catalog.json")
payload = json.loads(catalog_path.read_text(encoding="utf-8"))
activities = payload["activities"]

output_dir = Path("outputs/prototipo_poa")
output_dir.mkdir(parents=True, exist_ok=True)

html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Plataforma POA | Prototipo</title>
  <style>
    :root {{
      --ink: #17201f;
      --muted: #5b6763;
      --line: #d8dfdc;
      --field: #f8faf9;
      --accent: #0e766e;
      --accent-dark: #09544f;
      --gold: #a26718;
      --rose: #9b2f45;
      --bg: #eef3f1;
      --panel: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    button, input, select, textarea {{ font: inherit; }}
    .app {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px 1fr;
    }}
    aside {{
      background: #123331;
      color: white;
      padding: 24px 20px;
    }}
    .brand {{
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .caption {{
      color: #c6d7d4;
      font-size: 13px;
      line-height: 1.45;
    }}
    nav {{
      display: grid;
      gap: 8px;
      margin-top: 28px;
    }}
    .tab-btn {{
      border: 0;
      border-radius: 6px;
      padding: 12px;
      background: transparent;
      color: #eaf2f0;
      text-align: left;
      cursor: pointer;
    }}
    .tab-btn.active {{ background: #1d504c; }}
    main {{ padding: 24px; }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 18px;
    }}
    h1 {{ font-size: 26px; margin: 0; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 0 0 14px; }}
    .muted {{ color: var(--muted); font-size: 14px; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, .65fr);
      gap: 18px;
      align-items: start;
    }}
    section, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .fields {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: #31413e;
      font-weight: 700;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid #cbd5d1;
      border-radius: 6px;
      padding: 10px 11px;
      background: var(--field);
      color: var(--ink);
      min-height: 40px;
    }}
    textarea {{ min-height: 92px; resize: vertical; }}
    .span-2 {{ grid-column: 1 / -1; }}
    .autofill {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .auto-item {{
      border-left: 4px solid var(--accent);
      background: #eef8f6;
      padding: 10px;
      border-radius: 6px;
    }}
    .auto-item b {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    .btn {{
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      color: white;
      background: var(--accent);
      cursor: pointer;
      font-weight: 700;
    }}
    .btn.secondary {{ background: #40514e; }}
    .btn.warning {{ background: var(--gold); }}
    .btn.danger {{ background: var(--rose); }}
    .photo-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 10px;
    }}
    .photo-grid img {{
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--line);
    }}
    .report-list {{
      display: grid;
      gap: 10px;
      max-height: 560px;
      overflow: auto;
    }}
    .report-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfc;
    }}
    .report-card strong {{ display: block; margin-bottom: 4px; }}
    .report-card .mini {{ font-size: 12px; color: var(--muted); line-height: 1.4; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid var(--line);
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{ background: #e9f1ef; }}
    .hidden {{ display: none; }}
    #printArea {{ display: none; }}
    @media (max-width: 920px) {{
      .app {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
      .grid, .fields, .autofill {{ grid-template-columns: 1fr; }}
      main {{ padding: 16px; }}
    }}
    @media print {{
      body {{ background: white; }}
      .app {{ display: block; }}
      aside, main {{ display: none; }}
      #printArea {{
        display: block;
        padding: 22px;
        color: #111;
      }}
      #printArea h1 {{ font-size: 22px; margin-bottom: 8px; }}
      #printArea h2 {{ font-size: 16px; margin-top: 18px; }}
      #printArea .print-meta {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
        margin: 14px 0;
      }}
      #printArea .print-box {{
        border: 1px solid #bbb;
        padding: 8px;
        min-height: 38px;
      }}
      #printArea img {{
        width: 31%;
        margin: 0 1% 10px 0;
        aspect-ratio: 4 / 3;
        object-fit: cover;
      }}
      #printArea table {{ page-break-inside: auto; }}
      #printArea tr {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">Reportes POA</div>
      <div class="caption">Prototipo con catálogo importado desde el Excel de ejemplo. La Actividad POA autocompleta unidad, programa, eje y líneas ENC.</div>
      <nav>
        <button class="tab-btn active" data-tab="capture">Captura</button>
        <button class="tab-btn" data-tab="reports">Reportes individuales</button>
        <button class="tab-btn" data-tab="consolidated">Consolidado por sección</button>
        <button class="tab-btn" data-tab="catalog">Catálogo POA</button>
      </nav>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <h1 id="pageTitle">Captura de actividad</h1>
          <div class="muted">Los campos derivados vienen de la tabla Hoja1 del Excel.</div>
        </div>
        <button class="btn secondary" id="clearAllBtn">Limpiar registros demo</button>
      </div>

      <div id="capture" class="tab">
        <div class="grid">
          <section>
            <h2>Datos del reporte</h2>
            <form id="reportForm">
              <div class="fields">
                <label>Empleado
                  <input name="employee" required placeholder="Nombre completo" />
                </label>
                <label>Sección
                  <input name="section" required placeholder="Ej. Conservación" />
                </label>
                <label>Cargo / puesto
                  <input name="position" placeholder="Ej. Restaurador Perito" />
                </label>
                <label>Correo institucional
                  <input name="email" type="email" placeholder="usuario@institucion.gob.mx" />
                </label>
                <label class="span-2">Actividad POA
                  <select name="poaActivity" required id="poaActivity"></select>
                </label>
                <label class="span-2">Actividad que realizó
                  <textarea name="activityDone" required placeholder="Describa la actividad realizada"></textarea>
                </label>
                <label>Fecha de ejecución
                  <input name="executionDate" type="date" required />
                </label>
                <label>Planeación
                  <select name="planning">
                    <option value="Sí">Sí</option>
                    <option value="No">No</option>
                  </select>
                </label>
                <label>Planeado anual
                  <input name="annualPlan" type="number" min="0" step="1" />
                </label>
                <label>Trimestre
                  <select name="quarter">
                    <option>1er Trimestre</option>
                    <option>2do Trimestre</option>
                    <option>3er Trimestre</option>
                    <option>4to Trimestre</option>
                  </select>
                </label>
                <label>Cantidad realizada
                  <input name="quantity" type="number" min="0" step="1" value="1" />
                </label>
                <label>Personal que participa
                  <input name="participants" placeholder="Personas o áreas participantes" />
                </label>
                <label class="span-2">Resumen de intervención
                  <textarea name="summary" maxlength="1800" placeholder="Máximo sugerido: 300 palabras"></textarea>
                </label>
                <label class="span-2">Evidencia fotográfica
                  <input name="photos" id="photos" type="file" accept="image/*" multiple />
                </label>
              </div>
              <div class="autofill" id="autofill"></div>
              <div class="photo-grid" id="photoPreview"></div>
              <div class="actions">
                <button class="btn" type="submit">Guardar reporte</button>
                <button class="btn warning" type="button" id="previewBtn">Vista PDF individual</button>
              </div>
            </form>
          </section>
          <div class="panel">
            <h2>Registros recientes</h2>
            <div class="report-list" id="recentReports"></div>
          </div>
        </div>
      </div>

      <div id="reports" class="tab hidden">
        <section>
          <h2>Reportes individuales</h2>
          <div class="report-list" id="allReports"></div>
        </section>
      </div>

      <div id="consolidated" class="tab hidden">
        <section>
          <h2>Consolidado por sección</h2>
          <div class="fields">
            <label>Sección
              <select id="sectionFilter"></select>
            </label>
            <label>Periodo
              <input id="periodName" value="Periodo actual" />
            </label>
          </div>
          <div class="actions">
            <button class="btn" id="printConsolidatedBtn">Generar PDF consolidado</button>
          </div>
          <div id="consolidatedSummary" style="margin-top:16px;"></div>
        </section>
      </div>

      <div id="catalog" class="tab hidden">
        <section>
          <h2>Catálogo importado del Excel</h2>
          <div class="muted" style="margin-bottom:12px;">{len(activities)} actividades POA disponibles.</div>
          <div style="overflow:auto;">
            <table id="catalogTable"></table>
          </div>
        </section>
      </div>
    </main>
  </div>

  <div id="printArea"></div>

  <script>
    const POA_CATALOG = {json.dumps(activities, ensure_ascii=False)};
    const STORAGE_KEY = 'poa_reportes_demo_v1';
    let currentPhotos = [];

    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => Array.from(document.querySelectorAll(selector));
    const fields = ['Unidad de Medida', 'Programa Operativo', 'Eje', 'Línea de acción ENC', 'Eje estratégico ENC'];

    function getReports() {{
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    }}

    function saveReports(reports) {{
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reports));
      renderReports();
    }}

    function selectedCatalog() {{
      const name = $('#poaActivity').value;
      return POA_CATALOG.find(item => item['Actividad POA'] === name) || POA_CATALOG[0];
    }}

    function fillActivities() {{
      $('#poaActivity').innerHTML = '<option value="">Seleccione una actividad</option>' +
        POA_CATALOG.map(item => `<option>${{escapeHtml(item['Actividad POA'])}}</option>`).join('');
      renderCatalog();
    }}

    function renderAutofill() {{
      const item = selectedCatalog();
      $('#autofill').innerHTML = fields.map(field => `
        <div class="auto-item">
          <b>${{field}}</b>
          <span>${{escapeHtml(item?.[field] ?? '')}}</span>
        </div>
      `).join('');
    }}

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }}[ch]));
    }}

    function formData() {{
      const form = new FormData($('#reportForm'));
      const catalog = selectedCatalog();
      return {{
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        employee: form.get('employee'),
        section: form.get('section'),
        position: form.get('position'),
        email: form.get('email'),
        poaActivity: form.get('poaActivity'),
        activityDone: form.get('activityDone'),
        executionDate: form.get('executionDate'),
        planning: form.get('planning'),
        annualPlan: form.get('annualPlan'),
        quarter: form.get('quarter'),
        quantity: Number(form.get('quantity') || 0),
        participants: form.get('participants'),
        summary: form.get('summary'),
        auto: Object.fromEntries(fields.map(field => [field, catalog?.[field] ?? ''])),
        photos: currentPhotos
      }};
    }}

    function readPhotos(files) {{
      currentPhotos = [];
      $('#photoPreview').innerHTML = '';
      Array.from(files).slice(0, 6).forEach(file => {{
        const reader = new FileReader();
        reader.onload = () => {{
          currentPhotos.push(reader.result);
          renderPhotos();
        }};
        reader.readAsDataURL(file);
      }});
    }}

    function renderPhotos() {{
      $('#photoPreview').innerHTML = currentPhotos.map(src => `<img src="${{src}}" alt="Evidencia">`).join('');
    }}

    function reportCard(report) {{
      return `
        <div class="report-card">
          <strong>${{escapeHtml(report.employee)}} · ${{escapeHtml(report.section)}}</strong>
          <div class="mini">${{escapeHtml(report.executionDate)}} · ${{escapeHtml(report.auto['Unidad de Medida'])}}</div>
          <div class="mini">${{escapeHtml(report.poaActivity)}}</div>
          <div class="actions">
            <button class="btn warning" onclick="printIndividual('${{report.id}}')">PDF individual</button>
            <button class="btn danger" onclick="deleteReport('${{report.id}}')">Eliminar</button>
          </div>
        </div>
      `;
    }}

    function renderReports() {{
      const reports = getReports().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
      $('#recentReports').innerHTML = reports.slice(0, 5).map(reportCard).join('') || '<div class="muted">Sin reportes guardados.</div>';
      $('#allReports').innerHTML = reports.map(reportCard).join('') || '<div class="muted">Sin reportes guardados.</div>';
      renderSectionFilter(reports);
      renderConsolidated();
    }}

    function renderSectionFilter(reports) {{
      const sections = [...new Set(reports.map(r => r.section).filter(Boolean))].sort();
      $('#sectionFilter').innerHTML = sections.map(s => `<option>${{escapeHtml(s)}}</option>`).join('');
    }}

    function deleteReport(id) {{
      saveReports(getReports().filter(r => r.id !== id));
    }}

    function renderConsolidated() {{
      const section = $('#sectionFilter').value;
      const reports = getReports().filter(r => !section || r.section === section);
      const byEmployee = new Map();
      reports.forEach(r => byEmployee.set(r.employee, (byEmployee.get(r.employee) || 0) + r.quantity));
      $('#consolidatedSummary').innerHTML = `
        <table>
          <thead><tr><th>Empleado</th><th>Reportes</th><th>Total realizado</th></tr></thead>
          <tbody>${{[...byEmployee.entries()].map(([employee, total]) => `
            <tr><td>${{escapeHtml(employee)}}</td><td>${{reports.filter(r => r.employee === employee).length}}</td><td>${{total}}</td></tr>
          `).join('') || '<tr><td colspan="3">Sin datos para esta sección.</td></tr>'}}</tbody>
        </table>
      `;
    }}

    function renderCatalog() {{
      const headers = ['Actividad POA', ...fields];
      $('#catalogTable').innerHTML = `
        <thead><tr>${{headers.map(h => `<th>${{h}}</th>`).join('')}}</tr></thead>
        <tbody>${{POA_CATALOG.map(item => `<tr>${{headers.map(h => `<td>${{escapeHtml(item[h])}}</td>`).join('')}}</tr>`).join('')}}</tbody>
      `;
    }}

    function individualHtml(report) {{
      const autoRows = fields.map(field => `<div class="print-box"><b>${{field}}:</b><br>${{escapeHtml(report.auto[field])}}</div>`).join('');
      const photos = report.photos.map(src => `<img src="${{src}}" alt="Evidencia">`).join('');
      return `
        <h1>Reporte individual de actividad POA</h1>
        <div class="print-meta">
          <div class="print-box"><b>Empleado:</b><br>${{escapeHtml(report.employee)}}</div>
          <div class="print-box"><b>Sección:</b><br>${{escapeHtml(report.section)}}</div>
          <div class="print-box"><b>Cargo:</b><br>${{escapeHtml(report.position)}}</div>
          <div class="print-box"><b>Fecha:</b><br>${{escapeHtml(report.executionDate)}}</div>
          <div class="print-box"><b>Correo:</b><br>${{escapeHtml(report.email)}}</div>
          <div class="print-box"><b>${{escapeHtml(report.quarter)}}:</b><br>${{report.quantity}}</div>
          ${{autoRows}}
        </div>
        <h2>Actividad POA</h2>
        <p>${{escapeHtml(report.poaActivity)}}</p>
        <h2>Actividad realizada</h2>
        <p>${{escapeHtml(report.activityDone)}}</p>
        <h2>Resumen de intervención</h2>
        <p>${{escapeHtml(report.summary)}}</p>
        <h2>Personal que participa</h2>
        <p>${{escapeHtml(report.participants)}}</p>
        <h2>Evidencia fotográfica</h2>
        <div>${{photos || 'Sin fotografías adjuntas.'}}</div>
      `;
    }}

    function printIndividual(id) {{
      const report = getReports().find(r => r.id === id) || formData();
      $('#printArea').innerHTML = individualHtml(report);
      window.print();
    }}

    function printConsolidated() {{
      const section = $('#sectionFilter').value;
      const period = $('#periodName').value;
      const reports = getReports().filter(r => !section || r.section === section);
      const rows = reports.map(r => `
        <tr>
          <td>${{escapeHtml(r.employee)}}</td>
          <td>${{escapeHtml(r.executionDate)}}</td>
          <td>${{escapeHtml(r.poaActivity)}}</td>
          <td>${{escapeHtml(r.auto['Unidad de Medida'])}}</td>
          <td>${{escapeHtml(r.auto['Programa Operativo'])}}</td>
          <td>${{r.quantity}}</td>
        </tr>
      `).join('');
      $('#printArea').innerHTML = `
        <h1>Consolidado de actividades POA</h1>
        <div class="print-meta">
          <div class="print-box"><b>Sección:</b><br>${{escapeHtml(section || 'Todas')}}</div>
          <div class="print-box"><b>Periodo:</b><br>${{escapeHtml(period)}}</div>
          <div class="print-box"><b>Total de reportes:</b><br>${{reports.length}}</div>
          <div class="print-box"><b>Total realizado:</b><br>${{reports.reduce((sum, r) => sum + Number(r.quantity || 0), 0)}}</div>
        </div>
        <table>
          <thead><tr><th>Empleado</th><th>Fecha</th><th>Actividad POA</th><th>Unidad</th><th>Programa</th><th>Cantidad</th></tr></thead>
          <tbody>${{rows || '<tr><td colspan="6">Sin reportes para consolidar.</td></tr>'}}</tbody>
        </table>
      `;
      window.print();
    }}

    $$('.tab-btn').forEach(button => button.addEventListener('click', () => {{
      $$('.tab-btn').forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      $$('.tab').forEach(tab => tab.classList.add('hidden'));
      $('#' + button.dataset.tab).classList.remove('hidden');
      $('#pageTitle').textContent = button.textContent;
      renderConsolidated();
    }}));

    $('#poaActivity').addEventListener('change', renderAutofill);
    $('#photos').addEventListener('change', (event) => readPhotos(event.target.files));
    $('#reportForm').addEventListener('submit', (event) => {{
      event.preventDefault();
      const reports = getReports();
      reports.push(formData());
      saveReports(reports);
      $('#reportForm').reset();
      currentPhotos = [];
      renderPhotos();
      renderAutofill();
    }});
    $('#previewBtn').addEventListener('click', () => printIndividual(null));
    $('#sectionFilter').addEventListener('change', renderConsolidated);
    $('#printConsolidatedBtn').addEventListener('click', printConsolidated);
    $('#clearAllBtn').addEventListener('click', () => {{
      if (confirm('¿Limpiar los registros guardados en este prototipo?')) saveReports([]);
    }});

    fillActivities();
    renderAutofill();
    renderReports();
  </script>
</body>
</html>
"""

(output_dir / "index.html").write_text(html, encoding="utf-8")
print(output_dir / "index.html")
