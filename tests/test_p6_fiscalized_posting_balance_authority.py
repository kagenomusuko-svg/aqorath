"""Phase 6BJ.1 — frozen FiscalizedPostingInstruction balance-authority contracts.

FiscalizedPostingInstruction already validates exact confirmed fiscalized provenance,
zero-fiscal-line policy, omission audit metadata, source-line identity by value, and
exact debit/credit totals. 6AQ established ledger_signed_balance() as the authoritative
algebraic balance function, while 6BB/6BH/6BI converged earlier accounting and posting
boundaries onto it. This phase freezes the same convergence here only: after all existing
fiscalized-posting structure checks succeed, totals must be interpreted through
ledger_signed_balance(...) == Decimal("0"). No recalculation, re-resolution,
reconfirmation, persistence, posting execution, Journal construction, reporting, or
Application behavior is added.
"""

from dataclasses import fields
from datetime import date
from decimal import Decimal
import inspect

import pytest


def _confirmed(
    *,
    cash_amount="116.00",
    sales_amount="100.00",
    fiscal_amount="16.00",
    basis="net_before_fiscal",
):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationProvenance,
        FiscalizedConfirmationSnapshot,
    )

    fiscal_amount = Decimal(fiscal_amount)
    fact_amount = (
        Decimal("116.00")
        if basis == "gross_including_fiscal"
        else Decimal("100.00")
    )
    adjustment_role = (
        "sales_revenue" if basis == "gross_including_fiscal" else "cash"
    )
    provenance = FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=fact_amount,
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
        exact_fiscal_amount=fiscal_amount,
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="TEST:ROUNDING",
        rounded_fiscal_amount=fiscal_amount,
        amount_basis=basis,
        adjustment_role=adjustment_role,
        fiscal_role="tax_payable",
        fiscal_side="credit",
    )
    snapshot = FiscalizedConfirmationSnapshot(
        lines=(
            FiscalizedConfirmationLine(
                "cash", 1, "CASH", "Caja", "debit", Decimal(cash_amount)
            ),
            FiscalizedConfirmationLine(
                "sales_revenue",
                2,
                "SALES",
                "Ventas",
                "credit",
                Decimal(sales_amount),
            ),
            FiscalizedConfirmationLine(
                "tax_payable",
                3,
                "TAX",
                "Impuestos por pagar",
                "credit",
                fiscal_amount,
            ),
        ),
        explanation=(
            f"Fiscalized accounting composition: amount_basis={basis}; "
            f"adjustment_role={adjustment_role}; fiscal_role=tax_payable; "
            f"fiscal_side=credit; fiscal_amount={fiscal_amount}."
        ),
        provenance=provenance,
    )
    return ConfirmedFiscalizedProposal(snapshot=snapshot)


def _create(confirmed=None, policy="reject_zero_fiscal_line"):
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    if confirmed is None:
        confirmed = _confirmed()
    return create_fiscalized_posting_instruction(confirmed, policy)


def test_fiscalized_posting_public_shapes_remain_unchanged():
    import aqorath.fiscalized_posting as posting

    assert tuple(field.name for field in fields(posting.FiscalizedPostingLine)) == (
        "account_role",
        "account_id",
        "account_code",
        "account_name",
        "debit",
        "credit",
    )
    assert tuple(field.name for field in fields(posting.FiscalizedPostingInstruction)) == (
        "confirmed_proposal",
        "lines",
        "description",
        "zero_fiscal_line_policy",
        "omitted_zero_fiscal_line",
    )
    assert tuple(
        inspect.signature(posting.create_fiscalized_posting_instruction).parameters
    ) == ("confirmed_proposal", "zero_fiscal_line_policy")


def test_existing_nonzero_balanced_instruction_remains_valid():
    instruction = _create()

    assert tuple((line.debit, line.credit) for line in instruction.lines) == (
        (Decimal("116.00"), Decimal("0")),
        (Decimal("0"), Decimal("100.00")),
        (Decimal("0"), Decimal("16.00")),
    )
    assert instruction.omitted_zero_fiscal_line is None


def test_existing_confirmed_zero_omission_remains_valid():
    instruction = _create(
        _confirmed(cash_amount="100.00", fiscal_amount="0.00"),
        "omit_confirmed_zero_fiscal_line",
    )

    assert tuple((line.debit, line.credit) for line in instruction.lines) == (
        (Decimal("100.00"), Decimal("0")),
        (Decimal("0"), Decimal("100.00")),
    )
    assert instruction.omitted_zero_fiscal_line.amount.as_tuple() == Decimal(
        "0.00"
    ).as_tuple()


def test_balance_validation_delegates_exact_totals_to_ledger_signed_balance(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(posting, "ledger_signed_balance", fake)
    _create()

    assert calls == [(Decimal("116.00"), Decimal("116.00"))]


def test_zero_omission_delegates_exact_remaining_totals(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: calls.append(
            (debit_total, credit_total)
        ) or Decimal("0"),
    )

    _create(
        _confirmed(cash_amount="100.00", fiscal_amount="0.00"),
        "omit_confirmed_zero_fiscal_line",
    )

    assert calls == [(Decimal("100.00"), Decimal("100.00"))]


def test_balance_authority_is_called_exactly_once(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(posting, "ledger_signed_balance", fake)
    _create()

    assert len(calls) == 1


def test_unbalanced_confirmation_is_rejected_before_posting_authority(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: calls.append(
            (debit_total, credit_total)
        ) or Decimal("0"),
    )

    # Phase 6BK.2 made the confirmation snapshot itself an exact balance boundary.
    # Therefore an unbalanced confirmed input can no longer be fabricated here to
    # exercise a raw-total override at the later posting boundary.
    with pytest.raises(ValueError, match="confirmation snapshot must be balanced"):
        _confirmed(cash_amount="117.00")

    assert calls == []


def test_authoritative_positive_signed_balance_rejects_matching_raw_totals(monkeypatch):
    import aqorath.fiscalized_posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0.0001"),
    )

    with pytest.raises(ValueError):
        _create()


def test_authoritative_negative_signed_balance_rejects_matching_raw_totals(monkeypatch):
    import aqorath.fiscalized_posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("-0.0001"),
    )

    with pytest.raises(ValueError):
        _create()


def test_arbitrarily_small_nonzero_authoritative_balance_is_not_tolerated(monkeypatch):
    import aqorath.fiscalized_posting as posting

    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal(
            "0.0000000000000000000000000001"
        ),
    )

    with pytest.raises(ValueError):
        _create()


def test_convergence_uses_exact_zero_without_direct_total_comparison_or_tolerance():
    from aqorath.fiscalized_posting import FiscalizedPostingInstruction

    source = inspect.getsource(FiscalizedPostingInstruction.__post_init__).lower()

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


def test_invalid_zero_policy_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )

    with pytest.raises(ValueError):
        posting.create_fiscalized_posting_instruction(_confirmed(), "auto")

    assert calls == []


def test_non_fiscal_zero_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )

    with pytest.raises(ValueError):
        _create(
            _confirmed(cash_amount="0.00", sales_amount="0.00", fiscal_amount="0.00"),
            "omit_confirmed_zero_fiscal_line",
        )

    assert calls == []


def test_exact_source_line_matching_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_posting as posting

    calls = []
    monkeypatch.setattr(
        posting,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )
    valid = _create()
    calls.clear()
    first = valid.lines[0]
    forged_first = posting.FiscalizedPostingLine(
        first.account_role,
        first.account_id,
        first.account_code,
        first.account_name,
        first.debit + Decimal("1.00"),
        first.credit,
    )

    with pytest.raises(ValueError):
        posting.FiscalizedPostingInstruction(
            confirmed_proposal=valid.confirmed_proposal,
            lines=(forged_first, *valid.lines[1:]),
            description=valid.description,
            zero_fiscal_line_policy=valid.zero_fiscal_line_policy,
            omitted_zero_fiscal_line=valid.omitted_zero_fiscal_line,
        )

    assert calls == []


def test_balance_validation_does_not_use_normal_balance_or_journal_authorities():
    from aqorath.fiscalized_posting import FiscalizedPostingInstruction

    source = inspect.getsource(FiscalizedPostingInstruction.__post_init__).lower()
    for forbidden in (
        "normal_balance_amount",
        "normal_balance_for_account",
        "journal_line_normal_balance",
        "journal_line_totals",
        "journal_line_signed_balance",
        "journal_lines_signed_balance",
        "journal_lines_are_balanced",
        "journal_entry_totals",
        "journal_entry_signed_balance",
        ".nature",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source


def test_convergence_does_not_add_resolution_reconfirmation_persistence_execution_reporting_or_application():
    import aqorath.fiscalized_posting as posting

    method_source = inspect.getsource(
        posting.FiscalizedPostingInstruction.__post_init__
    ).lower()
    module_source = inspect.getsource(posting).lower()

    for forbidden in (
        "resolve_account",
        "resolve_fiscalized_proposal_accounts",
        "calculate_fiscal",
        "confirm_fiscalized_snapshot",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "post_entry",
        "execute_fiscalized_posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert forbidden not in method_source

    assert "aqorath.application" not in module_source
