"""Phase 6AP.1 — frozen pure JournalEntry domain contracts.

The architecture gives JournalEntry explicit lines, accounting period metadata, fiscal
rule-set provenance and lifecycle state. Aqorath already owns confirmation/execution
outside this value, so this phase freezes only the immutable entry truth plus pure balance
inspection. It does not replace models.JournalEntry, transition lifecycle state, persist,
resolve accounts, execute posting, or enter Application.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timezone
from decimal import Decimal
import inspect

import pytest


JOURNAL_ENTRY_FIELDS = (
    "id",
    "date",
    "concept",
    "lines",
    "period_id",
    "fiscal_rule_set_id",
    "state",
)


def _account(code, nature):
    from aqorath.account import Account

    if nature == "debit":
        account_type = "asset"
    else:
        account_type = "income"
    return Account(
        id=None,
        code=code,
        name=f"Cuenta {code}",
        account_type=account_type,
        subtype="current" if account_type == "asset" else "operating",
        nature=nature,
        is_canonical=True,
    )


def _line(entry_id=20, *, side="debit", amount="100.00"):
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


def _balanced_lines(entry_id=20, amount="100.00"):
    return (
        _line(entry_id, side="debit", amount=amount),
        _line(entry_id, side="credit", amount=amount),
    )


def _entry(**patch):
    from aqorath.journal_entry import JournalEntry

    values = dict(
        id=None,
        date=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        concept="Operación contable",
        lines=_balanced_lines(),
        period_id=None,
        fiscal_rule_set_id=None,
        state="draft",
    )
    values.update(patch)
    return JournalEntry(**values)


def test_journal_entry_domain_is_pure_frozen_and_has_exact_architecture_fields_and_defaults():
    import aqorath.journal_entry as domain
    from aqorath.journal_entry import JournalEntry

    entry = JournalEntry(
        id=None,
        date=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        concept="Operación contable",
        lines=(),
    )

    assert tuple(field.name for field in fields(JournalEntry)) == JOURNAL_ENTRY_FIELDS
    assert entry.period_id is None
    assert entry.fiscal_rule_set_id is None
    assert entry.state == "draft"

    with pytest.raises(FrozenInstanceError):
        entry.state = "posted"

    source = inspect.getsource(domain).lower()
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


def test_journal_entry_id_is_none_before_identity_or_exact_positive_int():
    assert _entry(id=None).id is None
    assert _entry(id=7).id == 7

    for invalid in (0, -1, True, False, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _entry(id=invalid)


def test_date_must_be_exact_datetime_and_is_preserved_without_clock_inference():
    instant = datetime(2026, 8, 28, 9, 30, 15, 123456, tzinfo=timezone.utc)
    entry = _entry(date=instant)
    assert entry.date is instant

    for invalid in (
        date(2026, 8, 28),
        "2026-08-28T09:30:15Z",
        None,
        0,
    ):
        with pytest.raises(TypeError):
            _entry(date=invalid)


def test_concept_is_exact_nonblank_text_without_normalization():
    value = "Venta crédito MXN"
    assert _entry(concept=value).concept == value

    for invalid in (None, 7, "", " texto", "texto ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _entry(concept=invalid)


def test_lines_must_be_exact_immutable_tuple():
    valid = _balanced_lines()
    assert _entry(lines=valid).lines is valid

    for invalid in ([], set(), {}, "lines", None):
        with pytest.raises(TypeError):
            _entry(lines=invalid)


def test_lines_items_must_be_nominal_journal_lines():
    valid = _line()
    for invalid in (
        (object(),),
        ({"debit": "100"},),
        (valid, object()),
    ):
        with pytest.raises(TypeError):
            _entry(lines=invalid)


def test_empty_lines_are_valid_draft_truth_and_balance_mathematically_to_zero():
    lines = ()
    entry = _entry(lines=lines)

    assert entry.lines is lines
    assert entry.state == "draft"
    assert entry.is_balanced() is True


def test_period_id_is_none_or_exact_positive_int():
    assert _entry(period_id=None).period_id is None
    assert _entry(period_id=3).period_id == 3

    for invalid in (0, -1, True, False, 1.0, "3"):
        with pytest.raises((TypeError, ValueError)):
            _entry(period_id=invalid)


def test_fiscal_rule_set_id_is_none_or_exact_positive_int():
    assert _entry(fiscal_rule_set_id=None).fiscal_rule_set_id is None
    assert _entry(fiscal_rule_set_id=9).fiscal_rule_set_id == 9

    for invalid in (0, -1, True, False, 1.0, "9"):
        with pytest.raises((TypeError, ValueError)):
            _entry(fiscal_rule_set_id=invalid)


def test_state_is_exact_governed_lifecycle_token_and_defaults_draft():
    assert _entry().state == "draft"
    for state in ("draft", "posted", "reversed"):
        assert _entry(state=state).state == state

    for invalid in (
        None,
        1,
        "",
        " draft",
        "draft ",
        "Draft",
        "confirmed",
        "cancelled",
    ):
        with pytest.raises((TypeError, ValueError)):
            _entry(state=invalid)


def test_is_balanced_public_contract_is_exact_and_balanced_entries_return_true():
    from aqorath.journal_entry import JournalEntry

    assert tuple(inspect.signature(JournalEntry.is_balanced).parameters) == ("self",)

    entry = _entry(lines=_balanced_lines(amount="123.4500"))
    assert entry.is_balanced() is True


def test_unbalanced_draft_is_representable_and_is_balanced_returns_false():
    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="99.99"),
    )
    entry = _entry(lines=lines, state="draft")

    assert entry.state == "draft"
    assert entry.is_balanced() is False


def test_posted_and_reversed_states_fail_closed_when_lines_are_unbalanced():
    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="99.99"),
    )

    for state in ("posted", "reversed"):
        with pytest.raises(ValueError):
            _entry(lines=lines, state=state)


def test_balance_uses_exact_decimal_truth_without_float_rounding_or_scale_changes():
    debit = Decimal("0.1000000000000000000000000001")
    credit = Decimal("0.1000000000000000000000000001")
    lines = (
        _line(side="debit", amount=str(debit)),
        _line(side="credit", amount=str(credit)),
    )
    entry = _entry(lines=lines)

    assert entry.lines[0].debit.as_tuple() == debit.as_tuple()
    assert entry.lines[1].credit.as_tuple() == credit.as_tuple()
    assert entry.is_balanced() is True


def test_line_entry_identity_is_opaque_to_this_foundation_and_order_is_preserved():
    first = _line(entry_id=111, side="credit", amount="50")
    second = _line(entry_id=222, side="debit", amount="50")
    lines = (first, second)
    entry = _entry(id=999, lines=lines)

    assert entry.lines is lines
    assert entry.lines == (first, second)
    assert entry.lines[0].entry_id == 111
    assert entry.lines[1].entry_id == 222
    assert entry.is_balanced() is True


def test_journal_entry_is_deterministic_hashable_and_has_no_transition_persistence_or_runtime_authority():
    import aqorath.journal_entry as domain

    lines = _balanced_lines(entry_id=77)
    instant = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    first = _entry(id=77, date=instant, lines=lines, state="posted")
    second = _entry(id=77, date=instant, lines=lines, state="posted")
    assert first == second
    assert hash(first) == hash(second)

    for forbidden_name in (
        "post",
        "reverse",
        "save_journal_entry",
        "post_entry",
        "persist_entry",
        "resolve_accounts",
    ):
        assert not hasattr(domain.JournalEntry, forbidden_name)
        assert not hasattr(domain, forbidden_name)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "models",
        "repository",
        "get_session",
        "sqlmodel",
        "sqlalchemy",
        "account_resolution",
        "posting_execution",
        "storage",
        "reporting_runtime",
        "application",
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source
