"""Phase 6AV.1 — frozen JournalEntry balance-authority convergence contracts.

JournalEntry.is_balanced() already exists from 6AP, while 6AS–6AU established one
explicit exact authority chain for line totals, entry totals and signed balance. This
phase freezes convergence only: is_balanced() must interpret the authoritative signed
balance as zero/nonzero. It does not change lifecycle states, posting, persistence,
selection, reporting, or Application.
"""

from datetime import datetime, timezone
from decimal import Decimal
import inspect

import pytest


def _account(code="1101", nature="debit"):
    from aqorath.account import Account

    return Account(
        id=None,
        code=code,
        name=f"Cuenta {code}",
        account_type="asset" if nature == "debit" else "income",
        subtype="current" if nature == "debit" else "operating",
        nature=nature,
        is_canonical=True,
    )


def _line(*, side="debit", amount="10.00", entry_id=20):
    from aqorath.journal_line import JournalLine

    value = Decimal(amount)
    if side == "debit":
        debit = value
        credit = Decimal("0")
        account = _account("1101", "debit")
    else:
        debit = Decimal("0")
        credit = value
        account = _account("4101", "credit")

    return JournalLine(
        id=None,
        entry_id=entry_id,
        account=account,
        debit=debit,
        credit=credit,
    )


def _entry(*, lines=(), state="draft"):
    from aqorath.journal_entry import JournalEntry

    return JournalEntry(
        id=None,
        date=datetime(2026, 8, 28, 9, 30, tzinfo=timezone.utc),
        concept="Asiento explícito",
        lines=lines,
        state=state,
    )


def test_is_balanced_public_contract_remains_self_only_and_returns_bool():
    from aqorath.journal_entry import JournalEntry

    assert tuple(inspect.signature(JournalEntry.is_balanced).parameters) == ("self",)

    balanced = _entry(
        lines=(
            _line(side="debit", amount="12.50"),
            _line(side="credit", amount="12.50"),
        )
    )
    result = balanced.is_balanced()
    assert type(result) is bool
    assert result is True


def test_empty_entry_remains_balanced_by_exact_zero_semantics():
    entry = _entry(lines=())
    assert entry.is_balanced() is True


def test_debit_excess_draft_remains_unbalanced():
    entry = _entry(
        lines=(
            _line(side="debit", amount="25.00"),
            _line(side="credit", amount="5.00"),
        )
    )
    assert entry.is_balanced() is False


def test_credit_excess_draft_remains_unbalanced():
    entry = _entry(
        lines=(
            _line(side="debit", amount="5.00"),
            _line(side="credit", amount="25.00"),
        )
    )
    assert entry.is_balanced() is False


def test_balance_preserves_exact_decimal_truth_without_tolerance():
    entry = _entry(
        lines=(
            _line(side="debit", amount="0.1000000000000000000000000001"),
            _line(side="credit", amount="0.1000000000000000000000000000"),
        )
    )
    assert entry.is_balanced() is False


def test_is_balanced_delegates_to_authoritative_signed_balance_zero(monkeypatch):
    import aqorath.account_balance as balance

    entry = _entry(lines=(_line(side="debit", amount="99"),))
    seen = []

    def fake_signed(value):
        seen.append(value)
        return Decimal("0")

    monkeypatch.setattr(balance, "journal_entry_signed_balance", fake_signed)

    assert entry.is_balanced() is True
    assert seen == [entry]
    assert seen[0] is entry


def test_is_balanced_delegates_to_authoritative_positive_signed_balance(monkeypatch):
    import aqorath.account_balance as balance

    entry = _entry(
        lines=(
            _line(side="debit", amount="10"),
            _line(side="credit", amount="10"),
        )
    )

    monkeypatch.setattr(
        balance,
        "journal_entry_signed_balance",
        lambda value: Decimal("0.0001"),
    )

    assert entry.is_balanced() is False


def test_is_balanced_delegates_to_authoritative_negative_signed_balance(monkeypatch):
    import aqorath.account_balance as balance

    entry = _entry(
        lines=(
            _line(side="debit", amount="10"),
            _line(side="credit", amount="10"),
        )
    )

    monkeypatch.setattr(
        balance,
        "journal_entry_signed_balance",
        lambda value: Decimal("-0.0001"),
    )

    assert entry.is_balanced() is False


def test_is_balanced_does_not_sum_or_inspect_lines_directly():
    from aqorath.journal_entry import JournalEntry

    source = inspect.getsource(JournalEntry.is_balanced).lower()
    for forbidden in (
        "sum(",
        ".debit",
        ".credit",
        "journal_line_totals",
        "journal_entry_totals",
        "ledger_signed_balance",
    ):
        assert forbidden not in source


def test_is_balanced_does_not_interpret_account_nature_or_normal_balance():
    from aqorath.journal_entry import JournalEntry

    source = inspect.getsource(JournalEntry.is_balanced).lower()
    for forbidden in (
        "account",
        "nature",
        "normal_balance_amount",
        "normal_balance_for_account",
    ):
        assert forbidden not in source


def test_posted_validation_uses_the_same_balance_authority(monkeypatch):
    import aqorath.account_balance as balance

    lines = (
        _line(side="debit", amount="10"),
        _line(side="credit", amount="10"),
    )
    monkeypatch.setattr(
        balance,
        "journal_entry_signed_balance",
        lambda value: Decimal("1"),
    )

    with pytest.raises(ValueError):
        _entry(lines=lines, state="posted")


def test_reversed_validation_uses_the_same_balance_authority(monkeypatch):
    import aqorath.account_balance as balance

    lines = (
        _line(side="debit", amount="10"),
        _line(side="credit", amount="10"),
    )
    monkeypatch.setattr(
        balance,
        "journal_entry_signed_balance",
        lambda value: Decimal("-1"),
    )

    with pytest.raises(ValueError):
        _entry(lines=lines, state="reversed")


def test_posted_and_reversed_accept_when_authoritative_signed_balance_is_zero(monkeypatch):
    import aqorath.account_balance as balance

    unbalanced_lines = (
        _line(side="debit", amount="10"),
        _line(side="credit", amount="1"),
    )
    monkeypatch.setattr(
        balance,
        "journal_entry_signed_balance",
        lambda value: Decimal("0"),
    )

    assert _entry(lines=unbalanced_lines, state="posted").state == "posted"
    assert _entry(lines=unbalanced_lines, state="reversed").state == "reversed"


def test_draft_construction_does_not_force_balance_evaluation(monkeypatch):
    import aqorath.account_balance as balance

    def forbidden(value):
        raise AssertionError("draft construction must not require balance evaluation")

    monkeypatch.setattr(balance, "journal_entry_signed_balance", forbidden)

    entry = _entry(lines=(_line(side="debit", amount="10"),), state="draft")
    assert entry.state == "draft"


def test_is_balanced_remains_deterministic_and_has_no_ambient_inputs():
    from aqorath.journal_entry import JournalEntry

    entry = _entry(
        lines=(
            _line(side="debit", amount="10.000"),
            _line(side="credit", amount="10.000"),
        )
    )
    assert entry.is_balanced() is True
    assert entry.is_balanced() is True

    source = inspect.getsource(JournalEntry.is_balanced).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_balance_authority_convergence_does_not_add_transition_persistence_reporting_or_application():
    import aqorath.application as application
    import aqorath.journal_entry as domain

    source = inspect.getsource(domain.JournalEntry.is_balanced).lower()
    for forbidden in (
        "post(",
        "reverse(",
        "repository",
        "get_session",
        "storage",
        "reporting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "application",
        "core",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "journal_entry_signed_balance" not in application_source
