"""Pure Entity, EntityProfile and FiscalProfile domain values.

Phase 6A keeps legal/economic identity independent from effective-dated fiscal
history.  This module deliberately has no persistence or fiscal-rule authority.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


_ALLOWED_ECONOMIC_PURPOSES = frozenset({"lucrativo", "no_lucrativo"})
_ALLOWED_LEGAL_PERSONALITIES = frozenset({"persona_fisica", "persona_moral"})


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_string_tuple(value, field_name):
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    seen = set()
    for item in value:
        _require_nonempty_text(item, f"{field_name} item")
        if item in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(item)


@dataclass(frozen=True)
class EntityProfile:
    """Immutable economic/capability profile for one accounting Entity."""

    economic_purpose: str
    is_donor_authorized: bool
    special_capabilities: tuple[str, ...]
    modules_enabled: tuple[str, ...]

    def __post_init__(self):
        if self.economic_purpose not in _ALLOWED_ECONOMIC_PURPOSES:
            raise ValueError(
                "economic_purpose must be 'lucrativo' or 'no_lucrativo'"
            )
        if type(self.is_donor_authorized) is not bool:
            raise TypeError("is_donor_authorized must be bool")
        _require_string_tuple(self.special_capabilities, "special_capabilities")
        _require_string_tuple(self.modules_enabled, "modules_enabled")


@dataclass(frozen=True)
class Entity:
    """Immutable legal/economic identity for the accounting entity."""

    id: Optional[int]
    name: str
    rfc: Optional[str]
    legal_personality: str
    legal_form: str
    profile: EntityProfile
    is_active: bool

    def __post_init__(self):
        _require_optional_id(self.id, "id")
        _require_nonempty_text(self.name, "name")
        if self.rfc is not None:
            _require_nonempty_text(self.rfc, "rfc")
        if self.legal_personality not in _ALLOWED_LEGAL_PERSONALITIES:
            raise ValueError(
                "legal_personality must be 'persona_fisica' or 'persona_moral'"
            )
        _require_nonempty_text(self.legal_form, "legal_form")
        if not isinstance(self.profile, EntityProfile):
            raise TypeError("profile must be EntityProfile")
        if type(self.is_active) is not bool:
            raise TypeError("is_active must be bool")


@dataclass(frozen=True)
class FiscalProfile:
    """One immutable, explicit, effective-dated fiscal profile interval."""

    id: Optional[int]
    entity_id: int
    jurisdiction: str
    fiscal_regime_code: str
    tax_characteristics: tuple[str, ...]
    effective_from: date
    effective_to: Optional[date]

    def __post_init__(self):
        _require_optional_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_nonempty_text(self.jurisdiction, "jurisdiction")
        _require_nonempty_text(self.fiscal_regime_code, "fiscal_regime_code")
        _require_string_tuple(self.tax_characteristics, "tax_characteristics")
        if type(self.effective_from) is not date:
            raise TypeError("effective_from must be date")
        if self.effective_to is not None:
            if type(self.effective_to) is not date:
                raise TypeError("effective_to must be date or None")
            if self.effective_to < self.effective_from:
                raise ValueError("effective_to cannot precede effective_from")
