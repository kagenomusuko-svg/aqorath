"""Phase 6BH.1 — frozen FiscalizedAccountingProposal balance-authority contracts.

FiscalizedAccountingProposal already owns structural fiscal composition validation and
computes exact debit/credit totals from its semantic lines. 6AQ established
ledger_signed_balance() as the authoritative algebraic balance function, and 6BB already
converged AccountingProposal onto it. This phase freezes the same convergence here only:
existing totals must be interpreted through ledger_signed_balance(...) == Decimal("0").
No fiscal recalculation, line construction changes, account resolution, confirmation,
persistence, posting, reporting, Journal authority, or Application behavior is added.
"""

from dataclasses import fields
from datetime import date
from decimal import Decimal
import inspect

import pytest


def _declaration(
    *,
    fact_amount="100.00",
    fiscal_amount="16.00",
    basis="net_before_fiscal",
    adjustment_role="cash",
    fiscal_role="tax_payable",
    fiscal_side="credit",
):
    from aqorath.economic_fact_accounting_provenance import (
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition
    from aqorath.fiscal_monetary_confirmation import (
        ConfirmedFiscalMonetaryAmount,
        FiscalMonetaryConfirmationSnapshot,
    )

    fact = EconomicFact("sale", Decimal(fact_amount), "cash")
    accounting = resolve_economic_fact_with_provenance(fact)
    snapshot = FiscalMonetaryConfirmationSnapshot(
        fact_type="sale",
        fact_amount=Decimal(fact_amount),
        payment_method="cash",
        effective_date=date(2026, 8, 28),
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
    treatment = declare_fiscal_accounting_treatment(
        confirmed,
        fiscal_role,
        fiscal_side,
    )
    effect = build_fiscal_accounting_effect(treatment)
    return declare_fiscal_economic_composition(
        accounting,
        effect,
        basis,
        adjustment_role,
    )


def _compose(**kwargs):
    from aqorath.fiscalized_accounting_proposal import (
        compose_fiscal_economic_accounting,
    )

    return compose_fiscal_economic_accounting(_declaration(**kwargs))


def test_fiscalized_proposal_public_shape_remains_declaration_lines_explanation_only():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    assert tuple(field.name for field in fields(FiscalizedAccountingProposal)) == (
        "declaration",
        "lines",
        "explanation",
    )
    assert tuple(inspect.signature(FiscalizedAccountingProposal).parameters) == (
        "declaration",
        "lines",
        "explanation",
    )


def test_existing_net_before_fiscal_balanced_proposal_remains_valid():
    proposal = _compose()

    assert tuple((line.side, line.amount) for line in proposal.lines) == (
        ("debit", Decimal("116.00")),
        ("credit", Decimal("100.00")),
        ("credit", Decimal("16.00")),
    )


def test_existing_gross_including_fiscal_balanced_proposal_remains_valid():
    proposal = _compose(
        fact_amount="116.00",
        basis="gross_including_fiscal",
        adjustment_role="sales_revenue",
    )

    assert tuple((line.side, line.amount) for line in proposal.lines) == (
        ("debit", Decimal("116.00")),
        ("credit", Decimal("100.00")),
        ("credit", Decimal("16.00")),
    )


def test_balance_validation_delegates_exact_totals_to_ledger_signed_balance(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(domain, "ledger_signed_balance", fake)

    _compose()

    assert calls == [(Decimal("116.00"), Decimal("116.00"))]


def test_zero_fiscal_effect_delegates_exact_unchanged_totals(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    calls = []
    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: calls.append(
            (debit_total, credit_total)
        ) or Decimal("0"),
    )

    _compose(fiscal_amount="0.00")

    assert calls == [(Decimal("100.00"), Decimal("100.00"))]


def test_balance_authority_is_called_exactly_once(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(domain, "ledger_signed_balance", fake)
    _compose()

    assert len(calls) == 1


def test_authoritative_positive_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0.0001"),
    )

    with pytest.raises(ValueError):
        _compose()


def test_authoritative_negative_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("-0.0001"),
    )

    with pytest.raises(ValueError):
        _compose()


def test_arbitrarily_small_nonzero_authoritative_balance_is_not_tolerated(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal(
            "0.0000000000000000000000000001"
        ),
    )

    with pytest.raises(ValueError):
        _compose()


def test_convergence_uses_exact_zero_without_direct_total_comparison():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    source = inspect.getsource(FiscalizedAccountingProposal.__post_init__).lower()

    assert "ledger_signed_balance" in source
    assert "decimal(\"0\")" in source
    assert "total_debit != total_credit" not in source


def test_balance_validation_does_not_use_normal_balance_or_account_nature():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    source = inspect.getsource(FiscalizedAccountingProposal.__post_init__).lower()
    for forbidden in (
        "normal_balance_amount",
        "normal_balance_for_account",
        "journal_line_normal_balance",
        ".nature",
        "account_type",
        "subtype",
    ):
        assert forbidden not in source


def test_balance_validation_does_not_route_through_journal_authorities():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    source = inspect.getsource(FiscalizedAccountingProposal.__post_init__).lower()
    for forbidden in (
        "journal_line_totals",
        "journal_line_signed_balance",
        "journal_lines_signed_balance",
        "journal_lines_are_balanced",
        "journal_entry_totals",
        "journal_entry_signed_balance",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source


def test_structural_fiscal_composition_validation_remains_independent_of_balance(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    baseline = _compose()
    declaration = baseline.declaration
    first = baseline.lines[0]
    forged_first = domain.FiscalizedProposalLine(
        account_role=first.account_role,
        side=first.side,
        amount=first.amount + Decimal("1.00"),
    )
    forged_lines = (forged_first,) + baseline.lines[1:]

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    with pytest.raises(ValueError):
        domain.FiscalizedAccountingProposal(
            declaration=declaration,
            lines=forged_lines,
            explanation=baseline.explanation,
        )


def test_explanation_validation_remains_independent_of_balance_authority(monkeypatch):
    import aqorath.fiscalized_accounting_proposal as domain

    baseline = _compose()
    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    with pytest.raises(ValueError):
        domain.FiscalizedAccountingProposal(
            declaration=baseline.declaration,
            lines=baseline.lines,
            explanation="forged explanation",
        )


def test_convergence_preserves_exact_decimal_semantics_without_tolerance_or_coercion():
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    source = inspect.getsource(FiscalizedAccountingProposal.__post_init__).lower()
    for forbidden in (
        "abs(",
        "isclose",
        "tolerance",
        "quantize",
        "round(",
        "float(",
    ):
        assert forbidden not in source


def test_convergence_does_not_add_resolution_confirmation_persistence_posting_reporting_or_application():
    import aqorath.fiscalized_accounting_proposal as domain
    from aqorath.fiscalized_accounting_proposal import FiscalizedAccountingProposal

    method_source = inspect.getsource(FiscalizedAccountingProposal.__post_init__).lower()
    module_source = inspect.getsource(domain).lower()

    for forbidden in (
        "resolve_account",
        "account_bindings",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "confirm(",
    ):
        assert forbidden not in method_source

    assert "aqorath.application" not in module_source
