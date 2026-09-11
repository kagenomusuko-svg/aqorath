"""Framework-neutral local presentation controller.

Pending tokens are ephemeral consent/presentation state only. They never represent
posted accounting or subledger truth and may disappear on process restart without
changing SQLite. All durable work delegates to application-facing surface modules.
"""

import secrets

from . import fiscal_v1_surface_application as _fiscal_v1
from . import inventory_surface_application as _inventory_v1
from . import surface_application as _application


_COMMON_FISCAL_KEYS = frozenset({"sale_general_paid", "sale_own_publication_paid"})


class LocalPresentationController:
    def __init__(self):
        self._pending = {}

    def _store(self, prepared, preview):
        token = secrets.token_urlsafe(24)
        while token in self._pending:
            token = secrets.token_urlsafe(24)
        self._pending[token] = prepared
        return {"token": token, "preview": preview}

    def capabilities(self):
        fiscal_kinds = tuple(_fiscal_v1.list_fiscal_v1_surface_kinds())
        try:
            inventory_products = _inventory_v1.list_inventory_surface_products()
            inventory_enabled = True
        except (LookupError, ValueError):
            inventory_products = []
            inventory_enabled = False
        return {
            "operations": [
                {"key": item.key, "label": item.label}
                for item in _application.list_common_operation_kinds()
            ] + [
                {"key": item.key, "label": item.label}
                for item in fiscal_kinds
                if item.key in _COMMON_FISCAL_KEYS
            ],
            "fiscal_v1_operations": [
                {"key": item.key, "label": item.label}
                for item in fiscal_kinds
            ],
            "credit_origins": (
                {"key": "sale_credit", "label": "Venta a crédito"},
                {"key": "utility_credit", "label": "Compra/gasto a crédito"},
            ),
            "third_parties": _application.list_surface_third_parties(),
            "entity": _application.get_surface_entity(),
            "views": ("common", "professional"),
            "inventory": {"enabled": inventory_enabled, "products": inventory_products},
        }

    def prepare(self, operation_key, amount, posting_date):
        if operation_key in _COMMON_FISCAL_KEYS:
            prepared = _fiscal_v1.prepare_fiscal_v1_surface_operation({
                "operation_key": operation_key,
                "amount": amount,
                "operation_date": posting_date,
            })
            return self._store(prepared, prepared.common_preview)
        prepared = _application.prepare_common_operation(
            operation_key,
            amount,
            posting_date,
        )
        return self._store(prepared, _application.common_preview(prepared))

    def prepare_fiscal_v1(self, payload):
        prepared = _fiscal_v1.prepare_fiscal_v1_surface_operation(payload)
        return self._store(prepared, prepared.common_preview)

    def prepare_inventory(self, payload):
        prepared = _inventory_v1.prepare_inventory_surface_operation(payload)
        return self._store(prepared, prepared.preview)

    def inventory_products(self):
        return _inventory_v1.list_inventory_surface_products()

    def create_inventory_product(self, payload):
        return _inventory_v1.create_inventory_surface_product(payload)

    def professional_inventory(self, movement_id):
        return _inventory_v1.load_inventory_surface_professional(movement_id)

    def reverse_inventory(self, movement_id, payload):
        return _inventory_v1.reverse_inventory_surface_operation(
            movement_id, payload.get("reason"), payload.get("reversal_date")
        )

    def professional_fiscal_v1(self, entry_id):
        return _fiscal_v1.load_fiscal_v1_surface_professional(entry_id)

    def donation_options(self):
        return _application.list_surface_donation_options()

    def prepare_monetary_donation(self, payload):
        prepared = _application.prepare_surface_monetary_donation(payload)
        return self._store(prepared, prepared.preview)

    def prepare_inkind_donation(self, payload):
        prepared = _application.prepare_surface_inkind_donation(payload)
        return self._store(prepared, prepared.preview)

    def import_cfdi(self, payload):
        return _application.import_surface_cfdi(payload)

    def cfdi_sources(self):
        return _application.list_surface_cfdi_sources()

    def prepare_cfdi(self, payload):
        prepared = _application.prepare_surface_cfdi(payload)
        return self._store(prepared, prepared.preview)

    def professional_cfdi(self, uuid):
        return _application.load_surface_cfdi_professional(uuid)

    def prepare_open_item_origin(self, payload):
        prepared = _application.prepare_surface_open_item_origin(
            payload.get("operation_key"),
            payload.get("amount"),
            payload.get("posting_date"),
            payload.get("third_party_id"),
            payload.get("due_date"),
            payload.get("document_type"),
            payload.get("document_number"),
            payload.get("document_date"),
        )
        return self._store(prepared, _application.subledger_common_preview(prepared))

    def prepare_open_item_application(self, payload):
        prepared = _application.prepare_surface_open_item_application(
            payload.get("open_item_id"),
            payload.get("amount"),
            payload.get("posting_date"),
            payload.get("document_type"),
            payload.get("document_number"),
            payload.get("document_date"),
        )
        return self._store(prepared, _application.subledger_common_preview(prepared))

    def prepare_open_item_application_batch(self, payload):
        prepared = _application.prepare_surface_open_item_application_batch(
            payload.get("allocations"),
            payload.get("posting_date"),
            payload.get("document_type"),
            payload.get("document_number"),
            payload.get("document_date"),
        )
        return self._store(prepared, _application.subledger_common_preview(prepared))

    def professional_preview(self, token):
        prepared = self._require_pending(token)
        if isinstance(prepared, _application.PreparedSurfaceOperation):
            return _application.professional_preview(prepared)
        if isinstance(prepared, _application.PreparedSurfaceDonationOperation):
            return _application.donation_professional_preview(prepared)
        if isinstance(prepared, _application.PreparedSurfaceCfdiOperation):
            return _application.cfdi_professional_preview(prepared)
        if isinstance(prepared, _application.PreparedSurfaceSubledgerAction):
            return _application.subledger_professional_preview(prepared)
        if isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):
            return _fiscal_v1.professional_fiscal_v1_preview(prepared)
        if isinstance(prepared, _inventory_v1.PreparedInventorySurfaceOperation):
            return _inventory_v1.professional_inventory_preview(prepared)
        raise TypeError("unsupported prepared presentation value")

    def confirm(self, token):
        prepared = self._require_pending(token)
        if isinstance(prepared, _application.PreparedSurfaceOperation):
            result = _application.confirm_and_post(prepared)
            response = {
                "entry_id": result.entry_id,
                "audit_event_id": result.audit_event_id,
                "state": result.state,
            }
        elif isinstance(prepared, _application.PreparedSurfaceDonationOperation):
            response = _application.confirm_surface_donation(prepared)
        elif isinstance(prepared, _application.PreparedSurfaceCfdiOperation):
            response = _application.confirm_surface_cfdi(prepared)
        elif isinstance(prepared, _application.PreparedSurfaceSubledgerAction):
            response = _application.confirm_and_post_subledger(prepared)
        elif isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):
            response = _fiscal_v1.confirm_and_execute_fiscal_v1_surface_operation(prepared)
        elif isinstance(prepared, _inventory_v1.PreparedInventorySurfaceOperation):
            response = _inventory_v1.confirm_inventory_surface_operation(prepared)
        else:
            raise TypeError("unsupported prepared presentation value")
        del self._pending[token]
        return response

    def cancel(self, token):
        self._require_pending(token)
        del self._pending[token]
        return {"cancelled": True}

    def third_parties(self):
        return _application.list_surface_third_parties()

    def create_third_party(self, payload):
        return _application.create_surface_third_party(
            payload.get("name"), payload.get("party_type"), payload.get("rfc"),
        )

    def reverse_operation(self, entry_id, payload):
        return _application.reverse_surface_operation(
            entry_id, payload.get("reason"), payload.get("reversal_date"),
        )

    def open_items(self, kind=None, as_of=None, include_settled=True):
        return _application.list_surface_open_items(
            kind=kind,
            as_of=as_of,
            include_settled=include_settled,
        )

    def open_item(self, open_item_id, as_of=None):
        return _application.load_surface_open_item(open_item_id, as_of=as_of)

    def professional_open_item(self, open_item_id, as_of=None):
        return _application.load_professional_open_item(open_item_id, as_of=as_of)

    def subledger_reconciliation(self, kind, as_of=None):
        return _application.get_surface_subledger_reconciliation(kind, as_of=as_of)

    def recent_professional_operations(self, limit=50):
        return _application.list_professional_operations(limit)

    def professional_operation(self, entry_id):
        return _application.load_professional_operation(entry_id)

    def professional_donation(self, donation_id):
        return _application.load_surface_donation_professional("monetary", donation_id)

    def professional_inkind_donation(self, donation_id):
        return _application.load_surface_donation_professional("inkind", donation_id)

    def trial_balance(self, as_of=None):
        return _application.get_professional_trial_balance(as_of)

    def bank_accounts(self):
        return _application.list_surface_bank_accounts()

    def create_bank_account(self, payload):
        return _application.create_surface_bank_account(
            payload.get("institution_name"), payload.get("account_identifier"), payload.get("currency", "MXN"),
        )

    def import_bank_csv(self, payload):
        return _application.import_surface_bank_csv(
            payload.get("bank_account_id"), payload.get("source_name"), payload.get("content"),
        )

    def create_reconciliation(self, payload):
        return _application.create_surface_reconciliation(
            payload.get("bank_account_id"), payload.get("statement_id"), payload.get("as_of"),
        )

    def match_bank_transaction(self, payload):
        return _application.match_surface_bank_transaction(
            payload.get("reconciliation_id"), payload.get("bank_transaction_id"), payload.get("journal_line_id"),
        )

    def revoke_bank_match(self, match_id, payload):
        return _application.revoke_surface_bank_match(match_id, payload.get("reason"))

    def reconciliation(self, reconciliation_id):
        return _application.load_surface_reconciliation(reconciliation_id)

    def funds(self):
        return _application.list_surface_funds()

    def donations(self):
        return _application.list_surface_donations()

    def create_donation(self, payload):
        return _application.create_surface_donation(payload)

    def create_inkind_donation(self, payload):
        return _application.create_surface_inkind_donation(payload)

    def create_fund(self, payload):
        return _application.create_surface_fund(payload)

    def create_funding_source(self, payload):
        return _application.create_surface_funding_source(payload)

    def fund_balance(self, fund_id, as_of=None):
        return _application.get_surface_fund_balance(fund_id, as_of)

    def fund_traceability(self, fund_id, as_of):
        return _application.get_surface_fund_traceability(fund_id, as_of)

    def funding_sources(self):
        return _application.list_surface_funding_sources()

    def fund_candidates(self, kind):
        return _application.list_surface_fund_candidates(kind)

    def record_fund_receipt(self, payload):
        return _application.record_surface_fund_receipt(payload)

    def record_fund_application(self, payload):
        return _application.record_surface_fund_application(payload)

    def bank_transfer(self, payload):
        return _application.execute_surface_bank_transfer(
            payload.get("source_bank_account_id"), payload.get("destination_bank_account_id"),
            payload.get("amount"), payload.get("posting_date"), payload.get("description"),
        )

    @property
    def pending_count(self):
        return len(self._pending)

    def _require_pending(self, token):
        if type(token) is not str or not token:
            raise ValueError("preview token is required")
        try:
            return self._pending[token]
        except KeyError as exc:
            raise LookupError("prepared accounting decision not found") from exc


__all__ = ["LocalPresentationController"]
