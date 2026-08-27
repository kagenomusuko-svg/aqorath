"""Phase 5G.1 — version-resolved fiscal rate runtime contracts.

This boundary composes 5A rule resolution with the pure 5F rate calculation.
It does not determine fiscal applicability, install rules, round currency,
choose accounts, build proposals, post, persist, or use legacy templates.
"""

from datetime import date
from decimal import Decimal
from inspect import signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _context(**overrides):
    from aqorath.fiscal_rules import FiscalContext

    values = {"jurisdiction": "MX", "regime": "general", "entity_type": "comercial"}
    values.update(overrides)
    return FiscalContext(**values)


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_fiscal_rate_runtime_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_runtime as runtime

    assert list(signature(runtime.calculate_fiscal_rate_for_date).parameters) == [
        "session", "rule_key", "effective_date", "context", "base"
    ]


def test_runtime_resolves_exact_rule_once_then_calculates_exact_base_once_in_order(monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as runtime

    context = _context()
    rule = object()
    result = object()
    calls = []

    def fake_resolve(session, rule_key, effective_date, received_context):
        calls.append(("resolve", session, rule_key, effective_date, received_context))
        assert session == "SESSION"
        assert rule_key == "iva.general_rate"
        assert effective_date == date(2026, 8, 27)
        assert received_context is context
        return rule

    def fake_calculate(base, received_rule):
        calls.append(("calculate", base, received_rule))
        assert base is BASE
        assert received_rule is rule
        return result

    BASE = Decimal("123.4500")
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", fake_resolve)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", fake_calculate)

    actual = runtime.calculate_fiscal_rate_for_date(
        "SESSION", "iva.general_rate", date(2026, 8, 27), context, BASE
    )
    assert actual is result
    assert calls == [
        ("resolve", "SESSION", "iva.general_rate", date(2026, 8, 27), context),
        ("calculate", BASE, rule),
    ]


def test_runtime_real_curated_iva_rule_resolves_and_calculates_exactly(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_runtime import calculate_fiscal_rate_for_date

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        result = calculate_fiscal_rate_for_date(
            session,
            "iva.general_rate",
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            Decimal("100.00"),
        )
        assert result.base == Decimal("100.00")
        assert result.amount == Decimal("16.0000")
        assert result.rule.value == Decimal("0.16")
        assert result.rule.effective_from == date(2010, 1, 1)
        assert result.rule.effective_to is None
        assert result.rule.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    finally:
        session.close()
        engine.dispose()


def test_runtime_preserves_unrounded_exact_decimal_result_from_primitive(tmp_path):
    from aqorath.fiscal_rule_registry import FiscalRuleRegistration, register_fiscal_rule_version
    from aqorath.fiscal_runtime import calculate_fiscal_rate_for_date

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(
            session,
            FiscalRuleRegistration(
                "test.rate",
                _context(),
                date(2020, 1, 1),
                Decimal("0.123456789"),
                "rate",
                "TEST:exact",
            ),
        )
        result = calculate_fiscal_rate_for_date(
            session,
            "test.rate",
            date(2026, 1, 1),
            _context(),
            Decimal("1.23456789"),
        )
        assert result.amount == Decimal("0.15241578750190521")
        assert result.amount != result.amount.quantize(Decimal("0.01"))
    finally:
        session.close()
        engine.dispose()


def test_runtime_missing_historical_or_context_rule_fails_before_calculation(tmp_path, monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import FiscalContext
    from aqorath.fiscal_runtime import calculate_fiscal_rate_for_date

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        calls = []
        real_calculate = calculation.calculate_fiscal_rate_amount

        def counted(*args, **kwargs):
            calls.append((args, kwargs))
            return real_calculate(*args, **kwargs)

        monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", counted)

        with pytest.raises(LookupError):
            calculate_fiscal_rate_for_date(
                session,
                "iva.general_rate",
                date(2009, 12, 31),
                data.MX_GENERAL_COMMERCIAL_IVA.context,
                Decimal("100.00"),
            )
        with pytest.raises(LookupError):
            calculate_fiscal_rate_for_date(
                session,
                "iva.general_rate",
                date(2026, 1, 1),
                FiscalContext("MX", "resico", "comercial"),
                Decimal("100.00"),
            )
        assert calls == []
    finally:
        session.close()
        engine.dispose()


def test_runtime_propagates_resolver_failure_without_retry_or_calculation(monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as runtime

    calls = []

    def fail_resolve(*args, **kwargs):
        calls.append("resolve")
        raise LookupError("missing")

    def forbidden(*args, **kwargs):
        raise AssertionError("calculation must not run after resolver failure")

    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", fail_resolve)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)

    with pytest.raises(LookupError, match="missing"):
        runtime.calculate_fiscal_rate_for_date(
            "SESSION", "missing", date(2026, 1, 1), _context(), Decimal("1")
        )
    assert calls == ["resolve"]


def test_runtime_propagates_calculation_failure_without_reresolving_or_retry(monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as runtime

    rule = object()
    calls = []

    def fake_resolve(*args, **kwargs):
        calls.append("resolve")
        return rule

    def fail_calculate(*args, **kwargs):
        calls.append("calculate")
        raise ValueError("bad calculation")

    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", fake_resolve)
    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", fail_calculate)

    with pytest.raises(ValueError, match="bad calculation"):
        runtime.calculate_fiscal_rate_for_date(
            "SESSION", "rule", date(2026, 1, 1), _context(), Decimal("1")
        )
    assert calls == ["resolve", "calculate"]


def test_runtime_uses_only_supplied_session_and_never_installs_posts_or_calls_legacy_tax_paths(tmp_path, monkeypatch):
    import aqorath.config as config
    import aqorath.fiscal_rule_data_mx as data
    import aqorath.fiscal_rule_install as installer
    import aqorath.posting as posting
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_runtime import calculate_fiscal_rate_for_date

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)

        def forbidden(*args, **kwargs):
            raise AssertionError("fiscal runtime must use only resolution + pure calculation")

        monkeypatch.setattr(storage, "get_session", forbidden)
        monkeypatch.setattr(installer, "install_fiscal_rule_set", forbidden)
        monkeypatch.setattr(tax, "calculate_taxes", forbidden)
        monkeypatch.setattr(templates, "get_template", forbidden)
        monkeypatch.setattr(config, "get_accounting_model", forbidden)
        monkeypatch.setattr(posting, "create_posting_instruction", forbidden)

        result = calculate_fiscal_rate_for_date(
            session,
            "iva.general_rate",
            date(2026, 1, 1),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            Decimal("250.00"),
        )
        assert result.amount == Decimal("40.0000")
    finally:
        session.close()
        engine.dispose()
