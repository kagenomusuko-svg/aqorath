"""Phase 2C.7 — application orchestration contracts for confirmation and posting."""

from decimal import Decimal
import pytest


def test_application_exposes_confirmation_posting_api():
    import aqorath.application as application

    for name in (
        "prepare_economic_fact_confirmation",
        "confirm_economic_fact",
        "post_confirmed_economic_fact",
    ):
        assert hasattr(application, name)
        assert callable(getattr(application, name))


def test_application_confirmation_posting_exact_signatures():
    from inspect import Parameter, signature
    import aqorath.application as application

    expected = {
        application.prepare_economic_fact_confirmation: ["session", "fact", "account_bindings"],
        application.confirm_economic_fact: ["snapshot"],
        application.post_confirmed_economic_fact: ["confirmed_proposal"],
    }
    for fn, names in expected.items():
        sig = signature(fn)
        assert list(sig.parameters) == names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD


def test_prepare_economic_fact_confirmation_delegates_exact_pipeline_in_order(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.confirmation

    session = object()
    fact = object()
    bindings = {"cash": "CASH-X", "sales_revenue": "SALES-X"}
    semantic = object()
    resolved = object()
    snapshot = object()
    calls = []

    monkeypatch.setattr(
        aqorath.economic_facts,
        "resolve_economic_fact",
        lambda received: calls.append(("resolve_fact", received)) or semantic,
    )
    monkeypatch.setattr(
        aqorath.account_resolution,
        "resolve_proposal_accounts",
        lambda received_session, proposal, received_bindings: calls.append(
            ("resolve_accounts", received_session, proposal, received_bindings)
        ) or resolved,
    )
    monkeypatch.setattr(
        aqorath.confirmation,
        "create_confirmation_snapshot",
        lambda proposal: calls.append(("snapshot", proposal)) or snapshot,
    )

    result = application.prepare_economic_fact_confirmation(session, fact, bindings)

    assert result is snapshot
    assert calls[0] == ("resolve_fact", fact)
    assert calls[1][0] == "resolve_accounts"
    assert calls[1][1] is session
    assert calls[1][2] is semantic
    assert calls[1][3] is bindings
    assert calls[2] == ("snapshot", resolved)


def test_prepare_economic_fact_confirmation_preserves_input_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.confirmation

    session = object()
    fact = object()
    bindings = {"role": "CODE"}
    semantic = object()
    resolved = object()
    snapshot = object()
    observed = {}

    def resolve_fact(received):
        observed["fact"] = received
        return semantic

    def resolve_accounts(received_session, proposal, received_bindings):
        observed["session"] = received_session
        observed["proposal"] = proposal
        observed["bindings"] = received_bindings
        return resolved

    monkeypatch.setattr(aqorath.economic_facts, "resolve_economic_fact", resolve_fact)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", resolve_accounts)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", lambda proposal: snapshot)

    assert application.prepare_economic_fact_confirmation(session, fact, bindings) is snapshot
    assert observed["fact"] is fact
    assert observed["session"] is session
    assert observed["proposal"] is semantic
    assert observed["bindings"] is bindings


def test_prepare_economic_fact_confirmation_does_not_confirm_or_post(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.confirmation
    import aqorath.posting
    import aqorath.posting_execution
    import aqorath.core
    import aqorath.storage

    semantic = object()
    resolved = object()
    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("prepare must not confirm or post")

    monkeypatch.setattr(aqorath.economic_facts, "resolve_economic_fact", lambda fact: semantic)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", lambda s, p, b: resolved)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", lambda proposal: snapshot)
    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", forbidden)
    monkeypatch.setattr(aqorath.posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", forbidden)
    monkeypatch.setattr(aqorath.core, "post_entry", forbidden)
    monkeypatch.setattr(aqorath.storage, "get_session", forbidden)

    result = application.prepare_economic_fact_confirmation(object(), object(), {})
    assert result is snapshot


def test_confirm_economic_fact_delegates_exact_snapshot_once(monkeypatch):
    import aqorath.application as application
    import aqorath.confirmation

    snapshot = object()
    confirmed = object()
    calls = []

    monkeypatch.setattr(
        aqorath.confirmation,
        "confirm_snapshot",
        lambda received: calls.append(received) or confirmed,
    )

    result = application.confirm_economic_fact(snapshot)
    assert result is confirmed
    assert calls == [snapshot]


def test_post_confirmed_economic_fact_builds_and_executes_exact_instruction_once(monkeypatch):
    import aqorath.application as application
    import aqorath.posting
    import aqorath.posting_execution

    confirmed = object()
    instruction = object()
    result_sentinel = object()
    calls = []

    monkeypatch.setattr(
        aqorath.posting,
        "create_posting_instruction",
        lambda received: calls.append(("build", received)) or instruction,
    )
    monkeypatch.setattr(
        aqorath.posting_execution,
        "execute_posting_instruction",
        lambda received: calls.append(("execute", received)) or result_sentinel,
    )

    result = application.post_confirmed_economic_fact(confirmed)
    assert result is result_sentinel
    assert calls == [("build", confirmed), ("execute", instruction)]


def test_post_confirmed_economic_fact_does_not_reresolve_reconfirm_or_call_core_directly(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.confirmation
    import aqorath.posting
    import aqorath.posting_execution
    import aqorath.core

    confirmed = object()
    instruction = object()
    result_sentinel = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("post confirmed must not recompute, reconfirm, or bypass executor")

    monkeypatch.setattr(aqorath.economic_facts, "resolve_economic_fact", forbidden)
    monkeypatch.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(aqorath.confirmation, "create_confirmation_snapshot", forbidden)
    monkeypatch.setattr(aqorath.confirmation, "confirm_snapshot", forbidden)
    monkeypatch.setattr(aqorath.core, "post_entry", forbidden)
    monkeypatch.setattr(aqorath.posting, "create_posting_instruction", lambda received: instruction)
    monkeypatch.setattr(aqorath.posting_execution, "execute_posting_instruction", lambda received: result_sentinel)

    assert application.post_confirmed_economic_fact(confirmed) is result_sentinel


def test_application_real_cash_sale_prepares_confirmation_snapshot(monkeypatch):
    import types
    import aqorath.application as application
    import aqorath.catalog
    from aqorath.economic_facts import EconomicFact
    from aqorath.confirmation import ConfirmationSnapshot, ConfirmationLine

    accounts = {
        "CASH-001": types.SimpleNamespace(id=101, code="CASH-001", name="Caja principal", origin="entity"),
        "SALES-001": types.SimpleNamespace(id=902, code="SALES-001", name="Ingresos por ventas", origin="canonical"),
    }
    session = object()
    calls = []

    def resolver(received_session, code):
        calls.append((received_session, code))
        return accounts.get(code)

    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", resolver)

    snapshot = application.prepare_economic_fact_confirmation(
        session,
        EconomicFact(type="sale", amount=Decimal("200.00"), payment_method="cash"),
        {"cash": "CASH-001", "sales_revenue": "SALES-001"},
    )

    assert isinstance(snapshot, ConfirmationSnapshot)
    assert isinstance(snapshot.lines, tuple)
    assert len(snapshot.lines) == 2
    assert all(isinstance(line, ConfirmationLine) for line in snapshot.lines)
    assert snapshot.lines[0].account_code == "CASH-001"
    assert snapshot.lines[0].amount == Decimal("200.00")
    assert snapshot.lines[1].account_code == "SALES-001"
    assert snapshot.lines[1].amount == Decimal("200.00")
    assert calls == [(session, "CASH-001"), (session, "SALES-001")]


def test_existing_application_api_remains_available():
    import aqorath.application as application

    for name in (
        "list_templates",
        "preview_template",
        "post_template",
        "get_trial_balance",
        "preview_economic_fact",
    ):
        assert hasattr(application, name)
        assert callable(getattr(application, name))
