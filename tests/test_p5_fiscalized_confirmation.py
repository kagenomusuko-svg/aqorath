"""Phase 5Y.1 — fiscalized informed confirmation contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _resolved_fiscalized(monkeypatch, *, fact_amount="100.00", fiscal_amount="16.00", basis="net_before_fiscal", adjustment_role="cash"):
    from datetime import date

    import aqorath.catalog as catalog
    from aqorath.economic_fact_accounting_provenance import resolve_economic_fact_with_provenance
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition
    from aqorath.fiscal_monetary_confirmation import ConfirmedFiscalMonetaryAmount, FiscalMonetaryConfirmationSnapshot
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    fact = EconomicFact("sale", Decimal(fact_amount), "cash")
    accounting = resolve_economic_fact_with_provenance(fact)
    snapshot = FiscalMonetaryConfirmationSnapshot(
        fact_type="sale",
        fact_amount=Decimal(fact_amount),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal("0.16"),
        unit="rate",
        rule_effective_from=date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref="TEST:RULE",
        exact_amount=Decimal(fiscal_amount),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="TEST:ROUNDING",
        rounded_amount=Decimal(fiscal_amount),
    )
    confirmed = ConfirmedFiscalMonetaryAmount(snapshot)
    treatment = declare_fiscal_accounting_treatment(confirmed, "tax_payable", "credit")
    effect = build_fiscal_accounting_effect(treatment)
    declaration = declare_fiscal_economic_composition(accounting, effect, basis, adjustment_role)
    fiscalized = compose_fiscal_economic_accounting(declaration)

    accounts = {
        "CASH": SimpleNamespace(id=1, code="CASH", name="Caja"),
        "SALES": SimpleNamespace(id=2, code="SALES", name="Ventas"),
        "TAX": SimpleNamespace(id=3, code="TAX", name="Impuestos por pagar"),
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])
    return resolve_fiscalized_proposal_accounts(
        object(),
        fiscalized,
        {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"},
    )


def test_fiscalized_confirmation_public_contract_and_exact_signatures_exist():
    import aqorath.fiscalized_confirmation as confirmation

    assert confirmation.__all__ == [
        "FiscalizedConfirmationLine",
        "FiscalizedConfirmationProvenance",
        "FiscalizedConfirmationSnapshot",
        "ConfirmedFiscalizedProposal",
        "create_fiscalized_confirmation_snapshot",
        "confirm_fiscalized_snapshot",
    ]
    create_sig = signature(confirmation.create_fiscalized_confirmation_snapshot)
    confirm_sig = signature(confirmation.confirm_fiscalized_snapshot)
    assert list(create_sig.parameters) == ["resolved_proposal"]
    assert list(confirm_sig.parameters) == ["snapshot"]
    for parameter in (*create_sig.parameters.values(), *confirm_sig.parameters.values()):
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_snapshot_copies_exact_concrete_lines_by_value_and_preserves_order(monkeypatch):
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationLine, create_fiscalized_confirmation_snapshot

    resolved = _resolved_fiscalized(monkeypatch)
    snapshot = create_fiscalized_confirmation_snapshot(resolved)

    assert isinstance(snapshot.lines, tuple)
    assert len(snapshot.lines) == 3
    assert tuple(
        (line.account_role, line.account_id, line.account_code, line.account_name, line.side, line.amount)
        for line in snapshot.lines
    ) == (
        ("cash", 1, "CASH", "Caja", "debit", Decimal("116.00")),
        ("sales_revenue", 2, "SALES", "Ventas", "credit", Decimal("100.00")),
        ("tax_payable", 3, "TAX", "Impuestos por pagar", "credit", Decimal("16.00")),
    )
    for source, copied in zip(resolved.lines, snapshot.lines):
        assert isinstance(copied, FiscalizedConfirmationLine)
        assert copied is not source


def test_snapshot_copies_full_fiscal_and_composition_provenance(monkeypatch):
    from datetime import date

    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(_resolved_fiscalized(monkeypatch))
    provenance = snapshot.provenance

    assert provenance.fact_type == "sale"
    assert provenance.fact_amount.as_tuple() == Decimal("100.00").as_tuple()
    assert provenance.payment_method == "cash"
    assert provenance.effective_date == date(2026, 8, 27)
    assert provenance.jurisdiction == "MX"
    assert provenance.regime == "general"
    assert provenance.entity_type == "comercial"
    assert provenance.rule_key == "iva.general_rate"
    assert provenance.base.as_tuple() == Decimal("100.00").as_tuple()
    assert provenance.rate.as_tuple() == Decimal("0.16").as_tuple()
    assert provenance.unit == "rate"
    assert provenance.rule_effective_from == date(2010, 1, 1)
    assert provenance.rule_effective_to is None
    assert provenance.rule_source_ref == "TEST:RULE"
    assert provenance.exact_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    assert provenance.rounding_policy_key == "two-decimals"
    assert provenance.rounding_quantizer.as_tuple() == Decimal("0.01").as_tuple()
    assert provenance.rounding_mode == "ROUND_HALF_UP"
    assert provenance.rounding_source_ref == "TEST:ROUNDING"
    assert provenance.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    assert provenance.amount_basis == "net_before_fiscal"
    assert provenance.adjustment_role == "cash"
    assert provenance.fiscal_role == "tax_payable"
    assert provenance.fiscal_side == "credit"


def test_snapshot_is_deeply_immutable_and_independent_from_forced_source_mutation(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    resolved = _resolved_fiscalized(monkeypatch)
    snapshot = create_fiscalized_confirmation_snapshot(resolved)
    original_first_amount = snapshot.lines[0].amount
    original_rule_key = snapshot.provenance.rule_key

    with pytest.raises(FrozenInstanceError):
        snapshot.explanation = "mutated"
    with pytest.raises(FrozenInstanceError):
        snapshot.lines[0].amount = Decimal("999.00")
    with pytest.raises(FrozenInstanceError):
        snapshot.provenance.rule_key = "other"
    with pytest.raises(TypeError):
        snapshot.lines[0] = snapshot.lines[1]

    object.__setattr__(resolved.lines[0], "amount", Decimal("999.00"))
    monetary_snapshot = (
        resolved.fiscalized_proposal.declaration.fiscal_effect.declaration.confirmed_monetary_amount.snapshot
    )
    object.__setattr__(monetary_snapshot, "rule_key", "poisoned")

    assert snapshot.lines[0].amount == original_first_amount
    assert snapshot.provenance.rule_key == original_rule_key


def test_snapshot_preserves_zero_fiscal_line_and_exact_decimal_scale(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(
        _resolved_fiscalized(monkeypatch, fiscal_amount="0.00")
    )
    assert len(snapshot.lines) == 3
    assert snapshot.lines[-1].amount.as_tuple() == Decimal("0.00").as_tuple()
    assert snapshot.provenance.exact_fiscal_amount.as_tuple() == Decimal("0.00").as_tuple()
    assert snapshot.provenance.rounded_fiscal_amount.as_tuple() == Decimal("0.00").as_tuple()


def test_gross_basis_snapshot_preserves_explicit_gross_provenance_and_final_lines(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(
        _resolved_fiscalized(
            monkeypatch,
            fact_amount="116.00",
            fiscal_amount="16.00",
            basis="gross_including_fiscal",
            adjustment_role="sales_revenue",
        )
    )
    assert snapshot.provenance.fact_amount.as_tuple() == Decimal("116.00").as_tuple()
    assert snapshot.provenance.amount_basis == "gross_including_fiscal"
    assert snapshot.provenance.adjustment_role == "sales_revenue"
    assert [line.amount for line in snapshot.lines] == [
        Decimal("116.00"),
        Decimal("100.00"),
        Decimal("16.00"),
    ]


def test_snapshot_requires_nominal_resolved_fiscalized_proposal_not_old_or_shape_input(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    resolved = _resolved_fiscalized(monkeypatch)
    fake = SimpleNamespace(
        fiscalized_proposal=resolved.fiscalized_proposal,
        lines=resolved.lines,
        explanation=resolved.explanation,
    )
    with pytest.raises(TypeError):
        create_fiscalized_confirmation_snapshot(fake)

    from aqorath.account_resolution import ResolvedAccountingProposal
    old = ResolvedAccountingProposal(lines=[], explanation="old")
    with pytest.raises(TypeError):
        create_fiscalized_confirmation_snapshot(old)


def test_confirmation_returns_exact_snapshot_identity_is_frozen_and_rejects_shape_input(monkeypatch):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        confirm_fiscalized_snapshot,
        create_fiscalized_confirmation_snapshot,
    )

    snapshot = create_fiscalized_confirmation_snapshot(_resolved_fiscalized(monkeypatch))
    confirmed = confirm_fiscalized_snapshot(snapshot)
    assert isinstance(confirmed, ConfirmedFiscalizedProposal)
    assert confirmed.snapshot is snapshot
    with pytest.raises(FrozenInstanceError):
        confirmed.snapshot = snapshot
    with pytest.raises(TypeError):
        confirm_fiscalized_snapshot(SimpleNamespace(lines=snapshot.lines, provenance=snapshot.provenance))


def test_snapshot_and_confirmation_never_reresolve_recalculate_reround_or_lookup_accounts(monkeypatch):
    import aqorath.catalog as catalog
    import aqorath.economic_facts as economic_facts
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.fiscal_rounding as fiscal_rounding
    import aqorath.fiscalized_account_resolution as resolution

    resolved = _resolved_fiscalized(monkeypatch)

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden recomputation during fiscalized confirmation")

    monkeypatch.setattr(catalog, "resolve_account_by_code", bomb)
    monkeypatch.setattr(economic_facts, "resolve_economic_fact", bomb)
    monkeypatch.setattr(fiscal_calculation, "calculate_fiscal_rate_amount", bomb)
    monkeypatch.setattr(fiscal_rounding, "round_confirmed_fiscal_amount", bomb)
    monkeypatch.setattr(resolution, "resolve_fiscalized_proposal_accounts", bomb)

    from aqorath.fiscalized_confirmation import confirm_fiscalized_snapshot, create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(resolved)
    confirmed = confirm_fiscalized_snapshot(snapshot)
    assert confirmed.snapshot is snapshot


def test_snapshot_and_confirmation_never_open_session_persist_or_post(monkeypatch):
    import aqorath.core as core
    import aqorath.posting as posting
    import aqorath.storage as storage

    resolved = _resolved_fiscalized(monkeypatch)

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden persistence during fiscalized confirmation")

    monkeypatch.setattr(core, "post_entry", bomb)
    monkeypatch.setattr(posting, "create_posting_instruction", bomb)
    monkeypatch.setattr(storage, "get_session", bomb)

    from aqorath.fiscalized_confirmation import confirm_fiscalized_snapshot, create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(resolved)
    confirmed = confirm_fiscalized_snapshot(snapshot)
    assert confirmed.snapshot is snapshot


def test_snapshot_is_balanced_and_fiscal_line_matches_provenance(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(_resolved_fiscalized(monkeypatch))
    total_debit = sum((line.amount for line in snapshot.lines if line.side == "debit"), Decimal("0"))
    total_credit = sum((line.amount for line in snapshot.lines if line.side == "credit"), Decimal("0"))
    assert total_debit == total_credit == Decimal("116.00")
    fiscal_line = snapshot.lines[-1]
    assert fiscal_line.account_role == snapshot.provenance.fiscal_role
    assert fiscal_line.side == snapshot.provenance.fiscal_side
    assert fiscal_line.amount.as_tuple() == snapshot.provenance.rounded_fiscal_amount.as_tuple()


def test_fiscalized_confirmation_is_deterministic_and_adds_no_posting_metadata(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    resolved = _resolved_fiscalized(monkeypatch)
    first = create_fiscalized_confirmation_snapshot(resolved)
    second = create_fiscalized_confirmation_snapshot(resolved)
    assert first == second
    assert first is not second
    assert first.lines[0] is not second.lines[0]
    assert first.provenance is not second.provenance
    for hidden in ("posting_instruction", "journal_entry_id", "entry_id", "posted_at", "posted_by"):
        assert not hasattr(first, hidden)
