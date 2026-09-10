from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest
from sqlalchemy import text
from sqlmodel import Session


@pytest.fixture
def donation_surface_runtime(tmp_path, monkeypatch):
    from test_aqr009_donations import _runtime
    import aqorath.storage as storage
    import aqorath.surface_application as surface_application
    import aqorath.donation_operations as donation_operations

    previous_env = os.environ.get("AQORATH_DB")
    previous_engine = storage._engine
    previous_db_path = storage._DB_PATH
    previous_public_db_path = storage.DB_PATH
    engine, entity, program, fund, source = _runtime(tmp_path)
    monkeypatch.setattr(surface_application._storage, "get_session", lambda: Session(engine))
    monkeypatch.setattr(donation_operations._storage, "get_session", lambda: Session(engine))
    try:
        yield engine, entity, program, fund, source
    finally:
        if storage._engine is not previous_engine and storage._engine is not None:
            storage._engine.dispose()
        storage._engine = previous_engine
        storage._DB_PATH = previous_db_path
        storage.DB_PATH = previous_public_db_path
        if previous_env is None:
            os.environ.pop("AQORATH_DB", None)
        else:
            os.environ["AQORATH_DB"] = previous_env


def _seed_surface_choices(engine):
    from aqorath.surface_application import (
        create_surface_bank_account,
        create_surface_third_party,
    )

    donor = create_surface_third_party("Donante de superficie", "other")
    bank = create_surface_bank_account("Banco de prueba", "CTA-EDU-001", "MXN")
    return donor, bank


def _monetary_payload():
    return {
        "donor_name": "Donante de superficie",
        "amount": "1000.00",
        "date": "2026-02-01",
        "bank_account_identifier": "CTA-EDU-001",
        "document_type": "acta",
        "document_number": "SURF-DON-001",
        "document_date": "2026-02-01",
        "fund_name": "Educación",
        "funding_source_name": "Donante principal",
        "program_name": "Educación",
        "restriction": "restricted",
        "purpose": "Programa educativo",
    }


def _inkind_payload():
    return {
        "donor_name": "Donante de superficie",
        "description": "Computadora donada",
        "quantity": "1",
        "date": "2026-02-02",
        "valuation_amount": "12000.00",
        "valuation_method": "avaluo",
        "valuation_evidence": "Avalúo firmado SURF-IK-001",
        "document_type": "constancia",
        "document_number": "SURF-IK-001",
        "document_date": "2026-02-02",
        "fund_name": "Educación",
        "program_name": "Educación",
        "asset_code": "SURF-AF-001",
        "asset_name": "Computadora donada",
        "useful_life_months": 36,
    }


def test_common_monetary_surface_resolves_human_choices_and_cancel_is_non_persistent(donation_surface_runtime):
    from aqorath.presentation_controller import LocalPresentationController
    from aqorath.surface_application import list_surface_donation_options

    engine, entity, program, fund, source = donation_surface_runtime
    _seed_surface_choices(engine)
    controller = LocalPresentationController()
    before = {}
    with Session(engine) as session:
        for table in ("journalentry", "donation", "documentreference", "fundreceipt", "auditevent"):
            before[table] = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()

    options = controller.donation_options()
    assert [row["name"] for row in options["donors"]] == ["Donante de superficie"]
    assert [row["name"] for row in options["programs"]] == ["Educación"]
    assert options["banks"][0]["account_identifier"] == "CTA-EDU-001"

    prepared = controller.prepare_monetary_donation(_monetary_payload())
    assert prepared["preview"]["amount"] == "1000.00"
    assert prepared["preview"]["donor"] == "Donante de superficie"
    assert prepared["preview"]["fund"] == "Educación"
    assert prepared["preview"]["program"] == "Educación"
    assert "account_code" not in str(prepared["preview"])
    assert "Debe" not in str(prepared["preview"])
    assert "Haber" not in str(prepared["preview"])

    professional_preview = controller.professional_preview(prepared["token"])
    assert professional_preview["rule_id"] == "economic_fact:donation:bank"
    assert professional_preview["donation"]["document_number"] == "SURF-DON-001"
    assert controller.cancel(prepared["token"]) == {"cancelled": True}
    assert controller.pending_count == 0
    with Session(engine) as session:
        for table, count in before.items():
            assert session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == count


def test_common_monetary_surface_confirm_uses_prepared_snapshot_and_professional_read_model(donation_surface_runtime):
    from aqorath.presentation_controller import LocalPresentationController

    engine, entity, program, fund, source = donation_surface_runtime
    _seed_surface_choices(engine)
    controller = LocalPresentationController()
    payload = _monetary_payload()
    prepared = controller.prepare_monetary_donation(payload)
    preview_snapshot = dict(prepared["preview"])

    payload["amount"] = "9999.00"
    payload["purpose"] = "Destino cambiado después del preview"
    result = controller.confirm(prepared["token"])
    assert result["entry_id"] > 0

    professional = controller.professional_donation(result["donation_id"])
    assert professional["donation"]["amount"] == "1000.00"
    assert professional["document"]["document_number"] == preview_snapshot["document_number"]
    assert professional["fund"]["name"] == "Educación"
    assert professional["funding_source"]["name"] == "Donante principal"
    assert professional["program"]["name"] == "Educación"
    assert [(line["debit"], line["credit"]) for line in professional["ledger"]["lines"]] == [
        ("1000.00", "0"),
        ("0", "1000.00"),
    ]
    assert professional["fiscality"]["supported"] is False
    assert "Tratamiento contable determinado" in professional["fiscality"]["limitation"]


def test_common_inkind_surface_preview_cancel_and_professional_read_model(donation_surface_runtime):
    from aqorath.presentation_controller import LocalPresentationController

    engine, entity, program, fund, source = donation_surface_runtime
    _seed_surface_choices(engine)
    controller = LocalPresentationController()
    with Session(engine) as session:
        before = {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("journalentry", "inkinddonation", "fixedasset", "documentreference", "auditevent")
        }
    prepared = controller.prepare_inkind_donation(_inkind_payload())
    preview = prepared["preview"]
    assert preview["amount"] == "12000.00"
    assert preview["asset"] == "Computadora donada"
    assert preview["cash_or_bank"] == "Sin efectivo ni banco"
    assert "12000.00" in preview["explanation"]
    assert "Avalúo firmado" in preview["evidence"]
    assert "Debe" not in str(preview)
    assert "Haber" not in str(preview)
    assert controller.cancel(prepared["token"]) == {"cancelled": True}
    with Session(engine) as session:
        for table, count in before.items():
            assert session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == count

    prepared = controller.prepare_inkind_donation(_inkind_payload())
    result = controller.confirm(prepared["token"])
    professional = controller.professional_inkind_donation(result["inkind_donation_id"])
    assert professional["inkind_donation"]["valuation_amount"] == "12000.00"
    assert professional["fixed_asset"]["acquisition_cost"] == "12000.00"
    assert professional["cash_or_bank"] == []
    assert professional["evidence"]["valuation"] == "Avalúo firmado SURF-IK-001"
    assert professional["fiscality"]["supported"] is False


def test_surface_assets_keep_presentation_free_of_accounting_authorities():
    from pathlib import Path
    import ast
    import aqorath.web_surface as web_surface

    source = Path(web_surface.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "aqorath.models" not in imported
    assert "aqorath.storage" not in imported
    assert "sqlmodel" not in imported


def test_web_surface_exposes_donation_prepare_and_professional_routes_and_common_copy():
    from aqorath.web_surface import app
    from aqorath.web_assets import APP_HTML

    paths = {route.path for route in app.routes}
    assert {
        "/api/osc/donation-options",
        "/api/osc/donations/prepare",
        "/api/osc/in-kind-donations/prepare",
        "/api/osc/donations/{donation_id}/professional",
        "/api/osc/in-kind-donations/{donation_id}/professional",
    } <= paths
    donation_common = APP_HTML.split('<section id="professional"', 1)[0].split('id="donationFlow"', 1)[1]
    assert "Donante" in donation_common
    assert "Cuenta bancaria propia" in donation_common
    assert "Evidencia de valuación" in donation_common
    assert "journal_line_id" not in donation_common
    assert "document_reference_id" not in donation_common
    assert "account_code" not in donation_common
    assert "Debe" not in donation_common
    assert "Haber" not in donation_common


def test_web_surface_donation_handlers_delegate_without_resolving_accounting(monkeypatch):
    import aqorath.web_surface as web_surface

    calls = []

    class FakeController:
        def donation_options(self):
            calls.append(("options",))
            return {"donors": []}

        def prepare_monetary_donation(self, payload):
            calls.append(("monetary", payload))
            return {"token": "m", "preview": {"amount": "1000.00"}}

        def prepare_inkind_donation(self, payload):
            calls.append(("inkind", payload))
            return {"token": "i", "preview": {"amount": "12000.00"}}

        def professional_donation(self, donation_id):
            calls.append(("professional-monetary", donation_id))
            return {"kind": "monetary"}

        def professional_inkind_donation(self, donation_id):
            calls.append(("professional-inkind", donation_id))
            return {"kind": "inkind"}

    monkeypatch.setattr(web_surface, "controller", FakeController())
    assert web_surface.donation_options() == {"donors": []}
    assert web_surface.prepare_monetary_donation({"amount": "1000.00"})["token"] == "m"
    assert web_surface.prepare_inkind_donation({"valuation_amount": "12000.00"})["token"] == "i"
    assert web_surface.professional_donation(4) == {"kind": "monetary"}
    assert web_surface.professional_inkind_donation(5) == {"kind": "inkind"}
    assert calls == [
        ("options",),
        ("monetary", {"amount": "1000.00"}),
        ("inkind", {"valuation_amount": "12000.00"}),
        ("professional-monetary", 4),
        ("professional-inkind", 5),
    ]
