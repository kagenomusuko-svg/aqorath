"""Phase 6AZ.1 — frozen explicit JournalLine tuple balance-predicate contracts.

6AY owns the exact debit-minus-credit signed balance for one caller-supplied immutable
tuple of JournalLine values. This phase freezes only its boolean interpretation:
exact signed zero -> balanced, any nonzero signed amount -> unbalanced. It does not
reaggregate lines, select by account/entry/date/state/analytics, interpret account
nature, persist, report, post, or enter Application.
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


def test_journal_lines_are_balanced_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_lines_are_balanced).parameters) == (
        "lines",
    )

    source = inspect.getsource(domain.journal_lines_are_balanced).lower()
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


def test_lines_validation_is_inherited_from_signed_balance_authority():
    from aqorath.account_balance import journal_lines_are_balanced

    valid = (
        _line(side="debit", amount="2"),
        _line(side="credit", amount="2"),
    )
    assert journal_lines_are_balanced(valid) is True

    for invalid in ([], set(), {}, "lines", None):
        with pytest.raises(TypeError):
            journal_lines_are_balanced(invalid)


def test_empty_tuple_is_balanced_by_exact_zero_signed_balance():
    from aqorath.account_balance import journal_lines_are_balanced

    result = journal_lines_are_balanced(())
    assert type(result) is bool
    assert result is True


def test_equal_debit_and_credit_totals_are_balanced():
    from aqorath.account_balance import journal_lines_are_balanced

    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="40.25"),
        _line(side="credit", amount="59.75"),
    )
    assert journal_lines_are_balanced(lines) is True


def test_debit_excess_is_unbalanced():
    from aqorath.account_balance import journal_lines_are_balanced

    lines = (
        _line(side="debit", amount="100.00"),
        _line(side="credit", amount="99.99"),
    )
    assert journal_lines_are_balanced(lines) is False


def test_credit_excess_is_unbalanced():
    from aqorath.account_balance import journal_lines_are_balanced

    lines = (
        _line(side="debit", amount="99.99"),
        _line(side="credit", amount="100.00"),
    )
    assert journal_lines_are_balanced(lines) is False


def test_balance_uses_exact_decimal_zero_without_tolerance():
    from aqorath.account_balance import journal_lines_are_balanced

    balanced = (
        _line(side="debit", amount="1.0000000000000000000000000001"),
        _line(side="credit", amount="1.0000000000000000000000000001"),
    )
    debit_excess = (
        _line(side="debit", amount="1.0000000000000000000000000002"),
        _line(side="credit", amount="1.0000000000000000000000000001"),
    )
    credit_excess = (
        _line(side="debit", amount="1.0000000000000000000000000001"),
        _line(side="credit", amount="1.0000000000000000000000000002"),
    )

    assert journal_lines_are_balanced(balanced) is True
    assert journal_lines_are_balanced(debit_excess) is False
    assert journal_lines_are_balanced(credit_excess) is False


def test_mixed_accounts_and_natures_are_opaque_to_balance_predicate():
    from aqorath.account_balance import journal_lines_are_balanced

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
        _line(side="credit", amount="95", account=revenue),
        _line(side="credit", amount="5", account=extension),
    )
    assert journal_lines_are_balanced(lines) is True


def test_mixed_entry_ids_are_opaque_and_never_filtered():
    from aqorath.account_balance import journal_lines_are_balanced

    lines = (
        _line(side="debit", amount="10", entry_id=111),
        _line(side="credit", amount="4", entry_id=222),
        _line(side="credit", amount="6", entry_id=333),
    )
    assert journal_lines_are_balanced(lines) is True


def test_line_identity_description_and_analytics_do_not_change_balance_truth():
    from aqorath.account_balance import journal_lines_are_balanced
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
    plain = _line(side="credit", amount="25.00", entry_id=701)

    assert journal_lines_are_balanced((decorated, plain)) is True


def test_balance_predicate_returns_exact_bool_and_compares_against_decimal_zero():
    import aqorath.account_balance as domain

    lines = ()
    result = domain.journal_lines_are_balanced(lines)
    assert type(result) is bool

    source = inspect.getsource(domain.journal_lines_are_balanced)
    compact = source.replace(" ", "").replace("\n", "")
    assert "==Decimal(\"0\")" in compact or "==Decimal('0')" in compact


def test_balance_predicate_reuses_signed_balance_authority_with_same_tuple(monkeypatch):
    import aqorath.account_balance as domain

    lines = (
        _line(side="debit", amount="9"),
        _line(side="credit", amount="9"),
    )
    seen = []
    results = iter((Decimal("0.000"), Decimal("0.0001"), Decimal("-0.0001")))

    def fake_signed(value):
        seen.append(value)
        assert value is lines
        return next(results)

    monkeypatch.setattr(domain, "journal_lines_signed_balance", fake_signed)

    assert domain.journal_lines_are_balanced(lines) is True
    assert domain.journal_lines_are_balanced(lines) is False
    assert domain.journal_lines_are_balanced(lines) is False
    assert seen == [lines, lines, lines]
    assert all(value is lines for value in seen)


def test_balance_predicate_does_not_bypass_signed_balance_or_use_normal_entry_authorities(monkeypatch):
    import aqorath.account_balance as domain

    lines = ()

    def forbidden(*args, **kwargs):
        raise AssertionError("lower or unrelated authority must not run directly")

    monkeypatch.setattr(domain, "journal_lines_signed_balance", lambda value: Decimal("0"))
    monkeypatch.setattr(domain, "journal_line_totals", forbidden)
    monkeypatch.setattr(domain, "ledger_signed_balance", forbidden)
    monkeypatch.setattr(domain, "journal_line_signed_balance", forbidden)
    monkeypatch.setattr(domain, "journal_line_normal_balance", forbidden)
    monkeypatch.setattr(domain, "normal_balance_amount", forbidden)
    monkeypatch.setattr(domain, "normal_balance_for_account", forbidden)
    monkeypatch.setattr(domain, "journal_entry_totals", forbidden)
    monkeypatch.setattr(domain, "journal_entry_signed_balance", forbidden)

    assert domain.journal_lines_are_balanced(lines) is True


def test_balance_predicate_never_reaggregates_rounds_or_uses_tolerance():
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_lines_are_balanced).lower()
    for forbidden in (
        "sum(",
        ".debit",
        ".credit",
        "abs(",
        "round(",
        "quantize",
        "isclose",
        "tolerance",
        "epsilon",
        "float(",
    ):
        assert forbidden not in source


def test_balance_predicate_never_mutates_inputs_and_is_deterministic_without_ambient_values():
    import aqorath.account_balance as domain

    first = _line(side="debit", amount="20.000", line_id=1)
    second = _line(side="credit", amount="20.000", line_id=2)
    lines = (first, second)
    before = (lines, first.debit, first.credit, second.debit, second.credit)

    one = domain.journal_lines_are_balanced(lines)
    two = domain.journal_lines_are_balanced(lines)

    after = (lines, first.debit, first.credit, second.debit, second.credit)
    assert after == before
    assert lines[0] is first
    assert lines[1] is second
    assert one is True
    assert two is True

    source = inspect.getsource(domain.journal_lines_are_balanced).lower()
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


def test_balance_predicate_does_not_filter_persist_post_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_lines_are_balanced).lower()
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
        "posting",
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
    assert "journal_lines_are_balanced" not in application_source
