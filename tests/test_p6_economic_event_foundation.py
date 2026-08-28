"""Phase 6BA.1 — frozen base EconomicEvent domain contracts.

Architecture defines EconomicEvent as the semantic record of what happened in economic
reality: identity, event type, datetime, exact Decimal amount, description, optional
third-party text, and opaque semantic context. This phase freezes only that base domain
shape. It deliberately does not decide the open lifecycle question of failed/successful
attempt persistence or versioning, and it does not translate events into accounting,
resolve accounts/third parties, apply fiscal rules, post, report, or enter Application.
"""

from dataclasses import fields
from datetime import datetime
from decimal import Decimal
import inspect

import pytest


ECONOMIC_EVENT_FIELDS = (
    "id",
    "event_type",
    "date",
    "amount",
    "description",
    "third_party",
    "context",
)


def _event(**patch):
    from aqorath.economic_event import EconomicEvent

    values = dict(
        id=None,
        event_type="sale",
        date=datetime(2026, 8, 28, 10, 30, 0),
        amount=Decimal("125.4500"),
        description="Venta de contado",
        third_party=None,
        context={},
    )
    values.update(patch)
    return EconomicEvent(**values)


def test_economic_event_public_domain_shape_is_exact_and_pure():
    import aqorath.economic_event as domain
    from aqorath.economic_event import EconomicEvent

    event = _event()
    assert tuple(field.name for field in fields(EconomicEvent)) == ECONOMIC_EVENT_FIELDS
    assert tuple(inspect.signature(EconomicEvent).parameters) == ECONOMIC_EVENT_FIELDS
    assert event.id is None

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


def test_id_is_none_before_identity_or_exact_positive_int():
    assert _event(id=None).id is None
    assert _event(id=7).id == 7

    for invalid in (0, -1, True, False, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _event(id=invalid)


def test_event_type_is_exact_nonblank_text_without_normalization():
    assert _event(event_type="sale").event_type == "sale"

    for invalid in (None, 7, "", " sale", "sale ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _event(event_type=invalid)


def test_event_type_is_open_semantic_vocabulary_not_closed_to_architecture_examples():
    custom = "membership_dues"
    event = _event(event_type=custom)
    assert event.event_type == custom


def test_date_must_be_exact_datetime_and_is_not_synthesized_from_ambient_time():
    supplied = datetime(2025, 12, 31, 23, 59, 58)
    event = _event(date=supplied)
    assert event.date is supplied

    for invalid in (None, "2025-12-31", 20251231, object()):
        with pytest.raises(TypeError):
            _event(date=invalid)


def test_amount_must_be_exact_decimal_never_numeric_coercion():
    amount = Decimal("123.4500")
    event = _event(amount=amount)
    assert event.amount is amount

    for invalid in (0, 1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            _event(amount=invalid)


def test_amount_must_be_finite_decimal():
    for invalid in (
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ):
        with pytest.raises(ValueError):
            _event(amount=invalid)


def test_amount_preserves_exact_decimal_precision_without_float_or_quantization():
    amount = Decimal("0.1000000000000000000000000001")
    event = _event(amount=amount)
    assert event.amount is amount
    assert event.amount.as_tuple() == amount.as_tuple()

    import aqorath.economic_event as domain
    source = inspect.getsource(domain).lower()
    for forbidden in ("float(", "quantize", "round(", "str("):
        assert forbidden not in source


def test_description_is_exact_nonblank_text_without_normalization():
    text = "Cuota anual de membresía"
    assert _event(description=text).description == text

    for invalid in (None, 7, "", " texto", "texto ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _event(description=invalid)


def test_third_party_is_none_or_exact_nonblank_text_without_resolution():
    assert _event(third_party=None).third_party is None
    assert _event(third_party="Cliente Ejemplo").third_party == "Cliente Ejemplo"

    for invalid in (7, object(), "", " tercero", "tercero ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _event(third_party=invalid)


def test_context_must_be_exact_dict_matching_architecture_semantic_context_shape():
    context = {"bank": "1101", "program": "education"}
    event = _event(context=context)
    assert event.context == context

    for invalid in (None, [], (), set(), "context"):
        with pytest.raises(TypeError):
            _event(context=invalid)


def test_context_keys_must_be_strings_but_vocabulary_is_open():
    context = {
        "bank": "1101",
        "program": "education",
        "future_semantic_key": 99,
    }
    assert _event(context=context).context == context

    for invalid in ({1: "value"}, {None: "value"}, {("x",): "value"}):
        with pytest.raises(TypeError):
            _event(context=invalid)


def test_context_values_are_opaque_and_do_not_become_accounting_assumptions():
    marker = object()
    context = {
        "bank": "unresolved-semantic-reference",
        "program": None,
        "metadata": {"source": "user"},
        "exact_amount": Decimal("1.2300"),
        "opaque": marker,
    }
    event = _event(context=context)

    assert event.context["bank"] == "unresolved-semantic-reference"
    assert event.context["program"] is None
    assert event.context["metadata"] == {"source": "user"}
    assert event.context["exact_amount"] == Decimal("1.2300")
    assert event.context["opaque"] is marker


def test_economic_event_is_deterministic_without_ambient_inputs():
    first = _event(context={"program": "education"})
    second = _event(context={"program": "education"})
    assert first == second

    import aqorath.economic_event as domain
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


def test_base_event_does_not_decide_open_attempt_persistence_or_repository_lifecycle():
    import aqorath.economic_event as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "repository",
        "get_session",
        "sqlmodel",
        "sqlalchemy",
        "storage",
        "commit(",
        "rollback(",
        "save(",
        "failed_attempt",
        "successful_attempt",
        "attempt_status",
    ):
        assert forbidden not in source

    assert tuple(field.name for field in fields(domain.EconomicEvent)) == ECONOMIC_EVENT_FIELDS


def test_economic_event_does_not_translate_account_resolve_post_report_or_enter_application():
    import aqorath.application as application
    import aqorath.economic_event as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "journalentry",
        "journalline",
        "accountingdecision",
        "resolve_account",
        "account_role",
        "posting",
        "fiscal",
        "reporting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "application",
        "core",
    ):
        assert forbidden not in source

    application_source = inspect.getsource(application).lower()
    assert "aqorath.economic_event" not in application_source
