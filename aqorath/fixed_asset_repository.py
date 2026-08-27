"""SQLite persistence authority for canonical fixed-asset registry metadata."""

from dataclasses import replace
from decimal import Decimal

from sqlmodel import select

from .fixed_asset import FixedAsset
from .models import EntityRecord, FixedAssetRecord


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_exact_bool(value, field_name):
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _from_record(record):
    return FixedAsset(
        id=record.id,
        entity_id=record.entity_id,
        code=record.code,
        name=record.name,
        acquisition_date=record.acquisition_date,
        in_service_date=record.in_service_date,
        acquisition_cost=Decimal(record.acquisition_cost),
        residual_value=Decimal(record.residual_value),
        useful_life_months=record.useful_life_months,
        depreciation_method=record.depreciation_method,
        is_active=record.is_active,
    )


def _load_owned_record(session, entity_id, fixed_asset_id):
    _require_positive_id(entity_id, "entity_id")
    _require_positive_id(fixed_asset_id, "fixed_asset_id")
    rows = session.exec(
        select(FixedAssetRecord).where(
            FixedAssetRecord.entity_id == entity_id,
            FixedAssetRecord.id == fixed_asset_id,
        )
    ).all()
    if not rows:
        raise LookupError("FixedAsset not found for Entity")
    if len(rows) != 1:
        raise RuntimeError("Ambiguous FixedAsset identity")
    return rows[0]


def create_fixed_asset(session, fixed_asset):
    """Persist one explicit canonical fixed-asset registry record."""
    if not isinstance(fixed_asset, FixedAsset):
        raise TypeError("fixed_asset must be FixedAsset")
    if fixed_asset.id is not None:
        raise ValueError("new FixedAsset id must be None")

    owner = session.get(EntityRecord, fixed_asset.entity_id)
    if owner is None:
        raise LookupError("FixedAsset owner Entity does not exist")
    if owner.is_active is not True:
        raise ValueError("FixedAsset owner Entity must be active")

    existing = session.exec(
        select(FixedAssetRecord).where(
            FixedAssetRecord.entity_id == fixed_asset.entity_id,
            FixedAssetRecord.code == fixed_asset.code,
        )
    ).all()
    if existing:
        raise ValueError("FixedAsset code already exists for Entity")

    record = FixedAssetRecord(
        entity_id=fixed_asset.entity_id,
        code=fixed_asset.code,
        name=fixed_asset.name,
        acquisition_date=fixed_asset.acquisition_date,
        in_service_date=fixed_asset.in_service_date,
        acquisition_cost=str(fixed_asset.acquisition_cost),
        residual_value=str(fixed_asset.residual_value),
        useful_life_months=fixed_asset.useful_life_months,
        depreciation_method=fixed_asset.depreciation_method,
        is_active=fixed_asset.is_active,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("FixedAsset identity was not assigned")
        persisted_id = record.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(fixed_asset, id=persisted_id)


def get_fixed_asset(session, entity_id, fixed_asset_id):
    """Load one Entity-scoped canonical fixed asset."""
    return _from_record(_load_owned_record(session, entity_id, fixed_asset_id))


def list_fixed_assets(session, entity_id, include_inactive=False):
    """List canonical fixed assets deterministically by identity."""
    _require_positive_id(entity_id, "entity_id")
    _require_exact_bool(include_inactive, "include_inactive")

    statement = select(FixedAssetRecord).where(
        FixedAssetRecord.entity_id == entity_id
    )
    if not include_inactive:
        statement = statement.where(FixedAssetRecord.is_active == True)  # noqa: E712
    records = session.exec(statement.order_by(FixedAssetRecord.id)).all()
    return tuple(_from_record(record) for record in records)


def set_fixed_asset_active(session, entity_id, fixed_asset_id, is_active):
    """Change active state without deleting or replacing registry identity."""
    _require_exact_bool(is_active, "is_active")
    record = _load_owned_record(session, entity_id, fixed_asset_id)
    record.is_active = is_active
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _from_record(record)
