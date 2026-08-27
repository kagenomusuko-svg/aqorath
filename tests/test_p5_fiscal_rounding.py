"""Phase 5N.1 — explicit fiscal monetary rounding contracts.

A confirmed fiscal treatment may contain an exact Decimal amount with more
precision than a downstream monetary representation. This boundary requires an
explicit nominal rounding policy; it never chooses a scale or rounding mode by
default and never claims that one policy is universally correct for Mexico.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import (
    Decimal,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
)
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _confirmed(exact_amount="1.005"):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_confirmation import (
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_rules import FiscalContext, ResolvedFiscalRule

    fact = EconomicFact("sale", Decimal("100.00"), "cash")
    context = FiscalContext("MX", "general", "comercial")
    declaration = declare_fiscal_rate_applicability(
        fact,
        date(2026, 8, 27),
        context,
        "test.rate",
        Decimal("100.00"),
    )
    rule = ResolvedFiscalRule(
        rule_key="test.rate",
        value=Decimal("0.01005"),
        unit="rate",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        source_ref="TEST:RULE",
    )
    calculation = FiscalRateCalculation(
        base=declaration.base,
        amount=Decimal(exact_amount),
        rule=rule,
    )
    declared = DeclaredFiscalRateCalculation(declaration, calculation)
    snapshot = create_fiscal_confirmation_snapshot(declared)
    return confirm_fiscal_snapshot(snapshot)


def _policy(
    *,
    policy_key="explicit.mx.presentation",
    quantizer=Decimal("0.01"),
    rounding_mode=ROUND_HALF_UP,
    source_ref="EXPLICIT:TEST:POLICY",
):
    from aqorath.fiscal_rounding import FiscalRoundingPolicy

    return FiscalRoundingPolicy(
        policy_key=policy_key,
        quantizer=quantizer,
        rounding_mode=rounding_mode,
        source_ref=source_ref,
    )


def test_fiscal_rounding_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_rounding as rounding

    assert rounding.__all__ == [
        "FiscalRoundingPolicy",
        "RoundedFiscalAmount",
        "round_confirmed_fiscal_amount",
    ]
    assert hasattr(rounding, "FiscalRoundingPolicy")
    assert hasattr(rounding, "RoundedFiscalAmount")

    sig = signature(rounding.round_confirmed_fiscal_amount)
    assert list(sig.parameters) == ["confirmed_treatment", "policy"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_rounding_requires_explicit_policy_and_preserves_treatment_policy_identities():
    from aqorath.fiscal_rounding import (
        RoundedFiscalAmount,
        round_confirmed_fiscal_amount,
    )

    confirmed = _confirmed("1.005")
    policy = _policy()
    result = round_confirmed_fiscal_amount(confirmed, policy)

    assert isinstance(result, RoundedFiscalAmount)
    assert result.confirmed_treatment is confirmed
    assert result.policy is policy
    assert result.exact_amount == Decimal("1.005")
    assert result.rounded_amount == Decimal("1.01")

    with pytest.raises(TypeError):
        round_confirmed_fiscal_amount(confirmed, None)


def test_rounding_mode_is_never_hidden_and_different_explicit_modes_produce_expected_results():
    from aqorath.fiscal_rounding import round_confirmed_fiscal_amount

    confirmed = _confirmed("1.005")
    half_up = round_confirmed_fiscal_amount(
        confirmed,
        _policy(policy_key="half-up", rounding_mode=ROUND_HALF_UP),
    )
    half_even = round_confirmed_fiscal_amount(
        confirmed,
        _policy(policy_key="half-even", rounding_mode=ROUND_HALF_EVEN),
    )
    down = round_confirmed_fiscal_amount(
        confirmed,
        _policy(policy_key="down", rounding_mode=ROUND_DOWN),
    )

    assert half_up.rounded_amount == Decimal("1.01")
    assert half_even.rounded_amount == Decimal("1.00")
    assert down.rounded_amount == Decimal("1.00")
    assert half_up.policy.rounding_mode == ROUND_HALF_UP
    assert half_even.policy.rounding_mode == ROUND_HALF_EVEN
    assert down.policy.rounding_mode == ROUND_DOWN


def test_quantizer_is_explicit_power_of_ten_and_precision_is_preserved_before_rounding():
    from aqorath.fiscal_rounding import round_confirmed_fiscal_amount

    confirmed = _confirmed("0.876543210987654321")
    policy = _policy(
        policy_key="three-decimals",
        quantizer=Decimal("0.001"),
        rounding_mode=ROUND_HALF_UP,
    )
    result = round_confirmed_fiscal_amount(confirmed, policy)

    assert str(result.exact_amount) == "0.876543210987654321"
    assert result.rounded_amount == Decimal("0.877")
    assert result.policy.quantizer == Decimal("0.001")


def test_policy_is_frozen_and_validates_key_quantizer_mode_and_provenance_fail_closed():
    from aqorath.fiscal_rounding import FiscalRoundingPolicy

    policy = _policy()
    with pytest.raises(FrozenInstanceError):
        policy.quantizer = Decimal("1")

    for bad_key in ("", "   ", None, 123):
        with pytest.raises((TypeError, ValueError)):
            FiscalRoundingPolicy(
                bad_key,
                Decimal("0.01"),
                ROUND_HALF_UP,
                "SOURCE",
            )

    for bad_quantizer in (
        0.01,
        "0.01",
        Decimal("0"),
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("0.05"),
        Decimal("0.25"),
    ):
        with pytest.raises((TypeError, ValueError)):
            FiscalRoundingPolicy(
                "policy",
                bad_quantizer,
                ROUND_HALF_UP,
                "SOURCE",
            )

    for bad_mode in ("", "HALF_UP", None, 123, "NOT_A_DECIMAL_MODE"):
        with pytest.raises((TypeError, ValueError)):
            FiscalRoundingPolicy(
                "policy",
                Decimal("0.01"),
                bad_mode,
                "SOURCE",
            )

    for bad_source in ("", "   ", None, 123):
        with pytest.raises((TypeError, ValueError)):
            FiscalRoundingPolicy(
                "policy",
                Decimal("0.01"),
                ROUND_HALF_UP,
                bad_source,
            )


def test_rounding_requires_nominal_confirmed_fiscal_treatment_not_snapshot_or_shape():
    from aqorath.fiscal_rounding import round_confirmed_fiscal_amount

    confirmed = _confirmed()
    policy = _policy()
    fake = SimpleNamespace(snapshot=confirmed.snapshot)

    with pytest.raises(TypeError):
        round_confirmed_fiscal_amount(confirmed.snapshot, policy)
    with pytest.raises(TypeError):
        round_confirmed_fiscal_amount(fake, policy)


def test_public_result_type_is_frozen_and_rejects_inconsistent_direct_construction():
    from aqorath.fiscal_rounding import RoundedFiscalAmount

    confirmed = _confirmed("1.005")
    policy = _policy()
    valid = RoundedFiscalAmount(
        confirmed_treatment=confirmed,
        policy=policy,
        exact_amount=Decimal("1.005"),
        rounded_amount=Decimal("1.01"),
    )
    assert valid.confirmed_treatment is confirmed
    assert valid.policy is policy

    with pytest.raises(FrozenInstanceError):
        valid.rounded_amount = Decimal("9.99")

    with pytest.raises(TypeError):
        RoundedFiscalAmount(
            confirmed_treatment=SimpleNamespace(snapshot=confirmed.snapshot),
            policy=policy,
            exact_amount=Decimal("1.005"),
            rounded_amount=Decimal("1.01"),
        )
    with pytest.raises(ValueError):
        RoundedFiscalAmount(
            confirmed_treatment=confirmed,
            policy=policy,
            exact_amount=Decimal("9.999"),
            rounded_amount=Decimal("10.00"),
        )
    with pytest.raises(ValueError):
        RoundedFiscalAmount(
            confirmed_treatment=confirmed,
            policy=policy,
            exact_amount=Decimal("1.005"),
            rounded_amount=Decimal("1.00"),
        )


def test_zero_and_already_scaled_amounts_round_deterministically_without_special_fallback():
    from aqorath.fiscal_rounding import round_confirmed_fiscal_amount

    policy = _policy()
    zero = round_confirmed_fiscal_amount(_confirmed("0"), policy)
    exact = round_confirmed_fiscal_amount(_confirmed("40.0000"), policy)

    assert zero.exact_amount == Decimal("0")
    assert zero.rounded_amount == Decimal("0.00")
    assert exact.exact_amount == Decimal("40.0000")
    assert exact.rounded_amount == Decimal("40.00")


def test_rounding_is_pure_and_never_resolves_recalculates_installs_posts_or_uses_legacy_tax(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_declaration_runtime as declaration_runtime
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage
    import aqorath.tax as legacy_tax

    confirmed = _confirmed("1.005")
    policy = _policy()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden dependency called by fiscal rounding")

    with monkeypatch.context() as m:
        m.setattr(fiscal_rules, "resolve_fiscal_rule", bomb)
        m.setattr(calculation, "calculate_fiscal_rate_amount", bomb)
        m.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", bomb)
        m.setattr(declaration_runtime, "calculate_declared_fiscal_rate", bomb)
        m.setattr(installer, "install_fiscal_rule_set", bomb)
        m.setattr(storage, "get_session", bomb)
        m.setattr(account_resolution, "resolve_proposal_accounts", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(legacy_tax, "calculate_taxes", bomb)

        import aqorath.fiscal_rounding as rounding

        rounding = reload(rounding)
        result = rounding.round_confirmed_fiscal_amount(confirmed, policy)
        assert result.rounded_amount == Decimal("1.01")

    reload(rounding)


def test_rounding_is_deterministic_does_not_mutate_inputs_and_adds_no_default_policy_metadata():
    from aqorath.fiscal_rounding import round_confirmed_fiscal_amount

    confirmed = _confirmed("7.123456789")
    policy = _policy(
        policy_key="explicit-four-decimals",
        quantizer=Decimal("0.0001"),
        rounding_mode=ROUND_HALF_UP,
        source_ref="MANUAL:EXPLICIT:TEST",
    )
    original_snapshot = confirmed.snapshot

    first = round_confirmed_fiscal_amount(confirmed, policy)
    second = round_confirmed_fiscal_amount(confirmed, policy)

    assert first == second
    assert first.confirmed_treatment is second.confirmed_treatment is confirmed
    assert first.policy is second.policy is policy
    assert confirmed.snapshot is original_snapshot
    assert confirmed.snapshot.calculated_amount == Decimal("7.123456789")
    assert policy.policy_key == "explicit-four-decimals"
    assert policy.source_ref == "MANUAL:EXPLICIT:TEST"
    for hidden in ("currency", "effective_date", "legal_default", "is_sat_default"):
        assert not hasattr(policy, hidden)
