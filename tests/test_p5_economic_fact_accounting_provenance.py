"""Phase 5U.1 — economic fact accounting provenance contracts."""

from dataclasses import FrozenInstanceError, is_dataclass
from decimal import Decimal
from importlib import reload
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _cash_sale():
    from aqorath.economic_facts import EconomicFact

    return EconomicFact("sale", Decimal("100.00"), "cash")


def test_economic_fact_accounting_provenance_public_contract_and_exact_signature_exist():
    import aqorath.economic_fact_accounting_provenance as provenance

    assert provenance.__all__ == [
        "EconomicFactAccountingResolution",
        "resolve_economic_fact_with_provenance",
    ]
    sig = signature(provenance.resolve_economic_fact_with_provenance)
    assert list(sig.parameters) == ["fact"]
    parameter = sig.parameters["fact"]
    assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is Parameter.empty


def test_provenance_calls_existing_resolver_exactly_once_with_same_fact_and_preserves_identities(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.economic_fact_accounting_provenance as provenance

    fact = _cash_sale()
    proposal = economic_facts.resolve_economic_fact(fact)
    calls = []

    def fake_resolver(received):
        calls.append(received)
        return proposal

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", fake_resolver)
    result = provenance.resolve_economic_fact_with_provenance(fact)

    assert calls == [fact]
    assert result.fact is fact
    assert result.proposal is proposal


def test_real_cash_sale_provenance_preserves_exact_existing_accounting_truth():
    from aqorath.economic_fact_accounting_provenance import (
        EconomicFactAccountingResolution,
        resolve_economic_fact_with_provenance,
    )

    fact = _cash_sale()
    result = resolve_economic_fact_with_provenance(fact)

    assert isinstance(result, EconomicFactAccountingResolution)
    assert result.fact is fact
    assert result.proposal.lines[0].account_role == "cash"
    assert result.proposal.lines[0].side == "debit"
    assert result.proposal.lines[0].amount == Decimal("100.00")
    assert result.proposal.lines[1].account_role == "sales_revenue"
    assert result.proposal.lines[1].side == "credit"
    assert result.proposal.lines[1].amount == Decimal("100.00")


def test_provenance_is_frozen_and_cannot_be_publicly_forged_from_arbitrary_fact_proposal_pair():
    from aqorath.economic_fact_accounting_provenance import (
        EconomicFactAccountingResolution,
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = _cash_sale()
    other_fact = EconomicFact("sale", Decimal("200.00"), "cash")
    other_proposal = resolve_economic_fact(other_fact)
    result = resolve_economic_fact_with_provenance(fact)

    assert is_dataclass(result)
    with pytest.raises(FrozenInstanceError):
        result.fact = other_fact
    with pytest.raises(FrozenInstanceError):
        result.proposal = other_proposal
    with pytest.raises(TypeError):
        EconomicFactAccountingResolution(fact, other_proposal)


def test_provenance_requires_nominal_economic_fact_before_resolver_call(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.economic_fact_accounting_provenance as provenance

    calls = []

    def fake_resolver(received):
        calls.append(received)
        raise AssertionError("resolver must not run")

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", fake_resolver)
    fake = SimpleNamespace(type="sale", amount=Decimal("100.00"), payment_method="cash")

    with pytest.raises(TypeError):
        provenance.resolve_economic_fact_with_provenance(fake)
    assert calls == []


def test_provenance_propagates_resolver_failure_without_retry(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.economic_fact_accounting_provenance as provenance

    fact = _cash_sale()
    calls = []

    def failing_resolver(received):
        calls.append(received)
        raise RuntimeError("resolver failed")

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", failing_resolver)
    with pytest.raises(RuntimeError, match="resolver failed"):
        provenance.resolve_economic_fact_with_provenance(fact)
    assert calls == [fact]


def test_provenance_uses_economic_facts_module_lookup_not_captured_function_alias(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.economic_fact_accounting_provenance as provenance

    fact = _cash_sale()
    marker = object()
    calls = []

    def fake_resolver(received):
        calls.append(received)
        return marker

    monkeypatch.setattr(economic_facts, "resolve_economic_fact", fake_resolver)
    with pytest.raises(TypeError):
        provenance.resolve_economic_fact_with_provenance(fact)
    assert calls == [fact]


def test_provenance_rejects_non_accounting_proposal_return_from_resolver(monkeypatch):
    import aqorath.economic_facts as economic_facts
    import aqorath.economic_fact_accounting_provenance as provenance

    fact = _cash_sale()
    fake = SimpleNamespace(lines=(), explanation="shape-compatible")
    monkeypatch.setattr(economic_facts, "resolve_economic_fact", lambda received: fake)

    with pytest.raises(TypeError):
        provenance.resolve_economic_fact_with_provenance(fact)


def test_provenance_is_pure_and_never_enters_resolution_fiscal_confirmation_or_posting(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.confirmation as confirmation
    import aqorath.fiscal_accounting_effect as fiscal_effect
    import aqorath.fiscal_applicability as fiscal_applicability
    import aqorath.posting as posting
    import aqorath.storage as storage

    fact = _cash_sale()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden downstream authority called by provenance")

    with monkeypatch.context() as m:
        m.setattr(account_resolution, "resolve_proposal_accounts", bomb)
        m.setattr(confirmation, "create_confirmation_snapshot", bomb)
        m.setattr(fiscal_applicability, "declare_fiscal_rate_applicability", bomb)
        m.setattr(fiscal_effect, "build_fiscal_accounting_effect", bomb)
        m.setattr(posting, "create_posting_instruction", bomb)
        m.setattr(storage, "get_session", bomb)

        import aqorath.economic_fact_accounting_provenance as provenance

        provenance = reload(provenance)
        result = provenance.resolve_economic_fact_with_provenance(fact)
        assert result.fact is fact
        assert result.proposal.lines[0].account_role == "cash"

    reload(provenance)


def test_provenance_is_deterministic_adds_no_fiscal_composition_or_posting_defaults():
    from aqorath.economic_fact_accounting_provenance import resolve_economic_fact_with_provenance

    fact = _cash_sale()
    first = resolve_economic_fact_with_provenance(fact)
    second = resolve_economic_fact_with_provenance(fact)

    assert first.fact is second.fact is fact
    assert first.proposal == second.proposal
    assert first.proposal is not second.proposal
    for hidden in (
        "fact_id",
        "rule_key",
        "tax_base",
        "fiscal_effect",
        "economic_amount_basis",
        "account_bindings",
        "posting_instruction",
        "journal_entry_id",
    ):
        assert not hasattr(first, hidden)
