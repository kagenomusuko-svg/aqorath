"""Phase 2C.5 — PostingInstruction -> core.post_entry execution contracts."""

from decimal import Decimal
import pytest


def _instruction():
    from aqorath.account_resolution import ResolvedProposalLine, ResolvedAccountingProposal
    from aqorath.confirmation import create_confirmation_snapshot, confirm_snapshot
    from aqorath.posting import create_posting_instruction

    resolved = ResolvedAccountingProposal(
        lines=[
            ResolvedProposalLine("cash", 101, "TEST-CASH-001", "Caja principal", "debit", Decimal("200.00")),
            ResolvedProposalLine("sales_revenue", 902, "TEST-SALES-900", "Ingresos por ventas", "credit", Decimal("200.00")),
        ],
        explanation="Sale transaction: 200.00 received in cash.",
    )
    return create_posting_instruction(confirm_snapshot(create_confirmation_snapshot(resolved)))


def test_posting_execution_module_exists():
    import aqorath.posting_execution


def test_posting_execution_public_contract_and_exact_signature_exists():
    from inspect import Parameter, signature
    import aqorath.posting_execution

    assert hasattr(aqorath.posting_execution, "execute_posting_instruction")
    assert callable(aqorath.posting_execution.execute_posting_instruction)
    sig = signature(aqorath.posting_execution.execute_posting_instruction)
    assert list(sig.parameters) == ["instruction"]
    p = sig.parameters["instruction"]
    assert p.default is Parameter.empty
    assert p.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert all(x.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD) for x in sig.parameters.values())


def test_posting_execution_accepts_posting_instruction_and_delegates_once(monkeypatch):
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    calls = []
    sentinel = object()
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: calls.append(payload) or sentinel)
    result = execute_posting_instruction(_instruction())
    assert result is sentinel
    assert len(calls) == 1


def test_posting_execution_builds_exact_minimal_core_payload(monkeypatch):
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    instruction = _instruction()
    calls = []
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: calls.append(payload) or {"ok": True})
    execute_posting_instruction(instruction)

    assert len(calls) == 1
    payload = calls[0]
    assert set(payload) == {"description", "lines"}
    assert payload["description"] == instruction.description
    assert isinstance(payload["lines"], list)
    assert payload["lines"] == [
        {
            "account_id": 101,
            "account_code": "TEST-CASH-001",
            "debit": Decimal("200.00"),
            "credit": Decimal("0"),
        },
        {
            "account_id": 902,
            "account_code": "TEST-SALES-900",
            "debit": Decimal("0"),
            "credit": Decimal("200.00"),
        },
    ]


def test_posting_execution_preserves_decimal_objects_and_order(monkeypatch):
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    instruction = _instruction()
    calls = []
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: calls.append(payload) or None)
    execute_posting_instruction(instruction)
    lines = calls[0]["lines"]

    assert [line["account_code"] for line in lines] == ["TEST-CASH-001", "TEST-SALES-900"]
    assert all(isinstance(line["debit"], Decimal) for line in lines)
    assert all(isinstance(line["credit"], Decimal) for line in lines)
    assert lines[0]["debit"] is instruction.lines[0].debit
    assert lines[0]["credit"] is instruction.lines[0].credit
    assert lines[1]["debit"] is instruction.lines[1].debit
    assert lines[1]["credit"] is instruction.lines[1].credit


def test_posting_execution_requires_posting_instruction_nominally(monkeypatch):
    import types
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: pytest.fail("must not post invalid input"))
    instruction = _instruction()
    for invalid in (
        instruction.lines,
        types.SimpleNamespace(lines=instruction.lines, description=instruction.description),
        None,
    ):
        with pytest.raises((TypeError, ValueError)):
            execute_posting_instruction(invalid)


def test_posting_execution_does_not_rebuild_reresolve_lookup_or_open_session(monkeypatch):
    import importlib
    import sqlite3
    import aqorath.posting_execution as execution
    import aqorath.core
    import aqorath.posting
    import aqorath.confirmation
    import aqorath.account_resolution
    import aqorath.economic_facts
    import aqorath.catalog
    import aqorath.storage
    import aqorath.models

    instruction = _instruction()
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError("posting execution must delegate only to core.post_entry")

    class ForbiddenJournalEntry:
        def __init__(self, *args, **kwargs):
            raise AssertionError("posting execution must not create JournalEntry")

    class ForbiddenJournalLine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("posting execution must not create JournalLine")

    try:
        with monkeypatch.context() as m:
            m.setattr(aqorath.posting, "create_posting_instruction", forbidden)
            m.setattr(aqorath.confirmation, "create_confirmation_snapshot", forbidden)
            m.setattr(aqorath.confirmation, "confirm_snapshot", forbidden)
            m.setattr(aqorath.account_resolution, "resolve_proposal_accounts", forbidden)
            m.setattr(aqorath.economic_facts, "resolve_economic_fact", forbidden)
            m.setattr(aqorath.catalog, "resolve_account_by_code", forbidden)
            m.setattr(aqorath.catalog, "create_entity_account", forbidden)
            m.setattr(aqorath.storage, "get_session", forbidden)
            m.setattr(aqorath.models, "JournalEntry", ForbiddenJournalEntry)
            m.setattr(aqorath.models, "JournalLine", ForbiddenJournalLine)
            m.setattr(sqlite3, "connect", forbidden)
            m.setattr(aqorath.core, "post_entry", lambda payload: calls.append(payload) or {"ok": True})

            execution = importlib.reload(execution)
            result = execution.execute_posting_instruction(instruction)
            assert result == {"ok": True}
            assert len(calls) == 1
    finally:
        importlib.reload(execution)


def test_posting_execution_propagates_core_failure_without_retry(monkeypatch):
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    calls = []
    error = RuntimeError("persistence sentinel")

    def failing_post(payload):
        calls.append(payload)
        raise error

    monkeypatch.setattr(aqorath.core, "post_entry", failing_post)
    with pytest.raises(RuntimeError) as exc_info:
        execute_posting_instruction(_instruction())
    assert exc_info.value is error
    assert len(calls) == 1


def test_posting_execution_does_not_mutate_instruction(monkeypatch):
    import aqorath.core
    from aqorath.posting_execution import execute_posting_instruction

    instruction = _instruction()
    before = (
        instruction.description,
        tuple((line.account_role, line.account_id, line.account_code, line.account_name, line.debit, line.credit) for line in instruction.lines),
    )
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: {"ok": True})
    execute_posting_instruction(instruction)
    after = (
        instruction.description,
        tuple((line.account_role, line.account_id, line.account_code, line.account_name, line.debit, line.credit) for line in instruction.lines),
    )
    assert after == before


def test_posting_execution_uses_core_module_lookup_not_captured_function(monkeypatch):
    import aqorath.core
    import aqorath.posting_execution as execution

    calls = []
    sentinel = object()
    monkeypatch.setattr(aqorath.core, "post_entry", lambda payload: calls.append(payload) or sentinel)
    result = execution.execute_posting_instruction(_instruction())
    assert result is sentinel
    assert len(calls) == 1
