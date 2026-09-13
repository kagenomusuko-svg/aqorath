"""Local browser adapter for V1-10 period and annual closing."""

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from . import period_surface_application as _periods
from .web_surface import app


def _error(exc):
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/periods", response_class=HTMLResponse)
def period_page():
    return HTMLResponse(PERIOD_HTML)


@app.get("/api/periods/{year}")
def periods(year: int):
    try:
        return _periods.list_period_surface(year)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/periods/years/{year}")
def open_year(year: int):
    try:
        return _periods.open_period_surface_year(year)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/periods/{period_id}/close")
def close_period(period_id: int):
    try:
        return _periods.close_period_surface(period_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/periods/years/{year}/close")
def close_year(year: int, payload: dict | None = None):
    try:
        payload = {} if payload is None else payload
        return _periods.close_fiscal_year_surface(year, payload.get("backup_root"))
    except Exception as exc:
        raise _error(exc) from exc


PERIOD_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aqorath · Períodos</title><style>
:root{--ink:#17211f;--muted:#64706d;--line:#d9dfdd;--paper:#f5f7f6;--card:#fff;--accent:#1f5148;--soft:#e9f0ee;--danger:#8a2f2f}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}header{background:var(--accent);color:#fff;padding:20px 24px}main{max-width:950px;margin:auto;padding:22px}.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:17px;margin-bottom:14px}input{padding:9px;border:1px solid #bcc6c3;border-radius:8px}button{border:0;border-radius:8px;padding:9px 13px;cursor:pointer;margin:4px}.primary{background:var(--accent);color:#fff}.secondary{background:var(--soft)}.danger{background:#f5e7e7;color:var(--danger)}.muted{color:var(--muted)}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:8px;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;background:#f1f4f3;padding:10px;border-radius:8px;overflow:auto}</style></head><body><header><h1>Períodos contables</h1><div>Apertura, bloqueo mensual y cierre anual con respaldo previo</div></header><main><section class="card"><label>Año <input id="year" type="number" min="1" max="9999"></label><button class="secondary" id="load">Consultar</button><button class="secondary" id="open">Abrir año si aún no existe</button><p class="muted">Cerrar un mes impide nuevas contabilizaciones en ese período. El cierre anual crea un respaldo antes de mover resultados.</p></section><section class="card"><table><thead><tr><th>Período</th><th>Fechas</th><th>Estado</th><th>Acción</th></tr></thead><tbody id="rows"></tbody></table></section><section class="card"><button class="danger" id="closeYear">Cerrar ejercicio anual</button><pre id="result"></pre></section></main><script>
const $=id=>document.getElementById(id);$('year').value=new Date().getFullYear();async function request(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const b=await r.json().catch(()=>({detail:r.statusText}));if(!r.ok)throw new Error(b.detail||'Error');return b}async function load(){try{const y=Number($('year').value),r=await request(`/api/periods/${y}`);$('result').textContent=`Ejercicio ${r.year}: ${r.state}`;$('rows').replaceChildren(...r.periods.map(p=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${p.id}</td><td>${p.start} — ${p.end}</td><td>${p.state}</td><td></td>`;const b=document.createElement('button');b.textContent=p.state==='closed'?'Cerrado':'Cerrar mes';b.className=p.state==='closed'?'secondary':'danger';b.disabled=p.state==='closed';b.onclick=async()=>{if(!confirm(`¿Cerrar el período ${p.id}? Las nuevas pólizas con esas fechas serán rechazadas.`))return;await request(`/api/periods/${p.id}/close`,{method:'POST'});await load()};tr.lastChild.appendChild(b);return tr}))}catch(e){$('result').textContent=e.message}}$('load').onclick=load;$('open').onclick=async()=>{try{await request(`/api/periods/years/${Number($('year').value)}`,{method:'POST'});await load()}catch(e){$('result').textContent=e.message}};$('closeYear').onclick=async()=>{const y=Number($('year').value);if(!confirm(`¿Cerrar definitivamente el ejercicio ${y}? Aqorath creará un respaldo antes del cierre.`))return;try{const r=await request(`/api/periods/years/${y}/close`,{method:'POST',body:'{}'});$('result').textContent=JSON.stringify(r,null,2);await load()}catch(e){$('result').textContent=e.message}};load();
</script></body></html>'''


__all__ = ["PERIOD_HTML"]
