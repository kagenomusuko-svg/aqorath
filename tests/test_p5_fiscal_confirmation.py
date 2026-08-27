"""Phase 5L.1 — fiscal confirmation snapshot contracts.

The user must be able to confirm exactly the fiscal truth already declared and
calculated. This boundary freezes that truth by value before any accounting,
persistence, rounding policy, or posting can consume it.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _context():
    from aqorath.fiscal_rules import FiscalContext

    return FiscalContext("MX", "general", "comercial")


def _declared(
    *,
    fact_amount="250.00",
    base="250.00",
    rate="0.16",
    calculated_amount="40.0000",
    effective_date=date(2026, 8, 27),
    rule_effective_from=date(2010, 1, 1),
    rule_effective_to=None,
    rule_key="iva.general_rate",
    source_ref="DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1",
):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_rules import ResolvedFiscalRule

    fact = EconomicFact(
        type="sale",
        amount=Decimal(fact_amount),
        payment_method="cash",
    )
    context = _context()
    declaration = declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        rule_key,
        Decimal(base),
    )
    rule = ResolvedFiscalRule(
        rule_key=rule_key,
        value=Decimal(rate),
        unit="rate",
        effective_from=rule_effective_from,
        effective_to=rule_effective_to,
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        source_ref=source_ref,
    )
    calculation = FiscalRateCalculation(
        base=declaration.base,
        amount=Decimal(calculated_amount),
        rule=rule,
    )
    return DeclaredFiscalRateCalculation(
        declaration=declaration,
        calculation=calculation,
    )


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'fiscal-confirmation.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_fiscal_confirmation_public_contract_and_exact_signatures_exist():
    import aqorath.fiscal_confirmation as confirmation

    assert confirmation.__all__ == [
        "FiscalConfirmationSnapshot",
        "ConfirmedFiscalTreatment",
        "create_fiscal_confirmation_snapshot",
        "confirm_fiscal_snapshot",
    ]

    create_sig = signature(confirmation.create_fiscal_confirmation_snapshot)
    assert list(create_sig.parameters) == ["declared_calculation"]
    parameter = create_sig.parameters["declared_calculation"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty

    confirm_sig = signature(confirmation.confirm_fiscal_snapshot)
    assert list(confirm_sig.parameters) == ["snapshot"]
    parameter = confirm_sig.parameters["snapshot"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_snapshot_copies_exact_declared_calculated_truth_and_provenance():
    from aqorath.fiscal_confirmation import (
        FiscalConfirmationSnapshot,
        create_fiscal_confirmation_snapshot,
    )

    declared = _declared(rule_effective_to=date(2030, 12, 31))
    snapshot = create_fiscal_confirmation_snapshot(declared)

    assert isinstance(snapshot, FiscalConfirmationSnapshot)
    assert snapshot.fact_type == "sale"
    assert snapshot.fact_amount == Decimal("250.00")
    assert snapshot.payment_method == "cash"
    assert snapshot.effective_date == date(2026, 8, 27)
    assert snapshot.jurisdiction == "MX"
    assert snapshot.regime == "general"
    assert snapshot.entity_type == "comercial"
    assert snapshot.rule_key == "iva.general_rate"
    assert snapshot.base == Decimal("250.00")
    assert snapshot.rate == Decimal("0.16")
    assert snapshot.unit == "rate"
    assert snapshot.rule_effective_from == date(2010, 1, 1)
    assert snapshot.rule_effective_to == date(2030, 12, 31)
    assert snapshot.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    assert snapshot.calculated_amount == Decimal("40.0000")


def test_snapshot_is_deeply_immutable_and_contains_only_value_truth_not_live_source_objects():
    from aqorath.fiscal_confirmation import create_fiscal_confirmation_snapshot

    snapshot = create_fiscal_confirmation_snapshot(_declared())

    with pytest.raises(FrozenInstanceError):
        snapshot.rule_key = "other.rule"
    with pytest.raises(FrozenInstanceError):
        snapshot.calculated_amount = Decimal("999")

    for forbidden_reference in (
        "fact",
        "context",
        "declaration",
        "calculation",
        "rule",
        "declared_calculation",
    ):
        assert not hasattr(snapshot, forbidden_reference)


def test_snapshot_is_independent_from_forced_source_mutation_after_creation():
    from aqorath.fiscal_confirmation import create_fiscal_confirmation_snapshot

    declared = _declared()
    snapshot = create_fiscal_confirmation_snapshot(declared)

    object.__setattr__(declared.declaration.fact, "type", "utility_expense")
    object.__setattr__(declared.declaration.fact, "amount", Decimal("999.00"))
    object.__setattr__(declared.declaration.context, "regime", "resico")
    object.__setattr__(declared.declaration, "rule_key", "mutated.rule")
    object.__setattr__(declared.declaration, "base", Decimal("1.00"))
    object.__setattr__(declared.calculation.rule, "value", Decimal("0.99"))
    object.__setattr__(declared.calculation.rule, "source_ref", "MUTATED")
    object.__setattr__(declared.calculation, "amount", Decimal("999.00"))

    assert snapshot.fact_type == "sale"
    assert snapshot.fact_amount == Decimal("250.00")
    assert snapshot.regime == "general"
    assert snapshot.rule_key == "iva.general_rate"
    assert snapshot.base == Decimal("250.00")
    assert snapshot.rate == Decimal("0.16")
    assert snapshot.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    assert snapshot.calculated_amount == Decimal("40.0000")


def test_snapshot_preserves_decimal_precision_and_open_ended_rule_without_rounding():
    from aqorath.fiscal_confirmation import create_fiscal_confirmation_snapshot

    declared = _declared(
        fact_amount="7.123456789",
        base="7.123456789",
        rate="0.123456789",
        calculated_amount="0.876543210987654321",
        rule_effective_to=None,
        rule_key="future.precise.rate",
        source_ref="SOURCE:PRECISE",
    )
    snapshot = create_fiscal_confirmation_snapshot(declared)

    assert str(snapshot.fact_amount) == "7.123456789"
    assert str(snapshot.base) == "7.123456789"
    assert str(snapshot.rate) == "0.123456789"
    assert str(snapshot.calculated_amount) == "0.876543210987654321"
    assert snapshot.rule_effective_to is None
    assert snapshot.source_ref == "SOURCE:PRECISE"


def test_snapshot_requires_nominal_declared_calculation_pipeline():
    from aqorath.fiscal_confirmation import create_fiscal_confirmation_snapshot

    declared = _declared()
    fake = SimpleNamespace(
        declaration=declared.declaration,
        calculation=declared.calculation,
    )

    with pytest.raises(TypeError):
        create_fiscal_confirmation_snapshot(fake)
    with pytest.raises(TypeError):
        create_fiscal_confirmation_snapshot(declared.declaration)
    with pytest.raises(TypeError):
        create_fiscal_confirmation_snapshot(declared.calculation)


def test_confirmation_returns_exact_snapshot_identity_is_frozen_and_rejects_shape_compatible_input():
    from aqorath.fiscal_confirmation import (
        ConfirmedFiscalTreatment,
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )

    snapshot = create_fiscal_confirmation_snapshot(_declared())
    confirmed = confirm_fiscal_snapshot(snapshot)

    assert isinstance(confirmed, ConfirmedFiscalTreatment)
    assert confirmed.snapshot is snapshot
    with pytest.raises(FrozenInstanceError):
        confirmed.snapshot = snapshot

    fake_snapshot = SimpleNamespace(**snapshot.__dict__)
    with pytest.raises(TypeError):
        confirm_fiscal_snapshot(fake_snapshot)
    with pytest.raises(TypeError):
        confirm_fiscal_snapshot(_declared())


def test_confirmation_never_redeclares_reresolves_recalculates_or_calls_legacy_tax(monkeypatch):
    import aqorath.fiscal_applicability as applicability
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_declaration_runtime as declaration_runtime
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.tax as legacy_tax

    declared = _declared()

    def bomb(*args, **kwargs):
        raise AssertionError("fiscal confirmation must not recompute fiscal truth")

    with monkeypatch.context() as m:
        m.setattr(applicability, "declare_fiscal_rate_applicability", bomb)
        m.setattr(calculation, "calculate_fiscal_rate_amount", bomb)
        m.setattr(declaration_runtime, "calculate_declared_fiscal_rate", bomb)
        m.setattr(fiscal_rules, "resolve_fiscal_rule", bomb)
        m.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", bomb)
        m.setattr(legacy_tax, "calculate_taxes", bomb)

        import aqorath.fiscal_confirmation as confirmation

        confirmation = reload(confirmation)
        snapshot = confirmation.create_fiscal_confirmation_snapshot(declared)
        confirmed = confirmation.confirm_fiscal_snapshot(snapshot)
        assert confirmed.snapshot is snapshot

    reload(confirmation)


def test_confirmation_never_opens_session_installs_selects_accounts_persists_or_posts(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.fiscal_rule_install as installer
    import aqorath.posting as posting
    import aqorath.storage as storage

    declared = _declared()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscal confirmation")

    with monkeypatch.context() as m:
        m.setattr(storage, "get_session", bomb)
        m.setattr(installer, "install_fiscal_rule_set", bomb)
        m.setattr(core, "post_entry", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(account_resolution, "resolve_proposal_accounts", bomb)
        m.setattr(catalog, "resolve_account_by_code", bomb)
        m.setattr(catalog, "create_entity_account", bomb)

        import aqorath.fiscal_confirmation as confirmation

        confirmation = reload(confirmation)
        snapshot = confirmation.create_fiscal_confirmation_snapshot(declared)
        confirmed = confirmation.confirm_fiscal_snapshot(snapshot)
        assert confirmed.snapshot is snapshot

    reload(confirmation)


def test_real_curated_iva_declared_calculation_becomes_exact_confirmation_snapshot(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_confirmation import (
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )
    from aqorath.fiscal_declaration_runtime import calculate_declared_fiscal_rate
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = EconomicFact("sale", Decimal("250.00"), "cash")
        declaration = declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            Decimal("250.00"),
        )
        declared = calculate_declared_fiscal_rate(session, declaration)

        snapshot = create_fiscal_confirmation_snapshot(declared)
        confirmed = confirm_fiscal_snapshot(snapshot)

        assert confirmed.snapshot is snapshot
        assert snapshot.fact_type == "sale"
        assert snapshot.fact_amount == Decimal("250.00")
        assert snapshot.rule_key == "iva.general_rate"
        assert snapshot.base == Decimal("250.00")
        assert snapshot.rate == Decimal("0.16")
        assert snapshot.calculated_amount == Decimal("40.0000")
        assert snapshot.rule_effective_from == date(2010, 1, 1)
        assert snapshot.rule_effective_to is None
        assert snapshot.source_ref == "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"
    finally:
        session.close()
        engine.dispose()


def test_fiscal_confirmation_is_deterministic_and_adds_no_hidden_confirmation_metadata():
    from aqorath.fiscal_confirmation import (
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )

    declared = _declared()
    first = create_fiscal_confirmation_snapshot(declared)
    second = create_fiscal_confirmation_snapshot(declared)

    assert first == second
    assert confirm_fiscal_snapshot(first).snapshot is first
    for hidden in (
        "confirmed_at",
        "confirmed_by",
        "confirmation_id",
        "hash",
        "signature",
    ):
        assert not hasattr(first, hidden)
