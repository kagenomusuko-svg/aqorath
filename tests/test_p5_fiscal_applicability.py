from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module, reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _fact(amount="200.00"):
    from aqorath.economic_facts import EconomicFact

    return EconomicFact(
        type="sale",
        amount=Decimal(amount),
        payment_method="cash",
    )


def _context(regime="general", entity_type="comercial"):
    from aqorath.fiscal_rules import FiscalContext

    return FiscalContext(
        jurisdiction="MX",
        regime=regime,
        entity_type=entity_type,
    )


def test_fiscal_applicability_public_contract_and_exact_signature_exist():
    module = import_module("aqorath.fiscal_applicability")

    assert module.__all__ == [
        "FiscalRateApplicabilityDeclaration",
        "declare_fiscal_rate_applicability",
    ]
    assert hasattr(module, "FiscalRateApplicabilityDeclaration")
    assert callable(module.declare_fiscal_rate_applicability)

    sig = signature(module.declare_fiscal_rate_applicability)
    assert list(sig.parameters) == [
        "fact",
        "effective_date",
        "context",
        "rule_key",
        "base",
    ]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_declaration_preserves_exact_fact_context_date_rule_and_base_identity():
    from aqorath.fiscal_applicability import (
        FiscalRateApplicabilityDeclaration,
        declare_fiscal_rate_applicability,
    )

    fact = _fact()
    context = _context()
    effective_date = date(2026, 8, 26)
    base = Decimal("200.00")

    declaration = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        "mx.iva.rate.general",
        base,
    )

    assert isinstance(declaration, FiscalRateApplicabilityDeclaration)
    assert declaration.fact is fact
    assert declaration.context is context
    assert declaration.effective_date is effective_date
    assert declaration.rule_key == "mx.iva.rate.general"
    assert declaration.base is base

    with pytest.raises(FrozenInstanceError):
        declaration.rule_key = "other"
    with pytest.raises(FrozenInstanceError):
        declaration.base = Decimal("1.00")


def test_tax_base_is_explicit_and_is_not_derived_from_economic_fact_amount():
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability

    fact = _fact("200.00")
    explicit_base = Decimal("123.4567")

    declaration = declare_fiscal_rate_applicability(
        fact,
        date(2026, 8, 26),
        _context(),
        "mx.iva.rate.general",
        explicit_base,
    )

    assert fact.amount == Decimal("200.00")
    assert declaration.base == Decimal("123.4567")
    assert declaration.base is explicit_base
    assert declaration.base != fact.amount


def test_sale_does_not_imply_iva_or_any_default_rule_key():
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability

    fact = _fact()
    context = _context()
    effective_date = date(2026, 8, 26)
    base = Decimal("200.00")

    iva = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        "mx.iva.rate.general",
        base,
    )
    explicit_other = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        "explicit.future.rule",
        base,
    )

    assert iva.rule_key == "mx.iva.rate.general"
    assert explicit_other.rule_key == "explicit.future.rule"
    assert iva.fact is explicit_other.fact is fact
    assert not hasattr(iva, "applies")


def test_declaration_requires_nominal_economic_fact_and_fiscal_context():
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability

    fact = _fact()
    context = _context()
    fake_fact = SimpleNamespace(
        type=fact.type,
        amount=fact.amount,
        payment_method=fact.payment_method,
    )
    fake_context = SimpleNamespace(
        jurisdiction=context.jurisdiction,
        regime=context.regime,
        entity_type=context.entity_type,
    )

    with pytest.raises(TypeError):
        declare_fiscal_rate_applicability(
            fake_fact,
            date(2026, 8, 26),
            context,
            "mx.iva.rate.general",
            Decimal("200.00"),
        )

    with pytest.raises(TypeError):
        declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 26),
            fake_context,
            "mx.iva.rate.general",
            Decimal("200.00"),
        )


def test_declaration_validates_date_context_rule_key_and_decimal_base_fail_closed():
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_rules import FiscalContext

    fact = _fact()
    context = _context()

    for bad_date in (
        "2026-08-26",
        datetime(2026, 8, 26, 12, 0),
        None,
    ):
        with pytest.raises(TypeError):
            declare_fiscal_rate_applicability(
                fact,
                bad_date,
                context,
                "mx.iva.rate.general",
                Decimal("200.00"),
            )

    for bad_context in (
        FiscalContext("", "general", "comercial"),
        FiscalContext("MX", "", "comercial"),
        FiscalContext("MX", "general", ""),
    ):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_rate_applicability(
                fact,
                date(2026, 8, 26),
                bad_context,
                "mx.iva.rate.general",
                Decimal("200.00"),
            )

    for bad_rule_key in ("", "   ", None, 123):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_rate_applicability(
                fact,
                date(2026, 8, 26),
                context,
                bad_rule_key,
                Decimal("200.00"),
            )

    for bad_base in (
        200,
        200.0,
        "200.00",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-0.01"),
    ):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_rate_applicability(
                fact,
                date(2026, 8, 26),
                context,
                "mx.iva.rate.general",
                bad_base,
            )

    zero = declare_fiscal_rate_applicability(
        fact,
        date(2026, 8, 26),
        context,
        "mx.iva.rate.general",
        Decimal("0"),
    )
    assert zero.base == Decimal("0")


def test_public_declaration_type_enforces_same_invariants_when_constructed_directly():
    from aqorath.fiscal_applicability import FiscalRateApplicabilityDeclaration

    fact = _fact()
    context = _context()

    valid = FiscalRateApplicabilityDeclaration(
        fact=fact,
        effective_date=date(2026, 8, 26),
        context=context,
        rule_key="mx.iva.rate.general",
        base=Decimal("200.00"),
    )
    assert valid.fact is fact
    assert valid.context is context

    with pytest.raises(TypeError):
        FiscalRateApplicabilityDeclaration(
            fact=SimpleNamespace(type="sale"),
            effective_date=date(2026, 8, 26),
            context=context,
            rule_key="mx.iva.rate.general",
            base=Decimal("200.00"),
        )

    with pytest.raises(ValueError):
        FiscalRateApplicabilityDeclaration(
            fact=fact,
            effective_date=date(2026, 8, 26),
            context=context,
            rule_key="mx.iva.rate.general",
            base=Decimal("-1"),
        )


def test_applicability_is_pure_and_never_resolves_calculates_or_uses_legacy_tax_paths(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.tax as legacy_tax

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden dependency called by fiscal applicability")

    with monkeypatch.context() as m:
        m.setattr(economic_facts, "resolve_economic_fact", bomb)
        m.setattr(fiscal_rules, "resolve_fiscal_rule", bomb)
        m.setattr(fiscal_calculation, "calculate_fiscal_rate_amount", bomb)
        m.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", bomb)
        m.setattr(legacy_tax, "calculate_taxes", bomb)

        import aqorath.fiscal_applicability as applicability

        applicability = reload(applicability)
        declaration = applicability.declare_fiscal_rate_applicability(
            _fact(),
            date(2026, 8, 26),
            _context(),
            "mx.iva.rate.general",
            Decimal("200.00"),
        )
        assert declaration.rule_key == "mx.iva.rate.general"

    reload(applicability)


def test_applicability_never_opens_session_persists_posts_or_selects_accounts(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.posting as posting
    import aqorath.storage as storage

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscal applicability")

    with monkeypatch.context() as m:
        m.setattr(storage, "get_session", bomb)
        m.setattr(core, "post_entry", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(account_resolution, "resolve_proposal_accounts", bomb)
        m.setattr(catalog, "resolve_account_by_code", bomb)
        m.setattr(catalog, "create_entity_account", bomb)

        import aqorath.fiscal_applicability as applicability

        applicability = reload(applicability)
        declaration = applicability.declare_fiscal_rate_applicability(
            _fact(),
            date(2026, 8, 26),
            _context(),
            "explicit.future.rule",
            Decimal("200.00"),
        )
        assert declaration.rule_key == "explicit.future.rule"

    reload(applicability)


def test_declaration_is_deterministic_preserves_inputs_and_does_not_verify_rule_existence():
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability

    fact = _fact()
    context = _context(regime="general", entity_type="comercial")
    effective_date = date(2026, 8, 26)
    base = Decimal("77.123456789")

    first = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        "rule.not.installed.yet",
        base,
    )
    second = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        "rule.not.installed.yet",
        base,
    )

    assert first == second
    assert first.fact is fact
    assert first.context is context
    assert first.effective_date is effective_date
    assert first.base is base
    assert fact.amount == Decimal("200.00")
    assert context.jurisdiction == "MX"
    assert context.regime == "general"
    assert context.entity_type == "comercial"
