"""Phase 6AU.1 — frozen pure JournalEntry signed-balance contracts.

6AT projects exact debit/credit totals from one explicit JournalEntry, and 6AQ owns the
LedgerSignedBalance definition. This phase freezes only their pure composition:
nominal JournalEntry -> exact debit-minus-credit signed balance. It does not interpret
account nature, filter lines, infer lifecycle transitions, persist, report, or enter
Application.
"""

from datetime import datetime, timezone
from decimal import Decimal
import inspect

import pytest


def _account(**patch):
    from aqorath.account import Account

    values = dict(
        id=10,
        code="1101",
        name="Bancos",
        account_type="asset",
        subtype="current",
        nature="debit",
        is_canonical=True,
        name_osc=None,
        name_comercial=None,
    )
    values.update(patch)
    return Account(**values)


def _line(*, side="debit", amount="10.00", account=None, entry_id=20, line_id=None):
    from aqorath.journal_line import JournalLine

    value = Decimal(amount)
    if side == "debit":
        debit = value
        credit = Decimal("0")
    else:
        debit = Decimal("0")
        credit = value

    return JournalLine(
        id=line_id,
        entry_id=entry_id,
        account=account or _account(),
        debit=debit,
        credit=credit,
        description=None,
        analytics=(),
    )


def _entry(*, lines=(), entry_id=None, state="draft", concept="Asiento explícito",
           date=None, period_id=None, fiscal_rule_set_id=None):
    from aqorath.journal_entry import JournalEntry

    return JournalEntry(
        id=entry_id,
        date=date or datetime(2026, 8, 28, 9, 30, tzinfo=timezone.utc),
        concept=concept,
        lines=lines,
        period_id=period_id,
        fiscal_rule_set_id=fiscal_rule_set_id,
        state=state,
    )


def test_journal_entry_signed_balance_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_entry_signed_balance).parameters) == (
        "entry",
    )

    source = inspect.getsource(domain.journal_entry_signed_balance).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_entry_must_be_nominal_journal_entry_not_duck_typed_metadata():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(lines=(_line(),))
    assert journal_entry_signed_balance(entry) == Decimal("10.00")

    for invalid in (
        object(),
        {"lines": entry.lines},
        entry.lines,
        None,
    ):
        with pytest.raises(TypeError):
            journal_entry_signed_balance(invalid)


def test_transient_journal_entry_identity_is_valid_for_pure_signed_balance():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(
        entry_id=None,
        lines=(
            _line(side="debit", amount="25.00", entry_id=101),
            _line(side="credit", amount="5.00", entry_id=202),
        ),
    )

    assert journal_entry_signed_balance(entry) == Decimal("20.00")


def test_empty_entry_has_exact_zero_signed_balance():
    from aqorath.account_balance import journal_entry_signed_balance

    result = journal_entry_signed_balance(_entry(lines=()))

    assert result == Decimal("0")
    assert type(result) is Decimal


def test_balanced_entry_has_exact_zero_signed_balance():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(
        lines=(
            _line(side="debit", amount="100.00"),
            _line(side="credit", amount="40.25"),
            _line(side="credit", amount="59.75"),
        )
    )

    assert journal_entry_signed_balance(entry) == Decimal("0.00")


def test_unbalanced_draft_debit_excess_is_positive_signed_balance():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(
        state="draft",
        lines=(
            _line(side="debit", amount="80.00"),
            _line(side="credit", amount="20.00"),
        ),
    )

    assert not entry.is_balanced()
    assert journal_entry_signed_balance(entry) == Decimal("60.00")


def test_unbalanced_draft_credit_excess_is_negative_signed_balance():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(
        state="draft",
        lines=(
            _line(side="debit", amount="20.00"),
            _line(side="credit", amount="80.00"),
        ),
    )

    assert not entry.is_balanced()
    assert journal_entry_signed_balance(entry) == Decimal("-60.00")


def test_posted_and_reversed_entries_have_zero_signed_balance_by_existing_domain_invariant():
    from aqorath.account_balance import journal_entry_signed_balance

    lines = (
        _line(side="debit", amount="42.50"),
        _line(side="credit", amount="42.50"),
    )

    posted = _entry(lines=lines, state="posted")
    reversed_entry = _entry(lines=lines, state="reversed")

    assert journal_entry_signed_balance(posted) == Decimal("0.00")
    assert journal_entry_signed_balance(reversed_entry) == Decimal("0.00")


def test_entry_metadata_is_opaque_to_signed_balance_projection():
    from aqorath.account_balance import journal_entry_signed_balance

    lines = (
        _line(side="debit", amount="13"),
        _line(side="credit", amount="5"),
    )
    first = _entry(
        lines=lines,
        entry_id=None,
        concept="Primero",
        date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_id=None,
        fiscal_rule_set_id=None,
    )
    second = _entry(
        lines=lines,
        entry_id=999,
        concept="Segundo",
        date=datetime(2027, 12, 31, tzinfo=timezone.utc),
        period_id=7,
        fiscal_rule_set_id=8,
    )

    assert journal_entry_signed_balance(first) == (
        journal_entry_signed_balance(second)
    ) == Decimal("8")


def test_signed_balance_preserves_exact_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import journal_entry_signed_balance

    entry = _entry(
        lines=(
            _line(side="debit", amount="0.1000000000000000000000000002"),
            _line(side="debit", amount="0.0000000000000000000000000001"),
            _line(side="credit", amount="0.2000000000000000000000000003"),
        )
    )
    result = journal_entry_signed_balance(entry)

    assert result == Decimal("-0.1000000000000000000000000000")
    assert type(result) is Decimal

    source = inspect.getsource(journal_entry_signed_balance).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_signed_balance_reuses_frozen_journal_entry_totals_authority(monkeypatch):
    import aqorath.account_balance as domain

    entry = _entry(lines=(_line(),))
    totals = (Decimal("123.45"), Decimal("67.89"))
    seen = []

    def fake_entry_totals(value):
        seen.append(value)
        return totals

    monkeypatch.setattr(domain, "journal_entry_totals", fake_entry_totals)

    assert domain.journal_entry_signed_balance(entry) == Decimal("55.56")
    assert seen == [entry]
    assert seen[0] is entry


def test_signed_balance_reuses_frozen_ledger_signed_balance_authority(monkeypatch):
    import aqorath.account_balance as domain

    entry = _entry(lines=(_line(),))
    totals = (Decimal("12.34"), Decimal("5.67"))
    sentinel = Decimal("999.001")
    seen = []

    monkeypatch.setattr(domain, "journal_entry_totals", lambda value: totals)

    def fake_ledger(debit_total, credit_total):
        seen.append((debit_total, credit_total))
        return sentinel

    monkeypatch.setattr(domain, "ledger_signed_balance", fake_ledger)

    result = domain.journal_entry_signed_balance(entry)

    assert result is sentinel
    assert seen == [totals]


def test_signed_balance_does_not_compute_normal_balance_or_inspect_account_nature(monkeypatch):
    import aqorath.account_balance as domain

    entry = _entry(
        lines=(
            _line(side="debit", amount="8"),
            _line(side="credit", amount="3"),
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("normal-balance interpretation must not run")

    monkeypatch.setattr(domain, "normal_balance_amount", forbidden)
    monkeypatch.setattr(domain, "normal_balance_for_account", forbidden)

    assert domain.journal_entry_signed_balance(entry) == Decimal("5")

    source = inspect.getsource(domain.journal_entry_signed_balance).lower()
    assert "nature" not in source
    assert "account" not in source


def test_signed_balance_does_not_delegate_to_entry_is_balanced(monkeypatch):
    import aqorath.account_balance as domain
    from aqorath.journal_entry import JournalEntry

    entry = _entry(
        lines=(
            _line(side="debit", amount="8"),
            _line(side="credit", amount="3"),
        )
    )

    def forbidden(self):
        raise AssertionError("signed balance must not call JournalEntry.is_balanced")

    monkeypatch.setattr(JournalEntry, "is_balanced", forbidden)

    assert domain.journal_entry_signed_balance(entry) == Decimal("5")

    source = inspect.getsource(domain.journal_entry_signed_balance).lower()
    assert "is_balanced" not in source


def test_journal_entry_signed_balance_is_deterministic_without_ambient_inputs():
    import aqorath.account_balance as domain

    entry = _entry(
        lines=(
            _line(side="debit", amount="10.000"),
            _line(side="credit", amount="3.000"),
        )
    )
    first = domain.journal_entry_signed_balance(entry)
    second = domain.journal_entry_signed_balance(entry)
    assert first == second == Decimal("7.000")

    source = inspect.getsource(domain.journal_entry_signed_balance).lower()
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


def test_journal_entry_signed_balance_does_not_filter_persist_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_entry_signed_balance).lower()
    for forbidden in (
        "entry.lines",
        "line.entry_id",
        "entry.id ==",
        "entry.state",
        "entry.date",
        "period_id",
        "fiscal_rule_set_id",
        "analytics",
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
