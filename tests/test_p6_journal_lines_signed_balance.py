"""Phase 6AY.1 — frozen explicit JournalLine tuple signed-balance contracts.

6AS owns exact debit/credit aggregation for an explicit immutable tuple of JournalLine
values, and 6AQ owns LedgerSignedBalance = debit total - credit total. This phase freezes
only their composition for caller-supplied lines. It does not select by account, entry,
date, state or analytics; interpret account nature; persist; report; or enter Application.
"""

from decimal import Decimal
import inspect

import pytest


def _account(*, code="1101", nature="debit", account_id=None, canonical=True):
    from aqorath.account import Account

    return Account(
        id=account_id,
        code=code,
        name=f"Cuenta {code}",
        account_type="asset" if nature == "debit" else "income",
        subtype="current" if nature == "debit" else "operating",
        nature=nature,
        is_canonical=canonical,
    )


def _line(
    *,
    side="debit",
    amount="10.00",
    account=None,
    entry_id=20,
    line_id=None,
    description=None,
    analytics=(),
):
    from aqorath.journal_line import JournalLine

    value = Decimal(amount)
    debit = value if side == "debit" else Decimal("0")
    credit = value if side == "credit" else Decimal("0")
    return JournalLine(
        id=line_id,
        entry_id=entry_id,
        account=account or _account(),
        debit=debit,
        credit=credit,
        description=description,
        analytics=analytics,
    )


def test_journal_lines_signed_balance_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_lines_signed_balance).parameters) == (
        "lines",
    )

    source = inspect.getsource(domain.journal_lines_signed_balance).lower()
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


def test_lines_must_be_exact_immutable_tuple_through_frozen_aggregation_authority():
    from aqorath.account_balance import journal_lines_signed_balance

    valid = (_line(side="debit", amount="2"),)
    assert journal_lines_signed_balance(valid) == Decimal("2")

    for invalid in ([], set(), {}, "lines", None):
        with pytest.raises(TypeError):
            journal_lines_signed_balance(invalid)


def test_empty_tuple_returns_exact_decimal_zero_signed_balance():
    from aqorath.account_balance import journal_lines_signed_balance

    result = journal_lines_signed_balance(())
    assert type(result) is Decimal
    assert result == Decimal("0")


def test_single_debit_line_returns_positive_signed_balance():
    from aqorath.account_balance import journal_lines_signed_balance

    line = _line(side="debit", amount="123.4500")
    assert journal_lines_signed_balance((line,)) == Decimal("123.4500")


def test_single_credit_line_returns_negative_signed_balance():
    from aqorath.account_balance import journal_lines_signed_balance

    line = _line(side="credit", amount="87.6500")
    assert journal_lines_signed_balance((line,)) == Decimal("-87.6500")


def test_multiple_lines_return_exact_debit_excess():
    from aqorath.account_balance import journal_lines_signed_balance

    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="40.25"),
        _line(side="debit", amount="12.75"),
        _line(side="credit", amount="60.00"),
    )
    assert journal_lines_signed_balance(lines) == Decimal("12.50")


def test_multiple_lines_return_exact_credit_excess():
    from aqorath.account_balance import journal_lines_signed_balance

    lines = (
        _line(side="debit", amount="20.00"),
        _line(side="credit", amount="25.50"),
        _line(side="credit", amount="4.50"),
    )
    assert journal_lines_signed_balance(lines) == Decimal("-10.00")


def test_mixed_accounts_and_natures_are_opaque_and_never_filtered_or_normalized():
    from aqorath.account_balance import journal_lines_signed_balance

    bank = _account(code="1101", nature="debit", account_id=1)
    revenue = _account(code="4101", nature="credit", account_id=2)
    extension = _account(
        code="4101.001",
        nature="credit",
        account_id=None,
        canonical=False,
    )
    lines = (
        _line(side="debit", amount="100", account=bank),
        _line(side="credit", amount="70", account=revenue),
        _line(side="debit", amount="5", account=extension),
    )
    assert journal_lines_signed_balance(lines) == Decimal("35")


def test_mixed_entry_ids_are_opaque_and_never_filtered():
    from aqorath.account_balance import journal_lines_signed_balance

    lines = (
        _line(side="debit", amount="10", entry_id=111),
        _line(side="credit", amount="4", entry_id=222),
        _line(side="credit", amount="6", entry_id=333),
    )
    assert journal_lines_signed_balance(lines) == Decimal("0")


def test_line_identity_description_and_analytics_do_not_change_signed_balance():
    from aqorath.account_balance import journal_lines_signed_balance
    from aqorath.analytical_dimension import AnalyticalDimensionValue

    analytic = AnalyticalDimensionValue(
        id=None,
        dimension_id=9,
        code="EDU",
        name="Educación",
    )
    decorated = _line(
        side="debit",
        amount="25.00",
        line_id=99,
        entry_id=700,
        description="Aplicación analítica",
        analytics=(analytic,),
    )
    plain = _line(side="credit", amount="5.00", entry_id=701)
    assert journal_lines_signed_balance((decorated, plain)) == Decimal("20.00")


def test_line_order_does_not_change_numeric_signed_balance():
    from aqorath.account_balance import journal_lines_signed_balance

    first = _line(side="debit", amount="9.75")
    second = _line(side="credit", amount="2.50")
    third = _line(side="debit", amount="0.25")
    assert journal_lines_signed_balance((first, second, third)) == (
        journal_lines_signed_balance((third, first, second))
    ) == Decimal("7.50")


def test_signed_balance_preserves_exact_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import journal_lines_signed_balance

    lines = (
        _line(side="debit", amount="0.1000000000000000000000000002"),
        _line(side="debit", amount="0.0000000000000000000000000001"),
        _line(side="credit", amount="0.2000000000000000000000000003"),
    )
    result = journal_lines_signed_balance(lines)
    assert result == Decimal("-0.1000000000000000000000000000")
    assert type(result) is Decimal

    source = inspect.getsource(journal_lines_signed_balance).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_signed_balance_reuses_totals_then_ledger_authority_in_exact_order(monkeypatch):
    import aqorath.account_balance as domain

    lines = (
        _line(side="debit", amount="9"),
        _line(side="credit", amount="4"),
    )
    debit_total = Decimal("123.4500")
    credit_total = Decimal("23.4500")
    sentinel = Decimal("999.000")
    seen = []

    def fake_totals(value):
        seen.append(("totals", value))
        assert value is lines
        return debit_total, credit_total

    def fake_ledger(debit, credit):
        seen.append(("ledger", debit, credit))
        assert debit is debit_total
        assert credit is credit_total
        return sentinel

    monkeypatch.setattr(domain, "journal_line_totals", fake_totals)
    monkeypatch.setattr(domain, "ledger_signed_balance", fake_ledger)

    result = domain.journal_lines_signed_balance(lines)
    assert result is sentinel
    assert seen == [
        ("totals", lines),
        ("ledger", debit_total, credit_total),
    ]


def test_tuple_signed_balance_does_not_call_per_line_normal_or_entry_authorities(monkeypatch):
    import aqorath.account_balance as domain

    def forbidden(*args, **kwargs):
        raise AssertionError("unrelated balance authority must not run")

    monkeypatch.setattr(domain, "journal_line_signed_balance", forbidden)
    monkeypatch.setattr(domain, "journal_line_normal_balance", forbidden)
    monkeypatch.setattr(domain, "normal_balance_amount", forbidden)
    monkeypatch.setattr(domain, "normal_balance_for_account", forbidden)
    monkeypatch.setattr(domain, "journal_entry_totals", forbidden)
    monkeypatch.setattr(domain, "journal_entry_signed_balance", forbidden)

    lines = (
        _line(side="debit", amount="8"),
        _line(side="credit", amount="3"),
    )
    assert domain.journal_lines_signed_balance(lines) == Decimal("5")


def test_tuple_signed_balance_never_mutates_inputs_and_is_deterministic():
    import aqorath.account_balance as domain

    first = _line(side="debit", amount="20.000", line_id=1)
    second = _line(side="credit", amount="7.000", line_id=2)
    lines = (first, second)
    before = (lines, first.debit, first.credit, second.debit, second.credit)

    one = domain.journal_lines_signed_balance(lines)
    two = domain.journal_lines_signed_balance(lines)

    after = (lines, first.debit, first.credit, second.debit, second.credit)
    assert after == before
    assert lines[0] is first
    assert lines[1] is second
    assert one == two == Decimal("13.000")

    source = inspect.getsource(domain.journal_lines_signed_balance).lower()
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


def test_tuple_signed_balance_does_not_filter_persist_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_lines_signed_balance).lower()
    for forbidden in (
        "account.code",
        "account.id",
        "entry_id ==",
        "state",
        "date",
        "analytics",
        "catalog",
        "repository",
        "get_session",
        "storage",
        "reporting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "application",
        "core",
        "filter",
        "select",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "journal_lines_signed_balance" not in application_source
