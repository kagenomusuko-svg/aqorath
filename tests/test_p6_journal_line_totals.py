"""Phase 6AS.1 — frozen pure JournalLine total aggregation contracts.

JournalLine already owns exact debit/credit monetary truth. This phase freezes only the
pure aggregation boundary that sums an explicit immutable tuple of lines into exact debit
and credit totals. It does not select lines by account, entry, date, state or analytics;
it does not compute signed/normal balances, persist, report, or enter Application.
"""

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


def _line(*, side="debit", amount="10.00", account=None, entry_id=20, line_id=None,
          description=None, analytics=()):
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
        description=description,
        analytics=analytics,
    )


def test_journal_line_totals_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_line_totals).parameters) == ("lines",)

    source = inspect.getsource(domain.journal_line_totals).lower()
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


def test_lines_must_be_exact_immutable_tuple():
    from aqorath.account_balance import journal_line_totals

    valid = (_line(),)
    assert journal_line_totals(valid) == (Decimal("10.00"), Decimal("0"))

    for invalid in ([], set(), {}, "lines", None):
        with pytest.raises(TypeError):
            journal_line_totals(invalid)


def test_line_items_must_be_nominal_journal_lines():
    from aqorath.account_balance import journal_line_totals

    valid = _line()
    for invalid in (
        (object(),),
        ({"debit": Decimal("1"), "credit": Decimal("0")},),
        (valid, object()),
    ):
        with pytest.raises(TypeError):
            journal_line_totals(invalid)


def test_empty_tuple_returns_exact_decimal_zero_totals():
    from aqorath.account_balance import journal_line_totals

    result = journal_line_totals(())

    assert type(result) is tuple
    assert len(result) == 2
    assert result == (Decimal("0"), Decimal("0"))
    assert all(type(value) is Decimal for value in result)


def test_single_debit_line_contributes_only_to_debit_total():
    from aqorath.account_balance import journal_line_totals

    line = _line(side="debit", amount="123.4500")
    assert journal_line_totals((line,)) == (
        Decimal("123.4500"),
        Decimal("0"),
    )


def test_single_credit_line_contributes_only_to_credit_total():
    from aqorath.account_balance import journal_line_totals

    line = _line(side="credit", amount="87.6500")
    assert journal_line_totals((line,)) == (
        Decimal("0"),
        Decimal("87.6500"),
    )


def test_multiple_lines_sum_debit_and_credit_sides_independently():
    from aqorath.account_balance import journal_line_totals

    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="40.25"),
        _line(side="debit", amount="12.75"),
        _line(side="credit", amount="60.00"),
    )

    assert journal_line_totals(lines) == (
        Decimal("112.75"),
        Decimal("100.25"),
    )


def test_mixed_accounts_are_opaque_and_are_not_filtered_by_this_aggregation():
    from aqorath.account_balance import journal_line_totals

    bank = _account(code="1101", name="Bancos", nature="debit")
    revenue = _account(
        id=11,
        code="4101",
        name="Ingresos",
        account_type="income",
        subtype="operating",
        nature="credit",
    )
    lines = (
        _line(side="debit", amount="100", account=bank),
        _line(side="credit", amount="100", account=revenue),
    )

    assert journal_line_totals(lines) == (Decimal("100"), Decimal("100"))


def test_mixed_entry_ids_are_opaque_and_are_not_filtered_by_this_aggregation():
    from aqorath.account_balance import journal_line_totals

    lines = (
        _line(side="debit", amount="10", entry_id=111),
        _line(side="credit", amount="4", entry_id=222),
        _line(side="credit", amount="6", entry_id=333),
    )

    assert journal_line_totals(lines) == (Decimal("10"), Decimal("10"))


def test_line_identity_description_and_analytics_do_not_change_monetary_totals():
    from aqorath.account_balance import journal_line_totals
    from aqorath.analytical_dimension import AnalyticalDimensionValue

    analytical_value = AnalyticalDimensionValue(
        id=None,
        dimension_id=7,
        code="EDU",
        name="Educación",
    )
    decorated = _line(
        side="debit",
        amount="25.00",
        line_id=99,
        description="Aplicación analítica",
        analytics=(analytical_value,),
    )
    plain = _line(side="credit", amount="5.00", entry_id=21)

    assert journal_line_totals((decorated, plain)) == (
        Decimal("25.00"),
        Decimal("5.00"),
    )


def test_line_order_does_not_change_numeric_totals():
    from aqorath.account_balance import journal_line_totals

    first = _line(side="debit", amount="9.75")
    second = _line(side="credit", amount="2.50")
    third = _line(side="debit", amount="0.25")

    assert journal_line_totals((first, second, third)) == (
        journal_line_totals((third, first, second))
    ) == (Decimal("10.00"), Decimal("2.50"))


def test_aggregation_preserves_exact_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import journal_line_totals

    lines = (
        _line(side="debit", amount="0.1000000000000000000000000002"),
        _line(side="debit", amount="0.0000000000000000000000000001"),
        _line(side="credit", amount="0.2000000000000000000000000003"),
    )
    debit_total, credit_total = journal_line_totals(lines)

    assert debit_total == Decimal("0.1000000000000000000000000003")
    assert credit_total == Decimal("0.2000000000000000000000000003")
    assert type(debit_total) is Decimal
    assert type(credit_total) is Decimal

    source = inspect.getsource(journal_line_totals).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_aggregation_does_not_compute_signed_or_normal_balance(monkeypatch):
    import aqorath.account_balance as domain

    def forbidden(*args, **kwargs):
        raise AssertionError("balance interpretation must not run during line aggregation")

    monkeypatch.setattr(domain, "ledger_signed_balance", forbidden)
    monkeypatch.setattr(domain, "normal_balance_amount", forbidden)
    monkeypatch.setattr(domain, "normal_balance_for_account", forbidden)

    result = domain.journal_line_totals(
        (
            _line(side="debit", amount="8"),
            _line(side="credit", amount="3"),
        )
    )
    assert result == (Decimal("8"), Decimal("3"))


def test_aggregation_never_mutates_the_input_tuple_or_journal_lines():
    from aqorath.account_balance import journal_line_totals

    first = _line(side="debit", amount="20.00", line_id=1)
    second = _line(side="credit", amount="7.00", line_id=2)
    lines = (first, second)
    before = (
        lines,
        first.debit,
        first.credit,
        second.debit,
        second.credit,
    )

    journal_line_totals(lines)

    after = (
        lines,
        first.debit,
        first.credit,
        second.debit,
        second.credit,
    )
    assert after == before
    assert lines[0] is first
    assert lines[1] is second


def test_journal_line_totals_are_deterministic_without_ambient_inputs():
    import aqorath.account_balance as domain

    lines = (
        _line(side="debit", amount="10.000"),
        _line(side="credit", amount="3.000"),
    )
    first = domain.journal_line_totals(lines)
    second = domain.journal_line_totals(lines)
    assert first == second == (Decimal("10.000"), Decimal("3.000"))

    source = inspect.getsource(domain.journal_line_totals).lower()
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


def test_journal_line_totals_do_not_filter_persist_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_line_totals).lower()
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
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "journal_line_totals" not in application_source
