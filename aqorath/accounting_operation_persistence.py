"""Atomic persistence adapter for the AQR-004 ordinary accounting use case.

This is deliberately an adapter, not a posting engine.  It converts the existing
``PostingInstruction`` with the existing posting payload adapter, stages the entry
through ``core._stage_entry_in_session`` and appends one general ``AuditEvent`` in
the same transaction.  Period, ledger and persistence invariants therefore remain
owned by their existing authorities.
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


def _line_matches_confirmed(posting_line, confirmation_line):
    if (
        posting_line.account_role != confirmation_line.account_role
        or posting_line.account_id != confirmation_line.account_id
        or posting_line.account_code != confirmation_line.account_code
        or posting_line.account_name != confirmation_line.account_name
    ):
        return False
    if confirmation_line.side == "debit":
        return (
            posting_line.debit == confirmation_line.amount
            and posting_line.credit == Decimal("0")
        )
    if confirmation_line.side == "credit":
        return (
            posting_line.debit == Decimal("0")
            and posting_line.credit == confirmation_line.amount
        )
    return False


def _validate_instruction(instruction, confirmed_decision):
    if not isinstance(instruction, _posting.PostingInstruction):
        raise TypeError("instruction must be PostingInstruction")
    if not isinstance(
        confirmed_decision,
        _decision.ConfirmedAccountingDecision,
    ):
        raise TypeError("confirmed_decision must be ConfirmedAccountingDecision")

    snapshot = confirmed_decision.confirmed_proposal.snapshot
    if instruction.description != snapshot.explanation:
        raise ValueError("posting instruction changed confirmed description")
    if len(instruction.lines) != len(snapshot.lines):
        raise ValueError("posting instruction changed confirmed line cardinality")
    for posting_line, confirmation_line in zip(instruction.lines, snapshot.lines):
        if not _line_matches_confirmed(posting_line, confirmation_line):
            raise ValueError("posting instruction changed confirmed accounting truth")


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


def execute_posting_with_audit(instruction, confirmed_decision):
    """Persist one confirmed ordinary decision as posted + AuditEvent atomically."""
    _validate_instruction(instruction, confirmed_decision)
    payload = _posting_execution.build_posting_payload(instruction)
    payload.update(
        date=confirmed_decision.decision.posting_date,
        state="posted",
    )

    session = None
    try:
        with _storage.get_session() as session:
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
            session.commit()
            return _decision.AccountingOperationResult(
                entry_id=journal_entry.id,
                audit_event_id=audit_event.id,
            )
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


__all__ = [
    "AccountingOperationPersistenceError",
    "execute_posting_with_audit",
]
