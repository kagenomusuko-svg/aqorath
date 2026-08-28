"""Phase 6AQ.1 — frozen account-balance semantic contracts.

The architecture explicitly distinguishes LedgerSignedBalance (debit minus credit) from
NormalBalanceAmount (the same signed truth interpreted through account nature). This phase
freezes only those pure Decimal authorities. It does not read catalogs, resolve accounts,
compute statements, persist balances, or replace transitional accounting_rules yet.
"""

from decimal import Decimal
import inspect

import pytest


def test_account_balance_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.ledger_signed_balance).parameters) == (
        "debit_total",
        "credit_total",
    )
    assert tuple(inspect.signature(domain.normal_balance_amount).parameters) == (
        "ledger_signed_balance",
        "nature",
    )

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


def test_ledger_signed_balance_requires_exact_decimal_totals_without_numeric_coercion():
    from aqorath.account_balance import ledger_signed_balance

    assert ledger_signed_balance(Decimal("1"), Decimal("0")) == Decimal("1")

    for invalid in (0, 1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            ledger_signed_balance(invalid, Decimal("0"))
        with pytest.raises(TypeError):
            ledger_signed_balance(Decimal("0"), invalid)


def test_ledger_signed_balance_requires_finite_nonnegative_totals():
    from aqorath.account_balance import ledger_signed_balance

    for invalid in (
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-0.01"),
    ):
        with pytest.raises(ValueError):
            ledger_signed_balance(invalid, Decimal("0"))
        with pytest.raises(ValueError):
            ledger_signed_balance(Decimal("0"), invalid)


def test_ledger_signed_balance_is_exact_debit_minus_credit():
    from aqorath.account_balance import ledger_signed_balance

    assert ledger_signed_balance(Decimal("40"), Decimal("0")) == Decimal("40")
    assert ledger_signed_balance(Decimal("0"), Decimal("100")) == Decimal("-100")
    assert ledger_signed_balance(Decimal("75.25"), Decimal("20.10")) == Decimal("55.15")


def test_ledger_signed_balance_can_be_positive_negative_or_zero():
    from aqorath.account_balance import ledger_signed_balance

    assert ledger_signed_balance(Decimal("10"), Decimal("4")) > Decimal("0")
    assert ledger_signed_balance(Decimal("4"), Decimal("10")) < Decimal("0")
    assert ledger_signed_balance(Decimal("10"), Decimal("10")) == Decimal("0")


def test_ledger_signed_balance_uses_decimal_precision_without_float_or_quantization():
    from aqorath.account_balance import ledger_signed_balance

    debit = Decimal("0.1000000000000000000000000002")
    credit = Decimal("0.0000000000000000000000000001")
    result = ledger_signed_balance(debit, credit)

    assert result == Decimal("0.1000000000000000000000000001")
    assert isinstance(result, Decimal)


def test_normal_balance_amount_requires_exact_finite_decimal_signed_balance():
    from aqorath.account_balance import normal_balance_amount

    assert normal_balance_amount(Decimal("1"), "debit") == Decimal("1")

    for invalid in (0, 1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            normal_balance_amount(invalid, "debit")

    for invalid in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValueError):
            normal_balance_amount(invalid, "debit")


def test_normal_balance_nature_is_exact_governed_debit_or_credit_token():
    from aqorath.account_balance import normal_balance_amount

    assert normal_balance_amount(Decimal("1"), "debit") == Decimal("1")
    assert normal_balance_amount(Decimal("-1"), "credit") == Decimal("1")

    for invalid in (
        None,
        1,
        "",
        " debit",
        "debit ",
        "DEBIT",
        "CREDIT",
        "Deudora",
        "Acreedora",
        "deudora",
        "acreedora",
        "asset",
    ):
        with pytest.raises((TypeError, ValueError)):
            normal_balance_amount(Decimal("1"), invalid)


def test_debit_nature_preserves_ledger_signed_balance_without_sign_change():
    from aqorath.account_balance import normal_balance_amount

    for value in (Decimal("40"), Decimal("-3.25"), Decimal("0")):
        assert normal_balance_amount(value, "debit") == value


def test_credit_nature_negates_ledger_signed_balance_exactly():
    from aqorath.account_balance import normal_balance_amount

    assert normal_balance_amount(Decimal("-100"), "credit") == Decimal("100")
    assert normal_balance_amount(Decimal("25.50"), "credit") == Decimal("-25.50")
    assert normal_balance_amount(Decimal("0"), "credit") == Decimal("0")


def test_normal_balance_does_not_absolute_value_or_hide_abnormal_balance():
    from aqorath.account_balance import normal_balance_amount

    assert normal_balance_amount(Decimal("-12"), "debit") == Decimal("-12")
    assert normal_balance_amount(Decimal("12"), "credit") == Decimal("-12")


def test_normal_balance_preserves_decimal_scale_without_quantization():
    from aqorath.account_balance import normal_balance_amount

    debit_value = Decimal("123.450000")
    credit_value = Decimal("-123.450000")

    debit_result = normal_balance_amount(debit_value, "debit")
    credit_result = normal_balance_amount(credit_value, "credit")

    assert debit_result.as_tuple() == debit_value.as_tuple()
    assert credit_result == Decimal("123.450000")
    assert credit_result.as_tuple().exponent == credit_value.as_tuple().exponent


def test_documented_income_and_expense_sign_semantics_compose_exactly():
    from aqorath.account_balance import ledger_signed_balance, normal_balance_amount

    income_signed = ledger_signed_balance(Decimal("0"), Decimal("100"))
    expense_signed = ledger_signed_balance(Decimal("40"), Decimal("0"))

    income_normal = normal_balance_amount(income_signed, "credit")
    expense_normal = normal_balance_amount(expense_signed, "debit")

    assert income_signed == Decimal("-100")
    assert expense_signed == Decimal("40")
    assert income_normal == Decimal("100")
    assert expense_normal == Decimal("40")
    assert income_normal - expense_normal == Decimal("60")


def test_balance_semantics_are_independent_of_account_type_code_name_or_catalog_lookup():
    import aqorath.account_balance as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "account_type",
        "account_code",
        "catalog",
        "catalogo",
        "load_catalog",
        "resolve_catalog",
        "accounting_rules",
    ):
        assert forbidden not in source


def test_balance_semantics_do_not_compute_statement_totals_or_reporting_results():
    import aqorath.account_balance as domain

    for forbidden_name in (
        "compute_totals_by_tipo",
        "compute_resultado_ejercicio",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert not hasattr(domain, forbidden_name)

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "reporting",
        "reporting_runtime",
        "storage",
        "repository",
        "get_session",
    ):
        assert forbidden not in source


def test_account_balance_semantics_are_deterministic_without_ambient_inputs_or_legacy_aliases():
    import aqorath.account_balance as domain

    first = domain.ledger_signed_balance(Decimal("10.000"), Decimal("3.000"))
    second = domain.ledger_signed_balance(Decimal("10.000"), Decimal("3.000"))
    assert first == second
    assert domain.normal_balance_amount(first, "debit") == domain.normal_balance_amount(
        second,
        "debit",
    )

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "deudora",
        "acreedora",
    ):
        assert forbidden not in source
