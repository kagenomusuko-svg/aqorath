"""AQR-015 guided onboarding over existing entity/catalog/period authorities.

This is product composition, not a second persistence engine. The user declares
identity, fiscal profile and semantic account bindings; canonical Account rows are
materialized from the governed embedded catalog and all durable writes delegate to
existing repositories/authorities.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from sqlmodel import select

from . import application as _application
from . import storage as _storage
from .account_bindings import get_account_binding, _stage_account_binding
from .accounting_period_repository import configure_calendar, open_fiscal_year
from .catalog import load_catalog
from .catalog_persistence import ensure_canonical_accounts
from .entity import Entity, EntityProfile, FiscalProfile
from .entity_repository import _stage_entity, _stage_fiscal_profile
from .models import Account, FiscalProfileRecord


_BINDING_ROLES = (
    {"key": "bank", "label": "Banco", "required": True, "suggested_codes": ("1101",)},
    {"key": "cash", "label": "Efectivo / caja", "required": True, "suggested_codes": ("1102",)},
    {"key": "accounts_receivable", "label": "Cuentas por cobrar", "required": True, "suggested_codes": ("1103",)},
    {"key": "accounts_payable", "label": "Cuentas por pagar", "required": True, "suggested_codes": ("2101",)},
    {"key": "sales_revenue", "label": "Ingreso por ventas o servicios", "required": True, "suggested_codes": ("4201", "4202")},
    {"key": "utilities_expense", "label": "Servicios básicos", "required": True, "suggested_codes": ("5102",)},
    {"key": "inventory", "label": "Inventario", "required": False, "suggested_codes": ("1104",)},
    {"key": "cost_of_goods_sold", "label": "Costo de venta", "required": False, "suggested_codes": ("5101",)},
    {"key": "depreciation_expense", "label": "Gasto por depreciación", "required": False, "suggested_codes": ("5106",)},
    {"key": "accumulated_depreciation", "label": "Depreciación acumulada", "required": False, "suggested_codes": ("1205",)},
    {"key": "fixed_asset_furniture_equipment", "label": "Activo: mobiliario/equipo", "required": False, "suggested_codes": ("1201",)},
    {"key": "fixed_asset_computer_equipment", "label": "Activo: equipo de cómputo", "required": False, "suggested_codes": ("1202",)},
    {"key": "fixed_asset_machinery_tools", "label": "Activo: maquinaria/herramientas", "required": False, "suggested_codes": ("1203",)},
    {"key": "fixed_asset_land_buildings", "label": "Activo: terrenos/edificios", "required": False, "suggested_codes": ("1204",)},
    {"key": "donation_income", "label": "Ingreso por donativo", "required": False, "suggested_codes": ("4101", "4102", "4103", "4104")},
    {"key": "professional_services_expense", "label": "Servicios profesionales", "required": False, "suggested_codes": ("5303",)},
    {"key": "freight_expense", "label": "Fletes/transporte", "required": False, "suggested_codes": ("5105",)},
)
_ROLE_KEYS = frozenset(item["key"] for item in _BINDING_ROLES)
_REQUIRED_ROLE_KEYS = frozenset(item["key"] for item in _BINDING_ROLES if item["required"])


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value, field):
    if value is None or value == "":
        return None
    return _text(value, field)


def _string_tuple(value, field):
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field} must be a list")
    result = tuple(_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def _iso_date(value, field):
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field} must be YYYY-MM-DD text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _catalog_options(economic_purpose=None):
    document = load_catalog()
    accounts = document.get("accounts", {})
    if economic_purpose == "no_lucrativo":
        preferred = "name_osc"
    else:
        preferred = "name_comercial"
    result = []
    for code in sorted(accounts):
        meta = accounts[code]
        result.append({
            "code": code,
            "name": meta.get(preferred) or meta.get("name_comercial") or meta.get("name_osc") or code,
            "nature": meta.get("naturaleza"),
            "type": meta.get("tipo"),
            "description": meta.get("descripcion"),
        })
    return result


def _current_bindings(session):
    result = {}
    for role in _ROLE_KEYS:
        code = get_account_binding(session, role)
        if code is not None:
            result[role] = code
    return result


def get_surface_onboarding():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        bindings = _current_bindings(session) if entity is not None else {}
        fiscal = []
        if entity is not None and entity.id is not None:
            rows = session.exec(
                select(FiscalProfileRecord)
                .where(FiscalProfileRecord.entity_id == entity.id)
                .order_by(FiscalProfileRecord.effective_from, FiscalProfileRecord.id)
            ).all()
            fiscal = [
                {
                    "id": row.id,
                    "jurisdiction": row.jurisdiction,
                    "fiscal_regime_code": row.fiscal_regime_code,
                    "effective_from": row.effective_from.isoformat(),
                    "effective_to": None if row.effective_to is None else row.effective_to.isoformat(),
                }
                for row in rows
            ]

    return {
        "configured": entity is not None,
        "entity": None if entity is None else asdict(entity),
        "fiscal_profiles": fiscal,
        "bindings": bindings,
        "binding_roles": list(_BINDING_ROLES),
        "accounts": _catalog_options(None if entity is None else entity.profile.economic_purpose),
        "limits": {
            "monoentity": True,
            "currency": "MXN",
            "internet_required": False,
            "binding_codes_are_select_values_not_user-entered_fields": True,
        },
    }


def configure_surface_onboarding(payload):
    if not isinstance(payload, dict):
        raise TypeError("onboarding payload must be an object")

    entity_profile = EntityProfile(
        economic_purpose=_text(payload.get("economic_purpose"), "economic_purpose"),
        is_donor_authorized=payload.get("is_donor_authorized", False),
        special_capabilities=_string_tuple(payload.get("special_capabilities"), "special_capabilities"),
        modules_enabled=_string_tuple(payload.get("modules_enabled"), "modules_enabled"),
    )
    entity = Entity(
        id=None,
        name=_text(payload.get("name"), "name"),
        rfc=_optional_text(payload.get("rfc"), "rfc"),
        legal_personality=_text(payload.get("legal_personality"), "legal_personality"),
        legal_form=_text(payload.get("legal_form"), "legal_form"),
        profile=entity_profile,
        is_active=True,
    )
    activity_start = _iso_date(payload.get("activity_start"), "activity_start")

    fiscal_payload = payload.get("fiscal_profile")
    if not isinstance(fiscal_payload, dict):
        raise ValueError("fiscal_profile is required and must be explicit")
    fiscal_from = _iso_date(fiscal_payload.get("effective_from"), "fiscal_profile.effective_from")
    fiscal_to_raw = fiscal_payload.get("effective_to")
    fiscal_to = None if fiscal_to_raw in (None, "") else _iso_date(fiscal_to_raw, "fiscal_profile.effective_to")
    jurisdiction = _text(fiscal_payload.get("jurisdiction"), "fiscal_profile.jurisdiction")
    regime = _text(fiscal_payload.get("fiscal_regime_code"), "fiscal_profile.fiscal_regime_code")
    tax_characteristics = _string_tuple(
        fiscal_payload.get("tax_characteristics"),
        "fiscal_profile.tax_characteristics",
    )
    if fiscal_to is not None and fiscal_to < fiscal_from:
        raise ValueError("fiscal_profile.effective_to cannot precede effective_from")

    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("bindings must be an object")
    unknown_roles = set(bindings) - _ROLE_KEYS
    if unknown_roles:
        raise ValueError(f"unknown onboarding binding roles: {sorted(unknown_roles)}")
    missing_roles = _REQUIRED_ROLE_KEYS - set(bindings)
    if missing_roles:
        raise ValueError(f"required onboarding bindings missing: {sorted(missing_roles)}")

    catalog_codes = {item["code"] for item in _catalog_options(entity_profile.economic_purpose)}
    normalized_bindings = {}
    for role, code in bindings.items():
        normalized = _text(code, f"binding {role}")
        if normalized not in catalog_codes:
            raise ValueError(
                f"binding {role} must select an account from the governed catalog during initial onboarding"
            )
        normalized_bindings[role] = normalized

    # All deterministic validation above occurs before the first durable write.
    # The complete setup below is one caller-owned transaction: no partial entity,
    # calendar, fiscal profile or binding state may survive a late failure.
    with _storage.get_session() as session:
        if _application.get_active_entity(session) is not None:
            raise ValueError("active entity already configured")

        try:
            ensure_canonical_accounts(session, entity_profile.economic_purpose)
            persisted = _stage_entity(session, entity)

            configure_calendar(
                session,
                persisted.id,
                activity_start,
                historical_states={},
                legacy_period_assignments={},
                historical_year_states={},
            )
            open_fiscal_year(session, activity_start.year)

            _stage_fiscal_profile(
                session,
                FiscalProfile(
                    id=None,
                    entity_id=persisted.id,
                    jurisdiction=jurisdiction,
                    fiscal_regime_code=regime,
                    tax_characteristics=tax_characteristics,
                    effective_from=fiscal_from,
                    effective_to=fiscal_to,
                ),
            )

            for role in sorted(normalized_bindings):
                _stage_account_binding(session, role, normalized_bindings[role])

            session.commit()
        except Exception:
            session.rollback()
            raise

    return get_surface_onboarding()


__all__ = ["get_surface_onboarding", "configure_surface_onboarding"]
