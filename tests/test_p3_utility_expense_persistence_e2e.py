"""Phase 3B.3 — confirmed utility expense persists exactly through SQLite authority."""

from decimal import Decimal


def test_utility_expense_confirmed_truth_persists_to_sqlite(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select

    import aqorath.application as application
    import aqorath.core as core
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    db_path = tmp_path / "utility-expense-e2e.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        utilities = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(utilities)
        session.add(bank)
        session.commit()
        session.refresh(utilities)
        session.refresh(bank)
        utilities_id = utilities.id
        bank_id = bank.id
        session.add(AccountRoleBinding(role="utilities_expense", account_id=utilities_id))
        session.add(AccountRoleBinding(role="bank", account_id=bank_id))
        session.commit()

    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    with Session(engine) as session:
        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense", Decimal("1500.00"), "bank"),
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
        assert set(by_code) == {"5102", "1101"}

        utilities_line = by_code["5102"]
        assert utilities_line.account_id == utilities_id
        assert Decimal(str(utilities_line.debit)) == Decimal("1500.00")
        assert Decimal(str(utilities_line.credit)) == Decimal("0")

        bank_line = by_code["1101"]
        assert bank_line.account_id == bank_id
        assert Decimal(str(bank_line.debit)) == Decimal("0")
        assert Decimal(str(bank_line.credit)) == Decimal("1500.00")

        assert all(line.entry_id == entry.id for line in lines)
