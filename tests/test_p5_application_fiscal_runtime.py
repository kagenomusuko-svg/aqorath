"""Phase 5H.1 — fiscal calculation application-boundary contracts.

This phase exposes the explicit version-resolved fiscal-rate runtime to adapters.
It does not decide tax applicability, infer a rule from an economic fact, round
currency, choose accounts, build proposals, confirm, post, or install rule data.
"""

from datetime import date
from decimal import Decimal
from inspect import signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _context(**overrides):
    from aqorath.fiscal_rules import FiscalContext

    values = {
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "comercial",
    }
    values.update(overrides)
    return FiscalContext(**values)


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscal.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_fiscal_rate_calculation_with_exact_signature():
    import aqorath.application as application

    assert callable(application.calculate_fiscal_rate_for_date)
    assert list(signature(application.calculate_fiscal_rate_for_date).parameters) == [
        "session",
        "rule_key",
        "effective_date",
        "context",
        "base",
    ]


def test_application_delegates_exact_fiscal_arguments_once_and_returns_runtime_identity(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_runtime as runtime

    context = _context()
    base = Decimal("123.4500")
    expected = object()
    calls = []

    def fake_runtime(session, rule_key, effective_date, received_context, received_base):
        calls.append(
            (session, rule_key, effective_date, received_context, received_base)
        )
        assert session == "SESSION"
        assert rule_key == "iva.general_rate"
        assert effective_date == date(2026, 8, 27)
        assert received_context is context
        assert received_base is base
        return expected

    monkeypatch.setattr(runtime, "calculate_fiscal_rate_for_date", fake_runtime)

    result = application.calculate_fiscal_rate_for_date(
        "SESSION",
        "iva.general_rate",
        date(2026, 8, 27),
        context,
        base,
    )
    assert result is expected
    assert calls == [
        ("SESSION", "iva.general_rate", date(2026, 8, 27), context, base)
    ]


def test_application_uses_runtime_module_lookup_not_captured_function_alias(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_runtime as runtime

    sentinel = object()
    calls = []

    def replacement(*args):
        calls.append(args)
        return sentinel

    # Application is imported before this monkeypatch. A direct captured function
    # alias would bypass the replacement and violate the boundary.
    monkeypatch.setattr(runtime, "calculate_fiscal_rate_for_date", replacement)

    context = _context()
    base = Decimal("1.00")
    result = application.calculate_fiscal_rate_for_date(
        "S", "rule", date(2026, 1, 1), context, base
    )
    assert result is sentinel
    assert calls == [("S", "rule", date(2026, 1, 1), context, base)]


def test_application_propagates_fiscal_runtime_failure_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_runtime as runtime

    calls = []

    def fail_runtime(*args, **kwargs):
        calls.append((args, kwargs))
        raise LookupError("missing fiscal rule")

    monkeypatch.setattr(runtime, "calculate_fiscal_rate_for_date", fail_runtime)

    with pytest.raises(LookupError, match="missing fiscal rule"):
        application.calculate_fiscal_rate_for_date(
            "S", "missing", date(2026, 1, 1), _context(), Decimal("10.00")
        )
    assert len(calls) == 1


def test_application_fiscal_boundary_does_not_resolve_calculate_install_or_discover_session_itself(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as runtime
    import aqorath.storage as storage

    expected = object()
    calls = []

    def fake_runtime(*args):
        calls.append(args)
        return expected

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate fiscal calculation only to fiscal_runtime")

    monkeypatch.setattr(runtime, "calculate_fiscal_rate_for_date", fake_runtime)
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(installer, "install_fiscal_rule_set", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)

    context = _context()
    base = Decimal("100.00")
    result = application.calculate_fiscal_rate_for_date(
        "SUPPLIED", "iva.general_rate", date(2026, 1, 1), context, base
    )
    assert result is expected
    assert calls == [
        ("SUPPLIED", "iva.general_rate", date(2026, 1, 1), context, base)
    ]


def test_application_real_curated_iva_calculation_uses_supplied_session_end_to_end(tmp_path):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        result = application.calculate_fiscal_rate_for_date(
            session,
            "iva.general_rate",
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            Decimal("250.00"),
        )
        assert result.base == Decimal("250.00")
        assert result.amount == Decimal("40.0000")
        assert result.rule.value == Decimal("0.16")
        assert result.rule.effective_from == date(2010, 1, 1)
        assert result.rule.source_ref == (
            "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
        )
    finally:
        session.close()
        engine.dispose()


def test_application_real_fiscal_boundary_remains_fail_closed_for_missing_date_and_context(tmp_path):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import FiscalContext

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)

        with pytest.raises(LookupError):
            application.calculate_fiscal_rate_for_date(
                session,
                "iva.general_rate",
                date(2009, 12, 31),
                data.MX_GENERAL_COMMERCIAL_IVA.context,
                Decimal("100.00"),
            )
        with pytest.raises(LookupError):
            application.calculate_fiscal_rate_for_date(
                session,
                "iva.general_rate",
                date(2026, 1, 1),
                FiscalContext("MX", "resico", "comercial"),
                Decimal("100.00"),
            )
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_fiscal_boundary():
    import aqorath.application as application

    existing = (
        "list_templates",
        "preview_template",
        "post_template",
        "get_trial_balance",
        "preview_economic_fact",
        "prepare_economic_fact_confirmation",
        "prepare_configured_economic_fact_confirmation",
        "set_account_binding",
        "get_account_binding",
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
    )
    assert all(callable(getattr(application, name)) for name in existing)
