"""Phase 6S.1 — frozen contracts for structured deterministic explanation.

Constitution anchors:
- R11 requires important operations to explain what happened, what Aqorath interpreted,
  which accounting roles were affected, and why, from the same rule truth.
- R12/R13 permit later adaptation of presentation, but must not turn explanation into a
  second accounting truth or mutate learning state implicitly.

This phase freezes only a pure structured explanation projection for the existing
EconomicFactAccountingResolution provenance. It does not adapt text to a user, read or
write UserKnowledgeState, resolve concrete accounts, infer fiscal treatment, confirm,
persist, or post.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import importlib
import inspect

import pytest


EFFECT_FIELDS = ("account_role", "side", "amount")
EXPLANATION_FIELDS = (
    "fact_type",
    "payment_method",
    "amount",
    "rule_key",
    "effects",
    "concepts",
    "professional_summary",
)


def _module():
    return importlib.import_module("aqorath.explanation")


def _resolution(*, fact_type="sale", payment_method="cash", amount="123.4500"):
    from aqorath.economic_fact_accounting_provenance import (
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact

    return resolve_economic_fact_with_provenance(
        EconomicFact(
            type=fact_type,
            amount=Decimal(amount),
            payment_method=payment_method,
        )
    )


def test_structured_explanation_public_contract_is_frozen_exact_and_pure_projection():
    module = _module()

    assert tuple(field.name for field in fields(module.ExplanationEffect)) == EFFECT_FIELDS
    assert tuple(field.name for field in fields(module.ExplanationData)) == EXPLANATION_FIELDS
    assert str(inspect.signature(module.build_economic_fact_explanation)) == "(accounting_resolution)"

    source = inspect.getsource(module).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "user_knowledge_state_repository",
        "appconfig",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source


def test_explanation_value_types_are_deeply_immutable():
    module = _module()
    explanation = module.build_economic_fact_explanation(_resolution())

    with pytest.raises(FrozenInstanceError):
        explanation.fact_type = "changed"
    with pytest.raises(FrozenInstanceError):
        explanation.effects[0].side = "credit"

    assert type(explanation.effects) is tuple
    assert type(explanation.concepts) is tuple


def test_explanation_effect_validates_only_structural_presentation_shape_fail_closed():
    module = _module()

    valid = module.ExplanationEffect(
        account_role="cash",
        side="debit",
        amount=Decimal("1.2300"),
    )
    assert valid.amount == Decimal("1.2300")

    for invalid_role in ("", " cash ", None, 1):
        with pytest.raises((TypeError, ValueError)):
            replace(valid, account_role=invalid_role)
    for invalid_side in ("", "Debit", "left", None):
        with pytest.raises((TypeError, ValueError)):
            replace(valid, side=invalid_side)
    for invalid_amount in (0, 1.0, "1.00", Decimal("0"), Decimal("-1")):
        with pytest.raises((TypeError, ValueError)):
            replace(valid, amount=invalid_amount)


def test_explanation_data_validates_value_shape_without_becoming_balance_authority():
    module = _module()
    source = module.build_economic_fact_explanation(_resolution())

    for name in ("fact_type", "payment_method", "rule_key", "professional_summary"):
        for invalid in ("", " spaced ", None, 1):
            with pytest.raises((TypeError, ValueError)):
                replace(source, **{name: invalid})

    for invalid_amount in (1.0, "1", Decimal("0"), Decimal("-1")):
        with pytest.raises((TypeError, ValueError)):
            replace(source, amount=invalid_amount)

    with pytest.raises((TypeError, ValueError)):
        replace(source, effects=list(source.effects))
    with pytest.raises((TypeError, ValueError)):
        replace(source, effects=("not-an-effect",))
    with pytest.raises((TypeError, ValueError)):
        replace(source, concepts=["economic_fact"])
    with pytest.raises((TypeError, ValueError)):
        replace(source, concepts=("economic_fact", "economic_fact"))
    with pytest.raises((TypeError, ValueError)):
        replace(source, concepts=(" spaced ",))

    # Direct value construction does not recompute or enforce double-entry. Accounting
    # balance remains owned by the existing accounting proposal/resolution authority.
    one_effect = replace(source, effects=(source.effects[0],))
    assert len(one_effect.effects) == 1


def test_builder_requires_nominal_economic_fact_accounting_resolution_before_any_projection():
    module = _module()
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(type="sale", amount=Decimal("10"), payment_method="cash")
    proposal = resolve_economic_fact(fact)

    for invalid in (None, fact, proposal, {"fact": fact, "proposal": proposal}):
        with pytest.raises(TypeError):
            module.build_economic_fact_explanation(invalid)


def test_cash_sale_explanation_preserves_exact_fact_rule_summary_and_semantic_effects():
    module = _module()
    resolution = _resolution(amount="123.4500")
    explanation = module.build_economic_fact_explanation(resolution)

    assert explanation.fact_type == "sale"
    assert explanation.payment_method == "cash"
    assert explanation.amount is resolution.fact.amount
    assert explanation.amount == Decimal("123.4500")
    assert explanation.rule_key == "economic_fact:sale:cash"
    assert explanation.professional_summary == resolution.proposal.explanation
    assert explanation.effects == (
        module.ExplanationEffect("cash", "debit", Decimal("123.4500")),
        module.ExplanationEffect("sales_revenue", "credit", Decimal("123.4500")),
    )


def test_effect_projection_preserves_proposal_order_roles_sides_and_decimal_scale_by_value():
    module = _module()
    resolution = _resolution(
        fact_type="utility_expense_incurred",
        payment_method="credit",
        amount="77.5000",
    )
    explanation = module.build_economic_fact_explanation(resolution)

    assert tuple(effect.account_role for effect in explanation.effects) == (
        "utilities_expense",
        "accounts_payable",
    )
    assert tuple(effect.side for effect in explanation.effects) == ("debit", "credit")
    assert tuple(str(effect.amount) for effect in explanation.effects) == (
        "77.5000",
        "77.5000",
    )
    assert all(effect is not source for effect, source in zip(explanation.effects, resolution.proposal.lines))


@pytest.mark.parametrize(
    ("fact_type", "payment_method", "debit_role", "credit_role"),
    (
        ("sale", "cash", "cash", "sales_revenue"),
        ("sale", "credit", "accounts_receivable", "sales_revenue"),
        ("utility_expense", "bank", "utilities_expense", "bank"),
        ("utility_expense_incurred", "credit", "utilities_expense", "accounts_payable"),
        ("receivable_collection", "bank", "bank", "accounts_receivable"),
        ("supplier_payment", "bank", "accounts_payable", "bank"),
    ),
)
def test_all_existing_economic_fact_verticals_get_deterministic_structured_rule_identity(
    fact_type,
    payment_method,
    debit_role,
    credit_role,
):
    module = _module()
    resolution = _resolution(
        fact_type=fact_type,
        payment_method=payment_method,
        amount="11.0100",
    )
    explanation = module.build_economic_fact_explanation(resolution)

    assert explanation.rule_key == f"economic_fact:{fact_type}:{payment_method}"
    assert tuple(effect.account_role for effect in explanation.effects) == (
        debit_role,
        credit_role,
    )
    assert tuple(effect.side for effect in explanation.effects) == ("debit", "credit")
    assert explanation.professional_summary == resolution.proposal.explanation


def test_builder_copies_source_values_so_later_proposal_list_mutation_cannot_rewrite_explanation():
    module = _module()
    resolution = _resolution(amount="20.00")
    explanation = module.build_economic_fact_explanation(resolution)
    original_effects = explanation.effects

    # AccountingProposal historically exposes a mutable list. The explanation projection
    # must copy values into its own immutable tuple rather than retain that list.
    resolution.proposal.lines.reverse()
    assert explanation.effects == original_effects
    assert tuple(effect.account_role for effect in explanation.effects) == (
        "cash",
        "sales_revenue",
    )


def test_builder_never_reresolves_fact_or_parses_professional_summary(monkeypatch):
    module = _module()
    resolution = _resolution(amount="31.00")

    import aqorath.economic_facts as economic_facts

    def forbidden_resolver(*args, **kwargs):
        raise AssertionError("must not re-resolve economic fact")

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", forbidden_resolver)
    explanation = module.build_economic_fact_explanation(resolution)
    assert explanation.professional_summary is resolution.proposal.explanation
    assert explanation.effects[0].account_role == resolution.proposal.lines[0].account_role

    source = inspect.getsource(module.build_economic_fact_explanation).lower()
    for forbidden in ("split(", "regex", "re.", "startswith", "endswith"):
        assert forbidden not in source


def test_concept_keys_are_deterministic_foundation_metadata_not_user_learning_inference():
    module = _module()

    for resolution in (
        _resolution(),
        _resolution(fact_type="sale", payment_method="credit"),
        _resolution(fact_type="supplier_payment", payment_method="bank"),
    ):
        explanation = module.build_economic_fact_explanation(resolution)
        assert explanation.concepts == ("economic_fact", "double_entry")

    assert "concepts_seen" not in inspect.getsource(module).lower()
    assert "learned_topics" not in inspect.getsource(module).lower()


def test_structured_explanation_does_not_infer_fiscal_truth_or_concrete_account_identity():
    module = _module()
    explanation = module.build_economic_fact_explanation(_resolution())

    forbidden_fields = {
        "account_id",
        "account_code",
        "tax",
        "tax_rate",
        "fiscal_effect",
        "fiscal_rule_set_id",
        "journal_entry_id",
        "confirmed",
        "posted",
    }
    assert forbidden_fields.isdisjoint(EXPLANATION_FIELDS)
    assert forbidden_fields.isdisjoint(EFFECT_FIELDS)
    for name in forbidden_fields:
        assert not hasattr(explanation, name)
        assert all(not hasattr(effect, name) for effect in explanation.effects)


def test_structured_explanation_is_not_accounting_confirmation_posting_or_persistence_authority():
    module = _module()
    explanation = module.build_economic_fact_explanation(_resolution())

    from aqorath.economic_facts import AccountingProposal
    from aqorath.confirmation import ConfirmationSnapshot

    assert not isinstance(explanation, AccountingProposal)
    assert not isinstance(explanation, ConfirmationSnapshot)

    source = inspect.getsource(module).lower()
    for forbidden in (
        "commit(",
        "rollback(",
        "session.",
        "post_entry",
        "confirm_snapshot",
        "resolve_proposal_accounts",
        "calculate_fiscal",
        "fiscal_rule",
    ):
        assert forbidden not in source


def test_builder_is_deterministic_and_does_not_mutate_provenance_or_add_ambient_metadata():
    module = _module()
    resolution = _resolution(amount="99.9900")
    before_fact = resolution.fact
    before_lines = tuple(resolution.proposal.lines)
    before_summary = resolution.proposal.explanation

    first = module.build_economic_fact_explanation(resolution)
    second = module.build_economic_fact_explanation(resolution)

    assert first == second
    assert resolution.fact is before_fact
    assert tuple(resolution.proposal.lines) == before_lines
    assert resolution.proposal.explanation == before_summary
    assert not hasattr(first, "created_at")
    assert not hasattr(first, "generated_at")
    assert not hasattr(first, "user_id")


def test_application_exposes_structured_explanation_as_exact_thin_delegation(monkeypatch):
    application = importlib.import_module("aqorath.application")
    module = _module()

    assert hasattr(application, "build_economic_fact_explanation")
    assert str(inspect.signature(application.build_economic_fact_explanation)) == "(accounting_resolution)"

    sentinel_resolution = object()
    sentinel_result = object()
    calls = []

    def fake_builder(accounting_resolution):
        calls.append(accounting_resolution)
        return sentinel_result

    monkeypatch.setattr(module, "build_economic_fact_explanation", fake_builder)
    assert application.build_economic_fact_explanation(sentinel_resolution) is sentinel_result
    assert calls == [sentinel_resolution]


def test_application_does_not_apply_user_preferences_resolve_accounts_or_rebuild_explanation_itself():
    application = importlib.import_module("aqorath.application")
    source = inspect.getsource(application.build_economic_fact_explanation).lower()

    assert "_explanation.build_economic_fact_explanation" in source
    for forbidden in (
        "get_user_knowledge_state",
        "explanation_level",
        "concepts_seen",
        "resolve_economic_fact",
        "resolve_proposal_accounts",
        "confirm",
        "post",
        "session",
    ):
        assert forbidden not in source
