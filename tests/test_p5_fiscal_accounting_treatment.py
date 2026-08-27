"""Phase 5R.1 — explicit fiscal accounting treatment declaration contracts."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _confirmed_money():
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_confirmation import (
        confirm_fiscal_snapshot,
        create_fiscal_confirmation_snapshot,
    )
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_monetary_confirmation import (
        confirm_fiscal_monetary_snapshot,
        create_fiscal_monetary_confirmation_snapshot,
    )
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
        value=Decimal("0.16"),
        unit="rate",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        source_ref="TEST:RULE",
    )
    calculation = FiscalRateCalculation(
        base=Decimal("100.00"),
        amount=Decimal("16.0000"),
        rule=rule,
    )
    declared = DeclaredFiscalRateCalculation(declaration, calculation)
    fiscal_snapshot = create_fiscal_confirmation_snapshot(declared)
    fiscal_confirmed = confirm_fiscal_snapshot(fiscal_snapshot)
    policy = FiscalRoundingPolicy(
        "two-decimals",
        Decimal("0.01"),
        ROUND_HALF_UP,
        "TEST:ROUNDING",
    )
    rounded = round_confirmed_fiscal_amount(fiscal_confirmed, policy)
    monetary_snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)
    return confirm_fiscal_monetary_snapshot(monetary_snapshot)


def test_fiscal_accounting_treatment_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_accounting_treatment as treatment

    assert treatment.__all__ == [
        "FiscalAccountingTreatmentDeclaration",
        "declare_fiscal_accounting_treatment",
    ]
    sig = signature(treatment.declare_fiscal_accounting_treatment)
    assert list(sig.parameters) == [
        "confirmed_monetary_amount",
        "account_role",
        "side",
    ]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_declaration_is_frozen_and_preserves_exact_monetary_identity_role_and_side():
    from aqorath.fiscal_accounting_treatment import (
        FiscalAccountingTreatmentDeclaration,
        declare_fiscal_accounting_treatment,
    )

    confirmed = _confirmed_money()
    declaration = declare_fiscal_accounting_treatment(
        confirmed,
        "tax_payable",
        "credit",
    )

    assert isinstance(declaration, FiscalAccountingTreatmentDeclaration)
    assert declaration.confirmed_monetary_amount is confirmed
    assert declaration.account_role == "tax_payable"
    assert declaration.side == "credit"
    assert declaration.confirmed_monetary_amount.snapshot.rounded_amount == Decimal("16.00")
    with pytest.raises(FrozenInstanceError):
        declaration.side = "debit"


def test_account_role_and_side_are_explicit_and_never_inferred_from_iva_sale_or_catalog():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment

    confirmed = _confirmed_money()
    custom_debit = declare_fiscal_accounting_treatment(
        confirmed,
        "custom_fiscal_role",
        "debit",
    )
    custom_credit = declare_fiscal_accounting_treatment(
        confirmed,
        "another_role",
        "credit",
    )

    assert custom_debit.account_role == "custom_fiscal_role"
    assert custom_debit.side == "debit"
    assert custom_credit.account_role == "another_role"
    assert custom_credit.side == "credit"
    assert not hasattr(custom_debit, "account_code")
    assert not hasattr(custom_debit, "account_id")


def test_public_type_enforces_same_nominal_and_field_invariants_when_constructed_directly():
    from aqorath.fiscal_accounting_treatment import FiscalAccountingTreatmentDeclaration

    confirmed = _confirmed_money()
    direct = FiscalAccountingTreatmentDeclaration(confirmed, "tax_payable", "credit")
    assert direct.confirmed_monetary_amount is confirmed

    with pytest.raises(TypeError):
        FiscalAccountingTreatmentDeclaration(
            SimpleNamespace(snapshot=confirmed.snapshot),
            "tax_payable",
            "credit",
        )
    for bad_role in ("", "   ", None, 123):
        with pytest.raises((TypeError, ValueError)):
            FiscalAccountingTreatmentDeclaration(confirmed, bad_role, "credit")
    for bad_side in ("", "charge", None, 123):
        with pytest.raises((TypeError, ValueError)):
            FiscalAccountingTreatmentDeclaration(confirmed, "tax_payable", bad_side)


def test_factory_requires_nominal_confirmed_fiscal_monetary_amount_not_shape_or_prior_stage():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment

    confirmed = _confirmed_money()
    fake = SimpleNamespace(snapshot=confirmed.snapshot)

    with pytest.raises(TypeError):
        declare_fiscal_accounting_treatment(fake, "tax_payable", "credit")
    with pytest.raises(TypeError):
        declare_fiscal_accounting_treatment(
            confirmed.snapshot,
            "tax_payable",
            "credit",
        )


def test_declaration_does_not_duplicate_or_transform_confirmed_monetary_truth():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment

    confirmed = _confirmed_money()
    declaration = declare_fiscal_accounting_treatment(confirmed, "tax_payable", "credit")

    assert declaration.confirmed_monetary_amount is confirmed
    assert confirmed.snapshot.exact_amount == Decimal("16.0000")
    assert confirmed.snapshot.rounded_amount == Decimal("16.00")
    for duplicated in (
        "amount",
        "exact_amount",
        "rounded_amount",
        "rule_key",
        "rate",
        "source_ref",
    ):
        assert not hasattr(declaration, duplicated)


def test_declaration_is_not_balanced_proposal_resolved_line_or_posting_instruction():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.posting import PostingInstruction, PostingLine

    declaration = declare_fiscal_accounting_treatment(
        _confirmed_money(),
        "tax_payable",
        "credit",
    )

    assert not isinstance(declaration, AccountingProposal)
    assert not isinstance(declaration, ProposalLine)
    assert not isinstance(declaration, PostingInstruction)
    assert not isinstance(declaration, PostingLine)
    assert not hasattr(declaration, "lines")
    assert not hasattr(declaration, "debit")
    assert not hasattr(declaration, "credit")


def test_declaration_is_pure_and_never_resolves_accounts_recalculates_rounds_posts_or_opens_session(monkeypatch):
    import aqorath.account_bindings as bindings
    import aqorath.account_resolution as resolution
    import aqorath.catalog as catalog
    import aqorath.economic_facts as economic_facts
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscal_runtime as fiscal_runtime
    import aqorath.posting as posting
    import aqorath.storage as storage

    confirmed = _confirmed_money()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscal accounting treatment")

    with monkeypatch.context() as m:
        m.setattr(bindings, "get_account_binding", bomb)
        m.setattr(resolution, "resolve_proposal_accounts", bomb)
        m.setattr(catalog, "resolve_account_by_code", bomb)
        m.setattr(economic_facts, "resolve_economic_fact", bomb)
        m.setattr(rounding, "round_confirmed_fiscal_amount", bomb)
        m.setattr(fiscal_runtime, "calculate_fiscal_rate_for_date", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(storage, "get_session", bomb)

        import aqorath.fiscal_accounting_treatment as treatment

        treatment = reload(treatment)
        result = treatment.declare_fiscal_accounting_treatment(
            confirmed,
            "tax_payable",
            "credit",
        )
        assert result.confirmed_monetary_amount is confirmed

    reload(treatment)


def test_declaration_is_deterministic_does_not_mutate_input_and_adds_no_hidden_accounting_defaults():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment

    confirmed = _confirmed_money()
    snapshot = confirmed.snapshot
    first = declare_fiscal_accounting_treatment(confirmed, "tax_payable", "credit")
    second = declare_fiscal_accounting_treatment(confirmed, "tax_payable", "credit")

    assert first == second
    assert first.confirmed_monetary_amount is second.confirmed_monetary_amount is confirmed
    assert confirmed.snapshot is snapshot
    for hidden in (
        "account_code",
        "account_id",
        "counterpart_role",
        "gross_amount",
        "net_amount",
        "posting_state",
        "created_at",
    ):
        assert not hasattr(first, hidden)


def test_sale_and_iva_do_not_automatically_choose_tax_payable_or_credit():
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment

    confirmed = _confirmed_money()
    debit = declare_fiscal_accounting_treatment(confirmed, "manual_role", "debit")

    assert confirmed.snapshot.fact_type == "sale"
    assert confirmed.snapshot.rule_key == "test.rate"
    assert debit.account_role == "manual_role"
    assert debit.side == "debit"
