"""Self-contained common browser flow for AQR-012 inventory facts."""

INVENTORY_HTML = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aqorath · Inventario</title>
<style>
:root{--ink:#17211f;--muted:#64706d;--line:#d9dfdd;--paper:#f5f7f6;--card:#fff;--accent:#1f5148;--soft:#e9f0ee;--danger:#8a2f2f}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}header{background:var(--accent);color:#fff;padding:20px 24px}main{max-width:1000px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.card{grid-column:span 12;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:17px}.half{grid-column:span 6}label{display:block;font-weight:650;margin:10px 0 4px}input,select{width:100%;padding:9px;border:1px solid #bcc6c3;border-radius:8px;background:#fff}button{border:0;border-radius:8px;padding:10px 14px;cursor:pointer}.primary{background:var(--accent);color:#fff}.secondary{background:var(--soft)}.danger{background:#f5e7e7;color:var(--danger)}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.muted{color:var(--muted)}.notice{padding:10px 12px;border-radius:8px;background:var(--soft);margin-top:12px}.error{background:#f7e8e8;color:var(--danger)}.hidden{display:none}.metrics{display:flex;gap:8px;flex-wrap:wrap}.metric{background:var(--soft);padding:6px 9px;border-radius:7px}pre{white-space:pre-wrap;background:#f1f4f3;padding:10px;border-radius:8px;overflow:auto}@media(max-width:720px){.half{grid-column:span 12}}
</style>
</head>
<body>
<header><h1>Inventario</h1><div>Compras, ventas y costo reproducible desde la misma verdad contable</div></header>
<main><div class="grid">
<section class="card"><h2>Producto</h2><div class="grid"><div class="half"><label>Producto</label><select id="product"></select></div><div class="half"><label>Nuevo producto</label><input id="newName" placeholder="Producto X"><input id="newSku" placeholder="SKU-X"><button class="secondary" id="createProduct">Crear producto</button></div></div></section>
<section class="card"><h2>Registrar movimiento</h2><p class="muted">Describe el hecho. Aqorath calcula existencia y costo; no necesitas elegir cuentas ni indicar Debe/Haber.</p><div class="grid">
<div class="half"><label>¿Qué ocurrió?</label><select id="kind"><option value="purchase">Compré mercancía</option><option value="sale">Vendí mercancía</option></select><label>Cantidad</label><input id="quantity" inputmode="decimal" placeholder="10"><label>Precio unitario</label><input id="unitPrice" inputmode="decimal" placeholder="10.00"><label>Fecha</label><input id="operationDate" type="date"></div>
<div class="half"><label>Liquidación</label><select id="settlement"><option value="cash">Efectivo</option><option value="bank">Banco</option><option value="credit">Crédito</option></select><label>Contraparte</label><select id="party"><option value="">Sin contraparte</option></select><label>Cuenta bancaria propia</label><select id="bank"><option value="">Usar configuración general</option></select><label>Vencimiento si es crédito</label><input id="dueDate" type="date"></div>
<div class="half"><label>Tipo de documento</label><input id="documentType" placeholder="invoice"><label>Folio</label><input id="documentNumber"><label>Fecha del documento</label><input id="documentDate" type="date"></div>
<div class="half"><label>CFDI importado</label><select id="cfdi"><option value="">Sin CFDI</option></select><label>Naturaleza fiscal explícita de la venta</label><select id="fiscalActivity"><option value="">Sin tratamiento fiscal solicitado</option><option value="ordinary_taxable_sale">Venta ordinaria gravada</option><option value="own_edited_publication_sale">Publicación propia editada</option></select><p class="muted">La selección describe la actividad; AQR-011 decide si existe cobertura. El CFDI no selecciona el tratamiento.</p></div>
</div><div class="actions"><button class="primary" id="prepare">Revisar antes de contabilizar</button></div><div id="error" class="notice error hidden"></div></section>
<section class="card hidden" id="previewCard"><h2>Decisión preparada</h2><div class="metrics" id="metrics"></div><pre id="preview"></pre><p class="muted">Confirmar usa exactamente este snapshot. Cancelar no escribe nada.</p><div class="actions"><button class="primary" id="confirm">Confirmar</button><button class="danger" id="cancel">Cancelar</button></div></section>
<section class="card hidden" id="posted"><h2>Operación registrada</h2><div id="postedText"></div><button class="secondary" id="professional">Ver reconstrucción profesional</button><pre id="professionalData" class="hidden"></pre></section>
</div></main>
<script>
let token=null,movementId=null;
const $=id=>document.getElementById(id);
async function request(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const b=await r.json().catch(()=>({detail:r.statusText}));if(!r.ok)throw new Error(b.detail||'Error');return b}
function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o}
async function load(){const [products,parties,banks,cfd] = await Promise.all([request('/api/inventory/products'),request('/api/subledger/third-parties'),request('/api/banking/accounts'),request('/api/cfdi/sources')]);$('product').replaceChildren(...products.map(x=>option(x.id,`${x.sku} · ${x.name}`)));$('party').replaceChildren(option('','Sin contraparte'),...parties.map(x=>option(x.id,x.name)));$('bank').replaceChildren(option('','Usar configuración general'),...banks.map(x=>option(x.id,`${x.institution_name} · ${x.account_identifier}`)));$('cfdi').replaceChildren(option('','Sin CFDI'),...cfd.map(x=>option(x.id||x.source_id,`${x.uuid} · ${x.total}`)));}
$('createProduct').onclick=async()=>{try{await request('/api/inventory/products',{method:'POST',body:JSON.stringify({sku:$('newSku').value,name:$('newName').value,unit:'unidad'})});await load()}catch(e){showError(e)}};
function showError(e){$('error').textContent=e.message;$('error').classList.remove('hidden')}
function payload(){const p={operation_kind:$('kind').value,product_id:Number($('product').value),quantity:$('quantity').value,unit_price:$('unitPrice').value,operation_date:$('operationDate').value,settlement_method:$('settlement').value};if($('party').value)p.third_party_id=Number($('party').value);if($('bank').value)p.bank_account_id=Number($('bank').value);if($('dueDate').value)p.due_date=$('dueDate').value;if($('cfdi').value)p.cfdi_source_id=Number($('cfdi').value);if($('fiscalActivity').value)p.fiscal_activity=$('fiscalActivity').value;const doc=[$('documentType').value,$('documentNumber').value,$('documentDate').value];if(doc.some(Boolean)){p.document_type=doc[0];p.document_number=doc[1];p.document_date=doc[2]}return p}
$('prepare').onclick=async()=>{try{$('error').classList.add('hidden');const r=await request('/api/inventory/prepare',{method:'POST',body:JSON.stringify(payload())});token=r.token;const v=r.preview;$('metrics').replaceChildren(optionMetric(`Existencia ${v.stock_before} → ${v.stock_after}`),optionMetric(`Promedio ${v.moving_average_after}`),...(v.estimated_cost_of_sale?[optionMetric(`Costo previsto ${v.estimated_cost_of_sale}`)]:[]));$('preview').textContent=JSON.stringify(v,null,2);$('previewCard').classList.remove('hidden')}catch(e){showError(e)}};
function optionMetric(text){const s=document.createElement('span');s.className='metric';s.textContent=text;return s}
$('cancel').onclick=async()=>{if(!token)return;await request(`/api/operations/${token}`,{method:'DELETE'});token=null;$('previewCard').classList.add('hidden')};
$('confirm').onclick=async()=>{try{const r=await request(`/api/operations/${token}/confirm`,{method:'POST'});movementId=r.movement_id;token=null;$('previewCard').classList.add('hidden');$('postedText').textContent=`Movimiento ${movementId} · póliza ${r.entry_id}`;$('posted').classList.remove('hidden')}catch(e){showError(e)}};
$('professional').onclick=async()=>{try{const r=await request(`/api/inventory/movements/${movementId}/professional`);$('professionalData').textContent=JSON.stringify(r,null,2);$('professionalData').classList.remove('hidden')}catch(e){showError(e)}};
load().catch(showError);
</script>
</body></html>'''

__all__ = ["INVENTORY_HTML"]
