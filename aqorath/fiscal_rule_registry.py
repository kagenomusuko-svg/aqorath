"""Governed write authority for versioned fiscal rules.

The registry controls creation of fiscal-rule history in the schema introduced
by Phase 5A. It does not contain legal/tax values, calculate taxes, choose
accounts, build proposals, or discover a database/session.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import select

from . import fiscal_rules as _fiscal_rules
from . import models as _models


@dataclass(frozen=True)
class FiscalRuleRegistration:
    rule_key: str
    context: _fiscal_rules.FiscalContext
    effective_from: date
    value: Decimal
    unit: str
    source_ref: str


def _require_nonempty_string(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_context(context):
    if not isinstance(context, _fiscal_rules.FiscalContext):
        raise TypeError("context must be a FiscalContext")
    _require_nonempty_string(context.jurisdiction, "context.jurisdiction")
    _require_nonempty_string(context.regime, "context.regime")
    _require_nonempty_string(context.entity_type, "context.entity_type")


def _validate_registration(registration):
    if not isinstance(registration, FiscalRuleRegistration):
        raise TypeError("registration must be a FiscalRuleRegistration")

    _require_nonempty_string(registration.rule_key, "registration.rule_key")
    _validate_context(registration.context)

    if type(registration.effective_from) is not date:
        raise TypeError("registration.effective_from must be a datetime.date")
    if not isinstance(registration.value, Decimal):
        raise TypeError("registration.value must be Decimal")
    if not registration.value.is_finite():
        raise ValueError("registration.value must be finite")
    if registration.value < Decimal("0"):
        raise ValueError("registration.value must not be negative")

    _require_nonempty_string(registration.unit, "registration.unit")
    _require_nonempty_string(registration.source_ref, "registration.source_ref")


def _history_statement(rule_key, context):
    return (
        select(_models.FiscalRuleVersion)
        .where(
            _models.FiscalRuleVersion.rule_key == rule_key,
            _models.FiscalRuleVersion.jurisdiction == context.jurisdiction,
            _models.FiscalRuleVersion.regime == context.regime,
            _models.FiscalRuleVersion.entity_type == context.entity_type,
        )
        .order_by(_models.FiscalRuleVersion.effective_from)
    )


def _load_records(session, rule_key, context):
    return list(session.exec(_history_statement(rule_key, context)).all())


def _validate_existing_history(records):
    for record in records:
        if record.effective_to is not None and record.effective_to < record.effective_from:
            raise ValueError("Fiscal rule history is corrupt: invalid effective interval")

    for previous, current in zip(records, records[1:]):
        if previous.effective_to is None:
            raise ValueError(
                "Fiscal rule history is ambiguous: multiple/open overlapping versions"
            )
        if previous.effective_to >= current.effective_from:
            raise ValueError("Fiscal rule history contains overlapping versions")


def _resolved(record):
    return _fiscal_rules.ResolvedFiscalRule(
        rule_key=record.rule_key,
        value=Decimal(record.value),
        unit=record.unit,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        jurisdiction=record.jurisdiction,
        regime=record.regime,
        entity_type=record.entity_type,
        source_ref=record.source_ref,
    )


def get_fiscal_rule_history(session, rule_key, context):
    """Return immutable ordered history for one exact fiscal rule scope."""
    _require_nonempty_string(rule_key, "rule_key")
    _validate_context(context)

    records = _load_records(session, rule_key, context)
    _validate_existing_history(records)
    return tuple(_resolved(record) for record in records)


def register_fiscal_rule_version(session, registration):
    """Append one governed fiscal-rule version transactionally.

    The operation is monotonic within one exact rule/context scope. If the
    current latest version is open-ended, it is closed on the calendar day
    immediately before the new version starts. Existing value/provenance/start
    fields are never rewritten. Missing legal rule data is never invented.
    """
    _validate_registration(registration)

    records = _load_records(session, registration.rule_key, registration.context)
    _validate_existing_history(records)

    latest = records[-1] if records else None
    if latest is not None:
        if registration.effective_from <= latest.effective_from:
            raise ValueError(
                "New fiscal rule version must start after the latest version"
            )
        if registration.unit != latest.unit:
            raise ValueError(
                "Fiscal rule unit cannot change within the same rule/context scope"
            )
        if (
            latest.effective_to is not None
            and registration.effective_from <= latest.effective_to
        ):
            raise ValueError("New fiscal rule version would overlap existing history")

    new_record = _models.FiscalRuleVersion(
        rule_key=registration.rule_key,
        jurisdiction=registration.context.jurisdiction,
        regime=registration.context.regime,
        entity_type=registration.context.entity_type,
        effective_from=registration.effective_from,
        effective_to=None,
        value=str(registration.value),
        unit=registration.unit,
        source_ref=registration.source_ref,
    )

    try:
        if latest is not None and latest.effective_to is None:
            latest.effective_to = registration.effective_from - timedelta(days=1)
            session.add(latest)
        session.add(new_record)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return _resolved(new_record)


__all__ = [
    "FiscalRuleRegistration",
    "register_fiscal_rule_version",
    "get_fiscal_rule_history",
]
