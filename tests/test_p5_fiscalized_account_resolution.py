"""Phase 5X.1 — fiscalized account resolution contracts."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _fiscalized_proposal(*, fiscal_role="tax_payable", fiscal_amount="16.00"):
    from datetime import date

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
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting

    fact = EconomicFact("sale", Decimal("100.00"), "cash")
    accounting = resolve_economic_fact_with_provenance(fact)
    snapshot = FiscalMonetaryConfirmationSnapshot(
        fact_type="sale",
        fact_amount=Decimal("100.00"),
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
    treatment = declare_fiscal_accounting_treatment(
        confirmed,
        fiscal_role,
        "credit",
    )
    effect = build_fiscal_accounting_effect(treatment)
    declaration = declare_fiscal_economic_composition(
        accounting,
        effect,
        "net_before_fiscal",
        "cash",
    )
    return compose_fiscal_economic_accounting(declaration)


def _account(code, account_id, name):
    return SimpleNamespace(id=account_id, code=code, name=name)


def test_fiscalized_account_resolution_public_contract_and_exact_signature_exist():
    import aqorath.fiscalized_account_resolution as resolution

    assert resolution.__all__ == [
        "ResolvedFiscalizedProposalLine",
        "ResolvedFiscalizedAccountingProposal",
        "resolve_fiscalized_proposal_accounts",
    ]
    sig = signature(resolution.resolve_fiscalized_proposal_accounts)
    assert list(sig.parameters) == ["session", "fiscalized_proposal", "account_bindings"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_resolution_requires_nominal_fiscalized_proposal_before_catalog_lookup(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    calls = []

    def bomb(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("catalog must not run")

    monkeypatch.setattr(catalog, "resolve_account_by_code", bomb)
    fake = SimpleNamespace(lines=(), explanation="shape-compatible")

    with pytest.raises(TypeError):
        resolve_fiscalized_proposal_accounts(object(), fake, {})
    assert calls == []


def test_resolution_uses_exact_explicit_bindings_supplied_session_and_one_lookup_per_line(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    session = object()
    bindings = {
        "cash": "CASH-001",
        "sales_revenue": "SALES-001",
        "tax_payable": "TAX-001",
    }
    accounts = {
        "CASH-001": _account("CASH-001", 1, "Caja"),
        "SALES-001": _account("SALES-001", 2, "Ventas"),
        "TAX-001": _account("TAX-001", 3, "Impuesto por pagar"),
    }
    calls = []

    def resolver(received_session, code):
        calls.append((received_session, code))
        return accounts.get(code)

    monkeypatch.setattr(catalog, "resolve_account_by_code", resolver)
    result = resolve_fiscalized_proposal_accounts(session, proposal, bindings)

    assert calls == [
        (session, "CASH-001"),
        (session, "SALES-001"),
        (session, "TAX-001"),
    ]
    assert all(received_session is session for received_session, _ in calls)
    assert result.fiscalized_proposal is proposal


def test_resolved_lines_preserve_exact_semantics_order_decimal_and_catalog_identity(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import (
        ResolvedFiscalizedAccountingProposal,
        ResolvedFiscalizedProposalLine,
        resolve_fiscalized_proposal_accounts,
    )

    proposal = _fiscalized_proposal()
    accounts = {
        "CASH": _account("CASH", 11, "Caja principal"),
        "SALES": _account("SALES", 22, "Ventas nacionales"),
        "TAX": _account("TAX", 33, "Impuestos por pagar"),
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts.get(code))

    result = resolve_fiscalized_proposal_accounts(
        object(),
        proposal,
        {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"},
    )

    assert isinstance(result, ResolvedFiscalizedAccountingProposal)
    assert isinstance(result.lines, tuple)
    assert result.fiscalized_proposal is proposal
    assert result.explanation == proposal.explanation
    assert tuple(
        (
            line.account_role,
            line.account_id,
            line.account_code,
            line.account_name,
            line.side,
            line.amount,
        )
        for line in result.lines
    ) == (
        ("cash", 11, "CASH", "Caja principal", "debit", Decimal("116.00")),
        ("sales_revenue", 22, "SALES", "Ventas nacionales", "credit", Decimal("100.00")),
        ("tax_payable", 33, "TAX", "Impuestos por pagar", "credit", Decimal("16.00")),
    )
    assert all(isinstance(line, ResolvedFiscalizedProposalLine) for line in result.lines)


def test_resolution_is_deeply_immutable_and_copies_lines_by_value(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    accounts = {
        "CASH": _account("CASH", 1, "Caja"),
        "SALES": _account("SALES", 2, "Ventas"),
        "TAX": _account("TAX", 3, "Impuesto"),
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])
    result = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"}
    )

    for source, resolved in zip(proposal.lines, result.lines):
        assert resolved is not source
        assert resolved.account_role == source.account_role
        assert resolved.side == source.side
        assert resolved.amount.as_tuple() == source.amount.as_tuple()
    with pytest.raises(FrozenInstanceError):
        result.explanation = "mutated"
    with pytest.raises(FrozenInstanceError):
        result.lines[0].account_code = "OTHER"
    with pytest.raises(TypeError):
        result.lines[0] = result.lines[1]


def test_missing_binding_fails_closed_without_partial_result_or_auto_creation(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    calls = []

    def resolver(session, code):
        calls.append(code)
        return _account(code, len(calls), code)

    monkeypatch.setattr(catalog, "resolve_account_by_code", resolver)
    with pytest.raises(ValueError, match="tax_payable"):
        resolve_fiscalized_proposal_accounts(
            object(),
            proposal,
            {"cash": "CASH", "sales_revenue": "SALES"},
        )
    assert calls == ["CASH", "SALES"]


def test_missing_catalog_account_fails_closed_without_fallback_or_auto_creation(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    calls = []

    def resolver(session, code):
        calls.append(code)
        if code == "TAX-MISSING":
            return None
        return _account(code, len(calls), code)

    monkeypatch.setattr(catalog, "resolve_account_by_code", resolver)
    with pytest.raises(ValueError, match="TAX-MISSING"):
        resolve_fiscalized_proposal_accounts(
            object(),
            proposal,
            {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX-MISSING"},
        )
    assert calls == ["CASH", "SALES", "TAX-MISSING"]


def test_different_explicit_bindings_produce_different_concrete_identity_without_hardcoded_codes(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    accounts = {
        code: _account(code, index, f"Name {code}")
        for index, code in enumerate(
            ("CASH-A", "SALES-A", "TAX-A", "CASH-B", "SALES-B", "TAX-B"),
            start=1,
        )
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])

    first = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH-A", "sales_revenue": "SALES-A", "tax_payable": "TAX-A"}
    )
    second = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH-B", "sales_revenue": "SALES-B", "tax_payable": "TAX-B"}
    )

    assert [line.account_code for line in first.lines] == ["CASH-A", "SALES-A", "TAX-A"]
    assert [line.account_code for line in second.lines] == ["CASH-B", "SALES-B", "TAX-B"]


def test_zero_fiscal_line_is_preserved_and_resolved_not_silently_dropped(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal(fiscal_amount="0.00")
    accounts = {
        "CASH": _account("CASH", 1, "Caja"),
        "SALES": _account("SALES", 2, "Ventas"),
        "TAX": _account("TAX", 3, "Impuesto"),
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])
    result = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"}
    )

    assert len(result.lines) == 3
    assert result.lines[-1].account_role == "tax_payable"
    assert result.lines[-1].amount.as_tuple() == Decimal("0.00").as_tuple()


def test_duplicate_semantic_roles_are_not_merged_during_resolution(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal(fiscal_role="cash")
    assert [line.account_role for line in proposal.lines] == ["cash", "sales_revenue", "cash"]
    accounts = {
        "CASH": _account("CASH", 1, "Caja"),
        "SALES": _account("SALES", 2, "Ventas"),
    }
    calls = []

    def resolver(session, code):
        calls.append(code)
        return accounts[code]

    monkeypatch.setattr(catalog, "resolve_account_by_code", resolver)
    result = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH", "sales_revenue": "SALES"}
    )

    assert [line.account_role for line in result.lines] == ["cash", "sales_revenue", "cash"]
    assert [line.account_code for line in result.lines] == ["CASH", "SALES", "CASH"]
    assert calls == ["CASH", "SALES", "CASH"]


def test_resolution_does_not_use_legacy_resolver_persistent_bindings_confirmation_posting_or_hidden_session(monkeypatch):
    import aqorath.account_bindings as account_bindings
    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.confirmation as confirmation
    import aqorath.posting as posting
    import aqorath.storage as storage
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    accounts = {
        "CASH": _account("CASH", 1, "Caja"),
        "SALES": _account("SALES", 2, "Ventas"),
        "TAX": _account("TAX", 3, "Impuesto"),
    }

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscalized account resolution")

    monkeypatch.setattr(account_resolution, "resolve_proposal_accounts", bomb)
    monkeypatch.setattr(account_bindings, "get_account_bindings", bomb)
    monkeypatch.setattr(confirmation, "create_confirmation_snapshot", bomb)
    monkeypatch.setattr(posting, "create_posting_instruction", bomb)
    monkeypatch.setattr(storage, "get_session", bomb)
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])

    result = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"}
    )
    assert result.fiscalized_proposal is proposal


def test_resolved_result_adds_no_confirmation_posting_or_persistence_metadata(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts

    proposal = _fiscalized_proposal()
    accounts = {
        "CASH": _account("CASH", 1, "Caja"),
        "SALES": _account("SALES", 2, "Ventas"),
        "TAX": _account("TAX", 3, "Impuesto"),
    }
    monkeypatch.setattr(catalog, "resolve_account_by_code", lambda session, code: accounts[code])
    result = resolve_fiscalized_proposal_accounts(
        object(), proposal, {"cash": "CASH", "sales_revenue": "SALES", "tax_payable": "TAX"}
    )

    for hidden in (
        "confirmed",
        "snapshot",
        "posting_instruction",
        "journal_entry_id",
        "entry_id",
        "state",
    ):
        assert not hasattr(result, hidden)
