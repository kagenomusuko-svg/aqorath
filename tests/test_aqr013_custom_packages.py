from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel


def _engine():
    import aqorath.models  # noqa: F401
    import aqorath.report_product_models  # noqa: F401

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=None,
        name="Entidad reportante",
        rfc="AAA010101AAA",
        legal_personality="persona_moral",
        legal_form="sociedad",
        profile=EntityProfile(
            economic_purpose="lucrativo",
            is_donor_authorized=False,
            special_capabilities=(),
            modules_enabled=(),
        ),
        is_active=True,
    )


def _package(entity_id, *, name="Mi paquete", reports=None):
    from aqorath.custom_report_package import CustomReportPackage
    from aqorath.report_product_catalog import list_report_definitions

    return CustomReportPackage(
        id=None,
        owner_entity_id=entity_id,
        name=name,
        included_reports=(
            tuple(list_report_definitions()) if reports is None else reports
        ),
        created_at=datetime(2026, 9, 11, 4, 30, tzinfo=timezone.utc),
    )


def test_custom_package_round_trip_persists_only_governed_selection():
    from aqorath.entity_repository import create_entity
    from aqorath.report_package_repository import (
        create_custom_report_package,
        get_custom_report_package,
    )
    from aqorath.report_product_models import CustomReportPackageRecord

    engine = _engine()
    with Session(engine) as session:
        entity = create_entity(session, _entity())
        saved = create_custom_report_package(session, _package(entity.id))
        loaded = get_custom_report_package(session, saved.id)
        row = session.get(CustomReportPackageRecord, saved.id)

        assert loaded.id == saved.id
        assert loaded.owner_entity_id == entity.id
        assert tuple(item.id for item in loaded.included_reports) == (1301, 1302, 1303)
        assert row.report_definition_ids_json == "[1301,1302,1303]"
        assert not hasattr(row, "balance")
        assert not hasattr(row, "amount")
        assert not hasattr(row, "result")
        assert not hasattr(row, "rendered_output")
    engine.dispose()


def test_custom_package_rejects_foreign_owner_duplicate_name_and_mutated_definition():
    from dataclasses import replace

    from aqorath.entity_repository import create_entity
    from aqorath.report_package_repository import create_custom_report_package
    from aqorath.report_product_catalog import TRIAL_BALANCE_PERIOD

    engine = _engine()
    with Session(engine) as session:
        entity = create_entity(session, _entity())

        with pytest.raises(ValueError, match="active Entity"):
            create_custom_report_package(session, _package(entity.id + 1))

        create_custom_report_package(
            session,
            _package(entity.id, name="Único", reports=(TRIAL_BALANCE_PERIOD,)),
        )
        with pytest.raises(ValueError, match="already exists"):
            create_custom_report_package(
                session,
                _package(entity.id, name="Único", reports=(TRIAL_BALANCE_PERIOD,)),
            )

        mutated = replace(TRIAL_BALANCE_PERIOD, name="Balanza alterada")
        with pytest.raises(ValueError, match="differs from governed"):
            create_custom_report_package(
                session,
                _package(entity.id, name="Alterado", reports=(mutated,)),
            )
    engine.dispose()


def test_custom_package_selection_is_editable_preset_without_changing_domain_truth():
    from aqorath.entity_repository import create_entity
    from aqorath.report_package_repository import (
        create_custom_report_package,
        replace_custom_report_package_selection,
    )
    from aqorath.report_product_catalog import (
        BALANCE_SHEET_AS_OF,
        TRIAL_BALANCE_PERIOD,
    )

    engine = _engine()
    with Session(engine) as session:
        entity = create_entity(session, _entity())
        saved = create_custom_report_package(
            session,
            _package(entity.id, reports=(TRIAL_BALANCE_PERIOD,)),
        )
        replaced = replace_custom_report_package_selection(
            session,
            saved.id,
            (BALANCE_SHEET_AS_OF, TRIAL_BALANCE_PERIOD),
        )
        assert replaced.id == saved.id
        assert replaced.name == saved.name
        assert replaced.created_at == saved.created_at
        assert tuple(item.id for item in replaced.included_reports) == (1303, 1301)
    engine.dispose()


def test_custom_package_corrupt_or_unknown_persisted_ids_fail_closed():
    from aqorath.entity_repository import create_entity
    from aqorath.report_package_repository import get_custom_report_package
    from aqorath.report_product_models import CustomReportPackageRecord

    engine = _engine()
    with Session(engine) as session:
        entity = create_entity(session, _entity())
        bad = CustomReportPackageRecord(
            entity_id=entity.id,
            name="Corrupto",
            report_definition_ids_json="[999999]",
            created_at=datetime(2026, 9, 11, 4, 31),
        )
        session.add(bad)
        session.commit()
        session.refresh(bad)
        with pytest.raises(LookupError):
            get_custom_report_package(session, bad.id)
    engine.dispose()
