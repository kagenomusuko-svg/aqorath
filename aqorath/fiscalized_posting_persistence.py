"""Atomic fiscalized posting + audit persistence — Phase 5AF.2 / 5AK.2 / AQR-011.

Persists one already-confirmed FiscalizedPostingInstruction and its immutable
fiscal audit snapshot in the same ORM session and the same commit. Accounting
staging is delegated to aqorath.core so this module does not become a second
posting engine. Additional fiscal effects are persisted as ordered child audit
metadata; the historical v4 parent record remains the projection of effect zero.

AQR-011 exposes the same staging operation to a caller-owned session so general
applicability AuditEvent evidence can participate in the one transaction. A
caller may also contribute an independently balanced set of already-resolved
accounting lines; those lines are composed into the payload before the single
canonical JournalEntry is staged. This is used by AQR-012 for COGS/inventory and
does not alter fiscal provenance or create a second posting authority.
"""

from decimal import Decimal, InvalidOperation

from . import core as _core
from . import fiscal_posting_audit as _audit
from . import fiscalized_posting as _posting
from . import models as _models
from . import storage as _storage


class FiscalizedPostingPersistenceError(RuntimeError):
    """Canonical fiscalized staging rejected the prepared persistence payload."""


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be Decimal-compatible") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return result


def _balanced_additional_lines(lines):
    if lines is None:
        return []
    if not isinstance(lines, (tuple, list)):
        raise TypeError("additional_balanced_lines must be a tuple/list or None")
    normalized = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise TypeError("additional_balanced_lines entries must be dict")
        account_code = line.get("account_code")
        if not isinstance(account_code, str) or not account_code.strip():
            raise ValueError("additional line account_code must be non-empty text")
        debit = _decimal(line.get("debit", Decimal("0")), f"additional line {index} debit")
        credit = _decimal(line.get("credit", Decimal("0")), f"additional line {index} credit")
        if debit == 0 and credit == 0:
            raise ValueError("additional line must have a debit or credit amount")
        if debit > 0 and credit > 0:
            raise ValueError("additional line cannot contain both debit and credit")
        item = {
            "account_code": account_code,
            "debit": debit,
            "credit": credit,
        }
        account_id = line.get("account_id")
        if account_id is not None:
            if type(account_id) is not int or account_id <= 0:
                raise ValueError("additional line account_id must be a positive integer or None")
            item["account_id"] = account_id
        normalized.append(item)
        debit_total += debit
        credit_total += credit
    if debit_total != credit_total:
        raise ValueError("additional accounting lines must be independently balanced")
    return normalized


def _build_entry_payload(instruction, additional_balanced_lines=None):
    lines = [
        {
            "account_id": line.account_id,
            "account_code": line.account_code,
            "debit": line.debit,
            "credit": line.credit,
        }
        for line in instruction.lines
    ]
    lines.extend(_balanced_additional_lines(additional_balanced_lines))
    return {
        "description": instruction.description,
        "lines": lines,
    }


def _build_audit_record(snapshot, entry_id):
    """Map one immutable audit snapshot's primary effect to v4 metadata."""
    if not isinstance(snapshot, _audit.FiscalPostingAuditSnapshot):
        raise TypeError("snapshot must be FiscalPostingAuditSnapshot")
    if not isinstance(entry_id, int) or isinstance(entry_id, bool):
        raise TypeError("entry_id must be an integer")

    provenance = snapshot.provenance
    omitted = snapshot.omitted_zero_fiscal_line

    return _models.FiscalPostingAuditRecord(
        entry_id=entry_id,
        fact_type=provenance.fact_type,
        fact_amount=str(provenance.fact_amount),
        payment_method=provenance.payment_method,
        effective_date=provenance.effective_date,
        jurisdiction=provenance.jurisdiction,
        regime=provenance.regime,
        entity_type=provenance.entity_type,
        rule_key=provenance.rule_key,
        base=str(provenance.base),
        rate=str(provenance.rate),
        unit=provenance.unit,
        rule_effective_from=provenance.rule_effective_from,
        rule_effective_to=provenance.rule_effective_to,
        rule_source_ref=provenance.rule_source_ref,
        exact_fiscal_amount=str(provenance.exact_fiscal_amount),
        rounding_policy_key=provenance.rounding_policy_key,
        rounding_quantizer=str(provenance.rounding_quantizer),
        rounding_mode=provenance.rounding_mode,
        rounding_source_ref=provenance.rounding_source_ref,
        rounded_fiscal_amount=str(provenance.rounded_fiscal_amount),
        amount_basis=provenance.amount_basis,
        adjustment_role=provenance.adjustment_role,
        fiscal_role=provenance.fiscal_role,
        fiscal_side=provenance.fiscal_side,
        zero_fiscal_line_policy=snapshot.zero_fiscal_line_policy,
        omitted_zero_account_role=(None if omitted is None else omitted.account_role),
        omitted_zero_account_id=(None if omitted is None else omitted.account_id),
        omitted_zero_account_code=(None if omitted is None else omitted.account_code),
        omitted_zero_account_name=(None if omitted is None else omitted.account_name),
        omitted_zero_side=(None if omitted is None else omitted.side),
        omitted_zero_amount=(None if omitted is None else str(omitted.amount)),
    )


def _build_additional_effect_records(snapshot, audit_record_id):
    """Map ordered effects after effect zero to exact child audit records."""
    if not isinstance(snapshot, _audit.FiscalPostingAuditSnapshot):
        raise TypeError("snapshot must be FiscalPostingAuditSnapshot")
    if not isinstance(audit_record_id, int) or isinstance(audit_record_id, bool):
        raise TypeError("audit_record_id must be an integer")

    return tuple(
        _models.FiscalPostingAuditEffectRecord(
            audit_record_id=audit_record_id,
            position=position,
            rule_key=effect.rule_key,
            base=str(effect.base),
            rate=str(effect.rate),
            unit=effect.unit,
            rule_effective_from=effect.rule_effective_from,
            rule_effective_to=effect.rule_effective_to,
            rule_source_ref=effect.rule_source_ref,
            exact_fiscal_amount=str(effect.exact_fiscal_amount),
            rounding_policy_key=effect.rounding_policy_key,
            rounding_quantizer=str(effect.rounding_quantizer),
            rounding_mode=effect.rounding_mode,
            rounding_source_ref=effect.rounding_source_ref,
            rounded_fiscal_amount=str(effect.rounded_fiscal_amount),
            fiscal_role=effect.fiscal_role,
            fiscal_side=effect.fiscal_side,
        )
        for position, effect in enumerate(
            snapshot.provenance.additional_fiscal_effects,
            start=1,
        )
    )


def stage_fiscalized_posting_with_audit(
    session,
    instruction,
    *,
    posting_date=None,
    state=None,
    additional_balanced_lines=None,
):
    """Stage one fiscalized JournalEntry and fiscal audit without committing.

    ``posting_date`` and ``state`` are optional so the Phase 5 historical wrapper
    preserves its exact minimal payload. AQR-011 supplies the operation date and
    ``posted`` state explicitly. ``additional_balanced_lines`` is caller-owned,
    must balance independently, and is composed before the one canonical staging
    call. The caller owns commit/rollback.
    """
    if not isinstance(instruction, _posting.FiscalizedPostingInstruction):
        raise TypeError(
            "stage_fiscalized_posting_with_audit requires FiscalizedPostingInstruction"
        )
    if state is not None:
        if not isinstance(state, str) or not state.strip():
            raise ValueError("state must be non-empty text or None")

    audit_snapshot = _audit.create_fiscal_posting_audit_snapshot(instruction)
    entry_payload = _build_entry_payload(instruction, additional_balanced_lines)
    if posting_date is not None:
        entry_payload["date"] = posting_date
    if state is not None:
        entry_payload["state"] = state

    journal_entry, error = _core._stage_entry_in_session(session, entry_payload)
    if error is not None:
        raise FiscalizedPostingPersistenceError(error)
    if journal_entry is None or journal_entry.id is None:
        raise FiscalizedPostingPersistenceError(
            "accounting staging returned no JournalEntry identity"
        )

    audit_record = _build_audit_record(audit_snapshot, journal_entry.id)
    session.add(audit_record)

    additional_effects = (
        instruction.confirmed_proposal.snapshot.provenance.additional_fiscal_effects
    )
    if additional_effects:
        session.flush()
        if audit_record.id is None:
            raise RuntimeError("fiscal audit staging returned no audit record identity")
        for effect_record in _build_additional_effect_records(
            audit_snapshot,
            audit_record.id,
        ):
            session.add(effect_record)

    return journal_entry.id


def execute_fiscalized_posting_with_audit(instruction):
    """Persist confirmed accounting truth and every fiscal provenance atomically."""
    if not isinstance(instruction, _posting.FiscalizedPostingInstruction):
        raise TypeError(
            "execute_fiscalized_posting_with_audit requires FiscalizedPostingInstruction"
        )

    session = None
    try:
        with _storage.get_session() as session:
            try:
                entry_id = stage_fiscalized_posting_with_audit(session, instruction)
            except FiscalizedPostingPersistenceError as exc:
                session.rollback()
                return {"ok": False, "error": str(exc)}
            session.commit()
            return {"ok": True, "entry_id": entry_id}
    except Exception as exc:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        return {"ok": False, "error": f"Error persisting fiscalized entry with audit: {exc}"}


__all__ = [
    "FiscalizedPostingPersistenceError",
    "stage_fiscalized_posting_with_audit",
    "execute_fiscalized_posting_with_audit",
]
