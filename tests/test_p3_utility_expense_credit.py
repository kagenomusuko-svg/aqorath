"""Phase 3E.1 — utility expense incurred on credit contracts."""

from decimal import Decimal

import pytest


def test_utility_expense_incurred_credit_fact_accepts_decimal_amount():
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit")
    assert fact.type == "utility_expense_incurred"
    assert fact.amount == Decimal("1500.00")
    assert fact.payment_method == "credit"


def test_utility_expense_incurred_resolves_to_accounting_proposal():
    from aqorath.economic_facts import EconomicFact, AccountingProposal, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit")
    )
    assert isinstance(proposal, AccountingProposal)
    assert len(proposal.lines) == 2


def test_utility_expense_incurred_debits_expense_and_credits_accounts_payable_without_bank():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit")
    )
    assert [(line.account_role, line.side, line.amount) for line in proposal.lines] == [
        ("utilities_expense", "debit", Decimal("1500.00")),
        ("accounts_payable", "credit", Decimal("1500.00")),
    ]
    assert all(line.account_role != "bank" for line in proposal.lines)


def test_utility_expense_incurred_is_decimal_exact_balanced_ordered_and_explained():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit")
    )
    debit = sum((line.amount for line in proposal.lines if line.side == "debit"), Decimal("0"))
    credit = sum((line.amount for line in proposal.lines if line.side == "credit"), Decimal("0"))
    assert debit == credit == Decimal("1500.00")
    assert all(isinstance(line.amount, Decimal) for line in proposal.lines)

    explanation = proposal.explanation.lower()
    assert any(word in explanation for word in ("utility", "service", "servicio"))
    assert any(word in explanation for word in ("credit", "payable", "por pagar", "obligation", "obligación"))
    assert "paid from bank" not in explanation


def test_utility_expense_incurred_resolution_is_deterministic():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit")
    assert resolve_economic_fact(fact) == resolve_economic_fact(fact)


def test_existing_economic_fact_verticals_and_utility_expense_contract_remain_unchanged():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    expected = {
        ("sale", "cash"): [("cash", "debit"), ("sales_revenue", "credit")],
        ("sale", "credit"): [("accounts_receivable", "debit"), ("sales_revenue", "credit")],
        ("utility_expense", "bank"): [("utilities_expense", "debit"), ("bank", "credit")],
        ("receivable_collection", "bank"): [("bank", "debit"), ("accounts_receivable", "credit")],
        ("supplier_payment", "bank"): [("accounts_payable", "debit"), ("bank", "credit")],
    }
    for (type_, payment), roles in expected.items():
        proposal = resolve_economic_fact(EconomicFact(type_, Decimal("100.00"), payment))
        assert [(line.account_role, line.side) for line in proposal.lines] == roles

    with pytest.raises((TypeError, ValueError)):
        EconomicFact("utility_expense", Decimal("100.00"), "credit")


def test_utility_expense_incurred_rejects_non_credit_payment_methods():
    from aqorath.economic_facts import EconomicFact

    for payment_method in ("cash", "bank"):
        with pytest.raises((TypeError, ValueError)):
            EconomicFact("utility_expense_incurred", Decimal("1500.00"), payment_method)


def test_configured_utility_expense_incurred_uses_persisted_expense_and_payable_bindings():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        expense = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        payable = Account(code="2101", name="Proveedores", nature="CREDIT")
        session.add(expense)
        session.add(payable)
        session.commit()
        session.refresh(expense)
        session.refresh(payable)
        session.add(AccountRoleBinding(role="utilities_expense", account_id=expense.id))
        session.add(AccountRoleBinding(role="accounts_payable", account_id=payable.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit"),
        )
        assert [(line.account_role, line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("utilities_expense", "5102", "debit", Decimal("1500.00")),
            ("accounts_payable", "2101", "credit", Decimal("1500.00")),
        ]


def test_utility_expense_incurred_confirmation_to_posting_instruction_preserves_truth():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    import aqorath.posting as posting
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        expense = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        payable = Account(code="2101", name="Proveedores", nature="CREDIT")
        session.add(expense)
        session.add(payable)
        session.commit()
        session.refresh(expense)
        session.refresh(payable)
        session.add(AccountRoleBinding(role="utilities_expense", account_id=expense.id))
        session.add(AccountRoleBinding(role="accounts_payable", account_id=payable.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit"),
        )
        confirmed = application.confirm_economic_fact(snapshot)
        instruction = posting.create_posting_instruction(confirmed)
        assert [(line.account_code, line.debit, line.credit) for line in instruction.lines] == [
            ("5102", Decimal("1500.00"), Decimal("0")),
            ("2101", Decimal("0"), Decimal("1500.00")),
        ]
        assert instruction.description == snapshot.explanation


def test_configured_utility_expense_incurred_missing_payable_binding_fails_before_account_resolution(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.economic_facts import EconomicFact

    session = object()
    calls = []

    def missing(supplied_session, roles):
        calls.append((supplied_session, roles))
        raise KeyError("accounts_payable binding missing")

    def forbidden(*args, **kwargs):
        raise AssertionError("account resolution must not run after binding load failure")

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", missing)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)

    with pytest.raises(KeyError, match="accounts_payable"):
        application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense_incurred", Decimal("1500.00"), "credit"),
        )

    assert calls == [(session, ("utilities_expense", "accounts_payable"))]
