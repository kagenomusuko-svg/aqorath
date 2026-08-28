"""Phase 6BI.1 — frozen PostingInstruction balance-authority convergence contracts.

create_posting_instruction() already validates one explicitly confirmed snapshot,
materializes exact PostingLine debit/credit values, and computes exact debit/credit
totals. 6AQ established ledger_signed_balance() as the authoritative algebraic balance
function, and 6BB/6BH converged semantic proposals onto it. This phase freezes the same
convergence at the pure posting-instruction boundary only: valid posting totals must be
interpreted through ledger_signed_balance(...) == Decimal("0"). Existing nominal
confirmation, amount, side, concrete-account, immutability, and purity rules remain
unchanged. No persistence, posting execution, Journal construction, account resolution,
reporting, or Application behavior is added here.
"""

from dataclasses import fields
from decimal import Decimal
import inspect

import pytest


def _confirmed(*, debit="200.00", credit="200.00", description="confirmed proposal"):
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal

    return ConfirmedProposal(
        ConfirmationSnapshot(
            (
                ConfirmationLine(
                    "cash",
                    101,
                    "TEST-CASH-001",
                    "Caja principal",
                    "debit",
                    Decimal(debit),
                ),
                ConfirmationLine(
                    "sales_revenue",
                    902,
                    "TEST-SALES-900",
                    "Ingresos por ventas",
                    "credit",
                    Decimal(credit),
                ),
            ),
            description,
        )
    )


def test_posting_public_shapes_and_signature_remain_unchanged():
    import aqorath.posting as posting

    assert tuple(field.name for field in fields(posting.PostingLine)) == (
        "account_role",
        "account_id",
        "account_code",
        "account_name",
        "debit",
        "credit",
    )
    assert tuple(field.name for field in fields(posting.PostingInstruction)) == (
        "lines",
        "description",
    )
    assert tuple(inspect.signature(posting.create_posting_instruction).parameters) == (
        "confirmed_proposal",
    )


def test_existing_balanced_confirmed_proposal_remains_valid():
    from aqorath.posting import PostingInstruction, create_posting_instruction

    confirmed = _confirmed(debit="125.4500", credit="125.4500", description="exact")
    instruction = create_posting_instruction(confirmed)

    assert isinstance(instruction, PostingInstruction)
    assert instruction.description == "exact"
    assert tuple((line.debit, line.credit) for line in instruction.lines) == (
        (Decimal("125.4500"), Decimal("0")),
        (Decimal("0"), Decimal("125.4500")),
    )


def test_balance_validation_delegates_exact_totals_to_ledger_signed_balance(monkeypatch):
    import aqorath.posting as posting

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(posting, "ledger_signed_balance", fake)
    posting.create_posting_instruction(_confirmed(debit="12.3400", credit="12.3400"))

    assert calls == [(Decimal("12.3400"), Decimal("12.3400"))]


def test_balance_authority_is_called_exactly_once(monkeypatch):
    import aqorath.posting as posting

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(posting, "ledger_signed_balance", fake)
    posting.create_posting_instruction(_confirmed())

    assert len(calls) == 1


def test_authoritative_zero_accepts_raw_total_difference_under_contract_override(monkeypatch):
    import aqorath.posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    instruction = posting.create_posting_instruction(
        _confirmed(debit="200.00", credit="199.00")
    )

    assert instruction.lines[0].debit == Decimal("200.00")
    assert instruction.lines[1].credit == Decimal("199.00")


def test_authoritative_positive_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0.0001"),
    )

    with pytest.raises(ValueError):
        posting.create_posting_instruction(_confirmed())


def test_authoritative_negative_signed_balance_rejects_even_when_raw_totals_match(monkeypatch):
    import aqorath.posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("-0.0001"),
    )

    with pytest.raises(ValueError):
        posting.create_posting_instruction(_confirmed())


def test_arbitrarily_small_nonzero_authoritative_balance_is_not_tolerated(monkeypatch):
    import aqorath.posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal(
            "0.0000000000000000000000000001"
        ),
    )

    with pytest.raises(ValueError):
        posting.create_posting_instruction(_confirmed())


def test_convergence_uses_exact_zero_without_direct_total_comparison_or_tolerance():
    import aqorath.posting as posting

    source = inspect.getsource(posting.create_posting_instruction).lower()

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


def test_side_to_debit_credit_and_account_identity_mapping_remains_unchanged(monkeypatch):
    import aqorath.posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    instruction = posting.create_posting_instruction(_confirmed())
    debit, credit = instruction.lines

    assert (
        debit.account_role,
        debit.account_id,
        debit.account_code,
        debit.account_name,
        debit.debit,
        debit.credit,
    ) == (
        "cash",
        101,
        "TEST-CASH-001",
        "Caja principal",
        Decimal("200.00"),
        Decimal("0"),
    )
    assert (
        credit.account_role,
        credit.account_id,
        credit.account_code,
        credit.account_name,
        credit.debit,
        credit.credit,
    ) == (
        "sales_revenue",
        902,
        "TEST-SALES-900",
        "Ingresos por ventas",
        Decimal("0"),
        Decimal("200.00"),
    )


def test_invalid_side_fails_before_balance_authority(monkeypatch):
    import aqorath.posting as posting
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )
    confirmed = ConfirmedProposal(
        ConfirmationSnapshot(
            (
                ConfirmationLine("cash", 101, "C", "Caja", "other", Decimal("1")),
                ConfirmationLine("sales", 902, "S", "Ventas", "credit", Decimal("1")),
            ),
            "invalid side",
        )
    )

    with pytest.raises(ValueError):
        posting.create_posting_instruction(confirmed)

    assert calls == []


def test_invalid_amount_fails_before_balance_authority(monkeypatch):
    import aqorath.posting as posting
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )
    confirmed = ConfirmedProposal(
        ConfirmationSnapshot(
            (
                ConfirmationLine("cash", 101, "C", "Caja", "debit", Decimal("Infinity")),
                ConfirmationLine("sales", 902, "S", "Ventas", "credit", Decimal("1")),
            ),
            "invalid amount",
        )
    )

    with pytest.raises(ValueError):
        posting.create_posting_instruction(confirmed)

    assert calls == []


def test_nominal_confirmed_proposal_requirement_remains_before_balance_authority(monkeypatch):
    import aqorath.posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )

    with pytest.raises(TypeError):
        posting.create_posting_instruction(object())

    assert calls == []


def test_balance_validation_does_not_use_normal_balance_or_account_nature():
    import aqorath.posting as posting

    source = inspect.getsource(posting.create_posting_instruction).lower()
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
    import aqorath.posting as posting

    source = inspect.getsource(posting.create_posting_instruction).lower()
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


def test_convergence_does_not_add_resolution_persistence_execution_reporting_or_application():
    import aqorath.posting as posting

    source = inspect.getsource(posting).lower()
    method_source = inspect.getsource(posting.create_posting_instruction).lower()

    for forbidden in (
        "resolve_account",
        "resolve_proposal_accounts",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "post_entry",
        "execute_posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert forbidden not in method_source

    assert "aqorath.application" not in source
