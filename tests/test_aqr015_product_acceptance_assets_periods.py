"""AQR-015 product acceptance coverage for V1-08, V1-09 and V1-10."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session


BINDINGS = {
    "bank": "1101",
    "cash": "1102",
    "accounts_receivable": "1103",
    "accounts_payable": "2101",
    "sales_revenue": "4201",
    "utilities_expense": "5102",
    "fixed_asset_computer_equipment": "1202",
    "depreciation_expense": "5106",
    "accumulated_depreciation": "1205",
}


def _fresh(tmp_path, monkeypatch, name):
    import aqorath.storage as storage

    if storage._engine is not None:
        storage._engine.dispose()
    storage._engine = None
    storage._DB_PATH = None
    db = tmp_path / name
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db))

    from aqorath.onboarding_surface_application import configure_surface_onboarding

    configure_surface_onboarding(
        {
            "name": "Entidad aceptación AQR-015",
            "rfc": "AAA010101AAA",
            "legal_personality": "persona_moral",
            "legal_form": "sociedad mercantil",
            "economic_purpose": "lucrativo",
            "is_donor_authorized": False,
            "special_capabilities": [],
            "modules_enabled": [],
            "activity_start": "2026-01-01",
            "bindings": dict(BINDINGS),
            "fiscal_profile": {
                "jurisdiction": "MX",
                "fiscal_regime_code": "603",
                "tax_characteristics": [],
                "effective_from": "2026-01-01",
                "effective_to": None,
            },
        }
    )
    return db, engine


def test_v1_08_and_v1_09_fixed_asset_acquisition_depreciation_and_book_state(tmp_path, monkeypatch):
    _db, engine = _fresh(tmp_path, monkeypatch, "assets.db")
    from aqorath import fixed_asset_surface_application as assets
    from aqorath.surface_application import load_professional_operation

    created = assets.create_fixed_asset_surface(
        {
            "code": "EQ-COMP-001",
            "name": "Computadora",
            "acquisition_date": "2026-01-15",
            "in_service_date": "2026-02-01",
            "acquisition_cost": "12000.00",
            "residual_value": "0.00",
            "useful_life_months": 12,
        }
    )
    asset_id = created["id"]

    acquisition = assets.prepare_fixed_asset_acquisition_surface(
        {
            "fixed_asset_id": asset_id,
            "asset_class": "computer_equipment",
            "settlement_method": "bank",
        }
    )
    assert acquisition.preview["amount"] == "12000.00"
    assert "account_code" not in str(acquisition.preview)
    professional_preview = assets.professional_fixed_asset_acquisition_preview(acquisition)
    assert [line["account_code"] for line in professional_preview["accounting"]["lines"]] == [
        "1202",
        "1101",
    ]
    assert [line["side"] for line in professional_preview["accounting"]["lines"]] == [
        "debit",
        "credit",
    ]

    posted = assets.confirm_fixed_asset_acquisition_surface(acquisition)
    assert posted["ok"] is True
    entry_id = posted["entry_id"]
    ledger = load_professional_operation(entry_id)
    assert [(line["account_code"], line["debit"], line["credit"]) for line in ledger["lines"]] == [
        ("1202", "12000.00", "0"),
        ("1101", "0", "12000.00"),
    ]

    retry = assets.prepare_fixed_asset_acquisition_surface(
        {
            "fixed_asset_id": asset_id,
            "asset_class": "computer_equipment",
            "settlement_method": "bank",
        }
    )
    retried = assets.confirm_fixed_asset_acquisition_surface(retry)
    assert retried["entry_id"] == entry_id
    assert retried["already_posted"] is True

    depreciation = assets.prepare_fixed_asset_depreciation_surface(
        {
            "fixed_asset_id": asset_id,
            "period_number": 1,
            "recognition_date": "2026-02-28",
        }
    )
    assert depreciation.preview["amount"] == "1000.00"
    assert "account_code" not in str(depreciation.preview)
    depreciation_professional = assets.professional_fixed_asset_depreciation_preview(depreciation)
    assert [line["account_code"] for line in depreciation_professional["accounting"]["lines"]] == [
        "5106",
        "1205",
    ]

    dep_posted = assets.confirm_fixed_asset_depreciation_surface(depreciation)
    assert dep_posted["ok"] is True
    dep_entry_id = dep_posted["entry_id"]

    dep_retry = assets.prepare_fixed_asset_depreciation_surface(
        {
            "fixed_asset_id": asset_id,
            "period_number": 1,
            "recognition_date": "2026-02-28",
        }
    )
    dep_retried = assets.confirm_fixed_asset_depreciation_surface(dep_retry)
    assert dep_retried["entry_id"] == dep_entry_id
    assert dep_retried["already_posted"] is True

    book = assets.load_fixed_asset_surface_book_state(asset_id)
    assert book["acquisition_cost"] == "12000.00"
    assert book["accumulated_depreciation"] == "1000.00"
    assert book["carrying_value"] == "11000.00"
    assert book["recognized_periods"] == [
        {
            "period_number": 1,
            "entry_id": dep_entry_id,
            "posting_date": "2026-02-28",
            "recognition_source_ref": f"AQR-015:V1-09:asset={asset_id}:period=1",
            "amount": "1000.00",
        }
    ]

    with Session(engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 2


def test_v1_10_closed_month_rejects_posting_and_annual_close_transfers_result_with_backup(tmp_path, monkeypatch):
    _db, engine = _fresh(tmp_path, monkeypatch, "periods.db")
    from aqorath.period_surface_application import (
        close_fiscal_year_surface,
        close_period_surface,
        list_period_surface,
    )
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    sale = controller.prepare("sale_cash", "200.00", "2026-12-15")
    sale_result = controller.confirm(sale["token"])
    expense = controller.prepare("utility_bank", "150.00", "2026-12-20")
    expense_result = controller.confirm(expense["token"])
    assert sale_result["state"] == expense_result["state"] == "posted"

    closed = close_period_surface(202601)
    assert closed == {"period_id": 202601, "state": "closed", "already_closed": False}
    assert close_period_surface(202601)["already_closed"] is True

    january = controller.prepare("sale_cash", "10.00", "2026-01-20")
    with pytest.raises(Exception):
        controller.confirm(january["token"])
    with Session(engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 2

    before = list_period_surface(2026)
    assert next(item for item in before["periods"] if item["id"] == 202601)["state"] == "closed"
    assert next(item for item in before["periods"] if item["id"] == 202612)["state"] == "open"

    result = close_fiscal_year_surface(2026, str(tmp_path / "backups"))
    assert result["ok"] is True
    assert result["transferred"] == "50.00"
    assert result["entry_id"] is not None
    assert Path(result["backup_path"]).exists()

    after = list_period_surface(2026)
    assert after["state"] == "closed"
    assert all(item["state"] == "closed" for item in after["periods"])
    assert after["closing_entry_id"] == result["entry_id"]

    with Session(engine) as session:
        closing_lines = session.execute(
            text(
                "SELECT account_code,debit,credit FROM journalline "
                "WHERE entry_id=:id ORDER BY id"
            ),
            {"id": result["entry_id"]},
        ).all()
    assert ("3104", "0", "50.00") in closing_lines


def test_v1_08_v1_09_v1_10_routes_register_on_the_one_local_app():
    import aqorath.web_surface as web_surface
    import aqorath.fixed_asset_web  # noqa: F401
    import aqorath.period_web  # noqa: F401

    paths = {route.path for route in web_surface.app.routes}
    assert {
        "/fixed-assets",
        "/api/fixed-assets",
        "/api/fixed-assets/acquisition/prepare",
        "/api/fixed-assets/depreciation/prepare",
        "/api/fixed-assets/{fixed_asset_id}/book-state",
        "/periods",
        "/api/periods/{year}",
        "/api/periods/{period_id}/close",
        "/api/periods/years/{year}/close",
    } <= paths
