"""Phase 3F — full accounts-receivable lifecycle preserves one revenue recognition."""

from decimal import Decimal


def test_accounts_receivable_lifecycle_sale_then_collection_returns_receivable_to_zero(
    tmp_path,
    monkeypatch,
):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select

    import aqorath.application as application
    import aqorath.core as core
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    db_path = tmp_path / "accounts-receivable-lifecycle-e2e.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        receivable = Account(code="1103", name="Clientes", nature="DEBIT")
        sales = Account(
            code="4201",
            name="Venta de productos elaborados",
            nature="CREDIT",
        )
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(receivable)
        session.add(sales)
        session.add(bank)
        session.commit()
        session.refresh(receivable)
        session.refresh(sales)
        session.refresh(bank)

        receivable_id = receivable.id
        sales_id = sales.id
        bank_id = bank.id

        session.add(
            AccountRoleBinding(
                role="accounts_receivable",
                account_id=receivable_id,
            )
        )
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales_id))
        session.add(AccountRoleBinding(role="bank", account_id=bank_id))
        session.commit()

    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    with Session(engine) as session:
        sale_snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "credit"),
        )
        sale_confirmed = application.confirm_economic_fact(sale_snapshot)
        sale_result = application.post_confirmed_economic_fact(sale_confirmed)

    with Session(engine) as session:
        collection_snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact(
                "receivable_collection",
                Decimal("200.00"),
                "bank",
            ),
        )
        collection_confirmed = application.confirm_economic_fact(collection_snapshot)
        collection_result = application.post_confirmed_economic_fact(collection_confirmed)

    assert isinstance(sale_result, dict)
    assert sale_result.get("ok") is True
    assert isinstance(collection_result, dict)
    assert collection_result.get("ok") is True

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry).order_by(JournalEntry.id)).all()
        lines = session.exec(select(JournalLine).order_by(JournalLine.id)).all()

        assert len(entries) == 2
        assert len(lines) == 4
        assert [entry.concept for entry in entries] == [
            sale_snapshot.explanation,
            collection_snapshot.explanation,
        ]

        lines_by_entry = {
            entry.id: [line for line in lines if line.entry_id == entry.id]
            for entry in entries
        }

        sale_lines = {
            line.account_code: line
            for line in lines_by_entry[entries[0].id]
        }
        assert set(sale_lines) == {"1103", "4201"}

        receivable_created = sale_lines["1103"]
        assert receivable_created.account_id == receivable_id
        assert Decimal(str(receivable_created.debit)) == Decimal("200.00")
        assert Decimal(str(receivable_created.credit)) == Decimal("0")

        sales_line = sale_lines["4201"]
        assert sales_line.account_id == sales_id
        assert Decimal(str(sales_line.debit)) == Decimal("0")
        assert Decimal(str(sales_line.credit)) == Decimal("200.00")

        collection_lines = {
            line.account_code: line
            for line in lines_by_entry[entries[1].id]
        }
        assert set(collection_lines) == {"1101", "1103"}

        bank_line = collection_lines["1101"]
        assert bank_line.account_id == bank_id
        assert Decimal(str(bank_line.debit)) == Decimal("200.00")
        assert Decimal(str(bank_line.credit)) == Decimal("0")

        receivable_collected = collection_lines["1103"]
        assert receivable_collected.account_id == receivable_id
        assert Decimal(str(receivable_collected.debit)) == Decimal("0")
        assert Decimal(str(receivable_collected.credit)) == Decimal("200.00")

        receivable_lines = [line for line in lines if line.account_code == "1103"]
        receivable_debits = sum(
            (Decimal(str(line.debit)) for line in receivable_lines),
            Decimal("0"),
        )
        receivable_credits = sum(
            (Decimal(str(line.credit)) for line in receivable_lines),
            Decimal("0"),
        )
        assert receivable_debits == receivable_credits == Decimal("200.00")

        sales_lines = [line for line in lines if line.account_code == "4201"]
        assert len(sales_lines) == 1
        assert sum(
            (Decimal(str(line.debit)) for line in sales_lines),
            Decimal("0"),
        ) == Decimal("0")
        assert sum(
            (Decimal(str(line.credit)) for line in sales_lines),
            Decimal("0"),
        ) == Decimal("200.00")

        bank_lines = [line for line in lines if line.account_code == "1101"]
        assert len(bank_lines) == 1
        assert sum(
            (Decimal(str(line.debit)) for line in bank_lines),
            Decimal("0"),
        ) == Decimal("200.00")
        assert sum(
            (Decimal(str(line.credit)) for line in bank_lines),
            Decimal("0"),
        ) == Decimal("0")

        assert {line.account_code for line in lines} == {"1103", "4201", "1101"}
