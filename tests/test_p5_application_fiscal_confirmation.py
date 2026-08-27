"""Phase 5M.1 — fiscal confirmation application-boundary contracts."""

from datetime import date
from decimal import Decimal
from inspect import Parameter, signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscal-confirmation.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _fact():
    from aqorath.economic_facts import EconomicFact

    return EconomicFact("sale", Decimal("250.00"), "cash")


def _context():
    from aqorath.fiscal_rules import FiscalContext

    return FiscalContext("MX", "general", "comercial")


def test_application_exposes_fiscal_confirmation_with_exact_signatures():
    import aqorath.application as application

    prepare_sig = signature(application.prepare_fiscal_confirmation)
    assert list(prepare_sig.parameters) == ["declared_calculation"]
    parameter = prepare_sig.parameters["declared_calculation"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty

    confirm_sig = signature(application.confirm_fiscal_treatment)
    assert list(confirm_sig.parameters) == ["snapshot"]
    parameter = confirm_sig.parameters["snapshot"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_application_prepare_fiscal_confirmation_delegates_exact_object_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_confirmation as confirmation

    declared = object()
    expected = object()
    calls = []

    def fake(declared_arg):
        calls.append(declared_arg)
        return expected

    monkeypatch.setattr(confirmation, "create_fiscal_confirmation_snapshot", fake)
    actual = application.prepare_fiscal_confirmation(declared)

    assert actual is expected
    assert calls == [declared]


def test_application_confirm_fiscal_treatment_delegates_exact_snapshot_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_confirmation as confirmation

    snapshot = object()
    expected = object()
    calls = []

    def fake(snapshot_arg):
        calls.append(snapshot_arg)
        return expected

    monkeypatch.setattr(confirmation, "confirm_fiscal_snapshot", fake)
    actual = application.confirm_fiscal_treatment(snapshot)

    assert actual is expected
    assert calls == [snapshot]


def test_application_uses_fiscal_confirmation_module_lookup_not_captured_aliases(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_confirmation as confirmation

    prepared = object()
    confirmed = object()
    monkeypatch.setattr(
        confirmation,
        "create_fiscal_confirmation_snapshot",
        lambda declared: prepared,
    )
    monkeypatch.setattr(
        confirmation,
        "confirm_fiscal_snapshot",
        lambda snapshot: confirmed,
    )

    assert application.prepare_fiscal_confirmation(object()) is prepared
    assert application.confirm_fiscal_treatment(prepared) is confirmed


def test_application_keeps_prepare_and_confirm_as_separate_explicit_acts(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_confirmation as confirmation

    snapshot = object()
    prepare_calls = []
    confirm_calls = []

    def fake_prepare(declared):
        prepare_calls.append(declared)
        return snapshot

    def forbidden_confirm(candidate):
        confirm_calls.append(candidate)
        raise AssertionError("prepare endpoint must not confirm")

    monkeypatch.setattr(confirmation, "create_fiscal_confirmation_snapshot", fake_prepare)
    monkeypatch.setattr(confirmation, "confirm_fiscal_snapshot", forbidden_confirm)

    declared = object()
    assert application.prepare_fiscal_confirmation(declared) is snapshot
    assert prepare_calls == [declared]
    assert confirm_calls == []

    def forbidden_prepare(candidate):
        raise AssertionError("confirm endpoint must not recreate snapshot")

    monkeypatch.setattr(confirmation, "create_fiscal_confirmation_snapshot", forbidden_prepare)
    monkeypatch.setattr(
        confirmation,
        "confirm_fiscal_snapshot",
        lambda candidate: ("confirmed", candidate),
    )
    assert application.confirm_fiscal_treatment(snapshot) == ("confirmed", snapshot)


def test_application_fiscal_confirmation_failures_propagate_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_confirmation as confirmation

    prepare_calls = []
    confirm_calls = []

    def fail_prepare(arg):
        prepare_calls.append(arg)
        raise TypeError("bad declared calculation")

    monkeypatch.setattr(confirmation, "create_fiscal_confirmation_snapshot", fail_prepare)
    with pytest.raises(TypeError, match="bad declared calculation"):
        application.prepare_fiscal_confirmation(object())
    assert len(prepare_calls) == 1

    def fail_confirm(arg):
        confirm_calls.append(arg)
        raise TypeError("bad fiscal snapshot")

    monkeypatch.setattr(confirmation, "confirm_fiscal_snapshot", fail_confirm)
    with pytest.raises(TypeError, match="bad fiscal snapshot"):
        application.confirm_fiscal_treatment(object())
    assert len(confirm_calls) == 1


def test_application_does_not_own_fiscal_snapshot_copying_recalculation_resolution_or_persistence(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_confirmation as confirmation
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.storage as storage

    prepared = object()
    confirmed = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not own fiscal authority")

    monkeypatch.setattr(applicability, "declare_fiscal_rate_applicability", forbidden)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(declared_runtime, "calculate_declared_fiscal_rate", forbidden)
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(
        confirmation,
        "create_fiscal_confirmation_snapshot",
        lambda declared: prepared,
    )
    monkeypatch.setattr(
        confirmation,
        "confirm_fiscal_snapshot",
        lambda snapshot: confirmed,
    )

    assert application.prepare_fiscal_confirmation(object()) is prepared
    assert application.confirm_fiscal_treatment(prepared) is confirmed


def test_application_real_explicit_fiscal_flow_reaches_informed_confirmation_without_accounting_effect(tmp_path):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = _fact()
        base = Decimal("250.00")

        declaration = application.declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            base,
        )
        declared = application.calculate_declared_fiscal_rate(session, declaration)
        snapshot = application.prepare_fiscal_confirmation(declared)
        confirmed = application.confirm_fiscal_treatment(snapshot)

        assert confirmed.snapshot is snapshot
        assert snapshot.fact_type == "sale"
        assert snapshot.fact_amount == Decimal("250.00")
        assert snapshot.rule_key == "iva.general_rate"
        assert snapshot.base == Decimal("250.00")
        assert snapshot.rate == Decimal("0.16")
        assert snapshot.calculated_amount == Decimal("40.0000")
        assert snapshot.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_fiscal_confirmation_boundary():
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
    ]
    for name in expected:
        assert callable(getattr(application, name))
