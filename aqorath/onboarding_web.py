"""AQR-015 guided onboarding presentation on the canonical localhost app."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .onboarding_presentation_controller import LocalOnboardingController
from .web_surface import app


controller = LocalOnboardingController()


ONBOARDING_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aqorath — Configuración inicial</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#17201f;background:#f5f7f6}body{margin:0}.wrap{max-width:940px;margin:auto;padding:28px 18px 60px}.card{background:#fff;border:1px solid #dce4e1;border-radius:14px;padding:20px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}label{display:block;font-weight:650;margin:8px 0 4px}input,select,button{font:inherit}input,select{width:100%;padding:10px;border:1px solid #bcc6c3;border-radius:8px;background:#fff}button{border:0;border-radius:8px;background:#245e56;color:#fff;padding:11px 15px;font-weight:650;cursor:pointer}.muted{color:#60706d}.notice{padding:12px;border-radius:8px;background:#e9f0ee}.error{background:#f7e8e8;color:#8b2f2f}.hidden{display:none}.roles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}@media(max-width:720px){.grid,.roles{grid-template-columns:1fr}}
</style></head><body><main class="wrap">
<a href="/">← Aqorath</a><h1>Configuración inicial</h1>
<p class="muted">Declara la entidad, vigencia fiscal y qué cuentas representan cada función. Aqorath no infiere régimen fiscal ni pide Debe/Haber en la operación ordinaria.</p>
<div id="configured" class="notice hidden"></div><div id="error" class="notice error hidden"></div>
<form id="form" class="hidden">
<section class="card"><h2>Entidad</h2><div class="grid">
<div><label>Nombre</label><input id="name" required></div><div><label>RFC (si aplica)</label><input id="rfc"></div>
<div><label>Personalidad jurídica</label><select id="legalPersonality"><option value="persona_fisica">Persona física</option><option value="persona_moral">Persona moral</option></select></div>
<div><label>Forma jurídica</label><input id="legalForm" required placeholder="persona física con actividad empresarial, asociación civil…"></div>
<div><label>Finalidad económica</label><select id="economicPurpose"><option value="lucrativo">Lucrativa</option><option value="no_lucrativo">No lucrativa</option></select></div>
<div><label>Inicio efectivo de actividad</label><input id="activityStart" type="date" required></div>
</div><label><input id="donorAuthorized" type="checkbox" style="width:auto"> Donataria autorizada declarada</label></section>
<section class="card"><h2>Perfil fiscal explícito</h2><p class="muted">Registrar un perfil no certifica cumplimiento ni autorización; sólo conserva lo declarado con vigencia.</p><div class="grid">
<div><label>Jurisdicción</label><input id="jurisdiction" value="MX" required></div><div><label>Régimen fiscal / código declarado</label><input id="regime" required></div>
<div><label>Vigente desde</label><input id="fiscalFrom" type="date" required></div><div><label>Vigente hasta (opcional)</label><input id="fiscalTo" type="date"></div>
</div></section>
<section class="card"><h2>Funciones contables básicas</h2><p class="muted">Elige por nombre; los códigos son identificadores internos del catálogo gobernado. Las seis funciones marcadas son necesarias para los recorridos comunes V1 de venta, gasto y crédito.</p><div id="roles" class="roles"></div></section>
<button type="submit">Guardar configuración inicial</button></form>
</main><script>
const q=id=>document.getElementById(id);let state=null;
function accountOptions(role){const suggested=new Set(role.suggested_codes||[]);const rows=[...state.accounts].sort((a,b)=>{const sa=suggested.has(a.code)?0:1,sb=suggested.has(b.code)?0:1;return sa-sb||a.name.localeCompare(b.name)});return '<option value="">Selecciona una cuenta…</option>'+rows.map(a=>`<option value="${a.code}">${a.name} · ${a.type||''} · ${a.nature||''}</option>`).join('')}
function render(){if(state.configured){q('configured').classList.remove('hidden');q('configured').innerHTML=`Configuración activa: <strong>${state.entity.name}</strong>. <a href="/">Continuar a Aqorath</a>`;q('form').classList.add('hidden');return}q('form').classList.remove('hidden');q('roles').innerHTML=state.binding_roles.filter(r=>r.required).map(r=>`<div><label>${r.label}${r.required?' *':''}</label><select data-role="${r.key}" ${r.required?'required':''}>${accountOptions(r)}</select></div>`).join('')}
async function load(){try{const r=await fetch('/api/onboarding');if(!r.ok)throw new Error((await r.json()).detail||r.statusText);state=await r.json();render()}catch(e){q('error').textContent=e.message;q('error').classList.remove('hidden')}}
q('economicPurpose').onchange=load;
q('form').onsubmit=async e=>{e.preventDefault();q('error').classList.add('hidden');const bindings={};document.querySelectorAll('[data-role]').forEach(x=>bindings[x.dataset.role]=x.value);const payload={name:q('name').value,rfc:q('rfc').value||null,legal_personality:q('legalPersonality').value,legal_form:q('legalForm').value,economic_purpose:q('economicPurpose').value,is_donor_authorized:q('donorAuthorized').checked,special_capabilities:[],modules_enabled:[],activity_start:q('activityStart').value,bindings,fiscal_profile:{jurisdiction:q('jurisdiction').value,fiscal_regime_code:q('regime').value,tax_characteristics:[],effective_from:q('fiscalFrom').value,effective_to:q('fiscalTo').value||null}};try{const r=await fetch('/api/onboarding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const v=await r.json();if(!r.ok)throw new Error(v.detail||r.statusText);state=v;render()}catch(err){q('error').textContent=err.message;q('error').classList.remove('hidden')}};
load();
</script></body></html>'''


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_index():
    return HTMLResponse(ONBOARDING_HTML)


@app.get("/api/onboarding")
def onboarding_status():
    try:
        return controller.status()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/onboarding")
def onboarding_configure(payload: dict):
    try:
        return controller.configure(payload)
    except Exception as exc:
        raise _error(exc) from exc


__all__ = ["app", "ONBOARDING_HTML", "controller"]
