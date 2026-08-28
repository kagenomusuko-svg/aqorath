"""Phase 6AO.1 — frozen pure JournalLine domain contracts.

R5 requires exact Decimal money and R17 requires analytical dimensions to enrich one
accounting truth rather than create parallel postings. The architecture gives JournalLine
an explicit Account plus debit/credit and analytical values. This phase freezes only that
pure immutable line value. It does not replace models.JournalLine, persist assignments,
resolve accounts, balance a JournalEntry, post anything, or enter Application.
"""

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
import inspect

import pytest


JOURNAL_LINE_FIELDS = (
    "id",
    "entry_id",
    "account",
    "debit",
    "credit",
    "description",
    "analytics",
)


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


def _analytic(dimension_id=1, **patch):
    from aqorath.analytical_dimension import AnalyticalDimensionValue

    values = dict(
        id=None,
        dimension_id=dimension_id,
        code=f"value-{dimension_id}",
        name=f"Valor {dimension_id}",
    )
    values.update(patch)
    return AnalyticalDimensionValue(**values)


def _line(**patch):
    from aqorath.journal_line import JournalLine

    values = dict(
        id=None,
        entry_id=20,
        account=_account(),
        debit=Decimal("100.00"),
        credit=Decimal("0"),
        description=None,
        analytics=(),
    )
    values.update(patch)
    return JournalLine(**values)


def test_journal_line_domain_is_pure_frozen_and_has_exact_architecture_fields_and_defaults():
    import aqorath.journal_line as domain
    from aqorath.journal_line import JournalLine

    line = JournalLine(
        id=None,
        entry_id=20,
        account=_account(),
        debit=Decimal("100.00"),
        credit=Decimal("0"),
    )
    assert tuple(field.name for field in fields(JournalLine)) == JOURNAL_LINE_FIELDS
    assert line.description is None
    assert line.analytics == ()

    with pytest.raises(FrozenInstanceError):
        line.debit = Decimal("1")

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


def test_journal_line_id_is_none_before_identity_or_exact_positive_int():
    assert _line(id=None).id is None
    assert _line(id=7).id == 7

    for invalid in (0, -1, True, False, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _line(id=invalid)


def test_entry_id_is_exact_positive_int_without_boolean_coercion():
    assert _line(entry_id=999).entry_id == 999

    for invalid in (0, -1, True, False, 1.0, "1", None):
        with pytest.raises((TypeError, ValueError)):
            _line(entry_id=invalid)


def test_account_must_be_nominal_account_without_repository_resolution():
    from aqorath.account import Account

    transient = _account(id=None, code="LOCAL-X", is_canonical=False)
    line = _line(account=transient)
    assert line.account is transient
    assert isinstance(line.account, Account)

    for invalid in (object(), {}, "1101", None):
        with pytest.raises(TypeError):
            _line(account=invalid)


def test_debit_and_credit_must_be_exact_decimal_values_never_numeric_coercions():
    debit = Decimal("123.4500")
    credit = Decimal("0")
    line = _line(debit=debit, credit=credit)
    assert line.debit is debit
    assert line.credit is credit

    for field_name in ("debit", "credit"):
        for invalid in (0, 1, 1.0, "1.00", True, None):
            with pytest.raises(TypeError):
                _line(**{field_name: invalid})


def test_debit_and_credit_must_be_finite_and_nonnegative():
    for field_name in ("debit", "credit"):
        for invalid in (
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            Decimal("-0.01"),
        ):
            with pytest.raises(ValueError):
                _line(**{field_name: invalid})


def test_each_journal_line_has_exactly_one_positive_side_and_the_other_side_zero():
    debit_line = _line(debit=Decimal("5.00"), credit=Decimal("0"))
    credit_line = _line(debit=Decimal("0"), credit=Decimal("5.00"))
    assert debit_line.debit == Decimal("5.00")
    assert credit_line.credit == Decimal("5.00")

    for debit, credit in (
        (Decimal("0"), Decimal("0")),
        (Decimal("1"), Decimal("1")),
        (Decimal("0.01"), Decimal("2")),
    ):
        with pytest.raises(ValueError):
            _line(debit=debit, credit=credit)


def test_money_scale_and_exact_supplied_decimal_objects_are_preserved_without_quantization():
    debit = Decimal("123.450000")
    zero = Decimal("0.0000")
    line = _line(debit=debit, credit=zero)

    assert line.debit is debit
    assert line.credit is zero
    assert line.debit.as_tuple() == debit.as_tuple()
    assert line.credit.as_tuple() == zero.as_tuple()


def test_description_is_none_or_exact_nonblank_text_without_normalization():
    assert _line(description=None).description is None
    assert _line(description="Banco operativo MXN").description == "Banco operativo MXN"

    for invalid in (7, "", " texto", "texto ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _line(description=invalid)


def test_analytics_must_be_exact_immutable_tuple():
    for invalid in ([], set(), {}, "program", None):
        with pytest.raises(TypeError):
            _line(analytics=invalid)


def test_analytics_items_must_be_nominal_analytical_dimension_values():
    valid = _analytic(1)
    for invalid in (
        (object(),),
        ({"dimension_id": 1},),
        (valid, object()),
    ):
        with pytest.raises(TypeError):
            _line(analytics=invalid)


def test_analytics_may_be_empty_and_preserve_exact_order_and_identity():
    assert _line(analytics=()).analytics == ()

    program = _analytic(1, code="education", name="Educación")
    source = _analytic(2, code="donation", name="Donativo")
    analytics = (source, program)
    line = _line(analytics=analytics)

    assert line.analytics is analytics
    assert line.analytics == (source, program)
    assert line.analytics[0] is source
    assert line.analytics[1] is program


def test_one_line_cannot_carry_multiple_values_for_the_same_dimension():
    first = _analytic(1, id=11, code="education", name="Educación")
    second = _analytic(1, id=12, code="health", name="Salud")

    with pytest.raises(ValueError):
        _line(analytics=(first, second))


def test_analytics_enrich_existing_line_truth_without_changing_account_or_money_or_requiring_persisted_value_identity():
    account = _account(id=None, code="1101-LOCAL", is_canonical=False)
    transient_value = _analytic(
        77,
        id=None,
        code="program-x",
        name="Programa X",
    )
    debit = Decimal("44.000")
    zero = Decimal("0")
    line = _line(
        account=account,
        debit=debit,
        credit=zero,
        analytics=(transient_value,),
    )

    assert line.account is account
    assert line.debit is debit
    assert line.credit is zero
    assert line.analytics[0] is transient_value
    assert line.analytics[0].id is None


def test_journal_line_is_deterministic_hashable_value_truth_without_ambient_inputs():
    analytics = (_analytic(1, id=3),)
    first = _line(id=4, analytics=analytics)
    second = _line(id=4, analytics=analytics)
    assert first == second
    assert hash(first) == hash(second)

    import aqorath.journal_line as domain
    source = inspect.getsource(domain).lower()
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


def test_journal_line_foundation_does_not_persist_balance_post_resolve_or_enter_application_runtime():
    import aqorath.application as application
    import aqorath.journal_line as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "models",
        "repository",
        "get_session",
        "sqlmodel",
        "sqlalchemy",
        "account_resolution",
        "posting",
        "storage",
        "reporting_runtime",
        "journal_line_analytical_dimension_record",
    ):
        assert forbidden not in source

    for forbidden_name in (
        "save_journal_line",
        "post_line",
        "balance_entry",
        "resolve_account",
        "assign_analytic",
    ):
        assert not hasattr(domain, forbidden_name)

    application_source = inspect.getsource(application).lower()
    assert "aqorath.journal_line" not in application_source
