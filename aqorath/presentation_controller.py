"""Framework-neutral local presentation controller for AQR-005.

Pending tokens are ephemeral UI state only. They never represent posted accounting
truth and may disappear on process restart without changing SQLite.
"""

import secrets

from . import surface_application as _application


class LocalPresentationController:
    def __init__(self):
        self._pending = {}

    def capabilities(self):
        return {
            "operations": [
                {"key": item.key, "label": item.label}
                for item in _application.list_common_operation_kinds()
            ],
            "entity": _application.get_surface_entity(),
            "views": ("common", "professional"),
        }

    def prepare(self, operation_key, amount, posting_date):
        prepared = _application.prepare_common_operation(
            operation_key,
            amount,
            posting_date,
        )
        token = secrets.token_urlsafe(24)
        while token in self._pending:
            token = secrets.token_urlsafe(24)
        self._pending[token] = prepared
        return {
            "token": token,
            "preview": _application.common_preview(prepared),
        }

    def professional_preview(self, token):
        prepared = self._require_pending(token)
        return _application.professional_preview(prepared)

    def confirm(self, token):
        prepared = self._require_pending(token)
        result = _application.confirm_and_post(prepared)
        del self._pending[token]
        return {
            "entry_id": result.entry_id,
            "audit_event_id": result.audit_event_id,
            "state": result.state,
        }

    def cancel(self, token):
        self._require_pending(token)
        del self._pending[token]
        return {"cancelled": True}

    def professional_operation(self, entry_id):
        return _application.load_professional_operation(entry_id)

    def trial_balance(self, as_of=None):
        return _application.get_professional_trial_balance(as_of)

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
