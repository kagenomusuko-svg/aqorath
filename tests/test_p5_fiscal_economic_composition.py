"""Phase 5V.1 — fiscal/economic composition declaration contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _composition_inputs(
    *,
    fact_amount="100.00",
    fiscal_fact_type="sale",
    fiscal_fact_amount="100.00",
    fiscal_payment_method="cash",
    fiscal_role="tax_payable",
    fiscal_side="credit",
    fiscal_amount="16.00",
):
    from aqorath.economic_fact_accounting_provenance import (
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_monetary_confirmation import (
        ConfirmedFiscalMonetaryAmount,
        FiscalMonetaryConfirmationSnapshot,
    )

    fact = EconomicFact("sale", Decimal(fact_amount), "cash")
    accounting = resolve_economic_fact_with_provenance(fact)
    fiscal_snapshot = FiscalMonetaryConfirmationSnapshot(
        fact_type=fiscal_fact_type,
        fact_amount=Decimal(fiscal_fact_amount),
        payment_method=fiscal_payment_method,
        effective_date=__import__("datetime").date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal("0.16"),
        unit="rate",
        rule_effective_from=__import__("datetime").date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref="TEST:RULE",
        exact_amount=Decimal(fiscal_amount),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="TEST:ROUNDING",
        rounded_amount=Decimal(fiscal_amount),
    )
    confirmed = ConfirmedFiscalMonetaryAmount(fiscal_snapshot)
    treatment = declare_fiscal_accounting_treatment(
        confirmed,
        fiscal_role,
        fiscal_side,
    )
    effect = build_fiscal_accounting_effect(treatment)
    return accounting, effect


def test_fiscal_economic_composition_declaration_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_economic_composition as composition

    assert composition.__all__ == [
        "FiscalEconomicCompositionDeclaration",
        "declare_fiscal_economic_composition",
    ]
    sig = signature(composition.declare_fiscal_economic_composition)
    assert list(sig.parameters) == [
        "accounting_resolution",
        "fiscal_effect",
        "amount_basis",
        "adjustment_role",
    ]
    for name in sig.parameters:
        parameter = sig.parameters[name]
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_declaration_is_frozen_and_preserves_exact_input_identities_and_explicit_choices():
    from aqorath.fiscal_economic_composition import (
        FiscalEconomicCompositionDeclaration,
        declare_fiscal_economic_composition,
    )

    accounting, effect = _composition_inputs()
    declaration = declare_fiscal_economic_composition(
        accounting,
        effect,
        "net_before_fiscal",
        "cash",
    )

    assert isinstance(declaration, FiscalEconomicCompositionDeclaration)
    assert declaration.accounting_resolution is accounting
    assert declaration.fiscal_effect is effect
    assert declaration.amount_basis == "net_before_fiscal"
    assert declaration.adjustment_role == "cash"
    with pytest.raises(FrozenInstanceError):
        declaration.amount_basis = "gross_including_fiscal"


def test_declaration_accepts_only_two_explicit_amount_basis_values_without_default():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, effect = _composition_inputs()
    net = declare_fiscal_economic_composition(
        accounting, effect, "net_before_fiscal", "cash"
    )
    gross = declare_fiscal_economic_composition(
        accounting, effect, "gross_including_fiscal", "sales_revenue"
    )

    assert net.amount_basis == "net_before_fiscal"
    assert gross.amount_basis == "gross_including_fiscal"
    for invalid in (None, "", "net", "gross", "auto", "inclusive"):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_economic_composition(accounting, effect, invalid, "cash")


def test_adjustment_role_must_identify_exactly_one_existing_accounting_proposal_role():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, effect = _composition_inputs()

    for invalid in (None, "", "missing_role", "tax_payable"):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_economic_composition(
                accounting,
                effect,
                "net_before_fiscal",
                invalid,
            )


def test_declaration_rejects_cross_branch_fact_type_payment_or_exact_amount_mismatch():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    mismatches = [
        _composition_inputs(fiscal_fact_type="utility_expense"),
        _composition_inputs(fiscal_payment_method="credit"),
        _composition_inputs(fiscal_fact_amount="99.00"),
        _composition_inputs(fiscal_fact_amount="100.0"),
    ]

    for accounting, effect in mismatches:
        with pytest.raises(ValueError):
            declare_fiscal_economic_composition(
                accounting,
                effect,
                "net_before_fiscal",
                "cash",
            )


def test_net_before_fiscal_requires_adjusting_existing_line_opposite_fiscal_side():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, credit_effect = _composition_inputs(fiscal_side="credit")
    declaration = declare_fiscal_economic_composition(
        accounting,
        credit_effect,
        "net_before_fiscal",
        "cash",
    )
    assert declaration.adjustment_role == "cash"

    with pytest.raises(ValueError):
        declare_fiscal_economic_composition(
            accounting,
            credit_effect,
            "net_before_fiscal",
            "sales_revenue",
        )

    accounting, debit_effect = _composition_inputs(fiscal_side="debit")
    declaration = declare_fiscal_economic_composition(
        accounting,
        debit_effect,
        "net_before_fiscal",
        "sales_revenue",
    )
    assert declaration.adjustment_role == "sales_revenue"


def test_gross_including_fiscal_requires_adjusting_existing_line_same_as_fiscal_side():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, credit_effect = _composition_inputs(fiscal_side="credit")
    declaration = declare_fiscal_economic_composition(
        accounting,
        credit_effect,
        "gross_including_fiscal",
        "sales_revenue",
    )
    assert declaration.adjustment_role == "sales_revenue"

    with pytest.raises(ValueError):
        declare_fiscal_economic_composition(
            accounting,
            credit_effect,
            "gross_including_fiscal",
            "cash",
        )

    accounting, debit_effect = _composition_inputs(fiscal_side="debit")
    declaration = declare_fiscal_economic_composition(
        accounting,
        debit_effect,
        "gross_including_fiscal",
        "cash",
    )
    assert declaration.adjustment_role == "cash"


def test_declaration_preserves_arbitrary_explicit_fiscal_role_without_sale_or_iva_inference():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, effect = _composition_inputs(
        fiscal_role="manual_fiscal_role",
        fiscal_side="credit",
    )
    declaration = declare_fiscal_economic_composition(
        accounting,
        effect,
        "net_before_fiscal",
        "cash",
    )

    assert declaration.fiscal_effect.line.account_role == "manual_fiscal_role"
    assert declaration.adjustment_role == "cash"


def test_declaration_requires_nominal_accounting_resolution_and_fiscal_effect():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, effect = _composition_inputs()
    fake_accounting = SimpleNamespace(
        fact=accounting.fact,
        proposal=accounting.proposal,
    )
    fake_effect = SimpleNamespace(
        declaration=effect.declaration,
        line=effect.line,
    )

    with pytest.raises(TypeError):
        declare_fiscal_economic_composition(
            fake_accounting,
            effect,
            "net_before_fiscal",
            "cash",
        )
    with pytest.raises(TypeError):
        declare_fiscal_economic_composition(
            accounting,
            fake_effect,
            "net_before_fiscal",
            "cash",
        )


def test_declaration_is_pure_and_never_reresolves_recalculates_resolves_accounts_or_posts(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.economic_facts as economic_facts
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.posting as posting
    import aqorath.storage as storage

    accounting, effect = _composition_inputs()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by composition declaration")

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", bomb)
    monkeypatch.setattr(account_resolution, "resolve_proposal_accounts", bomb)
    monkeypatch.setattr(fiscal_calculation, "calculate_rate_amount", bomb)
    monkeypatch.setattr(posting, "create_posting_instruction", bomb)
    monkeypatch.setattr(storage, "get_session", bomb)

    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    declaration = declare_fiscal_economic_composition(
        accounting,
        effect,
        "net_before_fiscal",
        "cash",
    )
    assert declaration.accounting_resolution is accounting
    assert declaration.fiscal_effect is effect


def test_declaration_adds_no_account_resolution_posting_or_hidden_transaction_identity():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting, effect = _composition_inputs()
    declaration = declare_fiscal_economic_composition(
        accounting,
        effect,
        "net_before_fiscal",
        "cash",
    )

    for hidden in (
        "fact_id",
        "transaction_id",
        "account_code",
        "account_id",
        "resolved_lines",
        "posting_instruction",
        "journal_entry_id",
        "composed_proposal",
    ):
        assert not hasattr(declaration, hidden)
