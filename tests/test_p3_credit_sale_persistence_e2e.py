"""Phase 3A.3 — confirmed credit sale persists exactly through SQLite authority."""

from decimal import Decimal


def test_credit_sale_confirmed_truth_persists_to_sqlite(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select

    import aqorath.application as application
    import aqorath.core as core
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    db_path = tmp_path / "credit-sale-e2e.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        receivable = Account(code="1201", name="Clientes", nature="DEBIT")
        sales = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(receivable)
        session.add(sales)
        session.commit()
        session.refresh(receivable)
        session.refresh(sales)
        receivable_id = receivable.id
        sales_id = sales.id
        session.add(AccountRoleBinding(role="accounts_receivable", account_id=receivable_id))
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales_id))
        session.commit()

    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    with Session(engine) as session:
        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "credit"),
        )
        confirmed = application.confirm_economic_fact(snapshot)
        result = application.post_confirmed_economic_fact(confirmed)

    assert isinstance(result, dict)
    assert result.get("ok") is True

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()

        assert len(entries) == 1
        assert len(lines) == 2
        entry = entries[0]
        assert entry.concept == snapshot.explanation

        by_code = {line.account_code: line for line in lines}
        assert set(by_code) == {"1201", "4101"}

        receivable_line = by_code["1201"]
        assert receivable_line.account_id == receivable_id
        assert Decimal(str(receivable_line.debit)) == Decimal("200.00")
        assert Decimal(str(receivable_line.credit)) == Decimal("0")

        sales_line = by_code["4101"]
        assert sales_line.account_id == sales_id
        assert Decimal(str(sales_line.debit)) == Decimal("0")
        assert Decimal(str(sales_line.credit)) == Decimal("200.00")

        assert all(line.entry_id == entry.id for line in lines)
