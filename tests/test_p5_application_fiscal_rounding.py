"""Phase 5O.1 — fiscal rounding application-boundary contracts."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscal-rounding.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_fiscal_rounding_with_exact_signature():
    import aqorath.application as application

    sig = signature(application.round_confirmed_fiscal_amount)
    assert list(sig.parameters) == ["confirmed_treatment", "policy"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_application_rounding_delegates_exact_objects_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_rounding as rounding

    confirmed = object()
    policy = object()
    expected = object()
    calls = []

    def fake(confirmed_arg, policy_arg):
        calls.append((confirmed_arg, policy_arg))
        return expected

    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", fake)
    actual = application.round_confirmed_fiscal_amount(confirmed, policy)

    assert actual is expected
    assert calls == [(confirmed, policy)]


def test_application_uses_fiscal_rounding_module_lookup_not_captured_function_alias(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_rounding as rounding

    expected = object()
    monkeypatch.setattr(
        rounding,
        "round_confirmed_fiscal_amount",
        lambda confirmed, policy: expected,
    )

    assert application.round_confirmed_fiscal_amount(object(), object()) is expected


def test_application_never_constructs_or_defaults_rounding_policy(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_rounding as rounding

    confirmed = object()
    supplied_policy = object()
    calls = []

    def forbidden_policy_constructor(*args, **kwargs):
        raise AssertionError("application must not construct a fiscal rounding policy")

    def fake_round(confirmed_arg, policy_arg):
        calls.append((confirmed_arg, policy_arg))
        return (confirmed_arg, policy_arg)

    monkeypatch.setattr(rounding, "FiscalRoundingPolicy", forbidden_policy_constructor)
    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", fake_round)

    result = application.round_confirmed_fiscal_amount(confirmed, supplied_policy)
    assert result == (confirmed, supplied_policy)
    assert calls == [(confirmed, supplied_policy)]


def test_application_rounding_failure_propagates_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_rounding as rounding

    calls = []

    def fail(confirmed, policy):
        calls.append((confirmed, policy))
        raise ValueError("explicit rounding failed")

    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", fail)

    confirmed = object()
    policy = object()
    with pytest.raises(ValueError, match="explicit rounding failed"):
        application.round_confirmed_fiscal_amount(confirmed, policy)
    assert calls == [(confirmed, policy)]


def test_application_rounding_does_not_reconfirm_resolve_recalculate_install_post_or_open_session(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_confirmation as confirmation
    import aqorath.fiscal_declaration_runtime as declaration_runtime
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage

    confirmed = object()
    policy = object()
    expected = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not own downstream fiscal/accounting authority")

    monkeypatch.setattr(confirmation, "confirm_fiscal_snapshot", forbidden)
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", forbidden)
    monkeypatch.setattr(declaration_runtime, "calculate_declared_fiscal_rate", forbidden)
    monkeypatch.setattr(installer, "install_fiscal_rule_set", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(
        rounding,
        "round_confirmed_fiscal_amount",
        lambda confirmed_arg, policy_arg: expected,
    )

    assert application.round_confirmed_fiscal_amount(confirmed, policy) is expected


def test_application_real_explicit_fiscal_flow_rounds_confirmed_amount_without_accounting_effect(tmp_path):
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
        snapshot = application.prepare_fiscal_confirmation(declared)
        confirmed = application.confirm_fiscal_treatment(snapshot)
        policy = FiscalRoundingPolicy(
            policy_key="explicit-two-decimals",
            quantizer=Decimal("0.01"),
            rounding_mode=ROUND_HALF_UP,
            source_ref="EXPLICIT:APPLICATION:TEST",
        )

        before = session.exec(select(JournalEntry)).all()
        result = application.round_confirmed_fiscal_amount(confirmed, policy)
        after = session.exec(select(JournalEntry)).all()

        assert result.confirmed_treatment is confirmed
        assert result.policy is policy
        assert result.exact_amount == Decimal("40.0000")
        assert result.rounded_amount == Decimal("40.00")
        assert before == after == []
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_fiscal_rounding_boundary():
    import aqorath.application as application

    expected = [
        "list_templates",
        "preview_template",
        "post_template",
        "get_trial_balance",
        "preview_economic_fact",
        "set_account_binding",
        "get_account_binding",
        "prepare_economic_fact_confirmation",
        "prepare_configured_economic_fact_confirmation",
        "confirm_economic_fact",
        "post_confirmed_economic_fact",
        "get_financial_report_snapshot",
        "get_income_statement_view",
        "get_balance_sheet_view",
        "get_financial_statements_bundle",
        "get_financial_report_csv",
        "get_financial_report_xlsx",
        "get_financial_statements_xlsx",
        "get_financial_statements_pdf",
        "calculate_fiscal_rate_for_date",
        "declare_fiscal_rate_applicability",
        "calculate_declared_fiscal_rate",
        "prepare_fiscal_confirmation",
        "confirm_fiscal_treatment",
        "round_confirmed_fiscal_amount",
    ]
    for name in expected:
        assert callable(getattr(application, name))
