"""Phase 3D.1 — supplier payment by bank contracts."""

from decimal import Decimal

import pytest


def test_supplier_payment_bank_fact_accepts_decimal_amount():
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact("supplier_payment", Decimal("800.00"), "bank")
    assert fact.type == "supplier_payment"
    assert fact.amount == Decimal("800.00")
    assert fact.payment_method == "bank"


def test_supplier_payment_resolves_to_accounting_proposal():
    from aqorath.economic_facts import EconomicFact, AccountingProposal, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("supplier_payment", Decimal("800.00"), "bank")
    )
    assert isinstance(proposal, AccountingProposal)
    assert len(proposal.lines) == 2


def test_supplier_payment_debits_accounts_payable_and_credits_bank_without_new_expense():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("supplier_payment", Decimal("800.00"), "bank")
    )
    assert [(line.account_role, line.side, line.amount) for line in proposal.lines] == [
        ("accounts_payable", "debit", Decimal("800.00")),
        ("bank", "credit", Decimal("800.00")),
    ]
    assert all(line.account_role != "utilities_expense" for line in proposal.lines)
    assert all(line.account_role != "sales_revenue" for line in proposal.lines)


def test_supplier_payment_is_decimal_exact_balanced_ordered_and_explained():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    proposal = resolve_economic_fact(
        EconomicFact("supplier_payment", Decimal("800.00"), "bank")
    )
    debit = sum((line.amount for line in proposal.lines if line.side == "debit"), Decimal("0"))
    credit = sum((line.amount for line in proposal.lines if line.side == "credit"), Decimal("0"))
    assert debit == credit == Decimal("800.00")
    assert all(isinstance(line.amount, Decimal) for line in proposal.lines)

    explanation = proposal.explanation.lower()
    assert any(word in explanation for word in ("supplier", "provider", "proveedor", "payable"))
    assert any(word in explanation for word in ("bank", "banco", "transfer"))
    assert any(word in explanation for word in ("payable", "liability", "obligation", "por pagar", "obligación"))
    assert "expense recognized" not in explanation


def test_supplier_payment_resolution_is_deterministic():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact("supplier_payment", Decimal("800.00"), "bank")
    assert resolve_economic_fact(fact) == resolve_economic_fact(fact)


def test_existing_economic_fact_verticals_remain_unchanged():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    expected = {
        ("sale", "cash"): [("cash", "debit"), ("sales_revenue", "credit")],
        ("sale", "credit"): [("accounts_receivable", "debit"), ("sales_revenue", "credit")],
        ("utility_expense", "bank"): [("utilities_expense", "debit"), ("bank", "credit")],
        ("receivable_collection", "bank"): [("bank", "debit"), ("accounts_receivable", "credit")],
    }
    for (type_, payment), roles in expected.items():
        proposal = resolve_economic_fact(EconomicFact(type_, Decimal("100.00"), payment))
        assert [(line.account_role, line.side) for line in proposal.lines] == roles


def test_supplier_payment_rejects_unsupported_payment_methods():
    from aqorath.economic_facts import EconomicFact

    for payment_method in ("cash", "credit"):
        with pytest.raises((TypeError, ValueError)):
            EconomicFact("supplier_payment", Decimal("800.00"), payment_method)


def test_configured_supplier_payment_uses_persisted_accounts_payable_and_bank_bindings():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        payable = Account(code="2101", name="Proveedores", nature="CREDIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(payable)
        session.add(bank)
        session.commit()
        session.refresh(payable)
        session.refresh(bank)
        session.add(AccountRoleBinding(role="accounts_payable", account_id=payable.id))
        session.add(AccountRoleBinding(role="bank", account_id=bank.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("supplier_payment", Decimal("800.00"), "bank"),
        )
        assert [(line.account_role, line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("accounts_payable", "2101", "debit", Decimal("800.00")),
            ("bank", "1101", "credit", Decimal("800.00")),
        ]


def test_supplier_payment_confirmation_to_posting_instruction_preserves_truth():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session

    import aqorath.application as application
    import aqorath.posting as posting
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        payable = Account(code="2101", name="Proveedores", nature="CREDIT")
        bank = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(payable)
        session.add(bank)
        session.commit()
        session.refresh(payable)
        session.refresh(bank)
        session.add(AccountRoleBinding(role="accounts_payable", account_id=payable.id))
        session.add(AccountRoleBinding(role="bank", account_id=bank.id))
        session.commit()

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("supplier_payment", Decimal("800.00"), "bank"),
        )
        confirmed = application.confirm_economic_fact(snapshot)
        instruction = posting.create_posting_instruction(confirmed)
        assert [(line.account_code, line.debit, line.credit) for line in instruction.lines] == [
            ("2101", Decimal("800.00"), Decimal("0")),
            ("1101", Decimal("0"), Decimal("800.00")),
        ]
        assert instruction.description == snapshot.explanation


def test_configured_supplier_payment_missing_binding_fails_before_account_resolution(monkeypatch):
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
            EconomicFact("supplier_payment", Decimal("800.00"), "bank"),
        )

    assert calls == [(session, ("accounts_payable", "bank"))]
