"""AQR-014 local recovery presentation surface.

This module extends the existing localhost FastAPI app without importing persistence
or accounting authorities. The launcher imports this module so the recovery routes
and discoverability link are installed before serving requests.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from . import web_assets as _web_assets
from .recovery_presentation_controller import LocalRecoveryController


_RECOVERY_LINK = (
    '<a id="aqorath-recovery-link" href="/recovery" '
    'style="position:fixed;right:18px;bottom:18px;z-index:9999;padding:10px 14px;'
    'border-radius:10px;background:#173f3a;color:#fff;text-decoration:none;'
    'box-shadow:0 4px 16px rgba(0,0,0,.18);font:600 14px system-ui">'
    'Respaldo y portabilidad</a>'
)
if "aqorath-recovery-link" not in _web_assets.APP_HTML:
    _web_assets.APP_HTML = _web_assets.APP_HTML.replace(
        "</body>", f"{_RECOVERY_LINK}</body>"
    )

# Import only after APP_HTML is decorated; web_surface copies the constant at import.
from .web_surface import app  # noqa: E402


controller = LocalRecoveryController()


RECOVERY_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aqorath — Respaldo y portabilidad</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#17201f;background:#f5f7f6}
body{margin:0}.wrap{max-width:900px;margin:0 auto;padding:32px 18px 60px}
a{color:#245e56}.card{background:#fff;border:1px solid #dce4e1;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 4px 18px rgba(0,0,0,.04)}
h1{margin:8px 0 4px}.muted{color:#586865;line-height:1.5}button,.button{border:0;border-radius:9px;background:#245e56;color:#fff;padding:10px 14px;font-weight:650;cursor:pointer}.danger{background:#8b2f2f}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}input[type=file]{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f1;padding:14px;border-radius:9px;min-height:38px}.ok{color:#1f694e}.bad{color:#8b2f2f}
</style>
</head>
<body><main class="wrap">
<a href="/">← Volver a Aqorath</a>
<h1>Respaldo, integridad y portabilidad</h1>
<p class="muted">SQLite sigue siendo la única fuente primaria de verdad. Los archivos ZIP de esta pantalla son copias de recuperación o intercambio; no son una segunda persistencia activa.</p>
<section class="card"><h2>Integridad de la instalación</h2><p class="muted">Comprueba SQLite, versión de schema, relaciones y documentos locales referenciados.</p><button id="integrity">Verificar integridad</button><pre id="integrity-result">Sin verificar.</pre></section>
<section class="card"><h2>Respaldo completo</h2><p class="muted">Crea un snapshot SQLite consistente y adjunta las evidencias locales referenciadas, con manifiesto SHA-256.</p><button id="backup">Descargar respaldo</button></section>
<section class="card"><h2>Restaurar respaldo</h2><p class="muted">La restauración valida completamente el paquete antes de sustituir la base. Si existe una base sana, Aqorath crea primero un respaldo preventivo. Los documentos se restauran en una ubicación administrada y se conservan sus hashes.</p><div class="row"><input id="restore-file" type="file" accept=".zip,application/zip"><button id="restore" class="danger">Restaurar</button></div><pre id="restore-result">No se ha restaurado nada.</pre></section>
<section class="card"><h2>Salida portable</h2><p class="muted">Exporta todas las tablas y relaciones V1, schema, tipos SQLite, BLOB en base64, montos como texto exacto cuando la autoridad los persiste así, conciliación y evidencias locales. El resultado puede leerse sin Aqorath.</p><button id="portable">Descargar exportación portable</button></section>
</main>
<script>
const pretty=v=>JSON.stringify(v,null,2);
async function download(path, fallback){
 const response=await fetch(path,{method:'POST'});
 if(!response.ok) throw new Error((await response.json()).detail||response.statusText);
 const blob=await response.blob();
 const disposition=response.headers.get('content-disposition')||'';
 const match=/filename="([^"]+)"/.exec(disposition);
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=match?match[1]:fallback;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
}
document.getElementById('integrity').onclick=async()=>{const out=document.getElementById('integrity-result');try{const r=await fetch('/api/system/integrity');const v=await r.json();if(!r.ok)throw new Error(v.detail||r.statusText);out.textContent=pretty(v);out.className=v.healthy?'ok':'bad'}catch(e){out.textContent=e.message;out.className='bad'}};
document.getElementById('backup').onclick=()=>download('/api/system/backup','aqorath-backup.zip').catch(e=>alert(e.message));
document.getElementById('portable').onclick=()=>download('/api/system/portable-export','aqorath-portable.zip').catch(e=>alert(e.message));
document.getElementById('restore').onclick=async()=>{const file=document.getElementById('restore-file').files[0];const out=document.getElementById('restore-result');if(!file){out.textContent='Selecciona primero un respaldo ZIP.';out.className='bad';return}if(!confirm('La restauración sustituirá la base activa únicamente después de validar el paquete. ¿Continuar?'))return;try{const r=await fetch('/api/system/restore',{method:'POST',headers:{'Content-Type':'application/zip','X-Aqorath-Confirm-Restore':'RESTORE'},body:file});const v=await r.json();if(!r.ok)throw new Error(v.detail||r.statusText);out.textContent=pretty(v);out.className='ok'}catch(e){out.textContent=e.message;out.className='bad'}};
</script></body></html>"""


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/recovery", response_class=HTMLResponse)
def recovery_index():
    return HTMLResponse(RECOVERY_HTML)


@app.get("/api/system/integrity")
def recovery_integrity():
    try:
        return controller.integrity()
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/system/backup")
def recovery_backup():
    try:
        artifact = controller.backup()
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                "X-Aqorath-Artifact-Sha256": artifact.summary["sha256"],
            },
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/system/portable-export")
def recovery_portable_export():
    try:
        artifact = controller.portable_export()
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                "X-Aqorath-Artifact-Sha256": artifact.summary["sha256"],
            },
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/system/restore")
async def recovery_restore(request: Request):
    if request.headers.get("X-Aqorath-Confirm-Restore") != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail="explicit restore confirmation is required",
        )
    content = await request.body()
    try:
        return controller.restore(content)
    except Exception as exc:
        raise _http_error(exc) from exc


__all__ = ["app", "RECOVERY_HTML", "controller"]
