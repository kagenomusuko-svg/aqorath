"""Phase 5P.1 — rounded fiscal amount confirmation contracts."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _rounded(exact_amount="1.005", quantizer="0.01"):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_confirmation import (
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_rounding import (
        FiscalRoundingPolicy,
        round_confirmed_fiscal_amount,
    )
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
        source_ref="TEST:RULE:SOURCE",
    )
    calculation = FiscalRateCalculation(
        base=declaration.base,
        amount=Decimal(exact_amount),
        rule=rule,
    )
    declared = DeclaredFiscalRateCalculation(declaration, calculation)
    fiscal_snapshot = create_fiscal_confirmation_snapshot(declared)
    confirmed = confirm_fiscal_snapshot(fiscal_snapshot)
    policy = FiscalRoundingPolicy(
        policy_key="explicit.presentation",
        quantizer=Decimal(quantizer),
        rounding_mode=ROUND_HALF_UP,
        source_ref="TEST:ROUNDING:POLICY",
    )
    return round_confirmed_fiscal_amount(confirmed, policy)


def test_fiscal_monetary_confirmation_public_contract_and_exact_signatures_exist():
    import aqorath.fiscal_monetary_confirmation as monetary

    assert monetary.__all__ == [
        "FiscalMonetaryConfirmationSnapshot",
        "ConfirmedFiscalMonetaryAmount",
        "create_fiscal_monetary_confirmation_snapshot",
        "confirm_fiscal_monetary_snapshot",
    ]

    create_sig = signature(monetary.create_fiscal_monetary_confirmation_snapshot)
    assert list(create_sig.parameters) == ["rounded_amount"]
    parameter = create_sig.parameters["rounded_amount"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty

    confirm_sig = signature(monetary.confirm_fiscal_monetary_snapshot)
    assert list(confirm_sig.parameters) == ["snapshot"]
    parameter = confirm_sig.parameters["snapshot"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_snapshot_copies_exact_confirmed_fiscal_truth_rounding_policy_and_result():
    from aqorath.fiscal_monetary_confirmation import (
        create_fiscal_monetary_confirmation_snapshot,
    )

    rounded = _rounded("1.005")
    snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)

    assert snapshot.fact_type == "sale"
    assert snapshot.fact_amount == Decimal("100.00")
    assert snapshot.payment_method == "cash"
    assert snapshot.effective_date == date(2026, 8, 27)
    assert snapshot.jurisdiction == "MX"
    assert snapshot.regime == "general"
    assert snapshot.entity_type == "comercial"
    assert snapshot.rule_key == "test.rate"
    assert snapshot.base == Decimal("100.00")
    assert snapshot.rate == Decimal("0.01005")
    assert snapshot.unit == "rate"
    assert snapshot.rule_effective_from == date(2026, 1, 1)
    assert snapshot.rule_effective_to is None
    assert snapshot.rule_source_ref == "TEST:RULE:SOURCE"
    assert snapshot.exact_amount == Decimal("1.005")
    assert snapshot.rounding_policy_key == "explicit.presentation"
    assert snapshot.rounding_quantizer == Decimal("0.01")
    assert snapshot.rounding_mode == ROUND_HALF_UP
    assert snapshot.rounding_source_ref == "TEST:ROUNDING:POLICY"
    assert snapshot.rounded_amount == Decimal("1.01")


def test_snapshot_is_deeply_immutable_and_contains_only_value_truth_not_live_sources():
    from aqorath.fiscal_monetary_confirmation import (
        FiscalMonetaryConfirmationSnapshot,
        create_fiscal_monetary_confirmation_snapshot,
    )
    from aqorath.fiscal_rounding import FiscalRoundingPolicy, RoundedFiscalAmount

    rounded = _rounded()
    snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)

    assert isinstance(snapshot, FiscalMonetaryConfirmationSnapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.rounded_amount = Decimal("9.99")

    for hidden in (
        "rounded_amount_source",
        "confirmed_treatment",
        "policy",
        "rule",
        "declaration",
        "calculation",
        "fact",
        "context",
    ):
        assert not hasattr(snapshot, hidden)

    assert not isinstance(snapshot, RoundedFiscalAmount)
    assert not isinstance(snapshot, FiscalRoundingPolicy)


def test_snapshot_is_independent_from_forced_source_mutation_after_creation():
    from aqorath.fiscal_monetary_confirmation import (
        create_fiscal_monetary_confirmation_snapshot,
    )

    rounded = _rounded("7.12345", "0.001")
    snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)

    object.__setattr__(rounded, "exact_amount", Decimal("999"))
    object.__setattr__(rounded, "rounded_amount", Decimal("888"))
    object.__setattr__(rounded.policy, "source_ref", "MUTATED")
    object.__setattr__(
        rounded.confirmed_treatment.snapshot,
        "source_ref",
        "MUTATED:RULE",
    )

    assert snapshot.exact_amount == Decimal("7.12345")
    assert snapshot.rounded_amount == Decimal("7.123")
    assert snapshot.rounding_source_ref == "TEST:ROUNDING:POLICY"
    assert snapshot.rule_source_ref == "TEST:RULE:SOURCE"


def test_snapshot_preserves_high_precision_exact_amount_and_explicit_rounding_without_recalculation():
    from aqorath.fiscal_monetary_confirmation import (
        create_fiscal_monetary_confirmation_snapshot,
    )

    rounded = _rounded("0.876543210987654321", "0.0001")
    snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)

    assert str(snapshot.exact_amount) == "0.876543210987654321"
    assert snapshot.rounding_quantizer == Decimal("0.0001")
    assert snapshot.rounded_amount == Decimal("0.8765")


def test_snapshot_requires_nominal_rounded_fiscal_amount_pipeline():
    from aqorath.fiscal_monetary_confirmation import (
        create_fiscal_monetary_confirmation_snapshot,
    )

    rounded = _rounded()
    fake = SimpleNamespace(
        confirmed_treatment=rounded.confirmed_treatment,
        policy=rounded.policy,
        exact_amount=rounded.exact_amount,
        rounded_amount=rounded.rounded_amount,
    )

    with pytest.raises(TypeError):
        create_fiscal_monetary_confirmation_snapshot(rounded.confirmed_treatment)
    with pytest.raises(TypeError):
        create_fiscal_monetary_confirmation_snapshot(fake)


def test_confirmation_returns_exact_snapshot_identity_is_frozen_and_rejects_shape_input():
    from aqorath.fiscal_monetary_confirmation import (
        ConfirmedFiscalMonetaryAmount,
        confirm_fiscal_monetary_snapshot,
        create_fiscal_monetary_confirmation_snapshot,
    )

    snapshot = create_fiscal_monetary_confirmation_snapshot(_rounded())
    confirmed = confirm_fiscal_monetary_snapshot(snapshot)

    assert isinstance(confirmed, ConfirmedFiscalMonetaryAmount)
    assert confirmed.snapshot is snapshot
    with pytest.raises(FrozenInstanceError):
        confirmed.snapshot = snapshot
    with pytest.raises(TypeError):
        confirm_fiscal_monetary_snapshot(SimpleNamespace(**snapshot.__dict__))


def test_monetary_confirmation_never_rerounds_reconfirms_resolves_recalculates_or_posts(monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_confirmation as fiscal_confirmation
    import aqorath.fiscal_declaration_runtime as declaration_runtime
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage

    rounded = _rounded("1.005")

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by monetary confirmation")

    with monkeypatch.context() as m:
        m.setattr(rounding, "round_confirmed_fiscal_amount", bomb)
        m.setattr(fiscal_confirmation, "confirm_fiscal_snapshot", bomb)
        m.setattr(calculation, "calculate_fiscal_rate_amount", bomb)
        m.setattr(declaration_runtime, "calculate_declared_fiscal_rate", bomb)
        m.setattr(fiscal_rules, "resolve_fiscal_rule", bomb)
        m.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(storage, "get_session", bomb)

        import aqorath.fiscal_monetary_confirmation as monetary

        monetary = reload(monetary)
        snapshot = monetary.create_fiscal_monetary_confirmation_snapshot(rounded)
        confirmed = monetary.confirm_fiscal_monetary_snapshot(snapshot)
        assert confirmed.snapshot is snapshot

    reload(monetary)


def test_monetary_confirmation_is_deterministic_and_adds_no_hidden_metadata():
    from aqorath.fiscal_monetary_confirmation import (
        confirm_fiscal_monetary_snapshot,
        create_fiscal_monetary_confirmation_snapshot,
    )

    rounded = _rounded("12.34567", "0.01")
    first = create_fiscal_monetary_confirmation_snapshot(rounded)
    second = create_fiscal_monetary_confirmation_snapshot(rounded)

    assert first == second
    assert confirm_fiscal_monetary_snapshot(first).snapshot is first
    for hidden in (
        "confirmed_at",
        "created_at",
        "user_id",
        "currency",
        "posting_state",
        "account_id",
        "account_code",
    ):
        assert not hasattr(first, hidden)
