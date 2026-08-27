"""Phase 5J.1 — declared fiscal calculation runtime contracts.

This boundary consumes an explicit 5I applicability declaration and delegates
its exact fiscal coordinates to the existing version-resolved 5G runtime. It
preserves both the declaration and returned calculation by identity. It does not
infer applicability, inspect the economic fact, resolve/calculate independently,
round, install, persist, choose accounts, build accounting proposals, or post.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _context():
    from aqorath.fiscal_rules import FiscalContext

    return FiscalContext("MX", "general", "comercial")


def _fact(amount="200.00"):
    from aqorath.economic_facts import EconomicFact

    return EconomicFact("sale", Decimal(amount), "cash")


def _declaration(*, rule_key="iva.general_rate", base="200.00", effective_date=None, context=None):
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability

    return declare_fiscal_rate_applicability(
        _fact(),
        effective_date or date(2026, 8, 27),
        context or _context(),
        rule_key,
        Decimal(base),
    )


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'declared-runtime.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_declared_fiscal_runtime_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_declaration_runtime as runtime

    assert runtime.__all__ == [
        "DeclaredFiscalRateCalculation",
        "calculate_declared_fiscal_rate",
    ]
    assert hasattr(runtime, "DeclaredFiscalRateCalculation")
    assert callable(runtime.calculate_declared_fiscal_rate)

    sig = signature(runtime.calculate_declared_fiscal_rate)
    assert list(sig.parameters) == ["session", "declaration"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_declared_result_is_frozen_and_requires_nominal_components():
    from aqorath.fiscal_applicability import FiscalRateApplicabilityDeclaration
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    declaration = _declaration()
    rule = ResolvedFiscalRule(
        rule_key="iva.general_rate",
        value=Decimal("0.16"),
        unit="rate",
        effective_from=date(2010, 1, 1),
        effective_to=None,
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        source_ref="TEST",
    )
    calculation = FiscalRateCalculation(
        base=declaration.base,
        amount=Decimal("32.0000"),
        rule=rule,
    )

    result = DeclaredFiscalRateCalculation(declaration, calculation)
    assert result.declaration is declaration
    assert result.calculation is calculation
    with pytest.raises(FrozenInstanceError):
        result.declaration = declaration

    with pytest.raises(TypeError):
        DeclaredFiscalRateCalculation(SimpleNamespace(), calculation)
    with pytest.raises(TypeError):
        DeclaredFiscalRateCalculation(declaration, SimpleNamespace())

    assert isinstance(result.declaration, FiscalRateApplicabilityDeclaration)
    assert isinstance(result.calculation, FiscalRateCalculation)


def test_runtime_requires_nominal_declaration_before_any_fiscal_runtime_call(monkeypatch):
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_runtime as fiscal_runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("fiscal runtime must not run for a fake declaration")

    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", forbidden)
    fake = SimpleNamespace(
        rule_key="iva.general_rate",
        effective_date=date(2026, 8, 27),
        context=_context(),
        base=Decimal("200.00"),
    )

    with pytest.raises(TypeError):
        declared_runtime.calculate_declared_fiscal_rate("SESSION", fake)


def test_runtime_delegates_exact_declaration_coordinates_once_and_wraps_identities(monkeypatch):
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_runtime as fiscal_runtime

    declaration = _declaration(base="123.4500")
    calculation = object()
    calls = []

    def fake_runtime(session, rule_key, effective_date, context, base):
        calls.append((session, rule_key, effective_date, context, base))
        return calculation

    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", fake_runtime)

    # The real result wrapper requires the nominal calculation type. Return one.
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    rule = ResolvedFiscalRule(
        "iva.general_rate", Decimal("0.16"), "rate", date(2010, 1, 1), None,
        "MX", "general", "comercial", "TEST"
    )
    calculation = FiscalRateCalculation(declaration.base, Decimal("19.752000"), rule)

    result = declared_runtime.calculate_declared_fiscal_rate("SESSION", declaration)

    assert calls == [(
        "SESSION",
        declaration.rule_key,
        declaration.effective_date,
        declaration.context,
        declaration.base,
    )]
    assert result.declaration is declaration
    assert result.calculation is calculation


def test_real_declared_curated_iva_calculation_preserves_explicit_decision_and_provenance(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_declaration_runtime import calculate_declared_fiscal_rate
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = _fact("250.00")
        base = Decimal("250.00")
        declaration = declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            base,
        )

        result = calculate_declared_fiscal_rate(session, declaration)

        assert result.declaration is declaration
        assert result.declaration.fact is fact
        assert result.calculation.base is base
        assert result.calculation.amount == Decimal("40.0000")
        assert result.calculation.rule.rule_key == "iva.general_rate"
        assert result.calculation.rule.value == Decimal("0.16")
        assert result.calculation.rule.effective_from == date(2010, 1, 1)
        assert result.calculation.rule.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    finally:
        session.close()
        engine.dispose()


def test_missing_declared_rule_or_context_fails_closed_without_retry(tmp_path, monkeypatch):
    import aqorath.fiscal_rule_data_mx as data
    import aqorath.fiscal_runtime as fiscal_runtime
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_declaration_runtime import calculate_declared_fiscal_rate
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import FiscalContext

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        real_runtime = fiscal_runtime.calculate_fiscal_rate_for_date
        calls = []

        def counted(*args, **kwargs):
            calls.append((args, kwargs))
            return real_runtime(*args, **kwargs)

        monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", counted)

        missing_date = declare_fiscal_rate_applicability(
            _fact(), date(2009, 12, 31), data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate", Decimal("100.00")
        )
        with pytest.raises(LookupError):
            calculate_declared_fiscal_rate(session, missing_date)

        missing_context = declare_fiscal_rate_applicability(
            _fact(), date(2026, 1, 1), FiscalContext("MX", "resico", "comercial"),
            "iva.general_rate", Decimal("100.00")
        )
        with pytest.raises(LookupError):
            calculate_declared_fiscal_rate(session, missing_context)

        assert len(calls) == 2
    finally:
        session.close()
        engine.dispose()


def test_runtime_failure_propagates_without_retry_or_fallback(monkeypatch):
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_runtime as fiscal_runtime

    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise LookupError("declared rule unavailable")

    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", fail)

    declaration = _declaration(rule_key="missing.rule")
    with pytest.raises(LookupError, match="declared rule unavailable"):
        declared_runtime.calculate_declared_fiscal_rate("SESSION", declaration)

    assert len(calls) == 1


def test_runtime_does_not_inspect_fact_or_infer_rule_from_sale(monkeypatch):
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_runtime as fiscal_runtime
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    declaration = _declaration(rule_key="explicit.future.rule", base="10.00")

    class PoisonFact:
        def __getattribute__(self, name):
            raise AssertionError("declared runtime must never inspect economic fact")

    object.__setattr__(declaration, "fact", PoisonFact())

    rule = ResolvedFiscalRule(
        "explicit.future.rule", Decimal("0.10"), "rate", date(2020, 1, 1), None,
        "MX", "general", "comercial", "TEST"
    )
    calculation = FiscalRateCalculation(declaration.base, Decimal("1.000"), rule)
    calls = []

    def fake(session, rule_key, effective_date, context, base):
        calls.append((session, rule_key, effective_date, context, base))
        return calculation

    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", fake)
    result = declared_runtime.calculate_declared_fiscal_rate("SESSION", declaration)

    assert result.declaration is declaration
    assert result.calculation is calculation
    assert calls[0][1] == "explicit.future.rule"


def test_runtime_uses_only_supplied_session_and_never_installs_posts_or_uses_legacy_tax(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage
    import aqorath.tax as legacy_tax
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    declaration = _declaration()
    rule = ResolvedFiscalRule(
        "iva.general_rate", Decimal("0.16"), "rate", date(2010, 1, 1), None,
        "MX", "general", "comercial", "TEST"
    )
    calculation = FiscalRateCalculation(declaration.base, Decimal("32.0000"), rule)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden authority called by declared fiscal runtime")

    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(installer, "install_fiscal_rule_set", forbidden)
    monkeypatch.setattr(posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(account_resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(catalog, "resolve_account_by_code", forbidden)
    monkeypatch.setattr(legacy_tax, "calculate_taxes", forbidden)
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", lambda *args: calculation)

    result = declared_runtime.calculate_declared_fiscal_rate("EXACT_SESSION", declaration)
    assert result.declaration is declaration
    assert result.calculation is calculation


def test_declared_runtime_is_deterministic_and_does_not_mutate_declaration(monkeypatch):
    import aqorath.fiscal_declaration_runtime as declared_runtime
    import aqorath.fiscal_runtime as fiscal_runtime
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    declaration = _declaration(base="77.123456789")
    original = (
        declaration.fact,
        declaration.effective_date,
        declaration.context,
        declaration.rule_key,
        declaration.base,
    )
    rule = ResolvedFiscalRule(
        "iva.general_rate", Decimal("0.16"), "rate", date(2010, 1, 1), None,
        "MX", "general", "comercial", "TEST"
    )
    calculation = FiscalRateCalculation(
        declaration.base,
        declaration.base * rule.value,
        rule,
    )
    monkeypatch.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", lambda *args: calculation)

    first = declared_runtime.calculate_declared_fiscal_rate("SESSION", declaration)
    second = declared_runtime.calculate_declared_fiscal_rate("SESSION", declaration)

    assert first == second
    assert first.declaration is second.declaration is declaration
    assert first.calculation is second.calculation is calculation
    assert (
        declaration.fact,
        declaration.effective_date,
        declaration.context,
        declaration.rule_key,
        declaration.base,
    ) == original
