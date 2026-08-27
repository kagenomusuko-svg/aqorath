"""Phase 5AD.1 — immutable fiscal posting audit snapshot contracts."""

import builtins
import dataclasses
import inspect
import sqlite3
from datetime import date
from decimal import Decimal

import pytest


def _provenance(*, rounded="16.00"):
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationProvenance

    return FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=Decimal("100.00") if rounded != "0.00" else Decimal("100.00"),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="commercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal("0.16") if rounded != "0.00" else Decimal("0.00"),
        unit="rate",
        rule_effective_from=date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref="CURATED:IVA",
        exact_fiscal_amount=Decimal(rounded),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="EXPLICIT:TEST",
        rounded_fiscal_amount=Decimal(rounded),
        amount_basis="net_before_fiscal",
        adjustment_role="cash",
        fiscal_role="tax_payable",
        fiscal_side="credit",
    )


def _instruction(*, rounded="16.00", policy="reject_zero_fiscal_line"):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationSnapshot,
    )
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    fiscal_amount = Decimal(rounded)
    cash_amount = Decimal("100.00") + fiscal_amount
    lines = (
        FiscalizedConfirmationLine(
            account_role="cash",
            account_id=1,
            account_code="1102",
            account_name="Caja chica",
            side="debit",
            amount=cash_amount,
        ),
        FiscalizedConfirmationLine(
            account_role="sales_revenue",
            account_id=2,
            account_code="4201",
            account_name="Venta de productos elaborados",
            side="credit",
            amount=Decimal("100.00"),
        ),
        FiscalizedConfirmationLine(
            account_role="tax_payable",
            account_id=3,
            account_code="2103",
            account_name="Impuestos por pagar",
            side="credit",
            amount=fiscal_amount,
        ),
    )
    snapshot = FiscalizedConfirmationSnapshot(
        lines=lines,
        explanation="Venta fiscalizada confirmada",
        provenance=_provenance(rounded=rounded),
    )
    confirmed = ConfirmedFiscalizedProposal(snapshot=snapshot)
    return create_fiscalized_posting_instruction(confirmed, policy)


def test_fiscal_posting_audit_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_posting_audit as audit

    assert dataclasses.is_dataclass(audit.FiscalPostingAuditSnapshot)
    assert dataclasses.is_dataclass(audit.FiscalPostingAuditOmittedLine)
    assert callable(audit.create_fiscal_posting_audit_snapshot)
    assert list(inspect.signature(audit.create_fiscal_posting_audit_snapshot).parameters) == [
        "instruction"
    ]


def test_audit_snapshot_copies_exact_positive_instruction_provenance_by_value():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction()
    result = audit.create_fiscal_posting_audit_snapshot(instruction)
    source = instruction.confirmed_proposal.snapshot

    assert result.description == source.explanation
    assert result.provenance == source.provenance
    assert result.provenance is not source.provenance
    assert result.zero_fiscal_line_policy == "reject_zero_fiscal_line"
    assert result.omitted_zero_fiscal_line is None


def test_audit_snapshot_preserves_every_fiscal_provenance_field_exactly():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction()
    result = audit.create_fiscal_posting_audit_snapshot(instruction)
    p = result.provenance

    assert p.fact_type == "sale"
    assert p.fact_amount.as_tuple() == Decimal("100.00").as_tuple()
    assert p.payment_method == "cash"
    assert p.effective_date == date(2026, 8, 27)
    assert (p.jurisdiction, p.regime, p.entity_type) == ("MX", "general", "commercial")
    assert p.rule_key == "iva.general_rate"
    assert p.base.as_tuple() == Decimal("100.00").as_tuple()
    assert p.rate.as_tuple() == Decimal("0.16").as_tuple()
    assert p.unit == "rate"
    assert p.rule_effective_from == date(2010, 1, 1)
    assert p.rule_effective_to is None
    assert p.rule_source_ref == "CURATED:IVA"
    assert p.exact_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    assert p.rounding_policy_key == "two-decimals"
    assert p.rounding_quantizer.as_tuple() == Decimal("0.01").as_tuple()
    assert p.rounding_mode == "ROUND_HALF_UP"
    assert p.rounding_source_ref == "EXPLICIT:TEST"
    assert p.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    assert p.amount_basis == "net_before_fiscal"
    assert p.adjustment_role == "cash"
    assert p.fiscal_role == "tax_payable"
    assert p.fiscal_side == "credit"


def test_zero_omission_audit_preserves_exact_confirmed_omitted_line_by_value():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction(
        rounded="0.00",
        policy="omit_confirmed_zero_fiscal_line",
    )
    result = audit.create_fiscal_posting_audit_snapshot(instruction)
    source = instruction.omitted_zero_fiscal_line

    assert result.zero_fiscal_line_policy == "omit_confirmed_zero_fiscal_line"
    assert result.provenance.rounded_fiscal_amount.as_tuple() == Decimal("0.00").as_tuple()
    assert result.omitted_zero_fiscal_line is not None
    assert result.omitted_zero_fiscal_line.account_role == "tax_payable"
    assert result.omitted_zero_fiscal_line.account_id == 3
    assert result.omitted_zero_fiscal_line.account_code == "2103"
    assert result.omitted_zero_fiscal_line.account_name == "Impuestos por pagar"
    assert result.omitted_zero_fiscal_line.side == "credit"
    assert result.omitted_zero_fiscal_line.amount.as_tuple() == Decimal("0.00").as_tuple()
    assert result.omitted_zero_fiscal_line is not source


def test_audit_snapshot_is_deeply_immutable_and_independent_from_source_mutation():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction()
    result = audit.create_fiscal_posting_audit_snapshot(instruction)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.description = "forged"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.provenance.rule_key = "forged"

    source_provenance = instruction.confirmed_proposal.snapshot.provenance
    object.__setattr__(source_provenance, "rule_key", "mutated.after.audit")
    object.__setattr__(source_provenance, "rounded_fiscal_amount", Decimal("99.99"))

    assert result.provenance.rule_key == "iva.general_rate"
    assert result.provenance.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()


def test_audit_snapshot_preserves_decimal_scale_without_float_conversion():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction()
    result = audit.create_fiscal_posting_audit_snapshot(instruction)

    for source_value, copied_value in (
        (instruction.confirmed_proposal.snapshot.provenance.fact_amount, result.provenance.fact_amount),
        (instruction.confirmed_proposal.snapshot.provenance.base, result.provenance.base),
        (instruction.confirmed_proposal.snapshot.provenance.rate, result.provenance.rate),
        (instruction.confirmed_proposal.snapshot.provenance.exact_fiscal_amount, result.provenance.exact_fiscal_amount),
        (instruction.confirmed_proposal.snapshot.provenance.rounding_quantizer, result.provenance.rounding_quantizer),
        (instruction.confirmed_proposal.snapshot.provenance.rounded_fiscal_amount, result.provenance.rounded_fiscal_amount),
    ):
        assert isinstance(copied_value, Decimal)
        assert copied_value.as_tuple() == source_value.as_tuple()


def test_audit_snapshot_requires_nominal_fiscalized_posting_instruction():
    import aqorath.fiscal_posting_audit as audit

    fake = type(
        "FakeInstruction",
        (),
        {
            "description": "shape",
            "confirmed_proposal": object(),
            "zero_fiscal_line_policy": "reject_zero_fiscal_line",
            "omitted_zero_fiscal_line": None,
        },
    )()

    with pytest.raises(TypeError, match="FiscalizedPostingInstruction"):
        audit.create_fiscal_posting_audit_snapshot(fake)


def test_public_audit_types_fail_closed_on_inconsistent_zero_policy_or_omission_metadata():
    import aqorath.fiscal_posting_audit as audit

    positive = _provenance(rounded="16.00")
    zero = _provenance(rounded="0.00")
    omitted = audit.FiscalPostingAuditOmittedLine(
        account_role="tax_payable",
        account_id=3,
        account_code="2103",
        account_name="Impuestos por pagar",
        side="credit",
        amount=Decimal("0.00"),
    )

    with pytest.raises(ValueError):
        audit.FiscalPostingAuditSnapshot(
            description="x",
            provenance=zero,
            zero_fiscal_line_policy="reject_zero_fiscal_line",
            omitted_zero_fiscal_line=None,
        )
    with pytest.raises(ValueError):
        audit.FiscalPostingAuditSnapshot(
            description="x",
            provenance=zero,
            zero_fiscal_line_policy="omit_confirmed_zero_fiscal_line",
            omitted_zero_fiscal_line=None,
        )
    with pytest.raises(ValueError):
        audit.FiscalPostingAuditSnapshot(
            description="x",
            provenance=positive,
            zero_fiscal_line_policy="reject_zero_fiscal_line",
            omitted_zero_fiscal_line=omitted,
        )
    with pytest.raises(ValueError):
        audit.FiscalPostingAuditSnapshot(
            description="x",
            provenance=positive,
            zero_fiscal_line_policy="unknown",
            omitted_zero_fiscal_line=None,
        )


def test_public_audit_types_validate_omitted_line_against_fiscal_provenance():
    import aqorath.fiscal_posting_audit as audit

    zero = _provenance(rounded="0.00")

    for kwargs in (
        {"account_role": "wrong", "side": "credit", "amount": Decimal("0.00")},
        {"account_role": "tax_payable", "side": "debit", "amount": Decimal("0.00")},
        {"account_role": "tax_payable", "side": "credit", "amount": Decimal("1.00")},
    ):
        omitted = audit.FiscalPostingAuditOmittedLine(
            account_role=kwargs["account_role"],
            account_id=3,
            account_code="2103",
            account_name="Impuestos por pagar",
            side=kwargs["side"],
            amount=kwargs["amount"],
        )
        with pytest.raises(ValueError):
            audit.FiscalPostingAuditSnapshot(
                description="x",
                provenance=zero,
                zero_fiscal_line_policy="omit_confirmed_zero_fiscal_line",
                omitted_zero_fiscal_line=omitted,
            )


def test_audit_snapshot_is_metadata_only_not_posting_instruction_or_accounting_payload():
    import aqorath.fiscal_posting_audit as audit
    from aqorath.fiscalized_posting import FiscalizedPostingInstruction

    result = audit.create_fiscal_posting_audit_snapshot(_instruction())

    assert not isinstance(result, FiscalizedPostingInstruction)
    assert not hasattr(result, "lines")
    assert not hasattr(result, "account_bindings")
    assert not hasattr(result, "entry_id")
    assert set(field.name for field in dataclasses.fields(result)) == {
        "description",
        "provenance",
        "zero_fiscal_line_policy",
        "omitted_zero_fiscal_line",
    }


def test_audit_creation_is_pure_and_never_queries_persists_posts_or_opens_session(monkeypatch):
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_execution as execution
    import aqorath.storage as storage

    instruction = _instruction()

    def forbidden(*args, **kwargs):
        raise AssertionError("audit snapshot creation must be pure")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(catalog, "resolve_account_by_code", forbidden)
    monkeypatch.setattr(core, "post_entry", forbidden)
    monkeypatch.setattr(execution, "execute_fiscalized_posting_instruction", forbidden)

    result = audit.create_fiscal_posting_audit_snapshot(instruction)
    assert result.description == instruction.description


def test_audit_creation_is_deterministic_and_does_not_mutate_instruction():
    import aqorath.fiscal_posting_audit as audit

    instruction = _instruction()
    before = repr(instruction)
    first = audit.create_fiscal_posting_audit_snapshot(instruction)
    second = audit.create_fiscal_posting_audit_snapshot(instruction)

    assert first == second
    assert first is not second
    assert repr(instruction) == before
