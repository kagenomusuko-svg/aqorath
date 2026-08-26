"""
Phase 2C.1: Confirmation Snapshot Contracts (Hardened)

Congelan el contrato de captura de snapshot inmutable para confirmación de usuario.

Arquitectura:
  ResolvedAccountingProposal (mutable container, frozen dataclass)
    ↓ create_confirmation_snapshot
    ↓ ConfirmationSnapshot (deeply immutable, tuple de ConfirmationLine)
    ↓ confirm_snapshot
    ↓ ConfirmedProposal (frozen, preserva snapshot identity)

Separación fundamental:
  - economic_facts: resuelve QUÉ ocurrió
  - account_resolution: resuelve EN QUÉ cuentas concretas
  - confirmation: congela lo que el usuario VE y CONFIRMA (pre-posting)
  - [posting futuro]: registra definitivamente

Regla de consentimiento: snapshot debe ser independiente de mutaciones posteriores.
HARDENING 2C.1A: firmas exactas, tipos nominales y purity bombs resistentes a imports directos.
"""

from decimal import Decimal
import pytest


def _make_resolved_proposal():
    """Construye una ResolvedAccountingProposal real y determinista para tests."""
    from aqorath.account_resolution import (
        ResolvedProposalLine,
        ResolvedAccountingProposal,
    )

    return ResolvedAccountingProposal(
        lines=[
            ResolvedProposalLine(
                account_role="cash",
                account_id=101,
                account_code="TEST-CASH-001",
                account_name="Caja principal",
                side="debit",
                amount=Decimal("200.00"),
            ),
            ResolvedProposalLine(
                account_role="sales_revenue",
                account_id=902,
                account_code="TEST-SALES-900",
                account_name="Ingresos por ventas",
                side="credit",
                amount=Decimal("200.00"),
            ),
        ],
        explanation=(
            "Sale transaction: 200.00 received in cash. "
            "Cash account increased (debit), sales revenue recognized (credit)."
        ),
    )


def test_confirmation_module_exists():
    """Contract: aqorath.confirmation module must exist."""
    import aqorath.confirmation


def test_confirmation_public_contract_exists():
    """Contract: public surface and exact infrastructure-free signatures."""
    from inspect import Parameter, signature
    import aqorath.confirmation

    required = (
        "ConfirmationLine",
        "ConfirmationSnapshot",
        "ConfirmedProposal",
        "create_confirmation_snapshot",
        "confirm_snapshot",
    )
    for name in required:
        assert hasattr(aqorath.confirmation, name)

    create_snapshot = aqorath.confirmation.create_confirmation_snapshot
    confirm = aqorath.confirmation.confirm_snapshot
    assert callable(create_snapshot)
    assert callable(confirm)

    snapshot_sig = signature(create_snapshot)
    confirm_sig = signature(confirm)

    assert list(snapshot_sig.parameters) == ["resolved_proposal"]
    assert list(confirm_sig.parameters) == ["snapshot"]

    snapshot_param = snapshot_sig.parameters["resolved_proposal"]
    confirm_param = confirm_sig.parameters["snapshot"]

    assert snapshot_param.default is Parameter.empty
    assert confirm_param.default is Parameter.empty
    assert snapshot_param.kind is Parameter.POSITIONAL_OR_KEYWORD
    assert confirm_param.kind is Parameter.POSITIONAL_OR_KEYWORD

    for sig in (snapshot_sig, confirm_sig):
        assert all(
            parameter.kind
            not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
            for parameter in sig.parameters.values()
        )


def test_confirmation_snapshot_accepts_resolved_accounting_proposal():
    """Contract: a real ResolvedAccountingProposal produces ConfirmationSnapshot."""
    from aqorath.confirmation import create_confirmation_snapshot, ConfirmationSnapshot

    resolved = _make_resolved_proposal()
    snapshot = create_confirmation_snapshot(resolved)

    assert snapshot is not None
    assert isinstance(snapshot, ConfirmationSnapshot)
    assert hasattr(snapshot, "lines")
    assert hasattr(snapshot, "explanation")


def test_confirmation_snapshot_preserves_exact_values_and_order():
    """Contract: snapshot preserves concrete identity, semantics, money and order."""
    from aqorath.confirmation import create_confirmation_snapshot, ConfirmationLine

    resolved = _make_resolved_proposal()
    snapshot = create_confirmation_snapshot(resolved)

    assert len(snapshot.lines) == 2
    assert isinstance(snapshot.lines, tuple)

    cash_line = snapshot.lines[0]
    assert isinstance(cash_line, ConfirmationLine)
    assert cash_line.account_role == "cash"
    assert cash_line.account_id == 101
    assert cash_line.account_code == "TEST-CASH-001"
    assert cash_line.account_name == "Caja principal"
    assert cash_line.side == "debit"
    assert cash_line.amount == Decimal("200.00")

    sales_line = snapshot.lines[1]
    assert isinstance(sales_line, ConfirmationLine)
    assert sales_line.account_role == "sales_revenue"
    assert sales_line.account_id == 902
    assert sales_line.account_code == "TEST-SALES-900"
    assert sales_line.account_name == "Ingresos por ventas"
    assert sales_line.side == "credit"
    assert sales_line.amount == Decimal("200.00")

    assert snapshot.explanation == resolved.explanation

    for line in snapshot.lines:
        assert not hasattr(line, "entry_id")
        assert not hasattr(line, "debit")
        assert not hasattr(line, "credit")
        assert not hasattr(line, "state")
        assert not hasattr(line, "posted_by")


def test_confirmation_snapshot_is_deeply_immutable():
    """Contract: snapshot, tuple container and confirmation lines are immutable."""
    from dataclasses import FrozenInstanceError
    from aqorath.confirmation import create_confirmation_snapshot

    snapshot = create_confirmation_snapshot(_make_resolved_proposal())

    assert isinstance(snapshot.lines, tuple)

    with pytest.raises(FrozenInstanceError):
        snapshot.explanation = "changed"

    with pytest.raises(FrozenInstanceError):
        snapshot.lines = ()

    with pytest.raises(TypeError):
        snapshot.lines[0] = snapshot.lines[1]

    with pytest.raises(FrozenInstanceError):
        snapshot.lines[0].account_code = "OTHER"

    with pytest.raises(FrozenInstanceError):
        snapshot.lines[0].amount = Decimal("999.00")


def test_confirmation_snapshot_is_independent_from_source_mutation():
    """Contract: later mutation of the source List cannot change the snapshot."""
    from aqorath.account_resolution import ResolvedProposalLine
    from aqorath.confirmation import create_confirmation_snapshot

    resolved = _make_resolved_proposal()
    snapshot = create_confirmation_snapshot(resolved)
    original_snapshot_values = tuple(
        (
            line.account_role,
            line.account_id,
            line.account_code,
            line.account_name,
            line.side,
            line.amount,
        )
        for line in snapshot.lines
    )

    resolved.lines.clear()
    assert len(resolved.lines) == 0
    assert len(snapshot.lines) == 2
    assert tuple(
        (
            line.account_role,
            line.account_id,
            line.account_code,
            line.account_name,
            line.side,
            line.amount,
        )
        for line in snapshot.lines
    ) == original_snapshot_values

    resolved_again = _make_resolved_proposal()
    snapshot_again = create_confirmation_snapshot(resolved_again)
    resolved_again.lines[0] = ResolvedProposalLine(
        account_role="cash",
        account_id=999,
        account_code="CHANGED",
        account_name="Changed source",
        side="credit",
        amount=Decimal("999.00"),
    )

    assert snapshot_again.lines[0].account_role == "cash"
    assert snapshot_again.lines[0].account_id == 101
    assert snapshot_again.lines[0].account_code == "TEST-CASH-001"
    assert snapshot_again.lines[0].account_name == "Caja principal"
    assert snapshot_again.lines[0].side == "debit"
    assert snapshot_again.lines[0].amount == Decimal("200.00")


def test_confirmation_snapshot_copies_lines_by_value():
    """Contract: ConfirmationLine is a new value object, not a reused resolved line."""
    from aqorath.account_resolution import ResolvedProposalLine
    from aqorath.confirmation import create_confirmation_snapshot, ConfirmationLine

    resolved = _make_resolved_proposal()
    snapshot = create_confirmation_snapshot(resolved)

    assert len(snapshot.lines) == len(resolved.lines) == 2

    for source, copied in zip(resolved.lines, snapshot.lines):
        assert copied is not source
        assert isinstance(source, ResolvedProposalLine)
        assert isinstance(copied, ConfirmationLine)
        assert not isinstance(copied, ResolvedProposalLine)
        assert copied.account_role == source.account_role
        assert copied.account_id == source.account_id
        assert copied.account_code == source.account_code
        assert copied.account_name == source.account_name
        assert copied.side == source.side
        assert copied.amount == source.amount


def test_confirm_snapshot_returns_confirmed_proposal():
    """Contract: a ConfirmationSnapshot can be explicitly confirmed."""
    from aqorath.confirmation import (
        create_confirmation_snapshot,
        confirm_snapshot,
        ConfirmedProposal,
    )

    snapshot = create_confirmation_snapshot(_make_resolved_proposal())
    confirmed = confirm_snapshot(snapshot)

    assert confirmed is not None
    assert isinstance(confirmed, ConfirmedProposal)


def test_confirmed_proposal_preserves_exact_snapshot_identity_and_is_immutable():
    """Contract: confirmation preserves snapshot identity and cannot be rebound."""
    from dataclasses import FrozenInstanceError
    from aqorath.confirmation import create_confirmation_snapshot, confirm_snapshot

    snapshot = create_confirmation_snapshot(_make_resolved_proposal())
    confirmed = confirm_snapshot(snapshot)

    assert confirmed.snapshot is snapshot

    with pytest.raises(FrozenInstanceError):
        confirmed.snapshot = None


def test_confirmation_requires_resolved_snapshot_pipeline():
    """Contract: pipeline stages are nominal and cannot be skipped or duck-typed."""
    import types
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.confirmation import create_confirmation_snapshot, confirm_snapshot

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    semantic_proposal = resolve_economic_fact(fact)

    with pytest.raises((TypeError, ValueError)):
        create_confirmation_snapshot(semantic_proposal)

    resolved = _make_resolved_proposal()
    with pytest.raises((TypeError, ValueError)):
        confirm_snapshot(resolved)

    fake_resolved = types.SimpleNamespace(
        lines=resolved.lines,
        explanation=resolved.explanation,
    )
    with pytest.raises((TypeError, ValueError)):
        create_confirmation_snapshot(fake_resolved)

    snapshot = create_confirmation_snapshot(resolved)
    fake_snapshot = types.SimpleNamespace(
        lines=snapshot.lines,
        explanation=snapshot.explanation,
    )
    with pytest.raises((TypeError, ValueError)):
        confirm_snapshot(fake_snapshot)


def test_confirmation_does_not_reresolve_or_lookup_accounts(monkeypatch):
    """Contract: confirmation cannot re-resolve even through direct-import aliases."""
    import importlib
    import aqorath.confirmation as confirmation
    import aqorath.economic_facts
    import aqorath.account_resolution
    import aqorath.catalog

    resolved = _make_resolved_proposal()

    def forbidden_resolve_fact(*args, **kwargs):
        raise AssertionError("confirmation must not call resolve_economic_fact")

    def forbidden_resolve_accounts(*args, **kwargs):
        raise AssertionError("confirmation must not call resolve_proposal_accounts")

    def forbidden_catalog_lookup(*args, **kwargs):
        raise AssertionError("confirmation must not call catalog.resolve_account_by_code")

    try:
        with monkeypatch.context() as m:
            m.setattr(
                aqorath.economic_facts,
                "resolve_economic_fact",
                forbidden_resolve_fact,
            )
            m.setattr(
                aqorath.account_resolution,
                "resolve_proposal_accounts",
                forbidden_resolve_accounts,
            )
            m.setattr(
                aqorath.catalog,
                "resolve_account_by_code",
                forbidden_catalog_lookup,
            )

            confirmation = importlib.reload(confirmation)
            snapshot = confirmation.create_confirmation_snapshot(resolved)
            confirmed = confirmation.confirm_snapshot(snapshot)
            assert confirmed.snapshot is snapshot
    finally:
        importlib.reload(confirmation)


def test_confirmation_does_not_persist_post_or_open_session(monkeypatch):
    """Contract: confirmation cannot persist/post/open DB even via captured aliases."""
    import importlib
    import sqlite3
    import aqorath.confirmation as confirmation
    import aqorath.core
    import aqorath.storage
    import aqorath.catalog
    import aqorath.models

    resolved = _make_resolved_proposal()

    def forbidden_post(*args, **kwargs):
        raise AssertionError("confirmation must not call core.post_entry")

    def forbidden_get_session(*args, **kwargs):
        raise AssertionError("confirmation must not call storage.get_session")

    def forbidden_create(*args, **kwargs):
        raise AssertionError("confirmation must not call create_entity_account")

    def forbidden_sqlite_connect(*args, **kwargs):
        raise AssertionError("confirmation must not open sqlite directly")

    class ForbiddenJournalEntry:
        def __init__(self, *args, **kwargs):
            raise AssertionError("confirmation must not create JournalEntry")

    class ForbiddenJournalLine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("confirmation must not create JournalLine")

    try:
        with monkeypatch.context() as m:
            m.setattr(aqorath.core, "post_entry", forbidden_post)
            m.setattr(aqorath.storage, "get_session", forbidden_get_session)
            m.setattr(aqorath.catalog, "create_entity_account", forbidden_create)
            m.setattr(aqorath.models, "JournalEntry", ForbiddenJournalEntry)
            m.setattr(aqorath.models, "JournalLine", ForbiddenJournalLine)
            m.setattr(sqlite3, "connect", forbidden_sqlite_connect)

            confirmation = importlib.reload(confirmation)
            snapshot = confirmation.create_confirmation_snapshot(resolved)
            confirmed = confirmation.confirm_snapshot(snapshot)
            assert snapshot is not None
            assert confirmed.snapshot is snapshot
    finally:
        importlib.reload(confirmation)
