"""Phase 2C.3 — pure ConfirmedProposal -> PostingInstruction contracts."""

from decimal import Decimal
import pytest


def _confirmed():
    from aqorath.account_resolution import ResolvedProposalLine, ResolvedAccountingProposal
    from aqorath.confirmation import create_confirmation_snapshot, confirm_snapshot

    resolved = ResolvedAccountingProposal(
        lines=[
            ResolvedProposalLine("cash", 101, "TEST-CASH-001", "Caja principal", "debit", Decimal("200.00")),
            ResolvedProposalLine("sales_revenue", 902, "TEST-SALES-900", "Ingresos por ventas", "credit", Decimal("200.00")),
        ],
        explanation="Sale transaction: 200.00 received in cash.",
    )
    return confirm_snapshot(create_confirmation_snapshot(resolved))


def test_posting_module_exists():
    import aqorath.posting


def test_posting_public_contract_and_exact_signature_exists():
    from dataclasses import fields
    from inspect import Parameter, signature
    import aqorath.posting

    assert [f.name for f in fields(aqorath.posting.PostingLine)] == [
        "account_role", "account_id", "account_code", "account_name", "debit", "credit"
    ]
    assert [f.name for f in fields(aqorath.posting.PostingInstruction)] == ["lines", "description"]
    assert callable(aqorath.posting.create_posting_instruction)

    sig = signature(aqorath.posting.create_posting_instruction)
    assert list(sig.parameters) == ["confirmed_proposal"]
    p = sig.parameters["confirmed_proposal"]
    assert p.default is Parameter.empty
    assert p.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert all(x.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD) for x in sig.parameters.values())


def test_posting_instruction_accepts_confirmed_proposal():
    from aqorath.posting import create_posting_instruction, PostingInstruction

    instruction = create_posting_instruction(_confirmed())
    assert isinstance(instruction, PostingInstruction)
    assert isinstance(instruction.lines, tuple)
    assert len(instruction.lines) == 2


def test_posting_instruction_preserves_account_identity_role_and_order():
    from aqorath.posting import create_posting_instruction, PostingLine

    cash, sales = create_posting_instruction(_confirmed()).lines
    assert isinstance(cash, PostingLine)
    assert (cash.account_role, cash.account_id, cash.account_code, cash.account_name) == (
        "cash", 101, "TEST-CASH-001", "Caja principal"
    )
    assert isinstance(sales, PostingLine)
    assert (sales.account_role, sales.account_id, sales.account_code, sales.account_name) == (
        "sales_revenue", 902, "TEST-SALES-900", "Ingresos por ventas"
    )


def test_posting_instruction_converts_sides_to_exact_decimal_debit_credit():
    from aqorath.posting import create_posting_instruction

    cash, sales = create_posting_instruction(_confirmed()).lines
    assert (cash.debit, cash.credit) == (Decimal("200.00"), Decimal("0"))
    assert (sales.debit, sales.credit) == (Decimal("0"), Decimal("200.00"))
    assert all(isinstance(v, Decimal) for v in (cash.debit, cash.credit, sales.debit, sales.credit))
    assert not hasattr(cash, "side") and not hasattr(cash, "amount")


def test_posting_instruction_preserves_exact_balance_and_confirmed_description():
    from aqorath.posting import create_posting_instruction

    confirmed = _confirmed()
    instruction = create_posting_instruction(confirmed)
    debit = sum((line.debit for line in instruction.lines), Decimal("0"))
    credit = sum((line.credit for line in instruction.lines), Decimal("0"))
    assert debit == credit == Decimal("200.00")
    assert instruction.description == confirmed.snapshot.explanation


def test_posting_instruction_is_deeply_immutable_and_copies_lines_by_value():
    from dataclasses import FrozenInstanceError
    from aqorath.confirmation import ConfirmationLine
    from aqorath.posting import create_posting_instruction, PostingLine

    confirmed = _confirmed()
    instruction = create_posting_instruction(confirmed)
    assert isinstance(instruction.lines, tuple)
    for source, posted in zip(confirmed.snapshot.lines, instruction.lines):
        assert isinstance(source, ConfirmationLine)
        assert isinstance(posted, PostingLine)
        assert posted is not source
        assert not isinstance(posted, ConfirmationLine)
    with pytest.raises(FrozenInstanceError):
        instruction.description = "changed"
    with pytest.raises(FrozenInstanceError):
        instruction.lines = ()
    with pytest.raises(TypeError):
        instruction.lines[0] = instruction.lines[1]
    with pytest.raises(FrozenInstanceError):
        instruction.lines[0].debit = Decimal("999")


def test_posting_instruction_requires_confirmed_proposal_nominally():
    import types
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import ResolvedAccountingProposal
    from aqorath.posting import create_posting_instruction

    semantic = resolve_economic_fact(EconomicFact("sale", Decimal("200.00"), "cash"))
    confirmed = _confirmed()
    for invalid in (
        semantic,
        ResolvedAccountingProposal(lines=[], explanation="resolved"),
        confirmed.snapshot,
        types.SimpleNamespace(snapshot=confirmed.snapshot),
    ):
        with pytest.raises((TypeError, ValueError)):
            create_posting_instruction(invalid)


def test_posting_instruction_rejects_invalid_side():
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal
    from aqorath.posting import create_posting_instruction

    confirmed = ConfirmedProposal(ConfirmationSnapshot((
        ConfirmationLine("cash", 101, "C", "Caja", "other", Decimal("1")),
        ConfirmationLine("sales_revenue", 902, "S", "Ventas", "credit", Decimal("1")),
    ), "invalid side"))
    with pytest.raises(ValueError):
        create_posting_instruction(confirmed)


def test_posting_instruction_rejects_non_decimal_zero_or_negative_amounts():
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal
    from aqorath.posting import create_posting_instruction

    def candidate(amount):
        return ConfirmedProposal(ConfirmationSnapshot((
            ConfirmationLine("cash", 101, "C", "Caja", "debit", amount),
            ConfirmationLine("sales_revenue", 902, "S", "Ventas", "credit", amount),
        ), "amount sentinel"))

    with pytest.raises((TypeError, ValueError)):
        create_posting_instruction(candidate(1.0))
    with pytest.raises(ValueError):
        create_posting_instruction(candidate(Decimal("0")))
    with pytest.raises(ValueError):
        create_posting_instruction(candidate(Decimal("-1")))


def test_posting_instruction_rejects_unbalanced_confirmed_snapshot():
    from aqorath.confirmation import ConfirmationLine, ConfirmationSnapshot, ConfirmedProposal
    from aqorath.posting import create_posting_instruction

    confirmed = ConfirmedProposal(ConfirmationSnapshot((
        ConfirmationLine("cash", 101, "C", "Caja", "debit", Decimal("200")),
        ConfirmationLine("sales_revenue", 902, "S", "Ventas", "credit", Decimal("199")),
    ), "unbalanced"))
    with pytest.raises(ValueError):
        create_posting_instruction(confirmed)


def test_posting_instruction_does_not_reresolve_lookup_persist_post_or_open_session(monkeypatch):
    import importlib
    import sqlite3
    import aqorath.posting as posting
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.catalog
    import aqorath.core
    import aqorath.storage
    import aqorath.models

    confirmed = _confirmed()

    def bomb(*args, **kwargs):
        raise AssertionError("posting instruction must remain pure")

    class ForbiddenJournalEntry:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no JournalEntry")

    class ForbiddenJournalLine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no JournalLine")

    try:
        with monkeypatch.context() as m:
            m.setattr(aqorath.economic_facts, "resolve_economic_fact", bomb)
            m.setattr(aqorath.account_resolution, "resolve_proposal_accounts", bomb)
            m.setattr(aqorath.catalog, "resolve_account_by_code", bomb)
            m.setattr(aqorath.catalog, "create_entity_account", bomb)
            m.setattr(aqorath.core, "post_entry", bomb)
            m.setattr(aqorath.storage, "get_session", bomb)
            m.setattr(aqorath.models, "JournalEntry", ForbiddenJournalEntry)
            m.setattr(aqorath.models, "JournalLine", ForbiddenJournalLine)
            m.setattr(sqlite3, "connect", bomb)
            posting = importlib.reload(posting)
            instruction = posting.create_posting_instruction(confirmed)
            assert instruction.description == confirmed.snapshot.explanation
            assert instruction.lines[0].debit == Decimal("200.00")
            assert instruction.lines[1].credit == Decimal("200.00")
    finally:
        importlib.reload(posting)
