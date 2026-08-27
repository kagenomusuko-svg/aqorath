"""Versioned fiscal-rule authority.

This module resolves one effective-dated fiscal rule from an explicit supplied
SQLite session and explicit fiscal context. It does not calculate taxes, choose
accounts, build accounting proposals, post entries, or discover configuration.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlmodel import select

from .models import FiscalRuleVersion


@dataclass(frozen=True)
class FiscalContext:
    jurisdiction: str
    regime: str
    entity_type: str


@dataclass(frozen=True)
class ResolvedFiscalRule:
    rule_key: str
    value: Decimal
    unit: str
    effective_from: date
    effective_to: Optional[date]
    jurisdiction: str
    regime: str
    entity_type: str
    source_ref: str


def _require_nonempty_string(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_context(context):
    if not isinstance(context, FiscalContext):
        raise TypeError("context must be a FiscalContext")
    _require_nonempty_string(context.jurisdiction, "context.jurisdiction")
    _require_nonempty_string(context.regime, "context.regime")
    _require_nonempty_string(context.entity_type, "context.entity_type")


def resolve_fiscal_rule(session, rule_key, effective_date, context):
    """Resolve exactly one fiscal rule for an exact context and effective date.

    Boundaries are inclusive. ``effective_to=None`` means open-ended. There is
    intentionally no wildcard context, latest-rule fallback, hidden session, or
    ambiguity repair: missing and overlapping applicable rules fail explicitly.
    """
    _require_nonempty_string(rule_key, "rule_key")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a datetime.date")
    _validate_context(context)

    statement = select(FiscalRuleVersion).where(
        FiscalRuleVersion.rule_key == rule_key,
        FiscalRuleVersion.jurisdiction == context.jurisdiction,
        FiscalRuleVersion.regime == context.regime,
        FiscalRuleVersion.entity_type == context.entity_type,
        FiscalRuleVersion.effective_from <= effective_date,
        or_(
            FiscalRuleVersion.effective_to.is_(None),
            FiscalRuleVersion.effective_to >= effective_date,
        ),
    )

    matches = list(session.exec(statement).all())
    if not matches:
        raise LookupError(
            "No fiscal rule found for "
            f"rule_key={rule_key!r}, effective_date={effective_date.isoformat()!r}, "
            f"jurisdiction={context.jurisdiction!r}, regime={context.regime!r}, "
            f"entity_type={context.entity_type!r}"
        )
    if len(matches) != 1:
        raise ValueError(
            "Fiscal rule resolution is ambiguous: multiple overlapping versions "
            f"apply to rule_key={rule_key!r} on {effective_date.isoformat()}"
        )

    record = matches[0]
    value = Decimal(record.value)

    return ResolvedFiscalRule(
        rule_key=record.rule_key,
        value=value,
        unit=record.unit,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        jurisdiction=record.jurisdiction,
        regime=record.regime,
        entity_type=record.entity_type,
        source_ref=record.source_ref,
    )


__all__ = [
    "FiscalContext",
    "ResolvedFiscalRule",
    "resolve_fiscal_rule",
]
