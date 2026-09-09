"""Self-contained browser shell for the local AQR-005 surface.

No template engine is required. The browser receives only presentation contracts;
accounting rules remain entirely server-side in Application.
"""

APP_HTML = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aqorath</title>
<style>
:root{--ink:#17211f;--muted:#64706d;--line:#d9dfdd;--paper:#f5f7f6;--card:#fff;--accent:#1f5148;--soft:#e9f0ee;--danger:#8a2f2f}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:var(--accent);color:white;padding:22px 28px}header h1{margin:0;font-size:25px;letter-spacing:.02em}header p{margin:4px 0 0;opacity:.82}main{max-width:1120px;margin:0 auto;padding:24px}.tabs{display:flex;gap:8px;margin-bottom:18px}.tab{border:1px solid var(--line);background:white;border-radius:8px;padding:9px 14px;cursor:pointer}.tab.active{background:var(--ink);border-color:var(--ink);color:white}.view{display:none}.view.active{display:block}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:0 1px 2px #00000008}.span7{grid-column:span 7}.span5{grid-column:span 5}.span12{grid-column:span 12}h2,h3{margin-top:0}label{display:block;font-weight:650;margin:12px 0 5px}input,select,button{font:inherit}input,select{width:100%;padding:10px 11px;border:1px solid #bcc6c3;border-radius:8px;background:white}button.primary,button.secondary,button.danger{border:0;border-radius:8px;padding:10px 14px;cursor:pointer;margin-top:14px}.primary{background:var(--accent);color:white}.secondary{background:var(--soft);color:var(--ink)}.danger{background:#f5e7e7;color:var(--danger)}.actions{display:flex;gap:9px;flex-wrap:wrap}.muted{color:var(--muted)}.notice{padding:11px 13px;border-radius:8px;background:var(--soft);margin:10px 0}.error{background:#f7e8e8;color:var(--danger)}.hidden{display:none!important}.metric{display:inline-block;margin:4px 8px 4px 0;padding:5px 8px;background:var(--soft);border-radius:7px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}code,pre{font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}pre{background:#f1f4f3;padding:12px;border-radius:8px;overflow:auto;max-height:300px}.toolbar{display:flex;gap:8px;align-items:end}.toolbar>div{flex:1}.status{font-weight:650}.small{font-size:13px}@media(max-width:780px){.span7,.span5,.span12{grid-column:span 12}.toolbar{display:block}}
</style>
</head>
<body>
<header><h1>Aqorath</h1><p id="entityLabel">Contabilidad local · cargando entidad…</p></header>
<main>
<div class="tabs"><button class="tab active" data-view="common">Vista común</button><button class="tab" data-view="professional">Vista profesional</button></div>
<section id="common" class="view active">
<div class="grid">
<div class="card span7"><h2>Registrar un hecho económico</h2><p class="muted">Describe qué ocurrió. Aqorath determina la representación contable.</p>
<label for="operation">¿Qué ocurrió?</label><select id="operation"></select>
<label for="amount">Importe</label><input id="amount" inputmode="decimal" placeholder="0.00" autocomplete="off">
<label for="postingDate">Fecha</label><input id="postingDate" type="date">
<button class="primary" id="prepareButton">Revisar antes de contabilizar</button><div id="commonError" class="notice error hidden"></div></div>
<div class="card span5"><h2>Decisión preparada</h2><div id="emptyPreview" class="muted">Aún no hay una operación preparada.</div><div id="preview" class="hidden"><div class="metric" id="previewOperation"></div><div class="metric" id="previewAmount"></div><div class="metric" id="previewDate"></div><p id="previewExplanation"></p><p class="small muted">Nada se contabiliza hasta confirmar esta decisión exacta.</p><div class="actions"><button class="primary" id="confirmButton">Confirmar y contabilizar</button><button class="danger" id="cancelButton">Cancelar</button></div></div><div id="postedNotice" class="notice hidden"></div></div>
</div></section>
<section id="professional" class="view">
<div class="grid">
<div class="card span12"><h2>Inspección profesional</h2><div class="toolbar"><div><label for="entryId">ID de póliza</label><input id="entryId" inputmode="numeric" placeholder="Ej. 12"></div><button class="primary" id="loadEntryButton">Cargar póliza</button><button class="secondary" id="loadLastButton">Última confirmada</button></div><div id="professionalError" class="notice error hidden"></div></div>
<div id="professionalContent" class="span12 hidden grid">
<div class="card span5"><h3>Póliza y período</h3><div id="entryMeta"></div></div>
<div class="card span7"><h3>Trazabilidad</h3><div id="traceMeta"></div></div>
<div class="card span12"><h3>Cuentas · cargos y abonos</h3><div style="overflow:auto"><table><thead><tr><th>Cuenta</th><th>Nombre</th><th class="num">Debe</th><th class="num">Haber</th></tr></thead><tbody id="linesBody"></tbody></table></div></div>
<div class="card span7"><h3>Documentos y referencias</h3><div id="documents"></div></div>
<div class="card span5"><h3>Fiscalidad</h3><div id="fiscal"></div></div>
</div>
<div class="card span12"><h3>Balanza desde la autoridad contable</h3><div class="toolbar"><div><label for="balanceDate">Fecha de corte (opcional)</label><input id="balanceDate" type="date"></div><button class="secondary" id="balanceButton">Consultar balanza</button></div><pre id="balanceOutput">Sin consulta.</pre></div>
</div></section>
</main>
<script>
const state={token:null,lastEntry:null};const $=id=>document.getElementById(id);function showError(id,e){const n=$(id);n.textContent=e?.message||String(e);n.classList.remove('hidden')}function clearError(id){$(id).classList.add('hidden')}async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});let body=null;try{body=await r.json()}catch{body={detail:await r.text()}}if(!r.ok)throw new Error(body.detail||'Error de operación');return body}function money(v){return v??'0'}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.view).classList.add('active')});
async function init(){const cap=await api('/api/capabilities');$('operation').innerHTML=cap.operations.map(x=>`<option value="${x.key}">${x.label}</option>`).join('');$('entityLabel').textContent=cap.entity?`${cap.entity.name}${cap.entity.rfc?' · '+cap.entity.rfc:''} · datos locales`:'Configuración de entidad pendiente · datos locales';$('postingDate').value=new Date().toISOString().slice(0,10)}
$('prepareButton').onclick=async()=>{clearError('commonError');try{const out=await api('/api/operations/prepare',{method:'POST',body:JSON.stringify({operation_key:$('operation').value,amount:$('amount').value,posting_date:$('postingDate').value})});state.token=out.token;$('previewOperation').textContent=out.preview.operation;$('previewAmount').textContent='$ '+out.preview.amount;$('previewDate').textContent=out.preview.posting_date;$('previewExplanation').textContent=out.preview.explanation;$('emptyPreview').classList.add('hidden');$('preview').classList.remove('hidden');$('postedNotice').classList.add('hidden')}catch(e){showError('commonError',e)}};
$('cancelButton').onclick=async()=>{if(!state.token)return;try{await api('/api/operations/'+encodeURIComponent(state.token),{method:'DELETE'});state.token=null;$('preview').classList.add('hidden');$('emptyPreview').classList.remove('hidden')}catch(e){showError('commonError',e)}};
$('confirmButton').onclick=async()=>{if(!state.token)return;clearError('commonError');try{const out=await api('/api/operations/'+encodeURIComponent(state.token)+'/confirm',{method:'POST'});state.lastEntry=out.entry_id;state.token=null;$('preview').classList.add('hidden');$('emptyPreview').classList.remove('hidden');$('postedNotice').textContent=`Póliza ${out.entry_id} contabilizada y auditada.`;$('postedNotice').classList.remove('hidden');$('entryId').value=out.entry_id}catch(e){showError('commonError',e)}};
function renderEntry(v){$('professionalContent').classList.remove('hidden');$('entryMeta').innerHTML=`<div class="metric">#${v.entry_id}</div><div class="metric status">${v.state}</div><p><b>Fecha:</b> ${v.posting_date}<br><b>Período:</b> ${v.period.id} (${v.period.year}-${String(v.period.month).padStart(2,'0')}) · ${v.period.state}<br><b>Ejercicio:</b> ${v.period.fiscal_year_state}</p><p>${v.concept}</p>`;$('linesBody').innerHTML=v.lines.map(l=>`<tr><td><code>${l.account_code}</code></td><td>${l.account_name}</td><td class="num">${money(l.debit)}</td><td class="num">${money(l.credit)}</td></tr>`).join('');$('documents').innerHTML=v.documents.length?v.documents.map(d=>`<p><b>${d.document_type}</b> · ${d.document_number}<br><span class="muted">${d.issuer_name||''} ${d.date} · ${d.is_validated?'validado':'sin validar'}</span></p>`).join(''):'<p class="muted">Sin documentos vinculados.</p>';$('traceMeta').innerHTML=`<p><b>Auditoría:</b> ${v.audit?`evento #${v.audit.id} · ${v.audit.event_type}`:'sin AuditEvent general histórico'}</p><p><b>Reversión:</b> ${v.reversal?`original ${v.reversal.original_entry_id} → reversión ${v.reversal.reversal_entry_id} · ${v.reversal.reason}`:'sin relación de reversión'}</p>${v.audit?`<details><summary>Detalle del evento</summary><pre>${JSON.stringify(v.audit.details,null,2)}</pre></details>`:''}`;$('fiscal').innerHTML=v.fiscal_audit?`<p><b>${v.fiscal_audit.jurisdiction}</b> · ${v.fiscal_audit.regime}</p><p>${v.fiscal_audit.effects.length} efecto(s) fiscal(es) auditado(s).</p><details><summary>Proveniencia fiscal</summary><pre>${JSON.stringify(v.fiscal_audit,null,2)}</pre></details>`:'<p class="muted">Esta póliza no tiene auditoría fiscalizada asociada.</p>'}
async function loadEntry(id){clearError('professionalError');try{const v=await api('/api/operations/'+encodeURIComponent(id)+'/professional');renderEntry(v)}catch(e){showError('professionalError',e)}}
$('loadEntryButton').onclick=()=>loadEntry($('entryId').value);$('loadLastButton').onclick=()=>{if(state.lastEntry){$('entryId').value=state.lastEntry;loadEntry(state.lastEntry)}else showError('professionalError',new Error('Aún no hay una póliza confirmada en esta sesión.'))};$('balanceButton').onclick=async()=>{clearError('professionalError');try{const q=$('balanceDate').value?'?as_of='+encodeURIComponent($('balanceDate').value):'';const v=await api('/api/trial-balance'+q);$('balanceOutput').textContent=JSON.stringify(v,null,2)}catch(e){showError('professionalError',e)}};
init().catch(e=>showError('commonError',e));
</script>
</body></html>'''

__all__ = ["APP_HTML"]
