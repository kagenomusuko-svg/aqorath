"""Atomic persistence adapter for the AQR-004 ordinary accounting use case.

This is deliberately an adapter, not a posting engine. It converts the existing
``PostingInstruction`` with the existing posting payload adapter, stages the entry
through ``core._stage_entry_in_session`` and appends one general ``AuditEvent`` in
the same transaction. Period, ledger and persistence invariants therefore remain
owned by their existing authorities.

AQR-006 reuses ``stage_posting_with_audit`` so additional operational metadata can
be staged before the same single commit; the original public executor remains the
transaction-owning wrapper for ordinary operations.

AQR-006 may also request a line-granular expansion of an already confirmed line
(for example one CxC credit of 1,000 materialized as 600 + 400). Expansion never
changes account identity, role, side or total amount. The default AQR-004 path keeps
its original exact-cardinality contract.
"""

from datetime import datetime, timezone
from decimal import Decimal

from . import accounting_decision as _decision
from . import audit_event_repository as _audit_repository
from . import core as _core
from . import entity_repository as _entity_repository
from . import posting as _posting
from . import posting_execution as _posting_execution
from . import storage as _storage
from .audit_event import AuditEvent


class AccountingOperationPersistenceError(RuntimeError):
    """The canonical persistence boundary rejected a prepared operation."""


def _line_identity_matches(posting_line, confirmation_line):
    return (
        posting_line.account_role == confirmation_line.account_role
        and posting_line.account_id == confirmation_line.account_id
        and posting_line.account_code == confirmation_line.account_code
        and posting_line.account_name == confirmation_line.account_name
    )


def _posting_line_side_amount(posting_line, confirmation_line):
    if not _line_identity_matches(posting_line, confirmation_line):
        return None
    if confirmation_line.side == "debit":
        if posting_line.debit <= Decimal("0") or posting_line.credit != Decimal("0"):
            return None
        return posting_line.debit
    if confirmation_line.side == "credit":
        if posting_line.credit <= Decimal("0") or posting_line.debit != Decimal("0"):
            return None
        return posting_line.credit
    return None


def _line_matches_confirmed(posting_line, confirmation_line):
    amount = _posting_line_side_amount(posting_line, confirmation_line)
    return amount == confirmation_line.amount


def _validate_exact_instruction(instruction, snapshot):
    if len(instruction.lines) != len(snapshot.lines):
        raise ValueError("posting instruction changed confirmed line cardinality")
    for posting_line, confirmation_line in zip(instruction.lines, snapshot.lines):
        if not _line_matches_confirmed(posting_line, confirmation_line):
            raise ValueError("posting instruction changed confirmed accounting truth")


def _validate_expanded_instruction(instruction, snapshot):
    """Allow only exact same-semantic subdivision of confirmed ledger effects."""
    unmatched = list(instruction.lines)
    for confirmation_line in snapshot.lines:
        matches = []
        remaining = []
        for posting_line in unmatched:
            amount = _posting_line_side_amount(posting_line, confirmation_line)
            if amount is None:
                remaining.append(posting_line)
            else:
                matches.append((posting_line, amount))
        if not matches:
            raise ValueError("expanded posting omitted a confirmed accounting effect")
        total = sum((amount for _, amount in matches), Decimal("0"))
        if total != confirmation_line.amount:
            raise ValueError("expanded posting changed a confirmed accounting amount")
        unmatched = remaining
    if unmatched:
        raise ValueError("expanded posting introduced an unconfirmed accounting effect")


def _validate_instruction(
    instruction,
    confirmed_decision,
    *,
    allow_confirmed_line_expansion=False,
):
    if not isinstance(instruction, _posting.PostingInstruction):
        raise TypeError("instruction must be PostingInstruction")
    if not isinstance(
        confirmed_decision,
        _decision.ConfirmedAccountingDecision,
    ):
        raise TypeError("confirmed_decision must be ConfirmedAccountingDecision")
    if type(allow_confirmed_line_expansion) is not bool:
        raise TypeError("allow_confirmed_line_expansion must be bool")

    snapshot = confirmed_decision.confirmed_proposal.snapshot
    if instruction.description != snapshot.explanation:
        raise ValueError("posting instruction changed confirmed description")
    if allow_confirmed_line_expansion:
        _validate_expanded_instruction(instruction, snapshot)
    else:
        _validate_exact_instruction(instruction, snapshot)


def _audit_details(confirmed_decision, entry_id):
    decision = confirmed_decision.decision
    explanation = decision.explanation
    return {
        "entry_id": entry_id,
        "decision": {
            "fact": {
                "type": decision.fact.type,
                "amount": str(decision.fact.amount),
                "payment_method": decision.fact.payment_method,
            },
            "posting_date": decision.posting_date.isoformat(),
            "rule_id": decision.rule_id,
            "rule_version": decision.rule_version,
            "consent": "explicit_confirmation",
            "explanation": {
                "effects": [
                    {
                        "account_role": effect.account_role,
                        "side": effect.side,
                        "amount": str(effect.amount),
                    }
                    for effect in explanation.effects
                ],
                "concepts": list(explanation.concepts),
                "professional_summary": explanation.professional_summary,
            },
        },
    }


def stage_posting_with_audit(
    session,
    instruction,
    confirmed_decision,
    *,
    allow_confirmed_line_expansion=False,
):
    """Stage posted ledger truth + general audit without committing caller session."""
    _validate_instruction(
        instruction,
        confirmed_decision,
        allow_confirmed_line_expansion=allow_confirmed_line_expansion,
    )
    payload = _posting_execution.build_posting_payload(instruction)
    payload.update(
        date=confirmed_decision.decision.posting_date,
        state="posted",
    )

    journal_entry, error = _core._stage_entry_in_session(session, payload)
    if error is not None:
        raise AccountingOperationPersistenceError(error)
    if journal_entry is None or journal_entry.id is None:
        raise AccountingOperationPersistenceError(
            "accounting staging returned no JournalEntry identity"
        )

    entity = _entity_repository.load_active_entity(session)
    if entity is None or entity.id is None:
        raise AccountingOperationPersistenceError(
            "active Entity is required for accounting audit evidence"
        )

    audit_event = _audit_repository.stage_audit_event(
        session,
        AuditEvent(
            id=None,
            entity_id=entity.id,
            event_type="entry_posted",
            timestamp=datetime.now(timezone.utc),
            details=_audit_details(confirmed_decision, journal_entry.id),
        ),
    )
    return _decision.AccountingOperationResult(
        entry_id=journal_entry.id,
        audit_event_id=audit_event.id,
    )


def execute_posting_with_audit(instruction, confirmed_decision):
    """Persist one confirmed ordinary decision as posted + AuditEvent atomically."""
    session = None
    try:
        with _storage.get_session() as session:
            result = stage_posting_with_audit(
                session,
                instruction,
                confirmed_decision,
            )
            session.commit()
            return result
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


__all__ = [
    "AccountingOperationPersistenceError",
    "stage_posting_with_audit",
    "execute_posting_with_audit",
]
