"""Phase 5K.1 — fiscal declaration application-boundary contracts."""

from datetime import date
from decimal import Decimal
from inspect import Parameter, signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _context():
    from aqorath.fiscal_rules import FiscalContext

    return FiscalContext("MX", "general", "comercial")


def _fact():
    from aqorath.economic_facts import EconomicFact

    return EconomicFact("sale", Decimal("250.00"), "cash")


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-declared-fiscal.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_fiscal_declaration_and_declared_calculation_exact_signatures():
    import aqorath.application as application

    declare_sig = signature(application.declare_fiscal_rate_applicability)
    assert list(declare_sig.parameters) == [
        "fact", "effective_date", "context", "rule_key", "base"
    ]
    for parameter in declare_sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty

    calculate_sig = signature(application.calculate_declared_fiscal_rate)
    assert list(calculate_sig.parameters) == ["session", "declaration"]
    for parameter in calculate_sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_application_declaration_delegates_exact_arguments_once_and_returns_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability

    fact = _fact()
    context = _context()
    effective_date = date(2026, 8, 27)
    base = Decimal("123.4567")
    expected = object()
    calls = []

    def fake(fact_arg, date_arg, context_arg, rule_key_arg, base_arg):
        calls.append((fact_arg, date_arg, context_arg, rule_key_arg, base_arg))
        return expected

    monkeypatch.setattr(applicability, "declare_fiscal_rate_applicability", fake)
    actual = application.declare_fiscal_rate_applicability(
        fact, effective_date, context, "explicit.rule", base
    )

    assert actual is expected
    assert calls == [(fact, effective_date, context, "explicit.rule", base)]


def test_application_declared_calculation_delegates_exact_session_and_declaration_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_declaration_runtime as declared_runtime

    declaration = object()
    expected = object()
    calls = []

    def fake(session, declaration_arg):
        calls.append((session, declaration_arg))
        return expected

    monkeypatch.setattr(declared_runtime, "calculate_declared_fiscal_rate", fake)
    actual = application.calculate_declared_fiscal_rate("SESSION", declaration)

    assert actual is expected
    assert calls == [("SESSION", declaration)]


def test_application_uses_module_lookup_not_captured_aliases_for_both_new_boundaries(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_declaration_runtime as declared_runtime

    declaration_result = object()
    calculation_result = object()

    monkeypatch.setattr(
        applicability,
        "declare_fiscal_rate_applicability",
        lambda *args: declaration_result,
    )
    monkeypatch.setattr(
        declared_runtime,
        "calculate_declared_fiscal_rate",
        lambda *args: calculation_result,
    )

    assert application.declare_fiscal_rate_applicability(
        _fact(), date(2026, 8, 27), _context(), "rule", Decimal("1")
    ) is declaration_result
    assert application.calculate_declared_fiscal_rate(
        "SESSION", declaration_result
    ) is calculation_result


def test_application_keeps_declaration_and_calculation_separate_without_implicit_composition(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_declaration_runtime as declared_runtime

    declaration = object()
    declare_calls = []
    calculate_calls = []

    def fake_declare(*args):
        declare_calls.append(args)
        return declaration

    def forbidden_calculate(*args):
        calculate_calls.append(args)
        raise AssertionError("declaration endpoint must not calculate")

    monkeypatch.setattr(applicability, "declare_fiscal_rate_applicability", fake_declare)
    monkeypatch.setattr(declared_runtime, "calculate_declared_fiscal_rate", forbidden_calculate)

    actual = application.declare_fiscal_rate_applicability(
        _fact(), date(2026, 8, 27), _context(), "explicit.rule", Decimal("250.00")
    )
    assert actual is declaration
    assert len(declare_calls) == 1
    assert calculate_calls == []

    def forbidden_declare(*args):
        raise AssertionError("calculation endpoint must not redeclare")

    monkeypatch.setattr(applicability, "declare_fiscal_rate_applicability", forbidden_declare)
    monkeypatch.setattr(
        declared_runtime,
        "calculate_declared_fiscal_rate",
        lambda session, declaration_arg: (session, declaration_arg),
    )
    assert application.calculate_declared_fiscal_rate(
        "SESSION", declaration
    ) == ("SESSION", declaration)


def test_application_new_fiscal_boundaries_propagate_failures_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_declaration_runtime as declared_runtime

    declare_calls = []
    calculate_calls = []

    def fail_declare(*args):
        declare_calls.append(args)
        raise ValueError("invalid declaration")

    monkeypatch.setattr(applicability, "declare_fiscal_rate_applicability", fail_declare)
    with pytest.raises(ValueError, match="invalid declaration"):
        application.declare_fiscal_rate_applicability(
            _fact(), date(2026, 8, 27), _context(), "rule", Decimal("1")
        )
    assert len(declare_calls) == 1

    def fail_calculate(*args):
        calculate_calls.append(args)
        raise LookupError("missing declared rule")

    monkeypatch.setattr(declared_runtime, "calculate_declared_fiscal_rate", fail_calculate)
    with pytest.raises(LookupError, match="missing declared rule"):
        application.calculate_declared_fiscal_rate("SESSION", object())
    assert len(calculate_calls) == 1


def test_application_does_not_own_fiscal_inference_resolution_calculation_or_persistence(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.storage as storage

    declaration = object()
    result = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate fiscal authority")

    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(
        applicability,
        "declare_fiscal_rate_applicability",
        lambda *args: declaration,
    )
    monkeypatch.setattr(
        declared_runtime,
        "calculate_declared_fiscal_rate",
        lambda session, declaration_arg: result,
    )

    assert application.declare_fiscal_rate_applicability(
        _fact(), date(2026, 8, 27), _context(), "rule", Decimal("1")
    ) is declaration
    assert application.calculate_declared_fiscal_rate(
        "SESSION", declaration
    ) is result


def test_application_real_explicit_declaration_then_declared_curated_iva_calculation(tmp_path):
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
        result = application.calculate_declared_fiscal_rate(session, declaration)

        assert result.declaration is declaration
        assert result.declaration.fact is fact
        assert result.calculation.base is base
        assert result.calculation.amount == Decimal("40.0000")
        assert result.calculation.rule.value == Decimal("0.16")
        assert result.calculation.rule.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_declared_fiscal_boundary():
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
    ]
    for name in expected:
        assert callable(getattr(application, name))
