"""Phase 6AW.1 — frozen pure JournalLine normal-balance contracts.

JournalLine already owns one explicit Account and exact debit/credit truth, while 6AR
owns Account-normal-balance interpretation. This phase freezes only their composition:
nominal JournalLine -> exact normal-balance effect through line.account. It does not
aggregate lines, select accounts, infer lifecycle, persist, report, or enter Application.
"""

from decimal import Decimal
import inspect

import pytest


def _account(*, nature="debit", canonical=True, account_id=None, code=None):
    from aqorath.account import Account

    if code is None:
        code = "1101" if nature == "debit" else "4101"
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
    nature="debit",
    side="debit",
    amount="10.00",
    account=None,
    line_id=None,
    entry_id=20,
    description=None,
    analytics=(),
):
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
        account=account or _account(nature=nature),
        debit=debit,
        credit=credit,
        description=description,
        analytics=analytics,
    )


def test_journal_line_normal_balance_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.journal_line_normal_balance).parameters) == (
        "line",
    )

    source = inspect.getsource(domain.journal_line_normal_balance).lower()
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


def test_line_must_be_nominal_journal_line_not_duck_typed_metadata():
    from aqorath.account_balance import journal_line_normal_balance

    line = _line()
    assert journal_line_normal_balance(line) == Decimal("10.00")

    for invalid in (
        object(),
        {"account": line.account, "debit": line.debit, "credit": line.credit},
        line.account,
        None,
    ):
        with pytest.raises(TypeError):
            journal_line_normal_balance(invalid)


def test_transient_line_and_transient_account_identity_are_valid():
    from aqorath.account_balance import journal_line_normal_balance

    account = _account(nature="debit", account_id=None)
    line = _line(account=account, line_id=None, side="debit", amount="25.00")

    assert line.id is None
    assert line.account.id is None
    assert journal_line_normal_balance(line) == Decimal("25.00")


def test_debit_nature_debit_line_is_positive_normal_balance_effect():
    from aqorath.account_balance import journal_line_normal_balance

    line = _line(nature="debit", side="debit", amount="80.00")
    assert journal_line_normal_balance(line) == Decimal("80.00")


def test_debit_nature_credit_line_remains_negative_abnormal_effect():
    from aqorath.account_balance import journal_line_normal_balance

    line = _line(nature="debit", side="credit", amount="80.00")
    assert journal_line_normal_balance(line) == Decimal("-80.00")


def test_credit_nature_credit_line_is_positive_normal_balance_effect():
    from aqorath.account_balance import journal_line_normal_balance

    line = _line(nature="credit", side="credit", amount="80.00")
    assert journal_line_normal_balance(line) == Decimal("80.00")


def test_credit_nature_debit_line_remains_negative_abnormal_effect():
    from aqorath.account_balance import journal_line_normal_balance

    line = _line(nature="credit", side="debit", amount="80.00")
    assert journal_line_normal_balance(line) == Decimal("-80.00")


def test_noncanonical_account_is_valid_and_uses_its_explicit_nature():
    from aqorath.account_balance import journal_line_normal_balance

    account = _account(
        nature="credit",
        canonical=False,
        account_id=77,
        code="4101.001",
    )
    line = _line(account=account, side="credit", amount="33.00")

    assert line.account.is_canonical is False
    assert journal_line_normal_balance(line) == Decimal("33.00")


def test_line_identity_description_entry_id_and_analytics_are_opaque():
    from aqorath.account_balance import journal_line_normal_balance
    from aqorath.analytical_dimension import AnalyticalDimensionValue

    analytic = AnalyticalDimensionValue(
        id=None,
        dimension_id=9,
        code="EDU",
        name="Educación",
    )
    account = _account(nature="debit", account_id=5)
    first = _line(
        account=account,
        side="debit",
        amount="12.50",
        line_id=None,
        entry_id=1,
        description=None,
        analytics=(),
    )
    second = _line(
        account=account,
        side="debit",
        amount="12.50",
        line_id=999,
        entry_id=777,
        description="Detalle",
        analytics=(analytic,),
    )

    assert journal_line_normal_balance(first) == (
        journal_line_normal_balance(second)
    ) == Decimal("12.50")


def test_normal_balance_preserves_exact_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import journal_line_normal_balance

    amount = "0.1000000000000000000000000001"
    line = _line(nature="credit", side="credit", amount=amount)
    result = journal_line_normal_balance(line)

    assert result == Decimal(amount)
    assert type(result) is Decimal

    source = inspect.getsource(journal_line_normal_balance).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_normal_balance_reuses_account_composition_with_exact_line_values(monkeypatch):
    import aqorath.account_balance as domain

    line = _line(nature="credit", side="debit", amount="12.34")
    sentinel = Decimal("987.654")
    seen = []

    def fake_normal(account, debit_total, credit_total):
        seen.append((account, debit_total, credit_total))
        return sentinel

    monkeypatch.setattr(domain, "normal_balance_for_account", fake_normal)

    result = domain.journal_line_normal_balance(line)

    assert result is sentinel
    assert seen == [(line.account, line.debit, line.credit)]
    assert seen[0][0] is line.account
    assert seen[0][1] is line.debit
    assert seen[0][2] is line.credit


def test_line_normal_balance_does_not_call_aggregate_or_entry_authorities(monkeypatch):
    import aqorath.account_balance as domain

    line = _line(nature="debit", side="debit", amount="8")

    def forbidden(*args, **kwargs):
        raise AssertionError("aggregate/entry authorities must not run for one line")

    monkeypatch.setattr(domain, "journal_line_totals", forbidden)
    monkeypatch.setattr(domain, "journal_entry_totals", forbidden)
    monkeypatch.setattr(domain, "journal_entry_signed_balance", forbidden)

    assert domain.journal_line_normal_balance(line) == Decimal("8")


def test_line_normal_balance_does_not_reimplement_account_structure_or_nature_rules():
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_line_normal_balance).lower()
    for forbidden in (
        ".nature",
        "account_type",
        "subtype",
        ".code",
        "is_canonical",
        "ledger_signed_balance",
        "normal_balance_amount",
    ):
        assert forbidden not in source


def test_line_normal_balance_never_mutates_line_account_or_money_identity():
    from aqorath.account_balance import journal_line_normal_balance

    account = _account(nature="debit", account_id=12)
    line = _line(account=account, side="debit", amount="20.000", line_id=3)
    before = (
        line.id,
        line.entry_id,
        line.account,
        line.debit,
        line.credit,
        line.description,
        line.analytics,
    )

    journal_line_normal_balance(line)

    after = (
        line.id,
        line.entry_id,
        line.account,
        line.debit,
        line.credit,
        line.description,
        line.analytics,
    )
    assert after == before
    assert line.account is account
    assert line.debit is before[3]
    assert line.credit is before[4]


def test_journal_line_normal_balance_is_deterministic_without_ambient_inputs():
    import aqorath.account_balance as domain

    line = _line(nature="credit", side="credit", amount="10.000")
    first = domain.journal_line_normal_balance(line)
    second = domain.journal_line_normal_balance(line)
    assert first == second == Decimal("10.000")

    source = inspect.getsource(domain.journal_line_normal_balance).lower()
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


def test_journal_line_normal_balance_does_not_persist_report_filter_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.journal_line_normal_balance).lower()
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
        "filter",
        "select",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "journal_line_normal_balance" not in application_source
