"""AQR-015 clean-install onboarding and first V1 common/professional flow."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, select


CORE_BINDINGS = {
    "bank": "1101",
    "cash": "1102",
    "accounts_receivable": "1103",
    "accounts_payable": "2101",
    "sales_revenue": "4201",
    "utilities_expense": "5102",
}


def _fresh_db(tmp_path, monkeypatch, name="onboarding.db"):
    import aqorath.storage as storage

    if storage._engine is not None:
        storage._engine.dispose()
    storage._engine = None
    storage._DB_PATH = None

    db_path = tmp_path / name
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    engine = storage.init_db(str(db_path))
    return db_path, engine


def _payload(**overrides):
    payload = {
        "name": "Negocio AQR-015",
        "rfc": "AAA010101AAA",
        "legal_personality": "persona_moral",
        "legal_form": "sociedad mercantil",
        "economic_purpose": "lucrativo",
        "is_donor_authorized": False,
        "special_capabilities": [],
        "modules_enabled": [],
        "activity_start": "2026-01-01",
        "bindings": dict(CORE_BINDINGS),
        "fiscal_profile": {
            "jurisdiction": "MX",
            "fiscal_regime_code": "603",
            "tax_characteristics": [],
            "effective_from": "2026-01-01",
            "effective_to": None,
        },
    }
    payload.update(overrides)
    return payload


def test_invalid_initial_binding_fails_before_any_product_truth_is_written(tmp_path, monkeypatch):
    _db, engine = _fresh_db(tmp_path, monkeypatch, "invalid.db")
    from aqorath.models import Account, EntityRecord
    from aqorath.onboarding_surface_application import configure_surface_onboarding

    payload = _payload()
    payload["bindings"]["sales_revenue"] = "9999"

    with pytest.raises(ValueError, match="governed catalog"):
        configure_surface_onboarding(payload)

    with Session(engine) as session:
        assert session.exec(select(EntityRecord)).all() == []
        assert session.exec(select(Account)).all() == []
        assert session.execute(text("SELECT COUNT(*) FROM accountingcalendar")).scalar_one() == 0


def test_late_onboarding_failure_rolls_back_every_staged_product_truth(tmp_path, monkeypatch):
    _db, engine = _fresh_db(tmp_path, monkeypatch, "atomic.db")
    import aqorath.onboarding_surface_application as onboarding
    from aqorath.models import (
        Account,
        AccountRoleBinding,
        EntityProfileRecord,
        EntityRecord,
        FiscalProfileRecord,
    )

    original = onboarding.set_account_binding
    calls = 0

    def fail_after_staging_second_binding(session, role, account_code, *, commit=True):
        nonlocal calls
        calls += 1
        original(session, role, account_code, commit=commit)
        if calls == 2:
            raise RuntimeError("simulated late onboarding failure")

    monkeypatch.setattr(onboarding, "set_account_binding", fail_after_staging_second_binding)

    with pytest.raises(RuntimeError, match="simulated late onboarding failure"):
        onboarding.configure_surface_onboarding(_payload())

    with Session(engine) as session:
        assert session.exec(select(Account)).all() == []
        assert session.exec(select(EntityRecord)).all() == []
        assert session.exec(select(EntityProfileRecord)).all() == []
        assert session.exec(select(FiscalProfileRecord)).all() == []
        assert session.exec(select(AccountRoleBinding)).all() == []
        assert session.execute(text("SELECT COUNT(*) FROM accountingcalendar")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM fiscalyear")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM accountingperiod")).scalar_one() == 0

    monkeypatch.setattr(onboarding, "set_account_binding", original)
    recovered = onboarding.configure_surface_onboarding(_payload(name="Retry AQR-015"))
    assert recovered["configured"] is True
    assert recovered["entity"]["name"] == "Retry AQR-015"


def test_clean_onboarding_materializes_governed_catalog_entity_period_profile_and_bindings(tmp_path, monkeypatch):
    _db, engine = _fresh_db(tmp_path, monkeypatch)
    from aqorath.account_bindings import get_account_bindings
    from aqorath.application import get_active_entity, get_fiscal_profile_for_date
    from aqorath.catalog import load_catalog
    from aqorath.models import Account
    from aqorath.onboarding_surface_application import (
        configure_surface_onboarding,
        get_surface_onboarding,
    )

    result = configure_surface_onboarding(_payload())
    assert result["configured"] is True
    assert result["entity"]["name"] == "Negocio AQR-015"
    assert result["bindings"] == CORE_BINDINGS

    with Session(engine) as session:
        entity = get_active_entity(session)
        assert entity is not None
        assert entity.profile.economic_purpose == "lucrativo"
        assert get_account_bindings(session, tuple(CORE_BINDINGS)) == CORE_BINDINGS
        profile = get_fiscal_profile_for_date(session, entity.id, date(2026, 9, 10))
        assert profile.jurisdiction == "MX"
        assert profile.fiscal_regime_code == "603"
        accounts = session.exec(select(Account)).all()
        assert len(accounts) == len(load_catalog()["accounts"])
        assert all(item.origin == "canonical" and item.parent_id is None for item in accounts)
        assert session.execute(text("SELECT state FROM fiscalyear WHERE year=2026")).scalar_one() == "open"
        assert session.execute(text("SELECT COUNT(*) FROM accountingperiod WHERE year=2026")).scalar_one() == 12

    status = get_surface_onboarding()
    assert status["limits"]["monoentity"] is True
    assert status["limits"]["internet_required"] is False
    with pytest.raises(ValueError, match="active entity already configured"):
        configure_surface_onboarding(_payload(name="Segunda entidad"))


def test_v1_01_is_operable_immediately_after_guided_onboarding_from_same_truth(tmp_path, monkeypatch):
    _db, engine = _fresh_db(tmp_path, monkeypatch, "v1-01.db")
    from aqorath.onboarding_surface_application import configure_surface_onboarding
    from aqorath.presentation_controller import LocalPresentationController

    configure_surface_onboarding(_payload())
    controller = LocalPresentationController()

    prepared = controller.prepare("sale_cash", "200.00", "2026-09-10")
    common = prepared["preview"]
    professional_preview = controller.professional_preview(prepared["token"])

    assert common["amount"] == "200.00"
    assert "account_code" not in str(common)
    assert [line["account_code"] for line in professional_preview["lines"]] == ["1102", "4201"]
    assert [line["amount"] for line in professional_preview["lines"]] == ["200.00", "200.00"]

    posted = controller.confirm(prepared["token"])
    assert posted["state"] == "posted"
    professional = controller.professional_operation(posted["entry_id"])
    assert professional["state"] == "posted"
    assert professional["period"]["id"] == 202609
    assert [(line["account_code"], line["debit"], line["credit"]) for line in professional["lines"]] == [
        ("1102", "200.00", "0"),
        ("4201", "0", "200.00"),
    ]
    assert professional["audit"]["details"]["decision"]["consent"] == "explicit_confirmation"

    with Session(engine) as session:
        totals = session.execute(
            text("SELECT account_code,debit,credit FROM journalline ORDER BY id")
        ).all()
    assert totals == [("1102", "200.00", "0"), ("4201", "0", "200.00")]


def test_onboarding_http_adapter_is_registered_on_same_canonical_app_and_human_readable(tmp_path, monkeypatch):
    _db, _engine = _fresh_db(tmp_path, monkeypatch, "http.db")
    import aqorath.onboarding_web as onboarding_web
    from aqorath.web_surface import app

    paths = {route.path for route in app.routes}
    assert {"/onboarding", "/api/onboarding"} <= paths
    assert "Configuración inicial" in onboarding_web.ONBOARDING_HTML
    assert "Debe/Haber" in onboarding_web.ONBOARDING_HTML
    assert "data-role" in onboarding_web.ONBOARDING_HTML


def test_catalog_persistence_stages_only_missing_governed_accounts_without_commit(tmp_path, monkeypatch):
    _db, engine = _fresh_db(tmp_path, monkeypatch, "catalog.db")
    from aqorath.catalog import load_catalog
    from aqorath.catalog_persistence import ensure_canonical_accounts
    from aqorath.models import Account

    expected = tuple(sorted(load_catalog()["accounts"]))
    with Session(engine) as session:
        inserted = ensure_canonical_accounts(session, "no_lucrativo")
        assert inserted == expected
        assert len(session.exec(select(Account)).all()) == len(expected)
        session.rollback()

    with Session(engine) as session:
        assert session.exec(select(Account)).all() == []
