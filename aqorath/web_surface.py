"""Thin FastAPI adapter for the localhost surface.

This module remains presentation-only. It imports the framework-neutral controller,
never accounting/storage authorities. The process launcher binds to 127.0.0.1 and
this adapter also rejects non-loopback clients defensively.
"""

from ipaddress import ip_address

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .presentation_controller import LocalPresentationController
from .web_assets import APP_HTML


app = FastAPI(
    title="Aqorath Local Surface",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
controller = LocalPresentationController()


def _loopback(host):
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    client = request.client
    if client is not None and not _loopback(client.host):
        return JSONResponse(status_code=403, content={"detail": "local access only"})
    return await call_next(request)


def _error(exc):
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(APP_HTML)


@app.get("/api/capabilities")
def capabilities():
    try:
        return controller.capabilities()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/operations/prepare")
def prepare_operation(payload: dict):
    try:
        return controller.prepare(
            payload.get("operation_key"),
            payload.get("amount"),
            payload.get("posting_date"),
        )
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/subledger/origins/prepare")
def prepare_open_item_origin(payload: dict):
    try:
        return controller.prepare_open_item_origin(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/subledger/applications/prepare")
def prepare_open_item_application(payload: dict):
    try:
        return controller.prepare_open_item_application(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/subledger/applications/batch/prepare")
def prepare_open_item_application_batch(payload: dict):
    try:
        return controller.prepare_open_item_application_batch(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/operations/{token}/professional-preview")
def professional_preview(token: str):
    try:
        return controller.professional_preview(token)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/operations/{token}/confirm")
def confirm_operation(token: str):
    try:
        return controller.confirm(token)
    except Exception as exc:
        raise _error(exc) from exc


@app.delete("/api/operations/{token}")
def cancel_operation(token: str):
    try:
        return controller.cancel(token)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/subledger/third-parties")
def third_parties():
    try:
        return controller.third_parties()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/subledger/open-items")
def open_items(
    kind: str | None = None,
    as_of: str | None = None,
    include_settled: bool = True,
):
    try:
        return controller.open_items(kind, as_of, include_settled)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/subledger/open-items/{open_item_id}")
def open_item(open_item_id: int, as_of: str | None = None):
    try:
        return controller.open_item(open_item_id, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/subledger/open-items/{open_item_id}/professional")
def professional_open_item(open_item_id: int, as_of: str | None = None):
    try:
        return controller.professional_open_item(open_item_id, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/subledger/reconciliation/{kind}")
def subledger_reconciliation(kind: str, as_of: str | None = None):
    try:
        return controller.subledger_reconciliation(kind, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/professional/operations")
def recent_professional_operations(limit: int = 50):
    try:
        return controller.recent_professional_operations(limit)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/operations/{entry_id}/professional")
def professional_operation(entry_id: int):
    try:
        return controller.professional_operation(entry_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/trial-balance")
def trial_balance(as_of: str | None = None):
    try:
        return controller.trial_balance(as_of)
    except Exception as exc:
        raise _error(exc) from exc


__all__ = ["app", "controller"]
