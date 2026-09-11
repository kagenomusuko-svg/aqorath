"""Thin FastAPI adapter for the localhost surface.

This module remains presentation-only. It imports the framework-neutral controller,
never accounting/storage authorities. The process launcher binds to 127.0.0.1 and
this adapter also rejects non-loopback clients defensively.
"""

from ipaddress import ip_address

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .inventory_web_assets import INVENTORY_HTML
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


@app.get("/inventory", response_class=HTMLResponse)
def inventory_index():
    return HTMLResponse(INVENTORY_HTML)


@app.get("/api/capabilities")
def capabilities():
    try:
        return controller.capabilities()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/reports/catalog")
def reporting_catalog():
    try:
        return controller.reporting_catalog()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/reports/dimensions")
def reporting_dimensions():
    try:
        return controller.reporting_dimensions()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/financial")
def generate_financial_reports(payload: dict):
    try:
        return controller.generate_financial_reports(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/financial/professional")
def professional_financial_reports(payload: dict):
    try:
        return controller.professional_financial_reports(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/professional-detail")
def generate_professional_detail_reports(payload: dict):
    try:
        return controller.generate_professional_detail_reports(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/professional-detail/professional")
def professional_detail_reports(payload: dict):
    try:
        return controller.professional_detail_reports(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/analytical")
def generate_analytical_report(payload: dict):
    try:
        return controller.generate_analytical_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/analytical/professional")
def professional_analytical_report(payload: dict):
    try:
        return controller.professional_analytical_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/inventory-valuation")
def generate_inventory_valuation_report(payload: dict):
    try:
        return controller.generate_inventory_valuation_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/inventory-valuation/professional")
def professional_inventory_valuation_report(payload: dict):
    try:
        return controller.professional_inventory_valuation_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/fiscal-evidence")
def generate_fiscal_evidence_report(payload: dict):
    try:
        return controller.generate_fiscal_evidence_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/fiscal-evidence/professional")
def professional_fiscal_evidence_report(payload: dict):
    try:
        return controller.professional_fiscal_evidence_report(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/donations")
def donations():
    try:
        return controller.donations()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/donation-options")
def donation_options():
    try:
        return controller.donation_options()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/donations/prepare")
def prepare_monetary_donation(payload: dict):
    try:
        return controller.prepare_monetary_donation(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/in-kind-donations/prepare")
def prepare_inkind_donation(payload: dict):
    try:
        return controller.prepare_inkind_donation(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/donations")
def create_donation(payload: dict):
    try:
        return controller.create_donation(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/in-kind-donations")
def create_inkind_donation(payload: dict):
    try:
        return controller.create_inkind_donation(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/donations/{donation_id}/professional")
def professional_donation(donation_id: int):
    try:
        return controller.professional_donation(donation_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/in-kind-donations/{donation_id}/professional")
def professional_inkind_donation(donation_id: int):
    try:
        return controller.professional_inkind_donation(donation_id)
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


@app.get("/api/inventory/products")
def inventory_products():
    try:
        return controller.inventory_products()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/products")
def create_inventory_product(payload: dict):
    try:
        return controller.create_inventory_product(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/prepare")
def prepare_inventory(payload: dict):
    try:
        return controller.prepare_inventory(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/inventory/movements/{movement_id}/professional")
def professional_inventory(movement_id: int):
    try:
        return controller.professional_inventory(movement_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/movements/{movement_id}/reverse")
def reverse_inventory(movement_id: int, payload: dict):
    try:
        return controller.reverse_inventory(movement_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/fiscal-v1/prepare")
def prepare_fiscal_v1(payload: dict):
    try:
        return controller.prepare_fiscal_v1(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/fiscal-v1/operations/{entry_id}/professional")
def professional_fiscal_v1(entry_id: int):
    try:
        return controller.professional_fiscal_v1(entry_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/cfdi/import")
def import_cfdi(payload: dict):
    try:
        return controller.import_cfdi(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/cfdi/sources")
def cfdi_sources():
    try:
        return controller.cfdi_sources()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/cfdi/prepare")
def prepare_cfdi(payload: dict):
    try:
        return controller.prepare_cfdi(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/cfdi/{uuid}/professional")
def professional_cfdi(uuid: str):
    try:
        return controller.professional_cfdi(uuid)
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


@app.post("/api/subledger/third-parties")
def create_third_party(payload: dict):
    try:
        return controller.create_third_party(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/operations/{entry_id}/reverse")
def reverse_operation(entry_id: int, payload: dict):
    try:
        return controller.reverse_operation(entry_id, payload)
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


@app.get("/api/banking/accounts")
def bank_accounts():
    try:
        return controller.bank_accounts()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/accounts")
def create_bank_account(payload: dict):
    try:
        return controller.create_bank_account(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/import")
def import_bank_csv(payload: dict):
    try:
        return controller.import_bank_csv(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/reconciliations")
def create_reconciliation(payload: dict):
    try:
        return controller.create_reconciliation(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/banking/reconciliations/{reconciliation_id}")
def reconciliation(reconciliation_id: int):
    try:
        return controller.reconciliation(reconciliation_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/matches")
def match_bank_transaction(payload: dict):
    try:
        return controller.match_bank_transaction(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/transfers")
def bank_transfer(payload: dict):
    try:
        return controller.bank_transfer(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/funds")
def funds():
    try:
        return controller.funds()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/funds")
def create_fund(payload: dict):
    try:
        return controller.create_fund(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/funding-sources")
def create_funding_source(payload: dict):
    try:
        return controller.create_funding_source(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/funding-sources")
def funding_sources():
    try:
        return controller.funding_sources()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/fund-candidates")
def fund_candidates(kind: str):
    try:
        return controller.fund_candidates(kind)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/fund-receipts")
def record_fund_receipt(payload: dict):
    try:
        return controller.record_fund_receipt(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/osc/fund-applications")
def record_fund_application(payload: dict):
    try:
        return controller.record_fund_application(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/funds/{fund_id}/balance")
def fund_balance(fund_id: int, as_of: str):
    try:
        return controller.fund_balance(fund_id, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/osc/funds/{fund_id}/traceability")
def fund_traceability(fund_id: int, as_of: str):
    try:
        return controller.fund_traceability(fund_id, as_of)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/banking/matches/{match_id}/revoke")
def revoke_bank_match(match_id: int, payload: dict):
    try:
        return controller.revoke_bank_match(match_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


__all__ = ["app", "controller"]