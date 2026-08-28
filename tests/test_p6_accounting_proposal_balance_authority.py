"""Phase 6BB.1 — frozen AccountingProposal balance-authority convergence contracts.

The legacy semantic AccountingProposal already computes debit and credit totals from its
own ProposalLine values. 6AQ established ledger_signed_balance() as the exact algebraic
balance authority. This phase freezes convergence only: proposal balance validation must
interpret those existing exact totals through ledger_signed_balance() == Decimal("0").
It does not turn ProposalLine into JournalLine, resolve accounts, persist, post, report,
apply fiscal rules, or enter Application.
"""

from dataclasses import fields
from decimal import Decimal
import inspect

import pytest


def _line(*, side, amount="10.00", role="semantic_role"):
    from aqorath.economic_facts import ProposalLine

    return ProposalLine(
        account_role=role,
        side=side,
        amount=Decimal(amount),
    )


def _proposal(
    *,
    debit="10.00",
    credit="10.00",
    debit_role="cash",
    credit_role="sales_revenue",
    explanation="Deterministic semantic proposal",
    lines=None,
):
    from aqorath.economic_facts import AccountingProposal

    if lines is None:
        lines = [
            _line(side="debit", amount=debit, role=debit_role),
            _line(side="credit", amount=credit, role=credit_role),
        ]
    return AccountingProposal(lines=lines, explanation=explanation)


def test_accounting_proposal_public_shape_remains_lines_and_explanation_only():
    from aqorath.economic_facts import AccountingProposal

    assert tuple(field.name for field in fields(AccountingProposal)) == (
        "lines",
        "explanation",
    )
    assert tuple(inspect.signature(AccountingProposal).parameters) == (
        "lines",
        "explanation",
    )


def test_existing_balanced_proposal_remains_valid():
    proposal = _proposal(debit="125.4500", credit="125.4500")
    assert proposal.lines[0].amount == Decimal("125.4500")
    assert proposal.lines[1].amount == Decimal("125.4500")


def test_debit_excess_remains_rejected():
    with pytest.raises(ValueError):
        _proposal(debit="10.01", credit="10.00")


def test_credit_excess_remains_rejected():
    with pytest.raises(ValueError):
        _proposal(debit="10.00", credit="10.01")


def test_balance_validation_remains_exact_without_tolerance():
    with pytest.raises(ValueError):
        _proposal(
            debit="1.0000000000000000000000000001",
            credit="1.0000000000000000000000000000",
        )


def test_balance_validation_delegates_exact_totals_to_ledger_signed_balance(monkeypatch):
    import aqorath.economic_facts as domain

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(domain, "ledger_signed_balance", fake)

    _proposal(debit="12.3400", credit="12.3400")

    assert calls == [(Decimal("12.3400"), Decimal("12.3400"))]


def test_authoritative_zero_accepts_even_when_raw_totals_differ_under_contract_override(monkeypatch):
    import aqorath.economic_facts as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    proposal = _proposal(debit="10.00", credit="9.00")
    assert proposal.lines[0].amount == Decimal("10.00")
    assert proposal.lines[1].amount == Decimal("9.00")


def test_authoritative_positive_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.economic_facts as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0.0001"),
    )

    with pytest.raises(ValueError):
        _proposal(debit="10.00", credit="10.00")


def test_authoritative_negative_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.economic_facts as domain

    monkeypatch.setattr(
        domain,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("-0.0001"),
    )

    with pytest.raises(ValueError):
        _proposal(debit="10.00", credit="10.00")


def test_balance_authority_is_called_exactly_once(monkeypatch):
    import aqorath.economic_facts as domain

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(domain, "ledger_signed_balance", fake)
    _proposal()

    assert len(calls) == 1


def test_balance_validation_does_not_use_normal_balance_or_account_nature():
    from aqorath.economic_facts import AccountingProposal

    source = inspect.getsource(AccountingProposal.__post_init__).lower()
    for forbidden in (
        "normal_balance_amount",
        "normal_balance_for_account",
        "journal_line_normal_balance",
        ".nature",
        "account_type",
        "subtype",
    ):
        assert forbidden not in source


def test_balance_validation_does_not_route_through_journal_line_or_entry_authorities():
    from aqorath.economic_facts import AccountingProposal

    source = inspect.getsource(AccountingProposal.__post_init__).lower()
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


def test_semantic_account_roles_and_line_order_remain_opaque_to_balance():
    lines = [
        _line(side="credit", amount="7.2500", role="future_credit_role"),
        _line(side="debit", amount="7.2500", role="future_debit_role"),
    ]
    proposal = _proposal(lines=lines)

    assert proposal.lines is lines
    assert proposal.lines[0].account_role == "future_credit_role"
    assert proposal.lines[1].account_role == "future_debit_role"


def test_existing_exactly_two_proposal_lines_contract_remains_unchanged():
    one_line = [_line(side="debit", amount="1.00")]
    with pytest.raises(ValueError):
        _proposal(lines=one_line)

    three_lines = [
        _line(side="debit", amount="2.00"),
        _line(side="credit", amount="1.00"),
        _line(side="credit", amount="1.00"),
    ]
    with pytest.raises(ValueError):
        _proposal(lines=three_lines)


def test_existing_explanation_validation_remains_independent_of_balance_authority():
    with pytest.raises(TypeError):
        _proposal(explanation=7)

    for invalid in ("", "   "):
        with pytest.raises(ValueError):
            _proposal(explanation=invalid)


def test_convergence_uses_exact_zero_without_direct_total_comparison_or_tolerance():
    from aqorath.economic_facts import AccountingProposal

    source = inspect.getsource(AccountingProposal.__post_init__).lower()
    assert "ledger_signed_balance" in source
    assert "decimal(\"0\")" in source
    assert "total_debit != total_credit" not in source
    for forbidden in (
        "abs(",
        "isclose",
        "tolerance",
        "quantize",
        "round(",
        "float(",
    ):
        assert forbidden not in source


def test_convergence_does_not_add_resolution_persistence_posting_reporting_fiscal_or_application():
    import aqorath.economic_facts as domain
    from aqorath.economic_facts import AccountingProposal

    method_source = inspect.getsource(AccountingProposal.__post_init__).lower()
    module_source = inspect.getsource(domain).lower()

    for forbidden in (
        "resolve_account",
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
        "fiscal_rule",
    ):
        assert forbidden not in method_source

    assert "aqorath.application" not in module_source
