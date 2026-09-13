"""Loopback browser routes for existing OSC Program identity."""

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .program_presentation_controller import ProgramPresentationController
from .web_surface import app


controller = ProgramPresentationController()


def _error(exc):
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/programs", response_class=HTMLResponse)
def program_page():
    return HTMLResponse(PROGRAM_HTML)


@app.get("/api/osc/programs")
def programs():
    try:
        return controller.programs()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/programs")
def create_program(payload: dict):
    try:
        return controller.create_program(payload)
    except Exception as exc:
        raise _error(exc) from exc


PROGRAM_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Programas · Aqorath</title><style>
body{margin:0;background:#f5f7f6;color:#17211f;font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:#1f5148;color:#fff;padding:22px 28px}main{max-width:860px;margin:auto;padding:24px}.card{background:#fff;border:1px solid #d9dfdd;border-radius:12px;padding:18px;margin-bottom:16px}label{display:block;font-weight:650;margin:12px 0 5px}input,textarea,button{font:inherit}input,textarea{width:100%;padding:10px;border:1px solid #bcc6c3;border-radius:8px;box-sizing:border-box}button{margin-top:14px;padding:10px 14px;border:0;border-radius:8px;background:#1f5148;color:#fff;cursor:pointer}.muted{color:#64706d}.error{color:#8a2f2f}.program{padding:11px 0;border-bottom:1px solid #e3e7e6}.program:last-child{border-bottom:0}a{color:#1f5148}</style></head>
<body><header><h1>Programas</h1><p>Identidades de gestión para organizar la misma contabilidad OSC.</p></header><main>
<p><a href="/">← Volver a Aqorath</a></p><section class="card"><h2>Crear programa</h2><p class="muted">Crear un programa no genera pólizas, saldos ni una contabilidad separada.</p>
<label for="name">Nombre</label><input id="name" autocomplete="off"><label for="description">Descripción opcional</label><textarea id="description" rows="3"></textarea><label for="budget">Presupuesto de referencia opcional</label><input id="budget" inputmode="decimal" placeholder="0.00"><button id="create">Guardar programa</button><p id="error" class="error"></p></section>
<section class="card"><h2>Programas disponibles</h2><div id="list" class="muted">Cargando…</div></section></main><script>
const q=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opt={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opt});const body=await r.text();if(!r.ok){let d=body;try{d=JSON.parse(body).detail}catch{}throw new Error(d)}return body?JSON.parse(body):null}
async function load(){try{const rows=await api('/api/osc/programs');q('list').className='';q('list').innerHTML=rows.length?rows.map(x=>`<div class="program"><strong>${esc(x.name)}</strong>${x.description?`<div>${esc(x.description)}</div>`:''}<div class="muted">Presupuesto: ${x.budget===null?'Sin presupuesto':esc(x.budget)}</div></div>`).join(''):'Aún no hay programas.'}catch(e){q('list').className='error';q('list').textContent=e.message}}
q('create').onclick=async()=>{q('error').textContent='';try{await api('/api/osc/programs',{method:'POST',body:JSON.stringify({name:q('name').value,description:q('description').value||null,budget:q('budget').value||null})});q('name').value='';q('description').value='';q('budget').value='';await load()}catch(e){q('error').textContent=e.message}};load();
</script></body></html>'''


__all__ = ["app", "PROGRAM_HTML"]
