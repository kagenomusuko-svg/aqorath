"""Phase 6AR.1 — frozen Account + balance semantic composition contracts.

6AQ separated LedgerSignedBalance from NormalBalanceAmount. The Account domain now owns
one explicit governed nature token, so this phase freezes only their pure composition:
nominal Account + exact debit/credit totals -> NormalBalanceAmount. It does not inspect
catalog metadata, resolve accounts, aggregate ledger lines, compute statements, persist,
or enter Application.
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


def test_normal_balance_for_account_public_contract_is_exact_and_pure():
    import aqorath.account_balance as domain

    assert tuple(inspect.signature(domain.normal_balance_for_account).parameters) == (
        "account",
        "debit_total",
        "credit_total",
    )

    source = inspect.getsource(domain.normal_balance_for_account).lower()
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


def test_account_must_be_nominal_account_not_duck_typed_metadata():
    from aqorath.account_balance import normal_balance_for_account

    account = _account()
    assert normal_balance_for_account(
        account,
        Decimal("10"),
        Decimal("0"),
    ) == Decimal("10")

    for invalid in (
        object(),
        {"nature": "debit"},
        "1101",
        None,
    ):
        with pytest.raises(TypeError):
            normal_balance_for_account(invalid, Decimal("10"), Decimal("0"))


def test_transient_and_noncanonical_accounts_are_valid_for_pure_balance_composition():
    from aqorath.account_balance import normal_balance_for_account

    account = _account(
        id=None,
        code="1101-LOCAL",
        is_canonical=False,
    )
    result = normal_balance_for_account(
        account,
        Decimal("125.00"),
        Decimal("25.00"),
    )

    assert result == Decimal("100.00")


def test_debit_and_credit_totals_require_exact_decimal_without_numeric_coercion():
    from aqorath.account_balance import normal_balance_for_account

    account = _account()
    for invalid in (0, 1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            normal_balance_for_account(account, invalid, Decimal("0"))
        with pytest.raises(TypeError):
            normal_balance_for_account(account, Decimal("0"), invalid)


def test_debit_and_credit_totals_must_be_finite_and_nonnegative():
    from aqorath.account_balance import normal_balance_for_account

    account = _account()
    for invalid in (
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-0.01"),
    ):
        with pytest.raises(ValueError):
            normal_balance_for_account(account, invalid, Decimal("0"))
        with pytest.raises(ValueError):
            normal_balance_for_account(account, Decimal("0"), invalid)


def test_debit_nature_composes_exact_ledger_signed_balance_without_sign_change():
    from aqorath.account_balance import normal_balance_for_account

    account = _account(nature="debit")
    assert normal_balance_for_account(
        account,
        Decimal("75.25"),
        Decimal("20.10"),
    ) == Decimal("55.15")
    assert normal_balance_for_account(
        account,
        Decimal("5"),
        Decimal("20"),
    ) == Decimal("-15")


def test_credit_nature_composes_exact_ledger_signed_balance_with_sign_inversion():
    from aqorath.account_balance import normal_balance_for_account

    account = _account(
        code="4101",
        name="Ingresos",
        account_type="income",
        subtype="operating",
        nature="credit",
    )
    assert normal_balance_for_account(
        account,
        Decimal("0"),
        Decimal("100"),
    ) == Decimal("100")
    assert normal_balance_for_account(
        account,
        Decimal("25.50"),
        Decimal("0"),
    ) == Decimal("-25.50")


def test_zero_totals_are_valid_and_return_exact_zero_for_either_nature():
    from aqorath.account_balance import normal_balance_for_account

    for nature in ("debit", "credit"):
        account = _account(nature=nature)
        result = normal_balance_for_account(
            account,
            Decimal("0.0000"),
            Decimal("0.0000"),
        )
        assert result == Decimal("0.0000")


def test_abnormal_balance_remains_negative_instead_of_being_absolute_valued():
    from aqorath.account_balance import normal_balance_for_account

    debit_account = _account(nature="debit")
    credit_account = _account(
        account_type="liability",
        nature="credit",
    )

    assert normal_balance_for_account(
        debit_account,
        Decimal("0"),
        Decimal("12"),
    ) == Decimal("-12")
    assert normal_balance_for_account(
        credit_account,
        Decimal("12"),
        Decimal("0"),
    ) == Decimal("-12")


def test_decimal_precision_and_result_scale_are_not_quantized():
    from aqorath.account_balance import normal_balance_for_account

    account = _account(nature="debit")
    debit = Decimal("123.4500000000000000000000000002")
    credit = Decimal("0.0000000000000000000000000001")
    result = normal_balance_for_account(account, debit, credit)

    assert result == Decimal("123.4500000000000000000000000001")
    assert isinstance(result, Decimal)


def test_only_account_nature_affects_sign_interpretation_not_other_account_metadata():
    from aqorath.account_balance import normal_balance_for_account

    first = _account(
        id=None,
        code="A",
        name="Cuenta A",
        account_type="asset",
        subtype="current",
        nature="debit",
        is_canonical=True,
        name_osc="OSC A",
        name_comercial="Comercial A",
    )
    second = _account(
        id=999,
        code="B",
        name="Cuenta B",
        account_type="expense",
        subtype="future-open-token",
        nature="debit",
        is_canonical=False,
        name_osc=None,
        name_comercial=None,
    )

    assert normal_balance_for_account(first, Decimal("10"), Decimal("3")) == (
        normal_balance_for_account(second, Decimal("10"), Decimal("3"))
    )


def test_composition_reuses_frozen_ledger_and_normal_balance_authorities(monkeypatch):
    import aqorath.account_balance as domain

    account = _account(nature="credit")
    signed_sentinel = Decimal("-777.123")
    normal_sentinel = Decimal("888.456")
    calls = []

    def fake_ledger(debit_total, credit_total):
        calls.append(("ledger", debit_total, credit_total))
        return signed_sentinel

    def fake_normal(ledger_signed_balance, nature):
        calls.append(("normal", ledger_signed_balance, nature))
        return normal_sentinel

    monkeypatch.setattr(domain, "ledger_signed_balance", fake_ledger)
    monkeypatch.setattr(domain, "normal_balance_amount", fake_normal)

    result = domain.normal_balance_for_account(
        account,
        Decimal("12.34"),
        Decimal("56.78"),
    )

    assert result is normal_sentinel
    assert calls == [
        ("ledger", Decimal("12.34"), Decimal("56.78")),
        ("normal", signed_sentinel, "credit"),
    ]


def test_composition_preserves_account_identity_and_never_mutates_domain_truth():
    from aqorath.account_balance import normal_balance_for_account

    account = _account(id=None, is_canonical=False)
    before = (
        account.id,
        account.code,
        account.name,
        account.account_type,
        account.subtype,
        account.nature,
        account.is_canonical,
        account.name_osc,
        account.name_comercial,
    )

    normal_balance_for_account(account, Decimal("20"), Decimal("5"))

    after = (
        account.id,
        account.code,
        account.name,
        account.account_type,
        account.subtype,
        account.nature,
        account.is_canonical,
        account.name_osc,
        account.name_comercial,
    )
    assert after == before


def test_account_composition_does_not_lookup_catalog_or_infer_nature_from_account_structure():
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.normal_balance_for_account).lower()
    for forbidden in (
        "account_type",
        "subtype",
        "code",
        "name_osc",
        "name_comercial",
        "catalog",
        "catalogo",
        "load_catalog",
        "resolve_catalog",
        "accounting_rules",
    ):
        assert forbidden not in source


def test_account_balance_composition_is_deterministic_without_ambient_inputs():
    import aqorath.account_balance as domain

    account = _account(nature="credit")
    first = domain.normal_balance_for_account(
        account,
        Decimal("3.000"),
        Decimal("10.000"),
    )
    second = domain.normal_balance_for_account(
        account,
        Decimal("3.000"),
        Decimal("10.000"),
    )
    assert first == second == Decimal("7.000")

    source = inspect.getsource(domain.normal_balance_for_account).lower()
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


def test_account_balance_composition_does_not_aggregate_persist_report_or_enter_application():
    import aqorath.application as application
    import aqorath.account_balance as domain

    source = inspect.getsource(domain.normal_balance_for_account).lower()
    for forbidden in (
        "journal_line",
        "journal_entry",
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
    assert "normal_balance_for_account" not in application_source
