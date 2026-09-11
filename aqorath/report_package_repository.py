"""Persistence authority for Entity-owned AQR-013 custom report package selections.

Only configuration is persisted: name, owner and governed ReportDefinition identities.
No ReportRequest, balance, calculated report content or rendered artifact is stored.
"""

from dataclasses import replace
import json

from sqlmodel import select

from . import entity_repository as _entities
from . import report_product_catalog as _catalog
from .custom_report_package import CustomReportPackage
from .report_product_models import CustomReportPackageRecord


def _active_entity(session):
    entity = _entities.load_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity is required for report package configuration")
    return entity


def _governed_definition_ids(package):
    ids = []
    seen = set()
    for supplied in package.included_reports:
        if supplied.id is None:
            raise ValueError("custom package reports must have governed identities")
        governed = _catalog.get_report_definition(supplied.id)
        if supplied != governed:
            raise ValueError(
                f"custom package report {supplied.id} differs from governed definition"
            )
        if supplied.id in seen:
            raise ValueError("custom package must not repeat report definitions")
        seen.add(supplied.id)
        ids.append(supplied.id)
    return tuple(ids)


def _decode_ids(raw):
    if type(raw) is not str:
        raise RuntimeError("persisted custom report package ids must be JSON text")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("persisted custom report package ids are invalid JSON") from exc
    if not isinstance(value, list):
        raise RuntimeError("persisted custom report package ids must decode to list")
    result = []
    seen = set()
    for item in value:
        if type(item) is not int or item <= 0:
            raise RuntimeError("persisted report definition identity must be positive int")
        if item in seen:
            raise RuntimeError("persisted custom report package ids contain duplicates")
        _catalog.get_report_definition(item)
        seen.add(item)
        result.append(item)
    return tuple(result)


def _from_record(record):
    ids = _decode_ids(record.report_definition_ids_json)
    return CustomReportPackage(
        id=record.id,
        owner_entity_id=record.entity_id,
        name=record.name,
        included_reports=tuple(_catalog.get_report_definition(item) for item in ids),
        created_at=record.created_at,
    )


def create_custom_report_package(session, package):
    """Persist one new custom selection after active-Entity and catalog validation."""
    if not isinstance(package, CustomReportPackage):
        raise TypeError("package must be CustomReportPackage")
    if package.id is not None:
        raise ValueError("new custom report package id must be None")
    entity = _active_entity(session)
    if package.owner_entity_id != entity.id:
        raise ValueError("custom report package does not belong to the active Entity")
    ids = _governed_definition_ids(package)
    duplicate = session.exec(
        select(CustomReportPackageRecord).where(
            CustomReportPackageRecord.entity_id == entity.id,
            CustomReportPackageRecord.name == package.name,
        )
    ).first()
    if duplicate is not None:
        raise ValueError("custom report package name already exists for Entity")

    record = CustomReportPackageRecord(
        entity_id=entity.id,
        name=package.name,
        report_definition_ids_json=json.dumps(
            list(ids),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        created_at=package.created_at,
    )
    try:
        session.add(record)
        session.flush()
        if record.id is None:
            raise RuntimeError("custom report package persistence assigned no identity")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return replace(package, id=record.id)


def get_custom_report_package(session, package_id):
    """Load one active-Entity-owned custom package by identity."""
    if type(package_id) is not int or package_id <= 0:
        raise ValueError("package_id must be a positive integer")
    entity = _active_entity(session)
    record = session.get(CustomReportPackageRecord, package_id)
    if record is None or record.entity_id != entity.id:
        raise LookupError("custom report package not found for active Entity")
    return _from_record(record)


def list_custom_report_packages(session):
    """List deterministic custom selections owned by the active Entity."""
    entity = _active_entity(session)
    rows = session.exec(
        select(CustomReportPackageRecord)
        .where(CustomReportPackageRecord.entity_id == entity.id)
        .order_by(CustomReportPackageRecord.name, CustomReportPackageRecord.id)
    ).all()
    return tuple(_from_record(row) for row in rows)


def replace_custom_report_package_selection(session, package_id, included_reports):
    """Replace only the governed report selection, preserving owner/name/created_at."""
    if type(included_reports) is not tuple:
        raise TypeError("included_reports must be tuple")
    current = get_custom_report_package(session, package_id)
    candidate = CustomReportPackage(
        id=current.id,
        owner_entity_id=current.owner_entity_id,
        name=current.name,
        included_reports=included_reports,
        created_at=current.created_at,
    )
    ids = _governed_definition_ids(candidate)
    record = session.get(CustomReportPackageRecord, package_id)
    record.report_definition_ids_json = json.dumps(
        list(ids), ensure_ascii=False, separators=(",", ":")
    )
    try:
        session.add(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _from_record(record)
