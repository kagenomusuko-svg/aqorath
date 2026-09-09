"""Phase 3E.3 — full accounts-payable lifecycle persists exact accounting truth."""

from decimal import Decimal


def test_accounts_payable_lifecycle_incurred_then_paid_returns_payable_to_zero(
    tmp_path,
    monkeypatch,
):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select

    import aqorath.application as application
    import aqorath.core as core
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    db_path = tmp_path / "accounts-payable-lifecycle-e2e.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        expense = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        payable = Account(code="2101", name="Proveedores", nature="CREDIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(expense)
        session.add(payable)
        session.add(bank)
        session.commit()
        session.refresh(expense)
        session.refresh(payable)
        session.refresh(bank)

        expense_id = expense.id
        payable_id = payable.id
        bank_id = bank.id

        session.add(
            AccountRoleBinding(role="utilities_expense", account_id=expense_id)
        )
        session.add(
            AccountRoleBinding(role="accounts_payable", account_id=payable_id)
        )
        session.add(AccountRoleBinding(role="bank", account_id=bank_id))
        session.commit()

    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(core, "get_session", isolated_get_session)
    monkeypatch.setattr(core, "_find_db_path", lambda: None)

    with Session(engine) as session:
        incurred_snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact(
                "utility_expense_incurred",
                Decimal("1500.00"),
                "credit",
            ),
        )
        incurred_confirmed = application.confirm_economic_fact(incurred_snapshot)
        incurred_result = application.post_confirmed_economic_fact(incurred_confirmed)

    with Session(engine) as session:
        payment_snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact(
                "supplier_payment",
                Decimal("1500.00"),
                "bank",
            ),
        )
        payment_confirmed = application.confirm_economic_fact(payment_snapshot)
        payment_result = application.post_confirmed_economic_fact(payment_confirmed)

    assert isinstance(incurred_result, dict)
    assert incurred_result.get("ok") is True
    assert isinstance(payment_result, dict)
    assert payment_result.get("ok") is True

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry).order_by(JournalEntry.id)).all()
        lines = session.exec(select(JournalLine).order_by(JournalLine.id)).all()

        assert len(entries) == 2
        assert len(lines) == 4
        assert [entry.concept for entry in entries] == [
            incurred_snapshot.explanation,
            payment_snapshot.explanation,
        ]

        lines_by_entry = {
            entry.id: [line for line in lines if line.entry_id == entry.id]
            for entry in entries
        }

        incurred_lines = {line.account_code: line for line in lines_by_entry[entries[0].id]}
        assert set(incurred_lines) == {"5102", "2101"}

        expense_line = incurred_lines["5102"]
        assert expense_line.account_id == expense_id
        assert Decimal(str(expense_line.debit)) == Decimal("1500.00")
        assert Decimal(str(expense_line.credit)) == Decimal("0")

        payable_created = incurred_lines["2101"]
        assert payable_created.account_id == payable_id
        assert Decimal(str(payable_created.debit)) == Decimal("0")
        assert Decimal(str(payable_created.credit)) == Decimal("1500.00")

        payment_lines = {line.account_code: line for line in lines_by_entry[entries[1].id]}
        assert set(payment_lines) == {"2101", "1101"}

        payable_paid = payment_lines["2101"]
        assert payable_paid.account_id == payable_id
        assert Decimal(str(payable_paid.debit)) == Decimal("1500.00")
        assert Decimal(str(payable_paid.credit)) == Decimal("0")

        bank_line = payment_lines["1101"]
        assert bank_line.account_id == bank_id
        assert Decimal(str(bank_line.debit)) == Decimal("0")
        assert Decimal(str(bank_line.credit)) == Decimal("1500.00")

        payable_lines = [line for line in lines if line.account_code == "2101"]
        payable_debits = sum(
            (Decimal(str(line.debit)) for line in payable_lines),
            Decimal("0"),
        )
        payable_credits = sum(
            (Decimal(str(line.credit)) for line in payable_lines),
            Decimal("0"),
        )
        assert payable_debits == payable_credits == Decimal("1500.00")

        expense_lines = [line for line in lines if line.account_code == "5102"]
        assert sum(
            (Decimal(str(line.debit)) for line in expense_lines),
            Decimal("0"),
        ) == Decimal("1500.00")
        assert sum(
            (Decimal(str(line.credit)) for line in expense_lines),
            Decimal("0"),
        ) == Decimal("0")

        bank_lines = [line for line in lines if line.account_code == "1101"]
        assert sum(
            (Decimal(str(line.debit)) for line in bank_lines),
            Decimal("0"),
        ) == Decimal("0")
        assert sum(
            (Decimal(str(line.credit)) for line in bank_lines),
            Decimal("0"),
        ) == Decimal("1500.00")

        assert {line.account_code for line in lines} == {"5102", "2101", "1101"}
