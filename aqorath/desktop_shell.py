"""Desktop presentation decorator for Aqorath's localhost UI.

The accounting/application authority remains server-side. This module only reshapes
presentation so the packaged Windows build behaves like a focused desktop app rather
than one long browser document.
"""

from __future__ import annotations


_DESKTOP_STYLE = r"""
<style id="aqorath-desktop-style">
:root{--aq-nav:#173f3a;--aq-nav-2:#1f5148;--aq-bg:#f3f5f4;--aq-border:#d8e0dd;--aq-muted:#64706d}
html,body{min-height:100%}
body.aq-desktop{background:var(--aq-bg)!important;overflow:hidden}
body.aq-desktop>header{position:fixed;left:238px;right:0;top:0;height:72px;z-index:50;padding:15px 28px!important;background:#fff!important;color:#17211f!important;border-bottom:1px solid var(--aq-border);box-shadow:none!important}
body.aq-desktop>header h1{font-size:21px!important;margin:0!important}
body.aq-desktop>header p,body.aq-desktop>header div{color:var(--aq-muted)!important;margin-top:2px!important}
body.aq-desktop>main{position:fixed;left:238px;right:0;top:72px;bottom:0;max-width:none!important;margin:0!important;padding:26px 30px 44px!important;overflow:auto}
#aq-sidebar{position:fixed;left:0;top:0;bottom:0;width:238px;background:linear-gradient(180deg,var(--aq-nav),#102d29);color:#fff;z-index:100;padding:22px 16px;display:flex;flex-direction:column;box-shadow:3px 0 18px rgba(0,0,0,.08)}
#aq-sidebar .brand{padding:4px 10px 22px;border-bottom:1px solid rgba(255,255,255,.14);margin-bottom:14px}
#aq-sidebar .brand strong{display:block;font-size:20px;letter-spacing:.08em}
#aq-sidebar .brand span{display:block;font-size:12px;opacity:.7;margin-top:3px}
#aq-sidebar nav{display:flex;flex-direction:column;gap:5px;overflow:auto}
#aq-sidebar a{display:block;color:#e9f1ef;text-decoration:none;padding:10px 12px;border-radius:9px;font-size:14px;font-weight:620}
#aq-sidebar a:hover{background:rgba(255,255,255,.09)}
#aq-sidebar a.active{background:#fff;color:var(--aq-nav);box-shadow:0 2px 10px rgba(0,0,0,.10)}
#aq-sidebar .bottom{margin-top:auto;padding:14px 10px 2px;font-size:11px;line-height:1.4;opacity:.58}
body.aq-desktop .tabs{display:none!important}
body.aq-desktop #common>.grid>.card{display:none}
body.aq-desktop #common>.grid>.card.aq-module-visible{display:block}
body.aq-desktop .card{border-color:var(--aq-border)!important;border-radius:14px!important;box-shadow:0 5px 18px rgba(23,63,58,.045)!important}
body.aq-desktop input,body.aq-desktop select{min-height:40px;background:#fff!important;border:1px solid #b9c6c2!important}
body.aq-desktop input:focus,body.aq-desktop select:focus{outline:2px solid rgba(31,81,72,.22);outline-offset:1px;border-color:var(--aq-nav-2)!important}
body.aq-desktop button{font-weight:650}
body.aq-desktop h2{font-size:20px;margin-bottom:5px}
body.aq-desktop h3{font-size:16px}
body.aq-desktop #aqorath-recovery-link{display:none!important}
.aq-module-title{margin:0 0 18px;font-size:25px;letter-spacing:-.02em}.aq-module-subtitle{margin:-12px 0 22px;color:var(--aq-muted)}
@media(max-width:900px){#aq-sidebar{width:196px}body.aq-desktop>header,body.aq-desktop>main{left:196px}}
</style>
"""

_SIDEBAR = r"""
<aside id="aq-sidebar" aria-label="Navegación principal">
  <div class="brand"><strong>AQORATH</strong><span>Sistema contable local</span></div>
  <nav>
    <a data-module="operations" href="/?module=operations">Inicio</a>
    <a data-module="donations" href="/?module=donations">Donativos</a>
    <a data-module="cfdi" href="/?module=cfdi">CFDI</a>
    <a data-module="parties" href="/?module=parties">Clientes y proveedores</a>
    <a data-module="banking" href="/?module=banking">Bancos</a>
    <a data-module="funds" href="/?module=funds">Fondos OSC</a>
    <a data-module="reports" href="/?module=reports">Reportes</a>
    <a data-module="inventory" href="/inventory">Inventario</a>
    <a data-module="professional" href="/?module=professional">Vista profesional</a>
    <a data-module="recovery" href="/recovery">Respaldo</a>
  </nav>
  <div class="bottom">Datos locales · sin elegir Debe/Haber para registrar hechos</div>
</aside>
"""

_MAIN_SCRIPT = r"""
<script id="aqorath-desktop-script">
(function(){
 const params=new URLSearchParams(location.search);
 let module=params.get('module')||'operations';
 const labels={operations:['Inicio','Registra y revisa hechos económicos antes de contabilizarlos.'],donations:['Donativos','Donativos monetarios y en especie con evidencia y destino.'],cfdi:['CFDI','Importa evidencia fiscal y úsala como documento fuente.'],parties:['Clientes y proveedores','Terceros, crédito, cobros y pagos.'],banking:['Bancos','Cuentas, estados de cuenta y conciliación.'],funds:['Fondos OSC','Fuentes, fondos y aplicación de recursos.'],reports:['Reportes','Consulta información sin alterar la contabilidad.'],professional:['Vista profesional','Reconstrucción, trazabilidad y detalle técnico.']};
 const classify=(title)=>{
   title=(title||'').toLowerCase();
   if(title.includes('registrar un hecho')||title.includes('decisión preparada'))return 'operations';
   if(title.includes('donativo'))return 'donations';
   if(title.includes('cfdi'))return 'cfdi';
   if(title.includes('clientes y proveedores')||title.includes('venta o compra a crédito')||title.includes('lo que te deben'))return 'parties';
   if(title.includes('cuenta bancaria')||title.includes('estado de cuenta'))return 'banking';
   if(title.includes('fondos y aplicación'))return 'funds';
   if(title==='reportes'||title.includes('paquetes de reportes'))return 'reports';
   return 'operations';
 };
 const common=document.getElementById('common');
 const professional=document.getElementById('professional');
 if(module==='professional'){
   if(common)common.classList.remove('active');
   if(professional)professional.classList.add('active');
 }else{
   if(professional)professional.classList.remove('active');
   if(common){common.classList.add('active');const cards=common.querySelectorAll(':scope > .grid > .card');cards.forEach(card=>{const h=card.querySelector(':scope > h2');card.dataset.aqModule=classify(h?h.textContent:'');card.classList.toggle('aq-module-visible',card.dataset.aqModule===module);});}
 }
 document.querySelectorAll('#aq-sidebar a').forEach(a=>a.classList.toggle('active',a.dataset.module===module));
 const main=document.querySelector('body.aq-desktop>main');
 if(main&&labels[module]){
   const title=document.createElement('h1');title.className='aq-module-title';title.textContent=labels[module][0];
   const sub=document.createElement('p');sub.className='aq-module-subtitle';sub.textContent=labels[module][1];
   main.prepend(sub);main.prepend(title);
 }
})();
</script>
"""

_INVENTORY_SCRIPT = r"""
<script id="aqorath-desktop-inventory-script">
(function(){document.querySelectorAll('#aq-sidebar a').forEach(a=>a.classList.toggle('active',a.dataset.module==='inventory'));})();
</script>
"""


def desktopize_main(html: str) -> str:
    if 'id="aqorath-desktop-style"' in html:
        return html
    html = html.replace("</head>", _DESKTOP_STYLE + "</head>")
    html = html.replace("<body>", '<body class="aq-desktop">' + _SIDEBAR, 1)
    return html.replace("</body>", _MAIN_SCRIPT + "</body>")


def desktopize_inventory(html: str) -> str:
    if 'id="aqorath-desktop-style"' in html:
        return html
    html = html.replace("</head>", _DESKTOP_STYLE + "</head>")
    html = html.replace("<body>", '<body class="aq-desktop">' + _SIDEBAR, 1)
    return html.replace("</body>", _INVENTORY_SCRIPT + "</body>")


__all__ = ["desktopize_main", "desktopize_inventory"]
