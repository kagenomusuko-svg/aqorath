"""Phase 5Z.1 — fiscalized posting instruction contracts."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _confirmed(*, fiscal_amount="16.00", basis="net_before_fiscal"):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationProvenance,
        FiscalizedConfirmationSnapshot,
    )

    fiscal_amount = Decimal(fiscal_amount)
    fact_amount = Decimal("116.00") if basis == "gross_including_fiscal" else Decimal("100.00")
    cash_amount = Decimal("116.00") if fiscal_amount else Decimal("100.00")
    sales_amount = Decimal("100.00")
    adjustment_role = "sales_revenue" if basis == "gross_including_fiscal" else "cash"

    provenance = FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=fact_amount,
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
            FiscalizedConfirmationLine("cash", 1, "CASH", "Caja", "debit", cash_amount),
            FiscalizedConfirmationLine("sales_revenue", 2, "SALES", "Ventas", "credit", sales_amount),
            FiscalizedConfirmationLine("tax_payable", 3, "TAX", "Impuestos por pagar", "credit", fiscal_amount),
        ),
        explanation=(
            f"Fiscalized accounting composition: amount_basis={basis}; "
            f"adjustment_role={adjustment_role}; fiscal_role=tax_payable; "
            f"fiscal_side=credit; fiscal_amount={fiscal_amount}."
        ),
        provenance=provenance,
    )
    return ConfirmedFiscalizedProposal(snapshot=snapshot)


def test_fiscalized_posting_public_contract_and_exact_signature_exist():
    import aqorath.fiscalized_posting as posting

    assert posting.__all__ == [
        "FiscalizedPostingLine",
        "FiscalizedPostingInstruction",
        "create_fiscalized_posting_instruction",
    ]
    sig = signature(posting.create_fiscalized_posting_instruction)
    assert list(sig.parameters) == ["confirmed_proposal", "zero_fiscal_line_policy"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_nonzero_confirmed_fiscalized_truth_becomes_exact_three_line_posting_instruction():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed()
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )

    assert instruction.confirmed_proposal is confirmed
    assert instruction.description == confirmed.snapshot.explanation
    assert instruction.zero_fiscal_line_policy == "reject_zero_fiscal_line"
    assert instruction.omitted_zero_fiscal_line is None
    assert tuple(
        (
            line.account_role,
            line.account_id,
            line.account_code,
            line.account_name,
            line.debit,
            line.credit,
        )
        for line in instruction.lines
    ) == (
        ("cash", 1, "CASH", "Caja", Decimal("116.00"), Decimal("0")),
        ("sales_revenue", 2, "SALES", "Ventas", Decimal("0"), Decimal("100.00")),
        ("tax_payable", 3, "TAX", "Impuestos por pagar", Decimal("0"), Decimal("16.00")),
    )


def test_gross_confirmed_truth_preserves_same_final_posting_lines_without_recalculation():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed(basis="gross_including_fiscal")
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "omit_confirmed_zero_fiscal_line",
    )

    assert [line.debit for line in instruction.lines] == [
        Decimal("116.00"),
        Decimal("0"),
        Decimal("0"),
    ]
    assert [line.credit for line in instruction.lines] == [
        Decimal("0"),
        Decimal("100.00"),
        Decimal("16.00"),
    ]
    assert instruction.confirmed_proposal.snapshot.provenance.amount_basis == "gross_including_fiscal"


def test_zero_fiscal_line_policy_is_explicit_restricted_and_has_no_default():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed()
    for invalid in (None, "", "omit", "reject", "auto", "drop_zero"):
        with pytest.raises((TypeError, ValueError)):
            create_fiscalized_posting_instruction(confirmed, invalid)

    for allowed in (
        "reject_zero_fiscal_line",
        "omit_confirmed_zero_fiscal_line",
    ):
        instruction = create_fiscalized_posting_instruction(confirmed, allowed)
        assert instruction.zero_fiscal_line_policy == allowed


def test_zero_fiscal_line_reject_policy_fails_closed_before_instruction_creation():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed(fiscal_amount="0.00")
    with pytest.raises(ValueError, match="zero fiscal line"):
        create_fiscalized_posting_instruction(
            confirmed,
            "reject_zero_fiscal_line",
        )


def test_zero_fiscal_line_omit_policy_omits_only_confirmed_final_zero_and_keeps_audit_copy():
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationLine
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed(fiscal_amount="0.00")
    source_zero = confirmed.snapshot.lines[-1]
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "omit_confirmed_zero_fiscal_line",
    )

    assert [line.account_role for line in instruction.lines] == ["cash", "sales_revenue"]
    assert [line.debit for line in instruction.lines] == [Decimal("100.00"), Decimal("0")]
    assert [line.credit for line in instruction.lines] == [Decimal("0"), Decimal("100.00")]
    omitted = instruction.omitted_zero_fiscal_line
    assert isinstance(omitted, FiscalizedConfirmationLine)
    assert omitted is not source_zero
    assert (
        omitted.account_role,
        omitted.account_id,
        omitted.account_code,
        omitted.account_name,
        omitted.side,
        omitted.amount.as_tuple(),
    ) == (
        source_zero.account_role,
        source_zero.account_id,
        source_zero.account_code,
        source_zero.account_name,
        source_zero.side,
        source_zero.amount.as_tuple(),
    )


def test_omit_policy_never_silently_drops_nonfinal_zero_lines():
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationProvenance,
        FiscalizedConfirmationSnapshot,
    )
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    source = _confirmed(fiscal_amount="0.00").snapshot
    forged = FiscalizedConfirmationSnapshot(
        lines=(
            FiscalizedConfirmationLine("cash", 1, "CASH", "Caja", "debit", Decimal("0.00")),
            FiscalizedConfirmationLine("sales_revenue", 2, "SALES", "Ventas", "credit", Decimal("0.00")),
            source.lines[-1],
        ),
        explanation=source.explanation,
        provenance=FiscalizedConfirmationProvenance(**source.provenance.__dict__),
    )
    confirmed = ConfirmedFiscalizedProposal(forged)

    with pytest.raises(ValueError, match="non-fiscal zero"):
        create_fiscalized_posting_instruction(
            confirmed,
            "omit_confirmed_zero_fiscal_line",
        )


def test_instruction_is_deeply_immutable_and_copies_posting_and_omitted_lines_by_value():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed(fiscal_amount="0.00")
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "omit_confirmed_zero_fiscal_line",
    )

    with pytest.raises(FrozenInstanceError):
        instruction.description = "mutated"
    with pytest.raises(FrozenInstanceError):
        instruction.lines[0].debit = Decimal("999.00")
    with pytest.raises(FrozenInstanceError):
        instruction.omitted_zero_fiscal_line.amount = Decimal("1.00")
    with pytest.raises(TypeError):
        instruction.lines[0] = instruction.lines[1]

    assert instruction.lines[0] is not confirmed.snapshot.lines[0]
    assert instruction.omitted_zero_fiscal_line is not confirmed.snapshot.lines[-1]


def test_instruction_requires_nominal_confirmed_fiscalized_proposal_not_snapshot_shape_or_old_confirmation():
    from aqorath.confirmation import ConfirmedProposal, ConfirmationSnapshot
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed()
    invalid = (
        confirmed.snapshot,
        SimpleNamespace(snapshot=confirmed.snapshot),
        ConfirmedProposal(ConfirmationSnapshot(lines=(), explanation="old")),
    )
    for value in invalid:
        with pytest.raises(TypeError):
            create_fiscalized_posting_instruction(value, "reject_zero_fiscal_line")


def test_posting_instruction_preserves_decimal_identity_order_balance_and_positive_persisted_lines():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed()
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )

    assert [line.account_role for line in instruction.lines] == [
        "cash",
        "sales_revenue",
        "tax_payable",
    ]
    assert all(isinstance(line.debit, Decimal) for line in instruction.lines)
    assert all(isinstance(line.credit, Decimal) for line in instruction.lines)
    assert all((line.debit > 0) ^ (line.credit > 0) for line in instruction.lines)
    total_debit = sum((line.debit for line in instruction.lines), Decimal("0"))
    total_credit = sum((line.credit for line in instruction.lines), Decimal("0"))
    assert total_debit == total_credit == Decimal("116.00")


def test_public_instruction_type_rejects_forged_lines_policy_or_omission_metadata():
    from aqorath.fiscalized_posting import (
        FiscalizedPostingInstruction,
        FiscalizedPostingLine,
        create_fiscalized_posting_instruction,
    )

    confirmed = _confirmed()
    valid = create_fiscalized_posting_instruction(confirmed, "reject_zero_fiscal_line")
    forged_lines = (
        FiscalizedPostingLine("cash", 1, "CASH", "Caja", Decimal("100.00"), Decimal("0")),
        *valid.lines[1:],
    )
    with pytest.raises(ValueError):
        FiscalizedPostingInstruction(
            confirmed_proposal=confirmed,
            lines=forged_lines,
            description=confirmed.snapshot.explanation,
            zero_fiscal_line_policy="reject_zero_fiscal_line",
            omitted_zero_fiscal_line=None,
        )

    with pytest.raises(ValueError):
        FiscalizedPostingInstruction(
            confirmed_proposal=confirmed,
            lines=valid.lines,
            description=confirmed.snapshot.explanation,
            zero_fiscal_line_policy="omit_confirmed_zero_fiscal_line",
            omitted_zero_fiscal_line=confirmed.snapshot.lines[-1],
        )


def test_creation_is_pure_and_never_reresolves_reconfirms_recalculates_posts_or_opens_session(monkeypatch):
    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.fiscalized_account_resolution as fiscalized_resolution
    import aqorath.fiscalized_confirmation as fiscalized_confirmation
    import aqorath.storage as storage

    confirmed = _confirmed()

    def bomb(*args, **kwargs):
        raise AssertionError("forbidden authority called by fiscalized posting instruction")

    monkeypatch.setattr(account_resolution, "resolve_proposal_accounts", bomb)
    monkeypatch.setattr(catalog, "resolve_account_by_code", bomb)
    monkeypatch.setattr(core, "post_entry", bomb)
    monkeypatch.setattr(fiscal_calculation, "calculate_fiscal_rate_amount", bomb)
    monkeypatch.setattr(fiscalized_resolution, "resolve_fiscalized_proposal_accounts", bomb)
    monkeypatch.setattr(fiscalized_confirmation, "confirm_fiscalized_snapshot", bomb)
    monkeypatch.setattr(storage, "get_session", bomb)

    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )
    assert instruction.confirmed_proposal is confirmed


def test_creation_is_deterministic_and_adds_no_persistence_metadata():
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    confirmed = _confirmed()
    first = create_fiscalized_posting_instruction(confirmed, "reject_zero_fiscal_line")
    second = create_fiscalized_posting_instruction(confirmed, "reject_zero_fiscal_line")

    assert first == second
    assert first is not second
    assert first.lines[0] is not second.lines[0]
    for hidden in ("journal_entry_id", "entry_id", "posted_at", "posted_by", "state"):
        assert not hasattr(first, hidden)
