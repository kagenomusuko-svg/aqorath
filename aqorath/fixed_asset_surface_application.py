"""Product-facing fixed-asset composition for V1-08/V1-09.

The registry, acquisition, depreciation, ledger and book-state authorities remain in
specialized canonical modules. This layer only translates common user facts into those
authorities and produces common/professional projections from the same truth.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import application as _application
from . import storage as _storage
from . import surface_application as _surface
from .fixed_asset import FixedAsset
from .fixed_asset_book_state import load_fixed_asset_book_state
from .fixed_asset_depreciation_allocation import FixedAssetDepreciationAllocationPolicy


_ASSET_CLASSES = (
    ("furniture_equipment", "Mobiliario y equipo"),
    ("computer_equipment", "Equipo de cómputo"),
    ("machinery_tools", "Maquinaria y herramientas"),
    ("land_buildings", "Terrenos y edificios"),
)
_SETTLEMENTS = (
    ("bank", "Banco"),
    ("cash", "Efectivo"),
    ("credit", "Crédito / cuenta por pagar"),
)
_ALLOCATION_POLICY = FixedAssetDepreciationAllocationPolicy(
    policy_key="monthly-monetary-allocation-v1",
    quantizer=Decimal("0.01"),
    rounding_mode=ROUND_HALF_UP,
    remainder_policy="final_period",
    source_ref="AQR-015:PRODUCT_ACCEPTANCE_V1:V1-09",
)


@dataclass(frozen=True)
class PreparedFixedAssetAcquisitionSurface:
    fixed_asset: FixedAsset
    asset_class: str
    settlement_method: str
    prepared: object | None
    existing_entry_id: int | None
    preview: dict


@dataclass(frozen=True)
class PreparedFixedAssetDepreciationSurface:
    fixed_asset: FixedAsset
    period_number: int
    recognition_date: date
    prepared: object | None
    existing_entry_id: int | None
    preview: dict


def _date(value, name):
    if type(value) is date:
        return value
    if type(value) is not str:
        raise TypeError(f"{name} must be date or YYYY-MM-DD text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def _decimal(value, name, *, allow_zero=True):
    if type(value) is Decimal:
        result = value
    elif type(value) is int:
        result = Decimal(value)
    elif type(value) is str:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{name} must be exact decimal text") from exc
    else:
        raise TypeError(f"{name} must be Decimal, int or exact decimal text")
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _asset_projection(asset):
    return {
        "id": asset.id,
        "code": asset.code,
        "name": asset.name,
        "acquisition_date": asset.acquisition_date.isoformat(),
        "in_service_date": asset.in_service_date.isoformat(),
        "acquisition_cost": str(asset.acquisition_cost),
        "residual_value": str(asset.residual_value),
        "useful_life_months": asset.useful_life_months,
        "depreciation_method": asset.depreciation_method,
        "is_active": asset.is_active,
    }


def _confirmation_professional(snapshot):
    generic = snapshot.confirmation_snapshot
    if generic is None:
        return {"lines": [], "explanation": "No accounting entry is required."}
    return {
        "lines": [
            {
                "account_role": line.account_role,
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "side": line.side,
                "amount": str(line.amount),
            }
            for line in generic.lines
        ],
        "explanation": generic.explanation,
    }


def list_fixed_asset_surface_options():
    return {
        "asset_classes": [
            {"key": key, "label": label} for key, label in _ASSET_CLASSES
        ],
        "settlements": [
            {"key": key, "label": label} for key, label in _SETTLEMENTS
        ],
        "depreciation": {
            "method": "straight_line",
            "quantizer": str(_ALLOCATION_POLICY.quantizer),
            "rounding": "ROUND_HALF_UP",
            "remainder": _ALLOCATION_POLICY.remainder_policy,
        },
    }


def list_fixed_asset_surface_assets():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active entity is required")
        assets = _application.list_fixed_assets(session, entity.id, include_inactive=True)
        result = []
        for asset in assets:
            view = _asset_projection(asset)
            try:
                acquisition = _application.load_fixed_asset_acquisition_posting(
                    session, asset.id
                )
            except LookupError:
                acquisition = None
            state = load_fixed_asset_book_state(session, entity.id, asset.id)
            view.update(
                {
                    "acquisition_posted": acquisition is not None,
                    "asset_class": None if acquisition is None else acquisition.asset_class,
                    "settlement_method": None if acquisition is None else acquisition.settlement_method,
                    "acquisition_entry_id": None if acquisition is None else acquisition.entry_id,
                    "accumulated_depreciation": str(state.accumulated_depreciation),
                    "carrying_value": str(state.carrying_value),
                    "recognized_periods": len(state.recognized_periods),
                }
            )
            result.append(view)
        return result


def create_fixed_asset_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    cost = _decimal(payload.get("acquisition_cost"), "acquisition_cost", allow_zero=False)
    residual = _decimal(payload.get("residual_value", "0.00"), "residual_value")
    life = _positive_int(payload.get("useful_life_months"), "useful_life_months")
    asset = None
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active entity is required")
        asset = _application.create_fixed_asset(
            session,
            FixedAsset(
                id=None,
                entity_id=entity.id,
                code=_text(payload.get("code"), "code"),
                name=_text(payload.get("name"), "name"),
                acquisition_date=_date(payload.get("acquisition_date"), "acquisition_date"),
                in_service_date=_date(payload.get("in_service_date"), "in_service_date"),
                acquisition_cost=cost,
                residual_value=residual,
                useful_life_months=life,
                depreciation_method="straight_line",
                is_active=True,
            ),
        )
    return _asset_projection(asset)


def prepare_fixed_asset_acquisition_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    fixed_asset_id = _positive_int(payload.get("fixed_asset_id"), "fixed_asset_id")
    asset_class = _text(payload.get("asset_class"), "asset_class")
    settlement = _text(payload.get("settlement_method"), "settlement_method")
    if asset_class not in dict(_ASSET_CLASSES):
        raise ValueError("unsupported asset_class")
    if settlement not in dict(_SETTLEMENTS):
        raise ValueError("unsupported settlement_method")

    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active entity is required")
        asset = _application.get_fixed_asset(session, entity.id, fixed_asset_id)
        try:
            existing = _application.load_fixed_asset_acquisition_posting(
                session, fixed_asset_id
            )
        except LookupError:
            existing = None
        if existing is not None:
            if existing.asset_class != asset_class or existing.settlement_method != settlement:
                raise ValueError("fixed asset acquisition is already posted with different facts")
            return PreparedFixedAssetAcquisitionSurface(
                asset,
                asset_class,
                settlement,
                None,
                existing.entry_id,
                {
                    "operation": "Adquisición de activo fijo",
                    "asset": _asset_projection(asset),
                    "asset_class": asset_class,
                    "settlement_method": settlement,
                    "amount": str(asset.acquisition_cost),
                    "already_posted": True,
                    "requires_confirmation": True,
                },
            )

        fact = _application.create_fixed_asset_acquisition_fact(
            asset, asset_class, settlement
        )
        resolution = _application.resolve_fixed_asset_acquisition_accounting(fact)
        prepared = _application.prepare_fixed_asset_acquisition_confirmation(
            session, resolution
        )
        return PreparedFixedAssetAcquisitionSurface(
            asset,
            asset_class,
            settlement,
            prepared,
            None,
            {
                "operation": "Adquisición de activo fijo",
                "asset": _asset_projection(asset),
                "asset_class": asset_class,
                "settlement_method": settlement,
                "amount": str(asset.acquisition_cost),
                "already_posted": False,
                "requires_confirmation": True,
                "explanation": resolution.explanation,
            },
        )


def professional_fixed_asset_acquisition_preview(value):
    if not isinstance(value, PreparedFixedAssetAcquisitionSurface):
        raise TypeError("value must be PreparedFixedAssetAcquisitionSurface")
    if value.existing_entry_id is not None:
        return {
            **value.preview,
            "persisted_entry_id": value.existing_entry_id,
            "accounting": _surface.load_professional_operation(value.existing_entry_id),
        }
    return {**value.preview, "accounting": _confirmation_professional(value.prepared)}


def confirm_fixed_asset_acquisition_surface(value):
    if not isinstance(value, PreparedFixedAssetAcquisitionSurface):
        raise TypeError("value must be PreparedFixedAssetAcquisitionSurface")
    if value.existing_entry_id is not None:
        return {
            "ok": True,
            "entry_id": value.existing_entry_id,
            "fixed_asset_id": value.fixed_asset.id,
            "already_posted": True,
        }
    confirmed = _application.confirm_fixed_asset_acquisition(value.prepared)
    instruction = _application.create_fixed_asset_acquisition_posting_instruction(confirmed)
    result = _application.execute_fixed_asset_acquisition_posting_once(instruction)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "fixed asset acquisition posting failed")
    return {
        **result,
        "fixed_asset_id": value.fixed_asset.id,
        "already_posted": False,
    }


def prepare_fixed_asset_depreciation_surface(payload):
    if type(payload) is not dict:
        raise TypeError("payload must be dict")
    fixed_asset_id = _positive_int(payload.get("fixed_asset_id"), "fixed_asset_id")
    period_number = _positive_int(payload.get("period_number"), "period_number")
    recognition_date = _date(payload.get("recognition_date"), "recognition_date")

    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active entity is required")
        asset = _application.get_fixed_asset(session, entity.id, fixed_asset_id)
        try:
            existing = _application.load_fixed_asset_depreciation_posting(
                session, fixed_asset_id, period_number
            )
        except LookupError:
            existing = None
        if existing is not None:
            if existing.posting_date != recognition_date:
                raise ValueError("depreciation period is already posted on a different date")
            return PreparedFixedAssetDepreciationSurface(
                asset,
                period_number,
                recognition_date,
                None,
                existing.entry_id,
                {
                    "operation": "Depreciación mensual",
                    "asset": _asset_projection(asset),
                    "period_number": period_number,
                    "recognition_date": recognition_date.isoformat(),
                    "already_posted": True,
                    "requires_confirmation": True,
                },
            )

        calculation = _application.calculate_fixed_asset_monthly_depreciation(asset)
        allocation = _application.allocate_fixed_asset_monthly_depreciation(
            calculation, _ALLOCATION_POLICY
        )
        recognition = _application.declare_fixed_asset_depreciation_recognition(
            allocation,
            period_number,
            recognition_date,
            f"AQR-015:V1-09:asset={fixed_asset_id}:period={period_number}",
        )
        resolution = _application.resolve_fixed_asset_depreciation_accounting(recognition)
        prepared = _application.prepare_fixed_asset_depreciation_confirmation(
            session, resolution
        )
        return PreparedFixedAssetDepreciationSurface(
            asset,
            period_number,
            recognition_date,
            prepared,
            None,
            {
                "operation": "Depreciación mensual",
                "asset": _asset_projection(asset),
                "period_number": period_number,
                "recognition_date": recognition_date.isoformat(),
                "amount": str(recognition.amount),
                "already_posted": False,
                "requires_confirmation": True,
                "explanation": resolution.explanation,
            },
        )


def professional_fixed_asset_depreciation_preview(value):
    if not isinstance(value, PreparedFixedAssetDepreciationSurface):
        raise TypeError("value must be PreparedFixedAssetDepreciationSurface")
    if value.existing_entry_id is not None:
        return {
            **value.preview,
            "persisted_entry_id": value.existing_entry_id,
            "accounting": _surface.load_professional_operation(value.existing_entry_id),
        }
    return {**value.preview, "accounting": _confirmation_professional(value.prepared)}


def confirm_fixed_asset_depreciation_surface(value):
    if not isinstance(value, PreparedFixedAssetDepreciationSurface):
        raise TypeError("value must be PreparedFixedAssetDepreciationSurface")
    if value.existing_entry_id is not None:
        return {
            "ok": True,
            "entry_id": value.existing_entry_id,
            "fixed_asset_id": value.fixed_asset.id,
            "period_number": value.period_number,
            "already_posted": True,
        }
    confirmed = _application.confirm_fixed_asset_depreciation(value.prepared)
    instruction = _application.create_fixed_asset_depreciation_posting_instruction(confirmed)
    result = _application.execute_fixed_asset_depreciation_posting_once(instruction)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "fixed asset depreciation posting failed")
    return {
        **result,
        "fixed_asset_id": value.fixed_asset.id,
        "period_number": value.period_number,
        "already_posted": False,
    }


def load_fixed_asset_surface_book_state(fixed_asset_id, as_of=None):
    fixed_asset_id = _positive_int(fixed_asset_id, "fixed_asset_id")
    day = None if as_of in (None, "") else _date(as_of, "as_of")
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active entity is required")
        asset = _application.get_fixed_asset(session, entity.id, fixed_asset_id)
        state = load_fixed_asset_book_state(session, entity.id, fixed_asset_id, day)
        try:
            acquisition = _application.load_fixed_asset_acquisition_posting(
                session, fixed_asset_id
            )
        except LookupError:
            acquisition = None
        return {
            "asset": _asset_projection(asset),
            "asset_class": None if acquisition is None else acquisition.asset_class,
            "settlement_method": None if acquisition is None else acquisition.settlement_method,
            "acquisition_entry_id": None if acquisition is None else acquisition.entry_id,
            "as_of": None if state.as_of is None else state.as_of.isoformat(),
            "acquisition_cost": str(state.acquisition_cost),
            "residual_value": str(state.residual_value),
            "accumulated_depreciation": str(state.accumulated_depreciation),
            "carrying_value": str(state.carrying_value),
            "recognized_periods": [
                {
                    "period_number": period.period_number,
                    "entry_id": period.entry_id,
                    "posting_date": period.posting_date.isoformat(),
                    "recognition_source_ref": period.recognition_source_ref,
                    "amount": str(period.amount),
                }
                for period in state.recognized_periods
            ],
        }


__all__ = [
    "PreparedFixedAssetAcquisitionSurface",
    "PreparedFixedAssetDepreciationSurface",
    "list_fixed_asset_surface_options",
    "list_fixed_asset_surface_assets",
    "create_fixed_asset_surface",
    "prepare_fixed_asset_acquisition_surface",
    "professional_fixed_asset_acquisition_preview",
    "confirm_fixed_asset_acquisition_surface",
    "prepare_fixed_asset_depreciation_surface",
    "professional_fixed_asset_depreciation_preview",
    "confirm_fixed_asset_depreciation_surface",
    "load_fixed_asset_surface_book_state",
]
