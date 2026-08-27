"""Phase 5Q.1 — fiscal monetary confirmation application-boundary contracts."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


def _assert_exact_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscal-money-confirm.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_fiscal_monetary_confirmation_with_exact_signatures():
    import aqorath.application as application

    _assert_exact_signature(
        application.prepare_fiscal_monetary_confirmation,
        ["rounded_amount"],
    )
    _assert_exact_signature(
        application.confirm_fiscal_monetary_amount,
        ["snapshot"],
    )


def test_application_prepare_monetary_confirmation_delegates_exact_object_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_monetary_confirmation as monetary

    rounded = object()
    expected = object()
    calls = []

    def fake(value):
        calls.append(value)
        return expected

    monkeypatch.setattr(monetary, "create_fiscal_monetary_confirmation_snapshot", fake)
    actual = application.prepare_fiscal_monetary_confirmation(rounded)

    assert actual is expected
    assert calls == [rounded]


def test_application_confirm_monetary_amount_delegates_exact_snapshot_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_monetary_confirmation as monetary

    snapshot = object()
    expected = object()
    calls = []

    def fake(value):
        calls.append(value)
        return expected

    monkeypatch.setattr(monetary, "confirm_fiscal_monetary_snapshot", fake)
    actual = application.confirm_fiscal_monetary_amount(snapshot)

    assert actual is expected
    assert calls == [snapshot]


def test_application_uses_fiscal_monetary_confirmation_module_lookup_not_captured_aliases(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_monetary_confirmation as monetary

    prepared = object()
    confirmed = object()
    monkeypatch.setattr(
        monetary,
        "create_fiscal_monetary_confirmation_snapshot",
        lambda rounded: prepared,
    )
    monkeypatch.setattr(
        monetary,
        "confirm_fiscal_monetary_snapshot",
        lambda snapshot: confirmed,
    )

    assert application.prepare_fiscal_monetary_confirmation(object()) is prepared
    assert application.confirm_fiscal_monetary_amount(object()) is confirmed


def test_application_keeps_round_prepare_and_confirm_as_three_separate_explicit_acts(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_monetary_confirmation as monetary
    import aqorath.fiscal_rounding as rounding

    rounded = object()
    snapshot = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not collapse fiscal monetary acts")

    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)
    monkeypatch.setattr(monetary, "confirm_fiscal_monetary_snapshot", forbidden)
    monkeypatch.setattr(
        monetary,
        "create_fiscal_monetary_confirmation_snapshot",
        lambda value: snapshot,
    )
    assert application.prepare_fiscal_monetary_confirmation(rounded) is snapshot

    monkeypatch.setattr(monetary, "create_fiscal_monetary_confirmation_snapshot", forbidden)
    monkeypatch.setattr(
        monetary,
        "confirm_fiscal_monetary_snapshot",
        lambda value: rounded,
    )
    assert application.confirm_fiscal_monetary_amount(snapshot) is rounded


def test_application_fiscal_monetary_confirmation_failures_propagate_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_monetary_confirmation as monetary

    create_calls = []
    confirm_calls = []

    def fail_create(value):
        create_calls.append(value)
        raise ValueError("prepare money failed")

    def fail_confirm(value):
        confirm_calls.append(value)
        raise ValueError("confirm money failed")

    monkeypatch.setattr(monetary, "create_fiscal_monetary_confirmation_snapshot", fail_create)
    with pytest.raises(ValueError, match="prepare money failed"):
        application.prepare_fiscal_monetary_confirmation(object())
    assert len(create_calls) == 1

    monkeypatch.setattr(monetary, "confirm_fiscal_monetary_snapshot", fail_confirm)
    with pytest.raises(ValueError, match="confirm money failed"):
        application.confirm_fiscal_monetary_amount(object())
    assert len(confirm_calls) == 1


def test_application_does_not_reround_resolve_recalculate_post_or_open_session(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_declaration_runtime as declaration_runtime
    import aqorath.fiscal_monetary_confirmation as monetary
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not own fiscal/accounting authority")

    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", forbidden)
    monkeypatch.setattr(declaration_runtime, "calculate_declared_fiscal_rate", forbidden)
    monkeypatch.setattr(posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)

    prepared = object()
    confirmed = object()
    monkeypatch.setattr(
        monetary,
        "create_fiscal_monetary_confirmation_snapshot",
        lambda value: prepared,
    )
    monkeypatch.setattr(
        monetary,
        "confirm_fiscal_monetary_snapshot",
        lambda value: confirmed,
    )

    assert application.prepare_fiscal_monetary_confirmation(object()) is prepared
    assert application.confirm_fiscal_monetary_amount(object()) is confirmed


def test_application_real_explicit_flow_reaches_confirmed_rounded_amount_without_accounting_effect(tmp_path):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_rounding import FiscalRoundingPolicy
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.models import JournalEntry

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = EconomicFact("sale", Decimal("250.00"), "cash")
        declaration = application.declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            Decimal("250.00"),
        )
        declared = application.calculate_declared_fiscal_rate(session, declaration)
        fiscal_snapshot = application.prepare_fiscal_confirmation(declared)
        fiscal_confirmed = application.confirm_fiscal_treatment(fiscal_snapshot)
        policy = FiscalRoundingPolicy(
            "explicit-two-decimals",
            Decimal("0.01"),
            ROUND_HALF_UP,
            "EXPLICIT:APPLICATION:TEST",
        )
        rounded = application.round_confirmed_fiscal_amount(fiscal_confirmed, policy)

        before = session.exec(select(JournalEntry)).all()
        monetary_snapshot = application.prepare_fiscal_monetary_confirmation(rounded)
        monetary_confirmed = application.confirm_fiscal_monetary_amount(monetary_snapshot)
        after = session.exec(select(JournalEntry)).all()

        assert monetary_confirmed.snapshot is monetary_snapshot
        assert monetary_snapshot.exact_amount == Decimal("40.0000")
        assert monetary_snapshot.rounded_amount == Decimal("40.00")
        assert monetary_snapshot.rule_source_ref
        assert monetary_snapshot.rounding_source_ref == "EXPLICIT:APPLICATION:TEST"
        assert before == after == []
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_fiscal_monetary_confirmation_boundary():
    import aqorath.application as application

    expected = [
        "preview_economic_fact",
        "prepare_configured_economic_fact_confirmation",
        "confirm_economic_fact",
        "post_confirmed_economic_fact",
        "get_financial_statements_bundle",
        "get_financial_statements_xlsx",
        "get_financial_statements_pdf",
        "declare_fiscal_rate_applicability",
        "calculate_declared_fiscal_rate",
        "prepare_fiscal_confirmation",
        "confirm_fiscal_treatment",
        "round_confirmed_fiscal_amount",
        "prepare_fiscal_monetary_confirmation",
        "confirm_fiscal_monetary_amount",
    ]
    for name in expected:
        assert callable(getattr(application, name))
