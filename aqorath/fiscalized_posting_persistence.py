"""Atomic fiscalized posting + audit persistence — Phase 5AF.2 / 5AK.2.

Persists one already-confirmed FiscalizedPostingInstruction and its immutable fiscal
audit snapshot in the same ORM session and the same commit. Accounting staging is
delegated to aqorath.core so this module does not become a second posting engine.
Additional fiscal effects are persisted as ordered child audit metadata; the
historical v4 parent record remains the projection of effect zero.
"""

from . import core as _core
from . import fiscal_posting_audit as _audit
from . import fiscalized_posting as _posting
from . import models as _models
from . import storage as _storage


def _build_entry_payload(instruction):
    return {
        "description": instruction.description,
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in instruction.lines
        ],
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


def execute_fiscalized_posting_with_audit(instruction):
    """Persist confirmed accounting truth and every fiscal provenance atomically."""
    if not isinstance(instruction, _posting.FiscalizedPostingInstruction):
        raise TypeError(
            "execute_fiscalized_posting_with_audit requires FiscalizedPostingInstruction"
        )

    audit_snapshot = _audit.create_fiscal_posting_audit_snapshot(instruction)
    entry_payload = _build_entry_payload(instruction)

    session = None
    try:
        with _storage.get_session() as session:
            journal_entry, error = _core._stage_entry_in_session(session, entry_payload)
            if error is not None:
                session.rollback()
                return {"ok": False, "error": error}
            if journal_entry is None or journal_entry.id is None:
                session.rollback()
                return {"ok": False, "error": "accounting staging returned no JournalEntry identity"}

            audit_record = _build_audit_record(audit_snapshot, journal_entry.id)
            session.add(audit_record)

            if audit_snapshot.provenance.additional_fiscal_effects:
                session.flush()
                if audit_record.id is None:
                    raise RuntimeError("fiscal audit staging returned no audit record identity")
                for effect_record in _build_additional_effect_records(
                    audit_snapshot,
                    audit_record.id,
                ):
                    session.add(effect_record)

            session.commit()
            return {"ok": True, "entry_id": journal_entry.id}
    except Exception as exc:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        return {"ok": False, "error": f"Error persisting fiscalized entry with audit: {exc}"}


__all__ = ["execute_fiscalized_posting_with_audit"]
