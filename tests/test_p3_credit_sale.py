"""Phase 3A.1 — second economic vertical: sale on credit contracts."""

from decimal import Decimal

import pytest


def test_credit_sale_fact_accepts_decimal_amount():
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="credit",
    )
    assert fact.type == "sale"
    assert fact.amount == Decimal("200.00")
    assert fact.payment_method == "credit"


def test_credit_sale_resolves_to_accounting_proposal():
    from aqorath.economic_facts import EconomicFact, AccountingProposal, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("sale", Decimal("200.00"), "credit")
    )
    assert isinstance(proposal, AccountingProposal)
    assert len(proposal.lines) == 2


def test_credit_sale_debits_accounts_receivable_and_credits_sales_revenue():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("sale", Decimal("200.00"), "credit")
    )

    assert [(line.account_role, line.side, line.amount) for line in proposal.lines] == [
        ("accounts_receivable", "debit", Decimal("200.00")),
        ("sales_revenue", "credit", Decimal("200.00")),
    ]

    for line in proposal.lines:
        assert not hasattr(line, "account_id")
        assert not hasattr(line, "account_code")
        assert not hasattr(line, "account_name")


def test_credit_sale_is_decimal_exact_balanced_ordered_and_explained():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("sale", Decimal("200.00"), "credit")
    )

    debit = sum(
        (line.amount for line in proposal.lines if line.side == "debit"),
        Decimal("0"),
    )
    credit = sum(
        (line.amount for line in proposal.lines if line.side == "credit"),
        Decimal("0"),
    )
    assert debit == credit == Decimal("200.00")
    assert all(isinstance(line.amount, Decimal) for line in proposal.lines)

    explanation = proposal.explanation.lower()
    assert any(word in explanation for word in ("sale", "venta", "sold"))
    assert any(word in explanation for word in ("credit", "receivable", "cuenta por cobrar", "cobrar"))
    assert any(word in explanation for word in ("revenue", "ingreso", "ventas"))


def test_credit_sale_resolution_is_deterministic():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact("sale", Decimal("200.00"), "credit")
    first = resolve_economic_fact(fact)
    second = resolve_economic_fact(fact)

    assert first == second
    assert first.explanation == second.explanation


def test_cash_sale_contract_remains_unchanged():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("sale", Decimal("200.00"), "cash")
    )
    assert [(line.account_role, line.side, line.amount) for line in proposal.lines] == [
        ("cash", "debit", Decimal("200.00")),
        ("sales_revenue", "credit", Decimal("200.00")),
    ]
    explanation = proposal.explanation.lower()
    assert "cash" in explanation or "efectivo" in explanation or "caja" in explanation


def test_configured_credit_sale_uses_persisted_accounts_receivable_binding():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        receivable = Account(code="1201", name="Clientes", nature="DEBIT")
        sales = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(receivable)
        session.add(sales)
        session.commit()
        session.refresh(receivable)
        session.refresh(sales)
        session.add(AccountRoleBinding(role="accounts_receivable", account_id=receivable.id))
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "credit"),
        )

        assert [(line.account_role, line.account_id, line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("accounts_receivable", receivable.id, "1201", "debit", Decimal("200.00")),
            ("sales_revenue", sales.id, "4101", "credit", Decimal("200.00")),
        ]


def test_credit_sale_confirmation_to_posting_instruction_preserves_truth():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding
    from aqorath.posting import PostingInstruction

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        receivable = Account(code="1201", name="Clientes", nature="DEBIT")
        sales = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(receivable)
        session.add(sales)
        session.commit()
        session.refresh(receivable)
        session.refresh(sales)
        session.add(AccountRoleBinding(role="accounts_receivable", account_id=receivable.id))
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "credit"),
        )
        confirmed = application.confirm_economic_fact(snapshot)

        import aqorath.posting as posting
        instruction = posting.create_posting_instruction(confirmed)

        assert isinstance(instruction, PostingInstruction)
        assert instruction.description == snapshot.explanation
        assert [(line.account_code, line.debit, line.credit) for line in instruction.lines] == [
            ("1201", Decimal("200.00"), Decimal("0")),
            ("4101", Decimal("0"), Decimal("200.00")),
        ]


def test_configured_credit_sale_missing_receivable_binding_fails_before_account_resolution(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.economic_facts import EconomicFact

    session = object()
    calls = []

    def missing_binding(supplied_session, roles):
        calls.append((supplied_session, roles))
        raise KeyError("accounts_receivable binding missing")

    def forbidden_resolution(*args, **kwargs):
        raise AssertionError("account resolution must not run after binding load failure")

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", missing_binding)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden_resolution)

    with pytest.raises(KeyError, match="accounts_receivable"):
        application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "credit"),
        )

    assert calls == [(session, ("accounts_receivable", "sales_revenue"))]
