"""Phase 3C.3 — confirmed receivable collection persists exactly through SQLite authority."""

from decimal import Decimal


def test_receivable_collection_confirmed_truth_persists_to_sqlite(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select

    import aqorath.application as application
    import aqorath.core as core
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    db_path = tmp_path / "receivable-collection-e2e.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        receivable = Account(code="1103", name="Clientes", nature="DEBIT")
        session.add(bank)
        session.add(receivable)
        session.commit()
        session.refresh(bank)
        session.refresh(receivable)
        bank_id = bank.id
        receivable_id = receivable.id
        session.add(AccountRoleBinding(role="bank", account_id=bank_id))
        session.add(
            AccountRoleBinding(
                role="accounts_receivable",
                account_id=receivable_id,
            )
        )
        session.commit()

    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    with Session(engine) as session:
        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact(
                "receivable_collection",
                Decimal("200.00"),
                "bank",
            ),
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
        assert set(by_code) == {"1101", "1103"}

        bank_line = by_code["1101"]
        assert bank_line.account_id == bank_id
        assert Decimal(str(bank_line.debit)) == Decimal("200.00")
        assert Decimal(str(bank_line.credit)) == Decimal("0")

        receivable_line = by_code["1103"]
        assert receivable_line.account_id == receivable_id
        assert Decimal(str(receivable_line.debit)) == Decimal("0")
        assert Decimal(str(receivable_line.credit)) == Decimal("200.00")

        assert all(line.entry_id == entry.id for line in lines)
