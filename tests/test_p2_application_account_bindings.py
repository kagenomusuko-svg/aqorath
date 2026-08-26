"""Phase 2D.4 — application integration for persistent account-role bindings."""

from decimal import Decimal
from types import SimpleNamespace

import pytest


def test_application_exposes_account_binding_configuration_and_configured_confirmation():
    import aqorath.application as application

    for name in (
        "set_account_binding",
        "get_account_binding",
        "prepare_configured_economic_fact_confirmation",
    ):
        assert hasattr(application, name)
        assert callable(getattr(application, name))


def test_application_account_binding_api_has_exact_signatures():
    from inspect import Parameter, signature
    import aqorath.application as application

    expected = {
        "set_account_binding": ["session", "role", "account_code"],
        "get_account_binding": ["session", "role"],
        "prepare_configured_economic_fact_confirmation": ["session", "fact"],
    }
    for name, parameter_names in expected.items():
        sig = signature(getattr(application, name))
        assert list(sig.parameters) == parameter_names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
            assert parameter.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)


def test_application_set_account_binding_delegates_exact_arguments_once(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings

    calls = []
    session = object()

    def fake_set(supplied_session, role, account_code):
        calls.append((supplied_session, role, account_code))
        return None

    monkeypatch.setattr(aqorath.account_bindings, "set_account_binding", fake_set)
    result = application.set_account_binding(session, "cash", "1101")

    assert result is None
    assert calls == [(session, "cash", "1101")]


def test_application_get_account_binding_delegates_exact_arguments_and_result(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings

    calls = []
    session = object()

    def fake_get(supplied_session, role):
        calls.append((supplied_session, role))
        return "1101.001"

    monkeypatch.setattr(aqorath.account_bindings, "get_account_binding", fake_get)
    result = application.get_account_binding(session, "cash")

    assert result == "1101.001"
    assert calls == [(session, "cash")]


def test_configured_confirmation_loads_roles_from_exact_resolved_fact_order(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_facts
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation

    session = object()
    fact = object()
    proposal = SimpleNamespace(
        lines=[
            SimpleNamespace(account_role="cash"),
            SimpleNamespace(account_role="sales_revenue"),
        ],
        explanation="proposal sentinel",
    )
    resolved = object()
    snapshot = object()
    events = []

    def resolve_fact(supplied_fact):
        events.append(("fact", supplied_fact))
        return proposal

    def load_bindings(supplied_session, roles):
        events.append(("bindings", supplied_session, roles))
        return {"cash": "1101.001", "sales_revenue": "4101"}

    def resolve_accounts(supplied_session, supplied_proposal, bindings):
        events.append(("accounts", supplied_session, supplied_proposal, bindings))
        return resolved

    def make_snapshot(supplied_resolved):
        events.append(("snapshot", supplied_resolved))
        return snapshot

    monkeypatch.setattr(aqorath.economic_facts, "resolve_economic_fact", resolve_fact)
    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", load_bindings)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", resolve_accounts)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", make_snapshot)

    result = application.prepare_configured_economic_fact_confirmation(session, fact)

    assert result is snapshot
    assert events[0] == ("fact", fact)
    assert events[1] == ("bindings", session, ("cash", "sales_revenue"))
    assert events[2] == (
        "accounts",
        session,
        proposal,
        {"cash": "1101.001", "sales_revenue": "4101"},
    )
    assert events[3] == ("snapshot", resolved)
    assert len(events) == 4


def test_configured_confirmation_real_cash_sale_uses_persisted_bindings(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session
    import aqorath.catalog
    import aqorath.application as application
    from aqorath.economic_facts import EconomicFact
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        cash = Account(code="1101", name="Bancos", nature="DEBIT")
        sales = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(cash)
        session.add(sales)
        session.commit()
        session.refresh(cash)
        session.refresh(sales)
        session.add(AccountRoleBinding(role="cash", account_id=cash.id))
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales.id))
        session.commit()

        account_map = {"1101": cash, "4101": sales}
        monkeypatch.setattr(
            aqorath.catalog,
            "resolve_account_by_code",
            lambda supplied_session, code: account_map.get(code),
        )

        snapshot = application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "cash"),
        )

        assert isinstance(snapshot.lines, tuple)
        assert len(snapshot.lines) == 2
        assert snapshot.lines[0].account_role == "cash"
        assert snapshot.lines[0].account_id == cash.id
        assert snapshot.lines[0].account_code == "1101"
        assert snapshot.lines[0].side == "debit"
        assert snapshot.lines[0].amount == Decimal("200.00")
        assert snapshot.lines[1].account_role == "sales_revenue"
        assert snapshot.lines[1].account_id == sales.id
        assert snapshot.lines[1].account_code == "4101"
        assert snapshot.lines[1].side == "credit"
        assert snapshot.lines[1].amount == Decimal("200.00")


def test_configured_confirmation_missing_binding_fails_before_account_resolution(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings
    import aqorath.account_resolution
    from aqorath.economic_facts import EconomicFact

    session = object()

    def missing(*args, **kwargs):
        raise KeyError("missing binding sentinel")

    def forbidden_resolution(*args, **kwargs):
        raise AssertionError("account resolution must not run after binding load failure")

    monkeypatch.setattr(aqorath.account_bindings, "get_account_bindings", missing)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden_resolution)

    with pytest.raises(KeyError, match="missing binding sentinel"):
        application.prepare_configured_economic_fact_confirmation(
            session,
            EconomicFact("sale", Decimal("200.00"), "cash"),
        )


def test_configured_confirmation_does_not_confirm_or_post(monkeypatch):
    import aqorath.application as application
    import aqorath.account_bindings
    import aqorath.account_resolution
    import aqorath.confirmation
    import aqorath.posting
    import aqorath.posting_execution
    import aqorath.core
    from aqorath.economic_facts import EconomicFact

    session = object()
    resolved = object()
    snapshot = object()

    monkeypatch.setattr(
        aqorath.account_bindings,
        "get_account_bindings",
        lambda supplied_session, roles: {"cash": "C", "sales_revenue": "S"},
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda supplied_session, proposal, bindings: resolved,
    )
    monkeypatch.setattr(
        aqorath.confirmation,
        "create_confirmation_snapshot",
        lambda supplied_resolved: snapshot,
    )

    def bomb(*args, **kwargs):
        raise AssertionError("preparation must not confirm or post")

    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", bomb)
    monkeypatch.setattr(aqorath.posting, "create_posting_instruction", bomb)
    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", bomb)
    monkeypatch.setattr(aqorath.core, "post_entry", bomb)

    result = application.prepare_configured_economic_fact_confirmation(
        session,
        EconomicFact("sale", Decimal("200.00"), "cash"),
    )
    assert result is snapshot
