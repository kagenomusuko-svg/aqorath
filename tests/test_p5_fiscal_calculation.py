"""Phase 5F.1 — pure fiscal rate calculation contracts.

This phase calculates one exact rate-based amount from an already-resolved
fiscal rule. It does not resolve rules, round to currency scale, determine tax
applicability, choose accounts, build proposals, post, or persist.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import Decimal
from inspect import signature

import pytest


def _rule(**overrides):
    from aqorath.fiscal_rules import ResolvedFiscalRule

    values = {
        "rule_key": "iva.general_rate",
        "value": Decimal("0.16"),
        "unit": "rate",
        "effective_from": date(2010, 1, 1),
        "effective_to": None,
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "comercial",
        "source_ref": "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1",
    }
    values.update(overrides)
    return ResolvedFiscalRule(**values)


def test_fiscal_rate_calculation_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_calculation as calculation

    assert [f.name for f in fields(calculation.FiscalRateCalculation)] == [
        "base", "amount", "rule"
    ]
    assert list(signature(calculation.calculate_fiscal_rate_amount).parameters) == [
        "base", "rule"
    ]

    result = calculation.FiscalRateCalculation(
        Decimal("100.00"), Decimal("16.0000"), _rule()
    )
    with pytest.raises(FrozenInstanceError):
        result.amount = Decimal("9")


def test_calculation_accepts_decimal_base_and_nominal_resolved_rate_rule():
    from aqorath.fiscal_calculation import FiscalRateCalculation, calculate_fiscal_rate_amount

    rule = _rule()
    result = calculate_fiscal_rate_amount(Decimal("100.00"), rule)
    assert isinstance(result, FiscalRateCalculation)
    assert result.base == Decimal("100.00")
    assert result.amount == Decimal("16.0000")
    assert result.rule is rule


def test_calculation_is_exact_decimal_multiplication_without_currency_rounding_or_float_conversion():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    base = Decimal("1.23456789")
    rule = _rule(value=Decimal("0.123456789"))
    result = calculate_fiscal_rate_amount(base, rule)

    expected = base * rule.value
    assert result.amount == expected
    assert result.amount == Decimal("0.15241578750190521")
    assert isinstance(result.amount, Decimal)
    assert result.amount != result.amount.quantize(Decimal("0.01"))


def test_calculation_preserves_exact_rule_identity_and_full_provenance():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    rule = _rule(
        value=Decimal("0.160000"),
        source_ref="DOF:exact-source",
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    result = calculate_fiscal_rate_amount(Decimal("999.99"), rule)

    assert result.rule is rule
    assert result.rule.rule_key == "iva.general_rate"
    assert result.rule.value == Decimal("0.160000")
    assert result.rule.effective_from == date(2024, 1, 1)
    assert result.rule.effective_to == date(2024, 12, 31)
    assert result.rule.jurisdiction == "MX"
    assert result.rule.regime == "general"
    assert result.rule.entity_type == "comercial"
    assert result.rule.source_ref == "DOF:exact-source"


def test_calculation_allows_zero_base_and_zero_rate_without_special_fallback():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    zero_base = calculate_fiscal_rate_amount(Decimal("0.00"), _rule())
    zero_rate = calculate_fiscal_rate_amount(
        Decimal("123.45"), _rule(value=Decimal("0.00"))
    )
    assert zero_base.amount == Decimal("0.0000")
    assert zero_rate.amount == Decimal("0.0000")


def test_calculation_rejects_non_decimal_nonfinite_or_negative_base():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    for bad in (100, 100.0, "100.00"):
        with pytest.raises(TypeError):
            calculate_fiscal_rate_amount(bad, _rule())
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01")):
        with pytest.raises(ValueError):
            calculate_fiscal_rate_amount(bad, _rule())


def test_calculation_requires_nominal_resolved_rule_and_rate_unit():
    from types import SimpleNamespace
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    fake = SimpleNamespace(value=Decimal("0.16"), unit="rate")
    with pytest.raises(TypeError):
        calculate_fiscal_rate_amount(Decimal("100.00"), fake)

    with pytest.raises(ValueError, match="rate|unit"):
        calculate_fiscal_rate_amount(
            Decimal("100.00"), _rule(unit="currency", value=Decimal("1000.00"))
        )


def test_calculation_rejects_invalid_resolved_rule_rate_value_fail_closed():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    with pytest.raises(TypeError):
        calculate_fiscal_rate_amount(Decimal("100.00"), _rule(value="0.16"))
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01")):
        with pytest.raises(ValueError):
            calculate_fiscal_rate_amount(Decimal("100.00"), _rule(value=bad))


def test_calculation_is_deterministic_and_does_not_mutate_base_or_rule():
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount

    base = Decimal("123.4500")
    rule = _rule(value=Decimal("0.160000"))
    before_rule = (
        rule.rule_key,
        rule.value,
        rule.unit,
        rule.effective_from,
        rule.effective_to,
        rule.jurisdiction,
        rule.regime,
        rule.entity_type,
        rule.source_ref,
    )

    first = calculate_fiscal_rate_amount(base, rule)
    second = calculate_fiscal_rate_amount(base, rule)
    assert first == second
    assert first.rule is rule
    assert second.rule is rule
    assert base == Decimal("123.4500")
    assert before_rule == (
        rule.rule_key,
        rule.value,
        rule.unit,
        rule.effective_from,
        rule.effective_to,
        rule.jurisdiction,
        rule.regime,
        rule.entity_type,
        rule.source_ref,
    )


def test_calculation_is_pure_and_never_resolves_persists_rounds_or_uses_legacy_tax_paths(monkeypatch):
    import importlib
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates
    import aqorath.posting as posting

    def forbidden(*args, **kwargs):
        raise AssertionError("fiscal calculation primitive must remain pure")

    with monkeypatch.context() as m:
        m.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
        m.setattr(storage, "get_session", forbidden)
        m.setattr(tax, "calculate_taxes", forbidden)
        m.setattr(templates, "get_template", forbidden)
        m.setattr(posting, "create_posting_instruction", forbidden)
        calculation = importlib.reload(calculation)

        result = calculation.calculate_fiscal_rate_amount(
            Decimal("100.00"), _rule()
        )
        assert result.amount == Decimal("16.0000")

    importlib.reload(calculation)
