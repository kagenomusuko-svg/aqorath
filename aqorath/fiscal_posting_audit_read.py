"""Read-only persisted fiscal posting audit boundary — Phase 5AH.2.

Reconstructs the immutable fiscal audit snapshot associated with one JournalEntry
from the supplied ORM session. Persisted metadata is treated as evidence: it is
parsed and validated, never recalculated, rerounded, resolved, or posted.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlmodel import select

from . import fiscal_posting_audit as _audit
from . import fiscalized_confirmation as _confirmation
from . import models as _models


def _decimal_exact(text, field_name):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{field_name} must contain exact Decimal text")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid persisted Decimal for {field_name}: {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"persisted Decimal for {field_name} must be finite")
    return value


def _build_provenance(record):
    return _confirmation.FiscalizedConfirmationProvenance(
        fact_type=record.fact_type,
        fact_amount=_decimal_exact(record.fact_amount, "fact_amount"),
        payment_method=record.payment_method,
        effective_date=record.effective_date,
        jurisdiction=record.jurisdiction,
        regime=record.regime,
        entity_type=record.entity_type,
        rule_key=record.rule_key,
        base=_decimal_exact(record.base, "base"),
        rate=_decimal_exact(record.rate, "rate"),
        unit=record.unit,
        rule_effective_from=record.rule_effective_from,
        rule_effective_to=record.rule_effective_to,
        rule_source_ref=record.rule_source_ref,
        exact_fiscal_amount=_decimal_exact(
            record.exact_fiscal_amount,
            "exact_fiscal_amount",
        ),
        rounding_policy_key=record.rounding_policy_key,
        rounding_quantizer=_decimal_exact(
            record.rounding_quantizer,
            "rounding_quantizer",
        ),
        rounding_mode=record.rounding_mode,
        rounding_source_ref=record.rounding_source_ref,
        rounded_fiscal_amount=_decimal_exact(
            record.rounded_fiscal_amount,
            "rounded_fiscal_amount",
        ),
        amount_basis=record.amount_basis,
        adjustment_role=record.adjustment_role,
        fiscal_role=record.fiscal_role,
        fiscal_side=record.fiscal_side,
    )


def _build_omitted_zero_line(record):
    fields = (
        record.omitted_zero_account_role,
        record.omitted_zero_account_id,
        record.omitted_zero_account_code,
        record.omitted_zero_account_name,
        record.omitted_zero_side,
        record.omitted_zero_amount,
    )
    if all(value is None for value in fields):
        return None
    if any(value is None for value in fields):
        raise ValueError("persisted omitted-zero fiscal metadata must be all-or-none")

    return _audit.FiscalPostingAuditOmittedLine(
        account_role=record.omitted_zero_account_role,
        account_id=record.omitted_zero_account_id,
        account_code=record.omitted_zero_account_code,
        account_name=record.omitted_zero_account_name,
        side=record.omitted_zero_side,
        amount=_decimal_exact(record.omitted_zero_amount, "omitted_zero_amount"),
    )


def load_fiscal_posting_audit_snapshot(session, entry_id):
    """Load one validated immutable fiscal audit snapshot from the supplied session."""
    if not isinstance(entry_id, int) or isinstance(entry_id, bool):
        raise TypeError("entry_id must be an integer")
    if entry_id <= 0:
        raise ValueError("entry_id must be greater than zero")

    entry = session.get(_models.JournalEntry, entry_id)
    if entry is None:
        raise LookupError(f"JournalEntry {entry_id} does not exist")
    if not isinstance(entry.concept, str) or not entry.concept.strip():
        raise ValueError("JournalEntry concept cannot supply an empty audit description")

    records = session.exec(
        select(_models.FiscalPostingAuditRecord).where(
            _models.FiscalPostingAuditRecord.entry_id == entry_id
        )
    ).all()
    if not records:
        raise LookupError(f"fiscal audit record for JournalEntry {entry_id} does not exist")
    if len(records) != 1:
        raise ValueError(f"multiple fiscal audit records found for JournalEntry {entry_id}")

    record = records[0]
    return _audit.FiscalPostingAuditSnapshot(
        description=entry.concept,
        provenance=_build_provenance(record),
        zero_fiscal_line_policy=record.zero_fiscal_line_policy,
        omitted_zero_fiscal_line=_build_omitted_zero_line(record),
    )


__all__ = ["load_fiscal_posting_audit_snapshot"]
