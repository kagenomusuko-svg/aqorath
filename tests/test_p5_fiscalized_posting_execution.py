"""Phase 5AA.1 — fiscalized posting execution contracts."""

from datetime import date
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest


def _instruction(*, fiscal_amount="16.00", policy="reject_zero_fiscal_line"):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationProvenance,
        FiscalizedConfirmationSnapshot,
    )
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    fiscal_amount = Decimal(fiscal_amount)
    cash_amount = Decimal("116.00") if fiscal_amount else Decimal("100.00")

    provenance = FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=Decimal("100.00"),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="comercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal("0.16") if fiscal_amount else Decimal("0.00"),
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
        fiscal_role="tax_payable",
        fiscal_side="credit",
    )
    snapshot = FiscalizedConfirmationSnapshot(
        lines=(
            FiscalizedConfirmationLine(
                "cash", 101, "CASH", "Caja", "debit", cash_amount
            ),
            FiscalizedConfirmationLine(
                "sales_revenue",
                202,
                "SALES",
                "Ventas",
                "credit",
                Decimal("100.00"),
            ),
            FiscalizedConfirmationLine(
                "tax_payable",
                303,
                "TAX",
                "IVA por pagar",
                "credit",
                fiscal_amount,
            ),
        ),
        explanation=(
            "Fiscalized accounting composition: amount_basis=net_before_fiscal; "
            "adjustment_role=cash; fiscal_role=tax_payable; fiscal_side=credit; "
            f"fiscal_amount={fiscal_amount}."
        ),
        provenance=provenance,
    )
    confirmed = ConfirmedFiscalizedProposal(snapshot=snapshot)
    return create_fiscalized_posting_instruction(confirmed, policy)


def test_fiscalized_posting_execution_public_contract_and_exact_signature_exist():
    import aqorath.fiscalized_posting_execution as execution

    assert execution.__all__ == ["execute_fiscalized_posting_instruction"]
    fn = execution.execute_fiscalized_posting_instruction
    sig = signature(fn)
    assert list(sig.parameters) == ["instruction"]
    p = sig.parameters["instruction"]
    assert p.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert p.default is Parameter.empty


def test_execution_accepts_fiscalized_instruction_delegates_once_and_returns_exact_core_result(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []
    sentinel = object()

    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or sentinel,
    )

    result = execute_fiscalized_posting_instruction(instruction)

    assert result is sentinel
    assert len(calls) == 1


def test_execution_builds_exact_minimal_three_line_core_payload(monkeypatch):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []
    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or {"ok": True},
    )

    execute_fiscalized_posting_instruction(instruction)

    assert calls == [
        {
            "description": instruction.description,
            "lines": [
                {
                    "account_id": 101,
                    "account_code": "CASH",
                    "debit": Decimal("116.00"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": 202,
                    "account_code": "SALES",
                    "debit": Decimal("0"),
                    "credit": Decimal("100.00"),
                },
                {
                    "account_id": 303,
                    "account_code": "TAX",
                    "debit": Decimal("0"),
                    "credit": Decimal("16.00"),
                },
            ],
        }
    ]


def test_execution_of_explicit_zero_omission_posts_only_remaining_confirmed_positive_lines(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction(
        fiscal_amount="0.00",
        policy="omit_confirmed_zero_fiscal_line",
    )
    assert instruction.omitted_zero_fiscal_line is not None
    calls = []
    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or {"ok": True},
    )

    execute_fiscalized_posting_instruction(instruction)

    payload = calls[0]
    assert [line["account_code"] for line in payload["lines"]] == ["CASH", "SALES"]
    assert payload["lines"] == [
        {
            "account_id": 101,
            "account_code": "CASH",
            "debit": Decimal("100.00"),
            "credit": Decimal("0"),
        },
        {
            "account_id": 202,
            "account_code": "SALES",
            "debit": Decimal("0"),
            "credit": Decimal("100.00"),
        },
    ]


def test_execution_preserves_decimal_objects_and_line_order(monkeypatch):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []
    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or None,
    )

    execute_fiscalized_posting_instruction(instruction)
    payload_lines = calls[0]["lines"]

    assert [line["account_code"] for line in payload_lines] == [
        "CASH",
        "SALES",
        "TAX",
    ]
    for payload_line, source_line in zip(payload_lines, instruction.lines):
        assert payload_line["debit"] is source_line.debit
        assert payload_line["credit"] is source_line.credit
        assert isinstance(payload_line["debit"], Decimal)
        assert isinstance(payload_line["credit"], Decimal)


def test_execution_requires_nominal_fiscalized_instruction_not_shape_old_or_prior_stage(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_confirmation import ConfirmedFiscalizedProposal
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )
    from aqorath.posting import PostingInstruction, PostingLine

    instruction = _instruction()
    old_instruction = PostingInstruction(
        lines=(
            PostingLine(
                "cash",
                1,
                "OLD-CASH",
                "Caja",
                Decimal("1.00"),
                Decimal("0"),
            ),
            PostingLine(
                "sales_revenue",
                2,
                "OLD-SALES",
                "Ventas",
                Decimal("0"),
                Decimal("1.00"),
            ),
        ),
        description="historical",
    )

    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: pytest.fail("invalid input must not reach core.post_entry"),
    )

    for invalid in (
        instruction.lines,
        SimpleNamespace(
            lines=instruction.lines,
            description=instruction.description,
        ),
        old_instruction,
        instruction.confirmed_proposal,
        instruction.confirmed_proposal.snapshot,
        None,
    ):
        with pytest.raises(TypeError):
            execute_fiscalized_posting_instruction(invalid)

    assert isinstance(
        instruction.confirmed_proposal,
        ConfirmedFiscalizedProposal,
    )


def test_execution_payload_does_not_leak_policy_provenance_or_omitted_audit_metadata(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction(
        fiscal_amount="0.00",
        policy="omit_confirmed_zero_fiscal_line",
    )
    calls = []
    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or {"ok": True},
    )

    execute_fiscalized_posting_instruction(instruction)
    payload = calls[0]

    assert set(payload) == {"description", "lines"}
    for forbidden in (
        "zero_fiscal_line_policy",
        "omitted_zero_fiscal_line",
        "confirmed_proposal",
        "provenance",
        "rule_key",
        "rounding_policy_key",
    ):
        assert forbidden not in payload

    assert all(
        set(line) == {"account_id", "account_code", "debit", "credit"}
        for line in payload["lines"]
    )


def test_execution_calls_only_core_post_entry_and_never_rebuilds_or_uses_other_authorities(
    monkeypatch,
):
    import sqlite3

    import aqorath.account_resolution as account_resolution
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.fiscalized_account_resolution as fiscalized_resolution
    import aqorath.fiscalized_confirmation as fiscalized_confirmation
    import aqorath.fiscalized_posting as fiscalized_posting
    import aqorath.models as models
    import aqorath.posting_execution as posting_execution
    import aqorath.storage as storage
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden authority called during fiscalized posting execution")

    class ForbiddenJournalEntry:
        def __init__(self, *args, **kwargs):
            raise AssertionError("execution must not construct JournalEntry directly")

    class ForbiddenJournalLine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("execution must not construct JournalLine directly")

    monkeypatch.setattr(
        account_resolution,
        "resolve_proposal_accounts",
        forbidden,
    )
    monkeypatch.setattr(catalog, "resolve_account_by_code", forbidden)
    monkeypatch.setattr(
        fiscal_calculation,
        "calculate_fiscal_rate_amount",
        forbidden,
    )
    monkeypatch.setattr(
        fiscalized_resolution,
        "resolve_fiscalized_proposal_accounts",
        forbidden,
    )
    monkeypatch.setattr(
        fiscalized_confirmation,
        "confirm_fiscalized_snapshot",
        forbidden,
    )
    monkeypatch.setattr(
        fiscalized_posting,
        "create_fiscalized_posting_instruction",
        forbidden,
    )
    monkeypatch.setattr(
        posting_execution,
        "execute_posting_instruction",
        forbidden,
    )
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(models, "JournalEntry", ForbiddenJournalEntry)
    monkeypatch.setattr(models, "JournalLine", ForbiddenJournalLine)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or {"ok": True},
    )

    result = execute_fiscalized_posting_instruction(instruction)

    assert result == {"ok": True}
    assert len(calls) == 1


def test_execution_propagates_core_exception_without_retry(monkeypatch):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []
    error = RuntimeError("posting sentinel")

    def failing_post(payload):
        calls.append(payload)
        raise error

    monkeypatch.setattr(core, "post_entry", failing_post)

    with pytest.raises(RuntimeError) as exc_info:
        execute_fiscalized_posting_instruction(instruction)

    assert exc_info.value is error
    assert len(calls) == 1


def test_execution_returns_core_failure_result_verbatim_without_retry_or_translation(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    calls = []
    failure = {"ok": False, "error": "sentinel"}

    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or failure,
    )

    result = execute_fiscalized_posting_instruction(instruction)

    assert result is failure
    assert len(calls) == 1


def test_execution_does_not_mutate_instruction_confirmed_snapshot_or_provenance(
    monkeypatch,
):
    import aqorath.core as core
    from aqorath.fiscalized_posting_execution import (
        execute_fiscalized_posting_instruction,
    )

    instruction = _instruction()
    before = (
        instruction.description,
        instruction.zero_fiscal_line_policy,
        instruction.omitted_zero_fiscal_line,
        tuple(
            (
                line.account_role,
                line.account_id,
                line.account_code,
                line.account_name,
                line.debit.as_tuple(),
                line.credit.as_tuple(),
            )
            for line in instruction.lines
        ),
        instruction.confirmed_proposal.snapshot,
        instruction.confirmed_proposal.snapshot.provenance,
    )

    monkeypatch.setattr(core, "post_entry", lambda payload: {"ok": True})

    execute_fiscalized_posting_instruction(instruction)

    after = (
        instruction.description,
        instruction.zero_fiscal_line_policy,
        instruction.omitted_zero_fiscal_line,
        tuple(
            (
                line.account_role,
                line.account_id,
                line.account_code,
                line.account_name,
                line.debit.as_tuple(),
                line.credit.as_tuple(),
            )
            for line in instruction.lines
        ),
        instruction.confirmed_proposal.snapshot,
        instruction.confirmed_proposal.snapshot.provenance,
    )
    assert after == before


def test_execution_uses_core_module_lookup_not_captured_function_alias(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscalized_posting_execution as execution

    calls = []
    sentinel = object()

    monkeypatch.setattr(
        core,
        "post_entry",
        lambda payload: calls.append(payload) or sentinel,
    )

    result = execution.execute_fiscalized_posting_instruction(_instruction())

    assert result is sentinel
    assert len(calls) == 1
