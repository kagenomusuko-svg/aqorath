from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}: {old[:80]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1))


# reporting_surface_application: expose human dimension choices without technical ids.
path = "aqorath/reporting_surface_application.py"
replace_once(
    path,
    "from . import entity_repository as _entities\n",
    "from . import analytical_dimension_repository as _analytics\nfrom . import entity_repository as _entities\n",
)
replace_once(
    path,
    "def _active_entity_id():\n    with _storage.get_session() as session:\n        entity = _entities.load_active_entity(session)\n        if entity is None or entity.id is None:\n            raise LookupError(\"active Entity not configured\")\n        return entity.id\n\n\n",
    "def _active_entity_id():\n    with _storage.get_session() as session:\n        entity = _entities.load_active_entity(session)\n        if entity is None or entity.id is None:\n            raise LookupError(\"active Entity not configured\")\n        return entity.id\n\n\ndef list_reporting_dimensions():\n    \"\"\"Return human choices for the active Entity; ids stay server-side.\"\"\"\n    with _storage.get_session() as session:\n        entity = _entities.load_active_entity(session)\n        if entity is None or entity.id is None:\n            raise LookupError(\"active Entity not configured\")\n        return [\n            {\"key\": item.key, \"name\": item.name}\n            for item in _analytics.list_analytical_dimensions(session, entity.id)\n        ]\n\n\n",
)

# Controller: read-only reporting methods, outside accounting confirmation tokens.
path = "aqorath/presentation_controller.py"
replace_once(
    path,
    "from . import inventory_surface_application as _inventory_v1\nfrom . import surface_application as _application\n",
    "from . import inventory_surface_application as _inventory_v1\nfrom . import reporting_surface_application as _reporting\nfrom . import surface_application as _application\n",
)
replace_once(
    path,
    '            "inventory": {"enabled": inventory_enabled, "products": inventory_products},\n',
    '            "inventory": {"enabled": inventory_enabled, "products": inventory_products},\n            "reporting": _reporting.list_reporting_surface_catalog(),\n            "reporting_dimensions": _reporting.list_reporting_dimensions(),\n',
)
replace_once(
    path,
    "    def donation_options(self):\n",
    "    def reporting_catalog(self):\n        return _reporting.list_reporting_surface_catalog()\n\n    def reporting_dimensions(self):\n        return _reporting.list_reporting_dimensions()\n\n    def generate_financial_reports(self, payload):\n        return _reporting.generate_financial_period_surface(payload)[\"common\"]\n\n    def professional_financial_reports(self, payload):\n        return _reporting.professional_financial_period_surface(payload)\n\n    def generate_professional_detail_reports(self, payload):\n        return _reporting.generate_professional_detail_surface(payload)[\"common\"]\n\n    def professional_detail_reports(self, payload):\n        return _reporting.professional_detail_surface(payload)\n\n    def generate_analytical_report(self, payload):\n        return _reporting.generate_analytical_surface(payload)[\"common\"]\n\n    def professional_analytical_report(self, payload):\n        return _reporting.generate_analytical_surface(payload)[\"professional\"]\n\n    def generate_inventory_valuation_report(self, payload):\n        return _reporting.generate_inventory_valuation_surface(payload)[\"common\"]\n\n    def professional_inventory_valuation_report(self, payload):\n        return _reporting.generate_inventory_valuation_surface(payload)[\"professional\"]\n\n    def generate_fiscal_evidence_report(self, payload):\n        return _reporting.generate_fiscal_evidence_surface(payload)[\"common\"]\n\n    def professional_fiscal_evidence_report(self, payload):\n        return _reporting.generate_fiscal_evidence_surface(payload)[\"professional\"]\n\n    def donation_options(self):\n",
)

# HTTP: read-only report routes delegate only to controller.
path = "aqorath/web_surface.py"
replace_once(
    path,
    "@app.get(\"/api/osc/donations\")\ndef donations():\n",
    "@app.get(\"/api/reports/catalog\")\ndef reporting_catalog():\n    try:\n        return controller.reporting_catalog()\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.get(\"/api/reports/dimensions\")\ndef reporting_dimensions():\n    try:\n        return controller.reporting_dimensions()\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/packages/financial\")\ndef generate_financial_reports(payload: dict):\n    try:\n        return controller.generate_financial_reports(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/packages/financial/professional\")\ndef professional_financial_reports(payload: dict):\n    try:\n        return controller.professional_financial_reports(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/packages/professional-detail\")\ndef generate_professional_detail_reports(payload: dict):\n    try:\n        return controller.generate_professional_detail_reports(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/packages/professional-detail/professional\")\ndef professional_detail_reports(payload: dict):\n    try:\n        return controller.professional_detail_reports(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/analytical\")\ndef generate_analytical_report(payload: dict):\n    try:\n        return controller.generate_analytical_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/analytical/professional\")\ndef professional_analytical_report(payload: dict):\n    try:\n        return controller.professional_analytical_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/inventory-valuation\")\ndef generate_inventory_valuation_report(payload: dict):\n    try:\n        return controller.generate_inventory_valuation_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/inventory-valuation/professional\")\ndef professional_inventory_valuation_report(payload: dict):\n    try:\n        return controller.professional_inventory_valuation_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/fiscal-evidence\")\ndef generate_fiscal_evidence_report(payload: dict):\n    try:\n        return controller.generate_fiscal_evidence_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.post(\"/api/reports/fiscal-evidence/professional\")\ndef professional_fiscal_evidence_report(payload: dict):\n    try:\n        return controller.professional_fiscal_evidence_report(payload)\n    except Exception as exc:\n        raise _error(exc) from exc\n\n\n@app.get(\"/api/osc/donations\")\ndef donations():\n",
)

# Browser common/pro report surface.
path = "aqorath/web_assets.py"
common_marker = '<div id="oscNotice" class="notice hidden"></div><pre id="oscBalanceOutput">Selecciona un fondo y una fecha.</pre></div>\n</div></section>\n<section id="professional" class="view">'
common_card = '''<div id="oscNotice" class="notice hidden"></div><pre id="oscBalanceOutput">Selecciona un fondo y una fecha.</pre></div>
<div class="card span12" id="reportingFlow"><h2>Reportes</h2><p class="muted">Elige el producto que necesitas. Aqorath consulta las mismas autoridades contables; generar un reporte no modifica tu contabilidad.</p><div class="toolbar"><div><label for="reportIntent">¿Qué necesitas?</label><select id="reportIntent"><option value="financial">Paquete financiero</option><option value="analytical">Actividad por programa o dimensión</option><option value="inventory">Valuación de inventario</option><option value="fiscal">Evidencia fiscal y documental</option></select></div><div><label for="reportFormat">Formato</label><select id="reportFormat"><option value="json">Vista en pantalla</option><option value="xlsx">Excel</option></select></div></div><div class="toolbar"><div><label for="reportFrom">Desde</label><input id="reportFrom" type="date"></div><div><label for="reportTo">Hasta</label><input id="reportTo" type="date"></div><div><label for="reportAsOf">Al</label><input id="reportAsOf" type="date"></div><div id="reportDimensionWrap" class="hidden"><label for="reportDimension">Programa / dimensión</label><select id="reportDimension"></select></div></div><div class="actions"><button class="primary" id="generateReport">Generar reporte</button><button class="secondary hidden" id="downloadReport">Descargar Excel</button></div><div id="reportError" class="notice error hidden"></div><pre id="reportOutput">Aún no has generado un reporte.</pre></div>
</div></section>
<section id="professional" class="view">'''
replace_once(path, common_marker, common_card)
pro_marker = '<div class="card span12"><h3>Trazabilidad profesional de fondos</h3><div class="toolbar"><div><label for="professionalFundId">Fondo</label><input id="professionalFundId" inputmode="numeric"></div><div><label for="professionalFundDate">Fecha de corte</label><input id="professionalFundDate" type="date"></div><button class="secondary" id="loadFundTrace">Consultar trazabilidad</button></div><pre id="fundTraceOutput">Sin consulta.</pre></div>\n</div></section>\n</main>'
pro_card = '''<div class="card span12"><h3>Trazabilidad profesional de fondos</h3><div class="toolbar"><div><label for="professionalFundId">Fondo</label><input id="professionalFundId" inputmode="numeric"></div><div><label for="professionalFundDate">Fecha de corte</label><input id="professionalFundDate" type="date"></div><button class="secondary" id="loadFundTrace">Consultar trazabilidad</button></div><pre id="fundTraceOutput">Sin consulta.</pre></div>
<div class="card span12"><h3>Reportes · trazabilidad profesional</h3><p class="muted">Reconstruye definición, solicitud, Entity, autoridades fuente y cifras del último reporte generado.</p><div class="actions"><button class="secondary" id="loadProfessionalReport">Ver trazabilidad del último reporte</button><button class="secondary" id="generateProfessionalDetail">Generar diario + mayor + balanza</button></div><pre id="professionalReportOutput">Sin reporte seleccionado.</pre></div>
</div></section>
</main>'''
replace_once(path, pro_marker, pro_card)
js_marker = "init().catch(e=>showError('commonError',e));\n\nconst donationState="
js = '''const reportState={professionalPath:null,payload:null,download:null};
function reportPayload(){const intent=$('reportIntent').value;const format=$('reportFormat').value;if(intent==='inventory')return{as_of_date:$('reportAsOf').value,format};const base={from_date:$('reportFrom').value,to_date:$('reportTo').value,format};if(intent==='analytical')base.dimension_key=$('reportDimension').value;return base}
function configureReportIntent(){const intent=$('reportIntent').value;$('reportDimensionWrap').classList.toggle('hidden',intent!=='analytical');const onlyJson=intent!=='financial';$('reportFormat').innerHTML=onlyJson?'<option value="json">Vista en pantalla</option>':'<option value="json">Vista en pantalla</option><option value="xlsx">Excel</option>';$('reportFrom').closest('div').classList.toggle('hidden',intent==='inventory');$('reportTo').closest('div').classList.toggle('hidden',intent==='inventory');$('reportAsOf').closest('div').classList.toggle('hidden',intent!=='inventory')}
function b64bytes(text){const raw=atob(text);const out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out}
async function initReporting(){const today=new Date().toISOString().slice(0,10);['reportFrom','reportTo','reportAsOf'].forEach(id=>$(id).value=today);const dims=await api('/api/reports/dimensions');$('reportDimension').innerHTML=dims.length?dims.map(d=>`<option value="${esc(d.key)}">${esc(d.name)}</option>`).join(''):'<option value="">Sin dimensiones configuradas</option>';configureReportIntent()}
$('reportIntent').onchange=configureReportIntent;
$('generateReport').onclick=async()=>{clearError('reportError');try{const intent=$('reportIntent').value,payload=reportPayload();let path,pro;if(intent==='financial'){path='/api/reports/packages/financial';pro=path+'/professional'}else if(intent==='analytical'){path='/api/reports/analytical';pro=path+'/professional'}else if(intent==='inventory'){path='/api/reports/inventory-valuation';pro=path+'/professional'}else{path='/api/reports/fiscal-evidence';pro=path+'/professional'}const out=await api(path,{method:'POST',body:JSON.stringify(payload)});reportState.professionalPath=pro;reportState.payload=payload;reportState.download=null;const shown={...out};if(shown.document_base64){reportState.download={bytes:b64bytes(shown.document_base64),type:shown.media_type||'application/octet-stream'};shown.document_base64='[archivo Excel listo para descargar]';$('downloadReport').classList.remove('hidden')}else $('downloadReport').classList.add('hidden');$('reportOutput').textContent=JSON.stringify(shown,null,2)}catch(e){showError('reportError',e)}};
$('downloadReport').onclick=()=>{if(!reportState.download)return;const blob=new Blob([reportState.download.bytes],{type:reportState.download.type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='aqorath-reporte.xlsx';a.click();URL.revokeObjectURL(url)};
$('loadProfessionalReport').onclick=async()=>{try{if(!reportState.professionalPath||!reportState.payload)throw new Error('Genera primero un reporte en la vista común.');const out=await api(reportState.professionalPath,{method:'POST',body:JSON.stringify(reportState.payload)});$('professionalReportOutput').textContent=JSON.stringify(out,null,2)}catch(e){showError('professionalError',e)}};
$('generateProfessionalDetail').onclick=async()=>{try{const payload={from_date:$('reportFrom').value,to_date:$('reportTo').value,format:'json'};const out=await api('/api/reports/packages/professional-detail/professional',{method:'POST',body:JSON.stringify(payload)});$('professionalReportOutput').textContent=JSON.stringify(out,null,2)}catch(e){showError('professionalError',e)}};
initReporting().catch(e=>showError('reportError',e));
init().catch(e=>showError('commonError',e));

const donationState='''
replace_once(path, js_marker, js)

print("AQR-013 surface patch applied")
