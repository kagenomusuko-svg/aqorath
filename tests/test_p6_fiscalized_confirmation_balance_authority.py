"""Phase 6BK.1 — frozen FiscalizedConfirmationSnapshot balance-authority contracts.

FiscalizedConfirmationSnapshot already validates immutable confirmed fiscalized content,
computes exact debit/credit totals from confirmation lines, and checks that ordered fiscal
lines match their value-only provenance. 6AQ established ledger_signed_balance() as the
authoritative algebraic balance function, while 6BB/6BH/6BI/6BJ converged earlier
accounting and posting boundaries onto it. This phase freezes the same convergence here
only: exact snapshot totals must be interpreted through
ledger_signed_balance(...) == Decimal("0"). Existing line, explanation, provenance, and
fiscal-line matching rules remain unchanged. No rule calculation, account resolution,
confirmation action, persistence, posting, Journal construction, reporting, or
Application behavior is added.
"""

from dataclasses import fields
from datetime import date
from decimal import Decimal
import inspect

import pytest


def _provenance(*, fiscal_amount="16.00", fiscal_role="tax_payable", fiscal_side="credit"):
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationProvenance

    fiscal_amount = Decimal(fiscal_amount)
    return FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=Decimal("100.00"),
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
        amount_basis="net_before_fiscal",
        adjustment_role="cash",
        fiscal_role=fiscal_role,
        fiscal_side=fiscal_side,
    )


def _snapshot(
    *,
    cash_amount="116.00",
    sales_amount="100.00",
    fiscal_amount="16.00",
    fiscal_line_role="tax_payable",
    fiscal_line_side="credit",
    provenance=None,
    explanation="confirmed fiscalized accounting",
):
    from aqorath.fiscalized_confirmation import (
        FiscalizedConfirmationLine,
        FiscalizedConfirmationSnapshot,
    )

    if provenance is None:
        provenance = _provenance(
            fiscal_amount=fiscal_amount,
            fiscal_role="tax_payable",
            fiscal_side="credit",
        )
    return FiscalizedConfirmationSnapshot(
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
                fiscal_line_role,
                3,
                "TAX",
                "Impuestos por pagar",
                fiscal_line_side,
                Decimal(fiscal_amount),
            ),
        ),
        explanation=explanation,
        provenance=provenance,
    )


def test_fiscalized_confirmation_public_shapes_remain_unchanged():
    import aqorath.fiscalized_confirmation as confirmation

    assert tuple(field.name for field in fields(confirmation.FiscalizedConfirmationLine)) == (
        "account_role",
        "account_id",
        "account_code",
        "account_name",
        "side",
        "amount",
    )
    assert tuple(field.name for field in fields(confirmation.FiscalizedConfirmationSnapshot)) == (
        "lines",
        "explanation",
        "provenance",
    )
    assert tuple(inspect.signature(confirmation.FiscalizedConfirmationSnapshot).parameters) == (
        "lines",
        "explanation",
        "provenance",
    )


def test_existing_balanced_snapshot_remains_valid():
    snapshot = _snapshot()

    assert tuple((line.side, line.amount) for line in snapshot.lines) == (
        ("debit", Decimal("116.00")),
        ("credit", Decimal("100.00")),
        ("credit", Decimal("16.00")),
    )
    assert snapshot.provenance.fiscal_role == "tax_payable"


def test_existing_zero_fiscal_amount_balanced_snapshot_remains_valid():
    snapshot = _snapshot(
        cash_amount="100.00",
        sales_amount="100.00",
        fiscal_amount="0.00",
    )

    assert snapshot.lines[-1].amount.as_tuple() == Decimal("0.00").as_tuple()
    assert snapshot.provenance.rounded_fiscal_amount.as_tuple() == Decimal("0.00").as_tuple()


def test_balance_validation_delegates_exact_totals_to_ledger_signed_balance(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(confirmation, "ledger_signed_balance", fake)
    _snapshot(
        cash_amount="116.0000",
        sales_amount="100.0000",
        fiscal_amount="16.0000",
        provenance=_provenance(fiscal_amount="16.0000"),
    )

    assert calls == [(Decimal("116.0000"), Decimal("116.0000"))]


def test_balance_authority_is_called_exactly_once(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    calls = []

    def fake(debit_total, credit_total):
        calls.append((debit_total, credit_total))
        return Decimal("0")

    monkeypatch.setattr(confirmation, "ledger_signed_balance", fake)
    _snapshot()

    assert len(calls) == 1


def test_authoritative_zero_accepts_raw_total_difference_when_other_snapshot_rules_hold(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    snapshot = _snapshot(cash_amount="117.00")

    assert snapshot.lines[0].amount == Decimal("117.00")
    assert sum(
        (line.amount for line in snapshot.lines if line.side == "credit"),
        Decimal("0"),
    ) == Decimal("116.00")


def test_authoritative_positive_signed_balance_rejects_matching_raw_totals(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0.0001"),
    )

    with pytest.raises(ValueError):
        _snapshot()


def test_authoritative_negative_signed_balance_rejects_matching_raw_totals(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("-0.0001"),
    )

    with pytest.raises(ValueError):
        _snapshot()


def test_arbitrarily_small_nonzero_authoritative_balance_is_not_tolerated(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal(
            "0.0000000000000000000000000001"
        ),
    )

    with pytest.raises(ValueError):
        _snapshot()


def test_convergence_uses_exact_zero_without_direct_total_comparison_or_tolerance():
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationSnapshot

    source = inspect.getsource(FiscalizedConfirmationSnapshot.__post_init__).lower()

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


def test_invalid_lines_container_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    calls = []
    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )

    with pytest.raises(ValueError):
        confirmation.FiscalizedConfirmationSnapshot(
            lines=[],
            explanation="invalid lines",
            provenance=_provenance(),
        )

    assert calls == []


def test_invalid_explanation_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    calls = []
    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )
    line = confirmation.FiscalizedConfirmationLine(
        "cash", 1, "CASH", "Caja", "debit", Decimal("1")
    )

    with pytest.raises(ValueError):
        confirmation.FiscalizedConfirmationSnapshot(
            lines=(line,),
            explanation="",
            provenance=_provenance(),
        )

    assert calls == []


def test_invalid_provenance_type_fails_before_balance_authority(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    calls = []
    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda *args: calls.append(args) or Decimal("0"),
    )
    line = confirmation.FiscalizedConfirmationLine(
        "cash", 1, "CASH", "Caja", "debit", Decimal("1")
    )

    with pytest.raises(TypeError):
        confirmation.FiscalizedConfirmationSnapshot(
            lines=(line,),
            explanation="invalid provenance",
            provenance=object(),
        )

    assert calls == []


def test_fiscal_line_provenance_matching_remains_independent_of_balance_authority(monkeypatch):
    import aqorath.fiscalized_confirmation as confirmation

    monkeypatch.setattr(
        confirmation,
        "ledger_signed_balance",
        lambda debit_total, credit_total: Decimal("0"),
    )

    with pytest.raises(ValueError, match="fiscal line role"):
        _snapshot(fiscal_line_role="tax_receivable")


def test_balance_validation_does_not_use_normal_balance_or_journal_authorities():
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationSnapshot

    source = inspect.getsource(FiscalizedConfirmationSnapshot.__post_init__).lower()
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


def test_convergence_does_not_add_rule_resolution_account_resolution_persistence_posting_reporting_or_application():
    import aqorath.fiscalized_confirmation as confirmation

    method_source = inspect.getsource(
        confirmation.FiscalizedConfirmationSnapshot.__post_init__
    ).lower()
    module_source = inspect.getsource(confirmation).lower()

    for forbidden in (
        "calculate_fiscal",
        "resolve_account",
        "resolve_fiscalized_proposal_accounts(",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "post_entry",
        "create_fiscalized_posting_instruction(",
        "execute_fiscalized_posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert forbidden not in method_source

    assert "aqorath.application" not in module_source
