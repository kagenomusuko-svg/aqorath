"""Phase 5W.1 — fiscalized accounting proposal composition contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _declaration(*, fact_amount="100.00", fiscal_amount="16.00", basis="net_before_fiscal", adjustment_role="cash", fiscal_role="tax_payable", fiscal_side="credit"):
    from datetime import date

    from aqorath.economic_fact_accounting_provenance import resolve_economic_fact_with_provenance
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition
    from aqorath.fiscal_monetary_confirmation import ConfirmedFiscalMonetaryAmount, FiscalMonetaryConfirmationSnapshot

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
    treatment = declare_fiscal_accounting_treatment(confirmed, fiscal_role, fiscal_side)
    effect = build_fiscal_accounting_effect(treatment)
    return declare_fiscal_economic_composition(accounting, effect, basis, adjustment_role)


def test_fiscalized_accounting_proposal_public_contract_and_exact_signature_exist():
    import aqorath.fiscalized_accounting_proposal as fiscalized

    assert fiscalized.__all__ == [
        "FiscalizedProposalLine",
        "FiscalizedAccountingProposal",
        "compose_fiscal_economic_accounting",
    ]
    sig = signature(fiscalized.compose_fiscal_economic_accounting)
    assert list(sig.parameters) == ["declaration"]
    parameter = sig.parameters["declaration"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_net_before_fiscal_composes_exact_balanced_three_line_sale():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration()
    proposal = compose_fiscal_economic_accounting(declaration)

    assert proposal.declaration is declaration
    assert tuple((line.account_role, line.side, line.amount) for line in proposal.lines) == (
        ("cash", "debit", Decimal("116.00")),
        ("sales_revenue", "credit", Decimal("100.00")),
        ("tax_payable", "credit", Decimal("16.00")),
    )


def test_gross_including_fiscal_composes_same_final_truth_by_reducing_declared_role():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration(
        fact_amount="116.00",
        basis="gross_including_fiscal",
        adjustment_role="sales_revenue",
    )
    proposal = compose_fiscal_economic_accounting(declaration)

    assert tuple((line.account_role, line.side, line.amount) for line in proposal.lines) == (
        ("cash", "debit", Decimal("116.00")),
        ("sales_revenue", "credit", Decimal("100.00")),
        ("tax_payable", "credit", Decimal("16.00")),
    )


def test_composition_changes_only_declared_adjustment_role_and_appends_exact_fiscal_line():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration()
    source = declaration.accounting_resolution.proposal
    proposal = compose_fiscal_economic_accounting(declaration)

    assert len(proposal.lines) == len(source.lines) + 1
    assert proposal.lines[0].amount == source.lines[0].amount + Decimal("16.00")
    assert proposal.lines[1].account_role == source.lines[1].account_role
    assert proposal.lines[1].side == source.lines[1].side
    assert proposal.lines[1].amount.as_tuple() == source.lines[1].amount.as_tuple()
    assert proposal.lines[-1].account_role == declaration.fiscal_effect.line.account_role
    assert proposal.lines[-1].side == declaration.fiscal_effect.line.side
    assert proposal.lines[-1].amount.as_tuple() == declaration.fiscal_effect.line.amount.as_tuple()


def test_composition_preserves_original_order_and_copies_every_line_by_value():
    from aqorath.economic_facts import ProposalLine
    from aqorath.fiscalized_accounting_proposal import FiscalizedProposalLine, compose_fiscal_economic_accounting

    declaration = _declaration()
    source_lines = declaration.accounting_resolution.proposal.lines
    proposal = compose_fiscal_economic_accounting(declaration)

    assert isinstance(proposal.lines, tuple)
    for index, source in enumerate(source_lines):
        result = proposal.lines[index]
        assert isinstance(result, FiscalizedProposalLine)
        assert not isinstance(result, ProposalLine)
        assert result is not source
        assert result.account_role == source.account_role
        assert result.side == source.side
    assert proposal.lines[-1] is not declaration.fiscal_effect.line


def test_composition_is_deeply_immutable_decimal_exact_and_balanced_without_float_conversion():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    proposal = compose_fiscal_economic_accounting(_declaration())
    assert all(isinstance(line.amount, Decimal) for line in proposal.lines)
    total_debit = sum((line.amount for line in proposal.lines if line.side == "debit"), Decimal("0"))
    total_credit = sum((line.amount for line in proposal.lines if line.side == "credit"), Decimal("0"))
    assert total_debit == total_credit == Decimal("116.00")

    with pytest.raises(FrozenInstanceError):
        proposal.explanation = "mutated"
    with pytest.raises(FrozenInstanceError):
        proposal.lines[0].amount = Decimal("999.00")
    with pytest.raises(TypeError):
        proposal.lines[0] = proposal.lines[1]


def test_composition_requires_nominal_phase_5v_declaration():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration()
    fake = SimpleNamespace(
        accounting_resolution=declaration.accounting_resolution,
        fiscal_effect=declaration.fiscal_effect,
        amount_basis=declaration.amount_basis,
        adjustment_role=declaration.adjustment_role,
    )
    with pytest.raises(TypeError):
        compose_fiscal_economic_accounting(fake)


def test_gross_composition_fails_closed_if_fiscal_amount_consumes_or_exceeds_adjusted_line():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    for fiscal_amount in ("100.00", "101.00"):
        declaration = _declaration(
            fact_amount="100.00",
            fiscal_amount=fiscal_amount,
            basis="gross_including_fiscal",
            adjustment_role="sales_revenue",
        )
        with pytest.raises(ValueError):
            compose_fiscal_economic_accounting(declaration)


def test_zero_fiscal_effect_is_preserved_as_explicit_zero_line_and_never_silently_dropped():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration(fiscal_amount="0.00")
    proposal = compose_fiscal_economic_accounting(declaration)

    assert len(proposal.lines) == 3
    assert proposal.lines[0].amount == Decimal("100.00")
    assert proposal.lines[-1].account_role == "tax_payable"
    assert proposal.lines[-1].side == "credit"
    assert proposal.lines[-1].amount.as_tuple() == Decimal("0.00").as_tuple()
    assert sum((line.amount for line in proposal.lines if line.side == "debit"), Decimal("0")) == sum(
        (line.amount for line in proposal.lines if line.side == "credit"), Decimal("0")
    )


def test_composition_explanation_is_deterministic_and_reports_only_explicit_composition_choices():
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    declaration = _declaration(fiscal_role="manual_fiscal_role")
    first = compose_fiscal_economic_accounting(declaration)
    second = compose_fiscal_economic_accounting(declaration)

    assert first == second
    assert first.explanation == (
        "Fiscalized accounting composition: amount_basis=net_before_fiscal; "
        "adjustment_role=cash; fiscal_role=manual_fiscal_role; "
        "fiscal_side=credit; fiscal_amount=16.00."
    )
    assert "IVA" not in first.explanation
    assert "iva" not in first.explanation


def test_public_result_types_fail_closed_on_inconsistent_direct_construction():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal, FiscalizedProposalLine

    declaration = _declaration()
    with pytest.raises(ValueError):
        FiscalizedProposalLine("cash", "debit", Decimal("-1.00"))
    with pytest.raises(ValueError):
        FiscalizedAccountingProposal(
            declaration=declaration,
            lines=(
                FiscalizedProposalLine("cash", "debit", Decimal("100.00")),
                FiscalizedProposalLine("sales_revenue", "credit", Decimal("100.00")),
                FiscalizedProposalLine("tax_payable", "credit", Decimal("16.00")),
            ),
            explanation="forged",
        )


def test_composition_is_pure_does_not_mutate_and_never_resolves_accounts_confirms_or_posts(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.confirmation as confirmation
    import aqorath.posting as posting
    import aqorath.storage as storage

    declaration = _declaration()
    source_before = tuple(
        (line.account_role, line.side, line.amount)
        for line in declaration.accounting_resolution.proposal.lines
    )

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden downstream authority called by fiscal composition")

    monkeypatch.setattr(account_resolution, "resolve_proposal_accounts", bomb)
    monkeypatch.setattr(confirmation, "create_confirmation_snapshot", bomb)
    monkeypatch.setattr(posting, "create_posting_instruction", bomb)
    monkeypatch.setattr(storage, "get_session", bomb)

    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    proposal = compose_fiscal_economic_accounting(declaration)
    assert proposal.declaration is declaration
    assert source_before == tuple(
        (line.account_role, line.side, line.amount)
        for line in declaration.accounting_resolution.proposal.lines
    )
    for hidden in ("account_id", "account_code", "posting_instruction", "journal_entry_id"):
        assert not hasattr(proposal, hidden)
