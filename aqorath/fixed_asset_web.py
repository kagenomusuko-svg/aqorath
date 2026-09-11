"""Local browser adapter for V1-08/V1-09 fixed-asset flows.

Imports the canonical web_surface app and registers routes on that same loopback-only
surface. Pending tokens are ephemeral confirmation state; durable truth remains in
SQLite through fixed_asset_surface_application and canonical authorities.
"""

import secrets

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from . import fixed_asset_surface_application as _assets
from .web_surface import app


_pending = {}


def _error(exc):
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


def _store(prepared):
    token = secrets.token_urlsafe(24)
    while token in _pending:
        token = secrets.token_urlsafe(24)
    _pending[token] = prepared
    return {"token": token, "preview": prepared.preview}


def _require(token):
    if type(token) is not str or not token:
        raise ValueError("preview token is required")
    try:
        return _pending[token]
    except KeyError as exc:
        raise LookupError("prepared fixed-asset decision not found") from exc


@app.get("/fixed-assets", response_class=HTMLResponse)
def fixed_asset_page():
    return HTMLResponse(FIXED_ASSET_HTML)


@app.get("/api/fixed-assets/options")
def fixed_asset_options():
    try:
        return _assets.list_fixed_asset_surface_options()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/fixed-assets")
def fixed_assets():
    try:
        return _assets.list_fixed_asset_surface_assets()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/fixed-assets")
def create_fixed_asset(payload: dict):
    try:
        return _assets.create_fixed_asset_surface(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/fixed-assets/{fixed_asset_id}/book-state")
def fixed_asset_book_state(fixed_asset_id: int, as_of: str | None = None):
    try:
        return _assets.load_fixed_asset_surface_book_state(fixed_asset_id, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/fixed-assets/acquisition/prepare")
def prepare_fixed_asset_acquisition(payload: dict):
    try:
        return _store(_assets.prepare_fixed_asset_acquisition_surface(payload))
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/fixed-assets/depreciation/prepare")
def prepare_fixed_asset_depreciation(payload: dict):
    try:
        return _store(_assets.prepare_fixed_asset_depreciation_surface(payload))
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/fixed-assets/decisions/{token}/professional-preview")
def fixed_asset_professional_preview(token: str):
    try:
        prepared = _require(token)
        if isinstance(prepared, _assets.PreparedFixedAssetAcquisitionSurface):
            return _assets.professional_fixed_asset_acquisition_preview(prepared)
        if isinstance(prepared, _assets.PreparedFixedAssetDepreciationSurface):
            return _assets.professional_fixed_asset_depreciation_preview(prepared)
        raise TypeError("unsupported fixed-asset prepared value")
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/fixed-assets/decisions/{token}/confirm")
def confirm_fixed_asset_decision(token: str):
    try:
        prepared = _require(token)
        if isinstance(prepared, _assets.PreparedFixedAssetAcquisitionSurface):
            result = _assets.confirm_fixed_asset_acquisition_surface(prepared)
        elif isinstance(prepared, _assets.PreparedFixedAssetDepreciationSurface):
            result = _assets.confirm_fixed_asset_depreciation_surface(prepared)
        else:
            raise TypeError("unsupported fixed-asset prepared value")
        del _pending[token]
        return result
    except Exception as exc:
        raise _error(exc) from exc


@app.delete("/api/fixed-assets/decisions/{token}")
def cancel_fixed_asset_decision(token: str):
    try:
        _require(token)
        del _pending[token]
        return {"cancelled": True}
    except Exception as exc:
        raise _error(exc) from exc


FIXED_ASSET_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aqorath · Activos fijos</title><style>
:root{--ink:#17211f;--muted:#64706d;--line:#d9dfdd;--paper:#f5f7f6;--card:#fff;--accent:#1f5148;--soft:#e9f0ee;--danger:#8a2f2f}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}header{background:var(--accent);color:#fff;padding:20px 24px}main{max-width:1050px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.card{grid-column:span 12;background:#fff;border:1px solid var(--line);border-radius:12px;padding:17px}.half{grid-column:span 6}label{display:block;font-weight:650;margin:9px 0 4px}input,select{width:100%;padding:9px;border:1px solid #bcc6c3;border-radius:8px;background:#fff}button{border:0;border-radius:8px;padding:10px 14px;cursor:pointer}.primary{background:var(--accent);color:#fff}.secondary{background:var(--soft)}.danger{background:#f5e7e7;color:var(--danger)}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.muted{color:var(--muted)}.notice{padding:10px 12px;border-radius:8px;background:var(--soft);margin-top:12px}.error{background:#f7e8e8;color:var(--danger)}.hidden{display:none}pre{white-space:pre-wrap;background:#f1f4f3;padding:10px;border-radius:8px;overflow:auto}@media(max-width:720px){.half{grid-column:span 12}}
</style></head><body><header><h1>Activos fijos</h1><div>Registro, adquisición, depreciación y valor en libros desde una sola verdad contable</div></header><main><div class="grid">
<section class="card"><h2>1. Registrar activo</h2><p class="muted">Describe el bien durable. Registrarlo no crea todavía una póliza de adquisición.</p><div class="grid"><div class="half"><label>Código</label><input id="code" placeholder="EQ-001"><label>Nombre</label><input id="name" placeholder="Computadora"><label>Fecha de adquisición</label><input id="acqDate" type="date"><label>Fecha en servicio</label><input id="serviceDate" type="date"></div><div class="half"><label>Costo</label><input id="cost" inputmode="decimal" placeholder="12000.00"><label>Valor residual</label><input id="residual" inputmode="decimal" value="0.00"><label>Vida útil (meses)</label><input id="life" type="number" min="1" value="12"><button class="secondary" id="create">Registrar activo</button></div></div></section>
<section class="card"><h2>2. Contabilizar adquisición</h2><div class="grid"><div class="half"><label>Activo</label><select id="asset"></select><label>Clase</label><select id="assetClass"></select></div><div class="half"><label>Cómo se pagó</label><select id="settlement"></select><button class="primary" id="prepareAcq">Revisar adquisición</button></div></div></section>
<section class="card"><h2>3. Reconocer depreciación</h2><div class="grid"><div class="half"><label>Período ordinal</label><input id="periodNumber" type="number" min="1" value="1"><label>Fecha de reconocimiento</label><input id="depDate" type="date"></div><div class="half"><p class="muted">Aqorath calcula el importe exacto desde costo, residual y vida útil; no capturas Debe/Haber.</p><button class="primary" id="prepareDep">Revisar depreciación</button></div></div></section>
<section class="card hidden" id="decision"><h2>Decisión preparada</h2><pre id="preview"></pre><div class="actions"><button class="secondary" id="professional">Ver reconstrucción profesional</button><button class="primary" id="confirm">Confirmar</button><button class="danger" id="cancel">Cancelar</button></div><pre id="professionalData" class="hidden"></pre></section>
<section class="card"><h2>Valor en libros</h2><button class="secondary" id="book">Consultar activo seleccionado</button><pre id="bookData"></pre></section><div id="error" class="card notice error hidden"></div>
</div></main><script>
let token=null;const $=id=>document.getElementById(id);async function request(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const b=await r.json().catch(()=>({detail:r.statusText}));if(!r.ok)throw new Error(b.detail||'Error');return b}function opt(v,t){const o=document.createElement('option');o.value=v;o.textContent=t;return o}function fail(e){$('error').textContent=e.message;$('error').classList.remove('hidden')}async function load(){const [assets,options]=await Promise.all([request('/api/fixed-assets'),request('/api/fixed-assets/options')]);$('asset').replaceChildren(...assets.map(x=>opt(x.id,`${x.code} · ${x.name} · valor ${x.carrying_value}`)));$('assetClass').replaceChildren(...options.asset_classes.map(x=>opt(x.key,x.label)));$('settlement').replaceChildren(...options.settlements.map(x=>opt(x.key,x.label)))}$('create').onclick=async()=>{try{await request('/api/fixed-assets',{method:'POST',body:JSON.stringify({code:$('code').value,name:$('name').value,acquisition_date:$('acqDate').value,in_service_date:$('serviceDate').value,acquisition_cost:$('cost').value,residual_value:$('residual').value,useful_life_months:Number($('life').value)})});await load()}catch(e){fail(e)}};async function prepare(url,payload){try{const r=await request(url,{method:'POST',body:JSON.stringify(payload)});token=r.token;$('preview').textContent=JSON.stringify(r.preview,null,2);$('professionalData').classList.add('hidden');$('decision').classList.remove('hidden')}catch(e){fail(e)}}$('prepareAcq').onclick=()=>prepare('/api/fixed-assets/acquisition/prepare',{fixed_asset_id:Number($('asset').value),asset_class:$('assetClass').value,settlement_method:$('settlement').value});$('prepareDep').onclick=()=>prepare('/api/fixed-assets/depreciation/prepare',{fixed_asset_id:Number($('asset').value),period_number:Number($('periodNumber').value),recognition_date:$('depDate').value});$('professional').onclick=async()=>{try{const r=await request(`/api/fixed-assets/decisions/${token}/professional-preview`);$('professionalData').textContent=JSON.stringify(r,null,2);$('professionalData').classList.remove('hidden')}catch(e){fail(e)}};$('confirm').onclick=async()=>{try{const r=await request(`/api/fixed-assets/decisions/${token}/confirm`,{method:'POST'});token=null;$('preview').textContent=JSON.stringify(r,null,2);await load()}catch(e){fail(e)}};$('cancel').onclick=async()=>{if(!token)return;await request(`/api/fixed-assets/decisions/${token}`,{method:'DELETE'});token=null;$('decision').classList.add('hidden')};$('book').onclick=async()=>{try{$('bookData').textContent=JSON.stringify(await request(`/api/fixed-assets/${Number($('asset').value)}/book-state`),null,2)}catch(e){fail(e)}};load().catch(fail);
</script></body></html>'''


__all__ = ["FIXED_ASSET_HTML"]
