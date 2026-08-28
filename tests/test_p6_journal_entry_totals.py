"""Phase 6AT.1 — frozen pure JournalEntry total projection contracts.

JournalEntry already owns one explicit immutable tuple of JournalLine values, and 6AS
froze exact aggregation for an explicit tuple. This phase freezes only their composition:
nominal JournalEntry -> exact debit/credit totals of entry.lines. It does not reconcile
line entry_id values, inspect state/date/account metadata, compute balances, persist,
report, or enter Application.
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


def test_journal_entry_totals_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_entry_totals).parameters) == ("entry",)

    source = inspect.getsource(domain.journal_entry_totals).lower()
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
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(lines=(_line(),))
    assert journal_entry_totals(entry) == (Decimal("10.00"), Decimal("0"))

    for invalid in (
        object(),
        {"lines": entry.lines},
        entry.lines,
        None,
    ):
        with pytest.raises(TypeError):
            journal_entry_totals(invalid)


def test_transient_journal_entry_identity_is_valid_for_pure_total_projection():
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(
        entry_id=None,
        lines=(
            _line(side="debit", amount="25.00", entry_id=101),
            _line(side="credit", amount="5.00", entry_id=101),
        ),
    )

    assert journal_entry_totals(entry) == (Decimal("25.00"), Decimal("5.00"))


def test_empty_entry_lines_return_exact_decimal_zero_totals():
    from aqorath.account_balance import journal_entry_totals

    result = journal_entry_totals(_entry(lines=()))

    assert type(result) is tuple
    assert result == (Decimal("0"), Decimal("0"))
    assert all(type(value) is Decimal for value in result)


def test_balanced_entry_projects_exact_debit_and_credit_totals():
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(
        lines=(
            _line(side="debit", amount="100.00"),
            _line(side="credit", amount="40.25"),
            _line(side="credit", amount="59.75"),
        ),
    )

    assert journal_entry_totals(entry) == (Decimal("100.00"), Decimal("100.00"))


def test_unbalanced_draft_projects_totals_without_rejecting_or_rebalancing():
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(
        state="draft",
        lines=(
            _line(side="debit", amount="80.00"),
            _line(side="credit", amount="20.00"),
        ),
    )

    assert not entry.is_balanced()
    assert journal_entry_totals(entry) == (Decimal("80.00"), Decimal("20.00"))


def test_posted_and_reversed_states_do_not_change_total_projection():
    from aqorath.account_balance import journal_entry_totals

    lines = (
        _line(side="debit", amount="42.50"),
        _line(side="credit", amount="42.50"),
    )

    posted = _entry(lines=lines, state="posted")
    reversed_entry = _entry(lines=lines, state="reversed")

    assert journal_entry_totals(posted) == (Decimal("42.50"), Decimal("42.50"))
    assert journal_entry_totals(reversed_entry) == (Decimal("42.50"), Decimal("42.50"))


def test_entry_id_does_not_need_to_match_line_entry_ids_for_this_projection():
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(
        entry_id=900,
        lines=(
            _line(side="debit", amount="11", entry_id=111),
            _line(side="credit", amount="3", entry_id=222),
        ),
    )

    assert journal_entry_totals(entry) == (Decimal("11"), Decimal("3"))


def test_entry_metadata_is_opaque_to_monetary_total_projection():
    from aqorath.account_balance import journal_entry_totals

    lines = (
        _line(side="debit", amount="50"),
        _line(side="credit", amount="50"),
    )
    first = _entry(
        lines=lines,
        entry_id=None,
        state="draft",
        concept="Primero",
        date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_id=None,
        fiscal_rule_set_id=None,
    )
    second = _entry(
        lines=lines,
        entry_id=999,
        state="posted",
        concept="Segundo",
        date=datetime(2027, 12, 31, tzinfo=timezone.utc),
        period_id=7,
        fiscal_rule_set_id=8,
    )

    assert journal_entry_totals(first) == journal_entry_totals(second) == (
        Decimal("50"),
        Decimal("50"),
    )


def test_projection_preserves_exact_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import journal_entry_totals

    entry = _entry(
        lines=(
            _line(side="debit", amount="0.1000000000000000000000000002"),
            _line(side="debit", amount="0.0000000000000000000000000001"),
            _line(side="credit", amount="0.2000000000000000000000000003"),
        )
    )
    debit_total, credit_total = journal_entry_totals(entry)

    assert debit_total == Decimal("0.1000000000000000000000000003")
    assert credit_total == Decimal("0.2000000000000000000000000003")
    assert type(debit_total) is Decimal
    assert type(credit_total) is Decimal

    source = inspect.getsource(journal_entry_totals).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_projection_reuses_frozen_journal_line_totals_authority(monkeypatch):
    import aqorath.account_balance as domain

    entry = _entry(lines=(_line(),))
    sentinel = (Decimal("123.45"), Decimal("67.89"))
    seen = []

    def fake_totals(lines):
        seen.append(lines)
        return sentinel

    monkeypatch.setattr(domain, "journal_line_totals", fake_totals)

    result = domain.journal_entry_totals(entry)

    assert result is sentinel
    assert seen == [entry.lines]
    assert seen[0] is entry.lines


def test_projection_does_not_compute_signed_or_normal_balance(monkeypatch):
    import aqorath.account_balance as domain

    entry = _entry(
        lines=(
            _line(side="debit", amount="8"),
            _line(side="credit", amount="3"),
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("balance interpretation must not run during entry projection")

    monkeypatch.setattr(domain, "ledger_signed_balance", forbidden)
    monkeypatch.setattr(domain, "normal_balance_amount", forbidden)
    monkeypatch.setattr(domain, "normal_balance_for_account", forbidden)

    assert domain.journal_entry_totals(entry) == (Decimal("8"), Decimal("3"))


def test_projection_never_mutates_entry_or_line_tuple_identity():
    from aqorath.account_balance import journal_entry_totals

    first = _line(side="debit", amount="20.00", line_id=1)
    second = _line(side="credit", amount="7.00", line_id=2)
    lines = (first, second)
    entry = _entry(lines=lines, entry_id=300)
    before = (
        entry.id,
        entry.date,
        entry.concept,
        entry.lines,
        entry.period_id,
        entry.fiscal_rule_set_id,
        entry.state,
    )

    journal_entry_totals(entry)

    after = (
        entry.id,
        entry.date,
        entry.concept,
        entry.lines,
        entry.period_id,
        entry.fiscal_rule_set_id,
        entry.state,
    )
    assert after == before
    assert entry.lines is lines
    assert entry.lines[0] is first
    assert entry.lines[1] is second


def test_journal_entry_totals_are_deterministic_without_ambient_inputs():
    import aqorath.account_balance as domain

    entry = _entry(
        lines=(
            _line(side="debit", amount="10.000"),
            _line(side="credit", amount="3.000"),
        )
    )
    first = domain.journal_entry_totals(entry)
    second = domain.journal_entry_totals(entry)
    assert first == second == (Decimal("10.000"), Decimal("3.000"))

    source = inspect.getsource(domain.journal_entry_totals).lower()
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


def test_projection_does_not_filter_lines_by_account_date_state_or_identity():
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_entry_totals).lower()
    for forbidden in (
        "account.code",
        "account.id",
        "line.entry_id",
        "entry.id ==",
        "entry.state",
        "entry.date",
        "period_id",
        "fiscal_rule_set_id",
        "analytics",
    ):
        assert forbidden not in source


def test_journal_entry_totals_do_not_persist_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_entry_totals).lower()
    for forbidden in (
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
    assert "journal_entry_totals" not in application_source
