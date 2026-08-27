"""Pure, reviewable manifest for versioned fiscal-rule source data.

A manifest describes rule data for one exact FiscalContext and materializes it
into governed FiscalRuleRegistration values. It does not install rules, open a
database, calculate taxes, choose accounts, or touch legacy templates.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Tuple

from . import fiscal_rule_registry as _registry
from . import fiscal_rules as _fiscal_rules


@dataclass(frozen=True)
class FiscalRuleSetEntry:
    rule_key: str
    effective_from: date
    value: Decimal
    unit: str
    source_ref: str


@dataclass(frozen=True)
class FiscalRuleSetManifest:
    set_key: str
    version: str
    context: _fiscal_rules.FiscalContext
    entries: Tuple[FiscalRuleSetEntry, ...]


def _require_nonempty_string(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _validate_context(context):
    if not isinstance(context, _fiscal_rules.FiscalContext):
        raise TypeError("manifest.context must be a FiscalContext")
    _require_nonempty_string(context.jurisdiction, "manifest.context.jurisdiction")
    _require_nonempty_string(context.regime, "manifest.context.regime")
    _require_nonempty_string(context.entity_type, "manifest.context.entity_type")


def _validate_entry(entry, index):
    if not isinstance(entry, FiscalRuleSetEntry):
        raise TypeError(f"manifest.entries[{index}] must be a FiscalRuleSetEntry")
    _require_nonempty_string(entry.rule_key, f"manifest.entries[{index}].rule_key")
    if type(entry.effective_from) is not date:
        raise TypeError(f"manifest.entries[{index}].effective_from must be datetime.date")
    if not isinstance(entry.value, Decimal):
        raise TypeError(f"manifest.entries[{index}].value must be Decimal")
    if not entry.value.is_finite():
        raise ValueError(f"manifest.entries[{index}].value must be finite")
    if entry.value < Decimal("0"):
        raise ValueError(f"manifest.entries[{index}].value must not be negative")
    _require_nonempty_string(entry.unit, f"manifest.entries[{index}].unit")
    _require_nonempty_string(entry.source_ref, f"manifest.entries[{index}].source_ref")


def materialize_fiscal_rule_set(manifest):
    """Validate one manifest and return governed registrations in authored order."""
    if not isinstance(manifest, FiscalRuleSetManifest):
        raise TypeError("manifest must be a FiscalRuleSetManifest")

    _require_nonempty_string(manifest.set_key, "manifest.set_key")
    _require_nonempty_string(manifest.version, "manifest.version")
    _validate_context(manifest.context)

    if not isinstance(manifest.entries, tuple):
        raise TypeError("manifest.entries must be a tuple")
    if not manifest.entries:
        raise ValueError("manifest.entries must not be empty")

    latest_start_by_rule = {}
    unit_by_rule = {}
    registrations = []

    for index, entry in enumerate(manifest.entries):
        _validate_entry(entry, index)

        if entry.rule_key in latest_start_by_rule:
            previous_start = latest_start_by_rule[entry.rule_key]
            if entry.effective_from == previous_start:
                raise ValueError(
                    f"duplicate fiscal rule start for {entry.rule_key!r}: "
                    f"{entry.effective_from.isoformat()}"
                )
            if entry.effective_from < previous_start:
                raise ValueError(
                    f"fiscal rule versions must be in increasing authored order "
                    f"for {entry.rule_key!r}"
                )

        if entry.rule_key in unit_by_rule and unit_by_rule[entry.rule_key] != entry.unit:
            raise ValueError(
                f"fiscal rule unit cannot drift within manifest for {entry.rule_key!r}"
            )

        latest_start_by_rule[entry.rule_key] = entry.effective_from
        unit_by_rule.setdefault(entry.rule_key, entry.unit)

        registrations.append(
            _registry.FiscalRuleRegistration(
                rule_key=entry.rule_key,
                context=manifest.context,
                effective_from=entry.effective_from,
                value=entry.value,
                unit=entry.unit,
                source_ref=entry.source_ref,
            )
        )

    return tuple(registrations)


__all__ = [
    "FiscalRuleSetEntry",
    "FiscalRuleSetManifest",
    "materialize_fiscal_rule_set",
]
