from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from sqlalchemy import create_engine
from sqlmodel import Session


def _runtime(tmp_path):
    import aqorath.storage as storage
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.models import Account
    from aqorath.account_bindings import set_account_binding
    from aqorath.program import Program
    from aqorath.program_repository import create_program
    from aqorath.fund import Fund, FundingSource
    from aqorath.fund_repository import create_fund, create_funding_source
    path = tmp_path / "e2e.db"
    engine = storage.init_db(str(path))
    with Session(engine) as session:
        entity = create_entity(session, Entity(id=None, name="OSC E2E", rfc=None, legal_personality="persona_moral", legal_form="A.C.", profile=EntityProfile("no_lucrativo", False, ("osc",), ("banking",)), is_active=True))
        bank = Account(code="1101", name="Banco", nature="DEBIT")
        income = Account(code="4301", name="Donativos", nature="CREDIT")
        asset = Account(code="1205", name="Equipo de cómputo", nature="DEBIT")
        session.add_all([bank, income, asset]); session.commit()
        set_account_binding(session, "bank", "1101"); set_account_binding(session, "donation_income", "4301"); set_account_binding(session, "fixed_asset_computer_equipment", "1205")
        program = create_program(session, Program(None, entity.id, "Educación", None, None))
        fund = create_fund(session, Fund(None, entity.id, "EDU", "Educación", "restricted", program_id=program.id))
        source = create_funding_source(session, FundingSource(None, entity.id, "Donante principal"))
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)
    return engine, entity, program, fund, source


def _monetary_prepared(engine, fund, source, program, donor=None):
    from aqorath.application import prepare_monetary_donation
    return prepare_monetary_donation(Session(engine), Decimal("1000.00"), datetime(2026, 2, 1, tzinfo=timezone.utc), donor_third_party_id=donor, document_type="acta", document_number="DON-001", document_date=datetime(2026, 2, 1, tzinfo=timezone.utc), fund_id=fund.id, funding_source_id=source.id, program_id=program.id, purpose="Educación", is_restricted=True)


def _inkind_prepared(engine, fund, program):
    from aqorath.application import prepare_inkind_donation
    return prepare_inkind_donation(Session(engine), Decimal("12000.00"), datetime(2026, 2, 2, tzinfo=timezone.utc), donor_third_party_id=None, document_type="constancia", document_number="IK-001", document_date=datetime(2026, 2, 2, tzinfo=timezone.utc), received_at=datetime(2026, 2, 2, tzinfo=timezone.utc), description="Computadora", quantity=Decimal("1"), valuation_method="avaluo", valuation_evidence="Avalúo firmado 12000", external_reference="IK-001", asset_code="AF-001", asset_name="Computadora donada", useful_life_months=36, program_id=program.id, fund_id=fund.id)


def test_schema10_adds_inkind_evidence_without_backfill(tmp_path):
    from aqorath.migrations import migrate_database
    path = tmp_path / "donations.db"
    migrate_database(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= {"donation", "inkinddonation"}
        assert conn.execute("SELECT count(*) FROM inkinddonation").fetchone()[0] == 0


def test_inkind_donation_persists_exact_valuation_and_never_posts(tmp_path):
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.inkind_donation import InKindDonation
    from aqorath.inkind_donation_repository import create_inkind_donation
    path = tmp_path / "donations.db"
    from aqorath.migrations import migrate_database
    migrate_database(path)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        entity = create_entity(session, Entity(id=None, name="OSC", rfc=None, legal_personality="persona_moral", legal_form="A.C.", profile=EntityProfile("no_lucrativo", False, ("osc",), ("banking",)), is_active=True))
        item = create_inkind_donation(session, InKindDonation(None, entity.id, None, None, None, None, None, None, datetime(2026, 1, 2, tzinfo=timezone.utc), "Computadoras", Decimal("2"), Decimal("1500.00"), "MXN", "appraisal", "Avalúo firmado", "IK-001"))
        assert item.valuation_amount == Decimal("1500.00")
        assert session.exec(__import__("sqlmodel").select(__import__("aqorath.models", fromlist=["InKindDonationRecord"]).InKindDonationRecord)).one().valuation_amount == "1500.00"


def test_monetary_donation_e2e_is_atomic_and_idempotent(tmp_path):
    from aqorath.application import confirm_monetary_donation, load_monetary_donation_trace
    from aqorath.models import JournalEntry, DonationRecord, DocumentReferenceRecord, AuditEventRecord
    from aqorath.fund_models import FundReceiptRecord
    engine, entity, program, fund, source = _runtime(tmp_path)
    prepared = _monetary_prepared(engine, fund, source, program)
    first = confirm_monetary_donation(prepared)
    second = confirm_monetary_donation(prepared)
    assert first == second
    with Session(engine) as session:
        assert len(session.exec(__import__("sqlmodel").select(JournalEntry)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(DonationRecord)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(DocumentReferenceRecord)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(FundReceiptRecord)).all()) == 1
        audits = session.exec(__import__("sqlmodel").select(AuditEventRecord)).all()
        assert len([a for a in audits if a.event_type == "entry_posted"]) == 1
        trace = load_monetary_donation_trace(session, entity.id, first["donation_id"])
        assert {tuple((line["debit"], line["credit"]) for line in trace["ledger"]["lines"])}
        assert sorted((line["debit"], line["credit"]) for line in trace["ledger"]["lines"]) == [("0", "1000.00"), ("1000.00", "0")]


def test_inkind_donation_e2e_creates_asset_line_not_cash_and_is_idempotent(tmp_path):
    from aqorath.application import confirm_inkind_donation
    from aqorath.models import JournalEntry, JournalLine, FixedAssetRecord, InKindDonationRecord, DocumentReferenceRecord, AuditEventRecord
    engine, entity, program, fund, source = _runtime(tmp_path)
    prepared = _inkind_prepared(engine, fund, program)
    first = confirm_inkind_donation(prepared)
    assert confirm_inkind_donation(prepared) == first
    with Session(engine) as session:
        assert len(session.exec(__import__("sqlmodel").select(JournalEntry)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(FixedAssetRecord)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(InKindDonationRecord)).all()) == 1
        assert len(session.exec(__import__("sqlmodel").select(DocumentReferenceRecord)).all()) == 1
        assert len([a for a in session.exec(__import__("sqlmodel").select(AuditEventRecord)).all() if a.event_type == "entry_posted"]) == 1
        lines = session.exec(__import__("sqlmodel").select(JournalLine).where(JournalLine.entry_id == first["entry_id"])).all()
        by_role = {"asset": next(x for x in lines if x.account_code == "1205"), "income": next(x for x in lines if x.account_code == "4301")}
        assert (by_role["asset"].debit, by_role["asset"].credit) == ("12000.00", "0")
        assert (by_role["income"].debit, by_role["income"].credit) == ("0", "12000.00")
        assert session.exec(__import__("sqlmodel").select(InKindDonationRecord)).one().journal_line_id == by_role["asset"].id


def test_donation_composition_rolls_back_everything_after_posting(tmp_path, monkeypatch):
    import aqorath.donation_operations as operations
    from aqorath.application import confirm_monetary_donation
    from aqorath.models import JournalEntry, DonationRecord, DocumentReferenceRecord, AuditEventRecord
    from aqorath.fund_models import FundReceiptRecord
    engine, entity, program, fund, source = _runtime(tmp_path)
    prepared = _monetary_prepared(engine, fund, source, program)
    real = operations.DocumentReferenceRecord
    class FailDocument:
        def __init__(self, *args, **kwargs): raise RuntimeError("document failure")
    monkeypatch.setattr(operations, "DocumentReferenceRecord", FailDocument)
    try:
        import pytest
        with pytest.raises(RuntimeError, match="document failure"):
            confirm_monetary_donation(prepared)
    finally:
        monkeypatch.setattr(operations, "DocumentReferenceRecord", real)
    with Session(engine) as session:
        assert session.exec(__import__("sqlmodel").select(JournalEntry)).all() == []
        assert session.exec(__import__("sqlmodel").select(DonationRecord)).all() == []
        assert session.exec(__import__("sqlmodel").select(DocumentReferenceRecord)).all() == []
        assert session.exec(__import__("sqlmodel").select(FundReceiptRecord)).all() == []
        assert [a for a in session.exec(__import__("sqlmodel").select(AuditEventRecord)).all() if a.event_type == "entry_posted"] == []


def test_monetary_reversal_preserves_history_and_removes_effective_receipt(tmp_path):
    from aqorath.application import confirm_monetary_donation, load_monetary_donation_trace
    from aqorath.fund_repository import load_fund_balance
    from aqorath.reversal import reverse_posted_entry
    engine, entity, program, fund, source = _runtime(tmp_path)
    result = confirm_monetary_donation(_monetary_prepared(engine, fund, source, program))
    with Session(engine) as session:
        reverse_posted_entry(session, result["entry_id"], "donativo revertido", datetime(2026, 2, 3, tzinfo=timezone.utc).date())
        session.commit()
        trace = load_monetary_donation_trace(session, entity.id, result["donation_id"])
        assert trace["donation"]["id"] == result["donation_id"]
        assert trace["ledger"]["state"] == "reversed"
        assert trace["ledger"]["reversal_entry_id"] is not None
        balance = load_fund_balance(session, entity.id, fund.id, datetime(2026, 2, 4, tzinfo=timezone.utc).date())
        assert balance.received == Decimal("0")


def test_inkind_reversal_preserves_asset_and_professional_trace(tmp_path):
    from aqorath.application import confirm_inkind_donation, load_inkind_donation_trace
    from aqorath.reversal import reverse_posted_entry
    engine, entity, program, fund, source = _runtime(tmp_path)
    result = confirm_inkind_donation(_inkind_prepared(engine, fund, program))
    with Session(engine) as session:
        reverse_posted_entry(session, result["entry_id"], "especie revertida", datetime(2026, 2, 3, tzinfo=timezone.utc).date())
        session.commit()
        trace = load_inkind_donation_trace(session, entity.id, result["inkind_donation_id"])
        assert trace["fixed_asset"]["id"] == result["fixed_asset_id"]
        assert trace["fixed_asset"]["acquisition_cost"] == "12000.00"
        assert trace["ledger"]["state"] == "reversed"
        assert trace["ledger"]["reversal_entry_id"] is not None
        assert trace["ledger"]["cash_or_bank_lines"] == []


def test_inkind_provenance_rejects_monetary_donation_line(tmp_path):
    import pytest
    from aqorath.application import confirm_monetary_donation
    from aqorath.inkind_donation import InKindDonation
    from aqorath.inkind_donation_repository import create_inkind_donation
    from aqorath.models import DonationRecord, JournalLine
    engine, entity, program, fund, source = _runtime(tmp_path)
    result = confirm_monetary_donation(_monetary_prepared(engine, fund, source, program))
    with Session(engine) as session:
        line = session.exec(__import__("sqlmodel").select(JournalLine).where(JournalLine.entry_id == result["entry_id"], JournalLine.debit != "0")).one()
        with pytest.raises(ValueError, match="in-kind donation provenance"):
            create_inkind_donation(session, InKindDonation(None, entity.id, None, None, fund.id, program.id, line.id, None, datetime(2026, 2, 1, tzinfo=timezone.utc), "Computadora", Decimal("1"), Decimal("1000"), "MXN", "avaluo", "evidence", "bad-ik"))
