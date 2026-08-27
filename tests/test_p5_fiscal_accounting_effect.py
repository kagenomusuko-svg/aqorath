"""Phase 5S.1 — fiscal accounting effect contracts."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _declaration(amount="16.00", role="tax_payable", side="credit"):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_applicability import declare_fiscal_rate_applicability
    from aqorath.fiscal_calculation import FiscalRateCalculation
    from aqorath.fiscal_confirmation import confirm_fiscal_snapshot, create_fiscal_confirmation_snapshot
    from aqorath.fiscal_declaration_runtime import DeclaredFiscalRateCalculation
    from aqorath.fiscal_monetary_confirmation import (
        confirm_fiscal_monetary_snapshot,
        create_fiscal_monetary_confirmation_snapshot,
    )
    from aqorath.fiscal_rounding import FiscalRoundingPolicy, round_confirmed_fiscal_amount
    from aqorath.fiscal_rules import FiscalContext, ResolvedFiscalRule

    fact = EconomicFact("sale", Decimal("100.00"), "cash")
    context = FiscalContext("MX", "general", "comercial")
    applicability = declare_fiscal_rate_applicability(
        fact, date(2026, 8, 27), context, "test.rate", Decimal("100.00")
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
        base=Decimal("100.00"), amount=Decimal(amount), rule=rule
    )
    declared = DeclaredFiscalRateCalculation(applicability, calculation)
    fiscal_snapshot = create_fiscal_confirmation_snapshot(declared)
    fiscal_confirmed = confirm_fiscal_snapshot(fiscal_snapshot)
    policy = FiscalRoundingPolicy(
        "two-decimals", Decimal("0.01"), ROUND_HALF_UP, "TEST:ROUNDING"
    )
    rounded = round_confirmed_fiscal_amount(fiscal_confirmed, policy)
    monetary_snapshot = create_fiscal_monetary_confirmation_snapshot(rounded)
    monetary_confirmed = confirm_fiscal_monetary_snapshot(monetary_snapshot)
    return declare_fiscal_accounting_treatment(monetary_confirmed, role, side)


def test_fiscal_accounting_effect_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_accounting_effect as effect

    assert effect.__all__ == [
        "FiscalAccountingEffectLine",
        "FiscalAccountingEffect",
        "build_fiscal_accounting_effect",
    ]
    sig = signature(effect.build_fiscal_accounting_effect)
    assert list(sig.parameters) == ["declaration"]
    parameter = sig.parameters["declaration"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_effect_is_frozen_preserves_declaration_identity_and_copies_exact_semantic_line():
    from aqorath.fiscal_accounting_effect import (
        FiscalAccountingEffect,
        FiscalAccountingEffectLine,
        build_fiscal_accounting_effect,
    )

    declaration = _declaration()
    result = build_fiscal_accounting_effect(declaration)

    assert isinstance(result, FiscalAccountingEffect)
    assert isinstance(result.line, FiscalAccountingEffectLine)
    assert result.declaration is declaration
    assert result.line.account_role == "tax_payable"
    assert result.line.side == "credit"
    assert result.line.amount == Decimal("16.00")
    with pytest.raises(FrozenInstanceError):
        result.line = result.line
    with pytest.raises(FrozenInstanceError):
        result.line.amount = Decimal("99.00")


def test_effect_uses_confirmed_rounded_amount_not_exact_amount_fact_amount_or_tax_base():
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect

    declaration = _declaration(amount="16.005")
    result = build_fiscal_accounting_effect(declaration)
    monetary = declaration.confirmed_monetary_amount.snapshot

    assert monetary.fact_amount == Decimal("100.00")
    assert monetary.base == Decimal("100.00")
    assert monetary.exact_amount == Decimal("16.005")
    assert monetary.rounded_amount == Decimal("16.01")
    assert result.line.amount == Decimal("16.01")


def test_effect_preserves_arbitrary_explicit_role_and_side_without_iva_or_sale_inference():
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect

    debit = build_fiscal_accounting_effect(_declaration(role="manual_role", side="debit"))
    credit = build_fiscal_accounting_effect(_declaration(role="other_role", side="credit"))

    assert debit.line.account_role == "manual_role"
    assert debit.line.side == "debit"
    assert credit.line.account_role == "other_role"
    assert credit.line.side == "credit"


def test_effect_requires_nominal_fiscal_accounting_treatment_declaration():
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect

    declaration = _declaration()
    fake = SimpleNamespace(
        confirmed_monetary_amount=declaration.confirmed_monetary_amount,
        account_role=declaration.account_role,
        side=declaration.side,
    )
    with pytest.raises(TypeError):
        build_fiscal_accounting_effect(fake)
    with pytest.raises(TypeError):
        build_fiscal_accounting_effect(declaration.confirmed_monetary_amount)


def test_public_effect_types_reject_inconsistent_direct_construction():
    from aqorath.fiscal_accounting_effect import FiscalAccountingEffect, FiscalAccountingEffectLine

    declaration = _declaration()
    valid_line = FiscalAccountingEffectLine("tax_payable", "credit", Decimal("16.00"))
    valid = FiscalAccountingEffect(declaration, valid_line)
    assert valid.declaration is declaration

    with pytest.raises((TypeError, ValueError)):
        FiscalAccountingEffectLine("", "credit", Decimal("16.00"))
    with pytest.raises((TypeError, ValueError)):
        FiscalAccountingEffectLine("tax_payable", "charge", Decimal("16.00"))
    with pytest.raises((TypeError, ValueError)):
        FiscalAccountingEffectLine("tax_payable", "credit", 16.0)
    with pytest.raises((TypeError, ValueError)):
        FiscalAccountingEffectLine("tax_payable", "credit", Decimal("-1"))
    with pytest.raises(TypeError):
        FiscalAccountingEffect(SimpleNamespace(), valid_line)
    with pytest.raises(ValueError):
        FiscalAccountingEffect(
            declaration,
            FiscalAccountingEffectLine("other", "credit", Decimal("16.00")),
        )
    with pytest.raises(ValueError):
        FiscalAccountingEffect(
            declaration,
            FiscalAccountingEffectLine("tax_payable", "debit", Decimal("16.00")),
        )
    with pytest.raises(ValueError):
        FiscalAccountingEffect(
            declaration,
            FiscalAccountingEffectLine("tax_payable", "credit", Decimal("15.99")),
        )


def test_effect_is_not_balanced_accounting_proposal_resolved_proposal_or_posting_instruction():
    from aqorath.account_resolution import ResolvedAccountingProposal
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.posting import PostingInstruction, PostingLine

    result = build_fiscal_accounting_effect(_declaration())

    assert not isinstance(result, AccountingProposal)
    assert not isinstance(result, ResolvedAccountingProposal)
    assert not isinstance(result, PostingInstruction)
    assert not isinstance(result.line, ProposalLine)
    assert not isinstance(result.line, PostingLine)
    assert not hasattr(result, "lines")
    assert not hasattr(result.line, "account_id")
    assert not hasattr(result.line, "account_code")
    assert not hasattr(result.line, "debit")
    assert not hasattr(result.line, "credit")


def test_zero_confirmed_fiscal_amount_is_preserved_as_explicit_semantic_noop_not_silently_dropped():
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect

    result = build_fiscal_accounting_effect(_declaration(amount="0.0000"))
    assert result.line.amount == Decimal("0.00")
    assert result.line.account_role == "tax_payable"
    assert result.line.side == "credit"


def test_effect_is_pure_and_never_resolves_accounts_balances_composes_posts_or_opens_session(monkeypatch):
    import aqorath.account_bindings as bindings
    import aqorath.account_resolution as resolution
    import aqorath.catalog as catalog
    import aqorath.confirmation as confirmation
    import aqorath.posting as posting
    import aqorath.storage as storage

    declaration = _declaration()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscal accounting effect")

    with monkeypatch.context() as m:
        m.setattr(bindings, "get_account_binding", bomb)
        m.setattr(resolution, "resolve_proposal_accounts", bomb)
        m.setattr(catalog, "resolve_account_by_code", bomb)
        m.setattr(confirmation, "create_confirmation_snapshot", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(storage, "get_session", bomb)

        import aqorath.fiscal_accounting_effect as effect

        effect = reload(effect)
        result = effect.build_fiscal_accounting_effect(declaration)
        assert result.line.amount == Decimal("16.00")

    reload(effect)


def test_effect_is_deterministic_does_not_mutate_sources_and_adds_no_composition_defaults():
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect

    declaration = _declaration()
    monetary_snapshot = declaration.confirmed_monetary_amount.snapshot
    first = build_fiscal_accounting_effect(declaration)
    second = build_fiscal_accounting_effect(declaration)

    assert first == second
    assert first.declaration is second.declaration is declaration
    assert declaration.confirmed_monetary_amount.snapshot is monetary_snapshot
    for hidden in (
        "counterpart_role",
        "gross_amount",
        "net_amount",
        "economic_amount_basis",
        "account_code",
        "account_id",
        "posting_state",
    ):
        assert not hasattr(first, hidden)
        assert not hasattr(first.line, hidden)
