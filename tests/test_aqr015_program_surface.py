"""AQR-015 product surface evidence for Program and OSC reuse."""

from decimal import Decimal

import pytest
from sqlmodel import Session, select


def _configured(tmp_path, monkeypatch, name, *, osc):
    from test_aqr015_onboarding import CORE_BINDINGS, _fresh_db, _payload
    from aqorath.onboarding_surface_application import configure_surface_onboarding

    _db, engine = _fresh_db(tmp_path, monkeypatch, name)
    bindings = dict(CORE_BINDINGS)
    if osc:
        bindings.update({
            "donation_income": "4104",
            "fixed_asset_computer_equipment": "1202",
        })
    configure_surface_onboarding(
        _payload(
            name="OSC AQR-015" if osc else "Negocio no OSC",
            legal_form="A.C." if osc else "sociedad mercantil",
            economic_purpose="no_lucrativo" if osc else "lucrativo",
            special_capabilities=["osc"] if osc else [],
            bindings=bindings,
        )
    )
    return engine


def test_non_osc_entity_cannot_create_program_and_no_ledger_truth_is_written(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry, ProgramRecord
    from aqorath.program_presentation_controller import ProgramPresentationController

    engine = _configured(tmp_path, monkeypatch, "program-non-osc.db", osc=False)
    controller = ProgramPresentationController()

    with pytest.raises(ValueError, match="explicit osc capability"):
        controller.create_program({
            "name": "No permitido",
            "description": None,
            "budget": "100.00",
        })

    with Session(engine) as session:
        assert session.exec(select(ProgramRecord)).all() == []
        assert session.exec(select(JournalEntry)).all() == []


def test_osc_program_surface_preserves_exact_budget_reopens_and_creates_no_ledger(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry, ProgramRecord
    from aqorath.program_presentation_controller import ProgramPresentationController

    engine = _configured(tmp_path, monkeypatch, "program-osc.db", osc=True)
    controller = ProgramPresentationController()
    created = controller.create_program({
        "name": "Educación Comunitaria",
        "description": "Programa anual de educación",
        "budget": "125000.2300",
    })

    assert created["name"] == "Educación Comunitaria"
    assert created["budget"] == "125000.2300"
    assert controller.programs() == [created]

    reopened = ProgramPresentationController()
    assert reopened.programs() == [created]

    with Session(engine) as session:
        record = session.get(ProgramRecord, created["id"])
        assert record.entity_id == created["entity_id"]
        assert record.budget == "125000.2300"
        assert Decimal(record.budget).as_tuple() == Decimal("125000.2300").as_tuple()
        assert session.exec(select(JournalEntry)).all() == []


def test_program_routes_share_canonical_app_and_page_is_common_human_surface(tmp_path, monkeypatch):
    _configured(tmp_path, monkeypatch, "program-http.db", osc=True)
    import aqorath.program_web as program_web
    from aqorath.web_surface import app

    paths = {route.path for route in app.routes}
    assert {"/programs", "/api/osc/programs"} <= paths
    assert "Crear programa" in program_web.PROGRAM_HTML
    assert "Crear un programa no genera pólizas, saldos ni una contabilidad separada" in program_web.PROGRAM_HTML
    for forbidden in ("account_code", "journal_line_id", "Debe", "Haber", "SQL", "sql"):
        assert forbidden not in program_web.PROGRAM_HTML


def test_created_program_is_reused_by_v1_07_v1_15_and_v1_22_without_parallel_ledger(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry
    from aqorath.presentation_controller import LocalPresentationController
    from aqorath.program_presentation_controller import ProgramPresentationController

    engine = _configured(tmp_path, monkeypatch, "program-osc-flows.db", osc=True)
    programs = ProgramPresentationController()
    program = programs.create_program({
        "name": "Educación",
        "description": "Programa educativo",
        "budget": "50000.00",
    })

    common = LocalPresentationController()
    donor = common.create_third_party({
        "name": "Donante principal",
        "party_type": "other",
    })
    bank = common.create_bank_account({
        "institution_name": "Banco OSC",
        "account_identifier": "OSC-001",
        "currency": "MXN",
    })
    fund = common.create_fund({
        "code": "EDU",
        "name": "Educación",
        "restriction": "restricted",
        "purpose": "Programa educativo",
        "program_id": program["id"],
    })
    source = common.create_funding_source({
        "name": "Convenio principal",
        "donor_third_party_id": donor["id"],
        "external_reference": "CONV-001",
    })

    monetary = common.prepare_monetary_donation({
        "donor_name": donor["name"],
        "amount": "1000.00",
        "date": "2026-02-01",
        "bank_account_identifier": bank["account_identifier"],
        "document_type": "acta",
        "document_number": "DON-001",
        "document_date": "2026-02-01",
        "fund_name": fund["name"],
        "funding_source_name": source["name"],
        "program_name": program["name"],
        "restriction": "restricted",
        "purpose": "Programa educativo",
    })
    monetary_result = common.confirm(monetary["token"])
    monetary_professional = common.professional_donation(monetary_result["donation_id"])
    assert monetary_professional["program"] == {"id": program["id"], "name": "Educación"}
    assert monetary_professional["fund"]["id"] == fund["id"]
    assert monetary_professional["funding_source"]["id"] == source["id"]
    assert any(
        line["account_id"] == bank["ledger_account_id"] and Decimal(line["debit"]) == Decimal("1000.00")
        for line in monetary_professional["ledger"]["lines"]
    )

    inkind = common.prepare_inkind_donation({
        "donor_name": donor["name"],
        "description": "Computadora donada",
        "quantity": "1",
        "date": "2026-02-02",
        "valuation_amount": "12000.00",
        "valuation_method": "avaluo",
        "valuation_evidence": "Avalúo firmado IK-001",
        "document_type": "constancia",
        "document_number": "IK-001",
        "document_date": "2026-02-02",
        "fund_name": fund["name"],
        "program_name": program["name"],
        "asset_code": "AF-IK-001",
        "asset_name": "Computadora donada",
        "useful_life_months": 36,
    })
    inkind_result = common.confirm(inkind["token"])
    inkind_professional = common.professional_inkind_donation(
        inkind_result["inkind_donation_id"]
    )
    assert inkind_professional["program"] == {"id": program["id"], "name": "Educación"}
    assert inkind_professional["fund"]["id"] == fund["id"]
    assert inkind_professional["cash_or_bank"] == []

    expense = common.prepare("utility_bank", "300.00", "2026-02-03")
    expense_result = common.confirm(expense["token"])
    candidates = common.fund_candidates("application")
    candidate = next(
        item for item in candidates if item["entry_id"] == expense_result["entry_id"]
    )
    application = common.record_fund_application({
        "fund_id": fund["id"],
        "program_id": program["id"],
        "journal_line_id": candidate["journal_line_id"],
        "amount": "300.00",
        "receipt_id": monetary_result["fund_receipt_id"],
        "purpose": "Servicios del programa",
    })
    assert application["program_id"] == program["id"]

    balance = common.fund_balance(fund["id"], "2026-02-03")
    assert Decimal(balance["received"]) == Decimal("1000.00")
    assert Decimal(balance["applied"]) == Decimal("300.00")
    assert Decimal(balance["available"]) == Decimal("700.00")
    assert balance["program_id"] == program["id"]

    trace = common.fund_traceability(fund["id"], "2026-02-03")
    assert trace["fund"]["program_id"] == program["id"]
    assert trace["receipts"][0]["source"]["id"] == source["id"]
    assert trace["applications"][0]["program_id"] == program["id"]

    # Program creation itself contributed no ledger row; only the two donations and
    # the actual utility expense are accounting facts.
    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 3

    # Reopening the product surface still resolves the same Program identity.
    assert ProgramPresentationController().programs() == [program]
