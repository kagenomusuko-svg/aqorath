"""Phase 3B.1 — utility expense paid by bank contracts."""

from decimal import Decimal

import pytest


def test_utility_expense_bank_fact_accepts_decimal_amount():
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact(
        type="utility_expense",
        amount=Decimal("1500.00"),
        payment_method="bank",
    )
    assert fact.type == "utility_expense"
    assert fact.amount == Decimal("1500.00")
    assert fact.payment_method == "bank"


def test_utility_expense_bank_resolves_to_accounting_proposal():
    from aqorath.economic_facts import EconomicFact, AccountingProposal, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense", Decimal("1500.00"), "bank")
    )
    assert isinstance(proposal, AccountingProposal)
    assert len(proposal.lines) == 2


def test_utility_expense_debits_utilities_expense_and_credits_bank():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense", Decimal("1500.00"), "bank")
    )

    assert [(line.account_role, line.side, line.amount) for line in proposal.lines] == [
        ("utilities_expense", "debit", Decimal("1500.00")),
        ("bank", "credit", Decimal("1500.00")),
    ]

    for line in proposal.lines:
        assert not hasattr(line, "account_id")
        assert not hasattr(line, "account_code")
        assert not hasattr(line, "account_name")


def test_utility_expense_is_decimal_exact_balanced_ordered_and_explained():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("utility_expense", Decimal("1500.00"), "bank")
    )

    debit = sum(
        (line.amount for line in proposal.lines if line.side == "debit"),
        Decimal("0"),
    )
    credit = sum(
        (line.amount for line in proposal.lines if line.side == "credit"),
        Decimal("0"),
    )
    assert debit == credit == Decimal("1500.00")
    assert all(isinstance(line.amount, Decimal) for line in proposal.lines)

    explanation = proposal.explanation.lower()
    assert any(word in explanation for word in ("utility", "utilities", "service", "servicio"))
    assert any(word in explanation for word in ("bank", "banco", "bank account"))
    assert any(word in explanation for word in ("paid", "payment", "pagado", "pago"))


def test_utility_expense_resolution_is_deterministic():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact("utility_expense", Decimal("1500.00"), "bank")
    first = resolve_economic_fact(fact)
    second = resolve_economic_fact(fact)

    assert first == second
    assert first.explanation == second.explanation


def test_existing_sale_verticals_remain_unchanged():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    cash = resolve_economic_fact(EconomicFact("sale", Decimal("200.00"), "cash"))
    credit = resolve_economic_fact(EconomicFact("sale", Decimal("200.00"), "credit"))

    assert [(line.account_role, line.side, line.amount) for line in cash.lines] == [
        ("cash", "debit", Decimal("200.00")),
        ("sales_revenue", "credit", Decimal("200.00")),
    ]
    assert [(line.account_role, line.side, line.amount) for line in credit.lines] == [
        ("accounts_receivable", "debit", Decimal("200.00")),
        ("sales_revenue", "credit", Decimal("200.00")),
    ]


def test_unsupported_type_payment_combinations_are_rejected():
    from aqorath.economic_facts import EconomicFact

    for type_, payment_method in (
        ("sale", "bank"),
        ("utility_expense", "cash"),
        ("utility_expense", "credit"),
    ):
        with pytest.raises((TypeError, ValueError)):
            EconomicFact(type_, Decimal("100.00"), payment_method)


def test_configured_utility_expense_uses_persisted_bindings():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        utilities = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(utilities)
        session.add(bank)
        session.commit()
        session.refresh(utilities)
        session.refresh(bank)
        session.add(AccountRoleBinding(role="utilities_expense", account_id=utilities.id))
        session.add(AccountRoleBinding(role="bank", account_id=bank.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense", Decimal("1500.00"), "bank"),
        )

        assert [(line.account_role, line.account_id, line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("utilities_expense", utilities.id, "5102", "debit", Decimal("1500.00")),
            ("bank", bank.id, "1101", "credit", Decimal("1500.00")),
        ]


def test_utility_expense_confirmation_to_posting_instruction_preserves_truth():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    import aqorath.posting as posting
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding
    from aqorath.posting import PostingInstruction

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        utilities = Account(code="5102", name="Servicios básicos", nature="DEBIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(utilities)
        session.add(bank)
        session.commit()
        session.refresh(utilities)
        session.refresh(bank)
        session.add(AccountRoleBinding(role="utilities_expense", account_id=utilities.id))
        session.add(AccountRoleBinding(role="bank", account_id=bank.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense", Decimal("1500.00"), "bank"),
        )
        confirmed = application.confirm_economic_fact(snapshot)
        instruction = posting.create_posting_instruction(confirmed)

        assert isinstance(instruction, PostingInstruction)
        assert instruction.description == snapshot.explanation
        assert [(line.account_code, line.debit, line.credit) for line in instruction.lines] == [
            ("5102", Decimal("1500.00"), Decimal("0")),
            ("1101", Decimal("0"), Decimal("1500.00")),
        ]


def test_configured_utility_expense_missing_binding_fails_before_account_resolution(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.economic_facts import EconomicFact

    session = object()
    calls = []

    def missing_binding(supplied_session, roles):
        calls.append((supplied_session, roles))
        raise KeyError("utilities_expense binding missing")

    def forbidden_resolution(*args, **kwargs):
        raise AssertionError("account resolution must not run after binding load failure")

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", missing_binding)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden_resolution)

    with pytest.raises(KeyError, match="utilities_expense"):
        application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("utility_expense", Decimal("1500.00"), "bank"),
        )

    assert calls == [(session, ("utilities_expense", "bank"))]
