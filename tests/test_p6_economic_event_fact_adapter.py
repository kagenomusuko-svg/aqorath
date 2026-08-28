"""Phase 6BD.1 — frozen EconomicEvent to legacy EconomicFact adapter contracts.

EconomicEvent is the generic pure record of what happened. The legacy EconomicFact
resolver supports a narrower deterministic vocabulary that additionally requires an
explicit payment method. This phase freezes only a fail-closed adapter between those two
truths: event_type and the exact Decimal amount pass through unchanged, while
payment_method must be supplied explicitly by event.context. No payment method, event
kind, account, fiscal treatment, posting, persistence, reporting, or Application behavior
may be inferred by the adapter.
"""

from datetime import datetime
from decimal import Decimal
import inspect

import pytest


def _event(**patch):
    from aqorath.economic_event import EconomicEvent

    values = dict(
        id=None,
        event_type="sale",
        date=datetime(2026, 8, 28, 10, 30, 0),
        amount=Decimal("125.4500"),
        description="Venta de contado",
        third_party="Cliente Ejemplo",
        context={"payment_method": "cash"},
    )
    values.update(patch)
    return EconomicEvent(**values)


def test_adapter_public_signature_is_exactly_one_event_parameter():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    assert tuple(inspect.signature(economic_fact_from_event).parameters) == ("event",)


def test_adapter_requires_nominal_economic_event_not_duck_typing():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    for invalid in (object(), {}, {"event_type": "sale"}, "sale"):
        with pytest.raises(TypeError):
            economic_fact_from_event(invalid)


def test_payment_method_must_be_explicitly_present_in_event_context():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(context={})
    with pytest.raises(ValueError):
        economic_fact_from_event(event)


def test_adapter_delegates_once_to_economic_fact_with_exact_event_values(monkeypatch):
    import aqorath.economic_event_fact_adapter as adapter

    amount = Decimal("99.9900000000000000000000000001")
    payment_method = "cash"
    event = _event(amount=amount, context={"payment_method": payment_method})
    marker = object()
    calls = []

    def fake_economic_fact(*, type, amount, payment_method):
        calls.append((type, amount, payment_method))
        return marker

    monkeypatch.setattr(adapter._economic_facts, "EconomicFact", fake_economic_fact)

    result = adapter.economic_fact_from_event(event)

    assert result is marker
    assert calls == [(event.event_type, amount, payment_method)]
    assert calls[0][1] is amount
    assert calls[0][2] is payment_method


def test_cash_sale_maps_without_normalization():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(event_type="sale", context={"payment_method": "cash"})
    fact = economic_fact_from_event(event)

    assert fact.type == "sale"
    assert fact.amount is event.amount
    assert fact.payment_method == "cash"


def test_credit_sale_maps_without_normalization():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(event_type="sale", context={"payment_method": "credit"})
    fact = economic_fact_from_event(event)

    assert fact.type == "sale"
    assert fact.amount is event.amount
    assert fact.payment_method == "credit"


def test_utility_expense_maps_only_when_bank_is_explicit():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(
        event_type="utility_expense",
        context={"payment_method": "bank"},
    )
    fact = economic_fact_from_event(event)

    assert fact.type == "utility_expense"
    assert fact.payment_method == "bank"
    assert fact.amount is event.amount


def test_unsupported_event_type_fails_closed_through_existing_economic_fact_rules():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(
        event_type="membership_dues",
        context={"payment_method": "cash"},
    )
    with pytest.raises(ValueError):
        economic_fact_from_event(event)


def test_invalid_explicit_payment_method_combination_fails_closed_without_inference():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    event = _event(
        event_type="utility_expense",
        context={"payment_method": "cash"},
    )
    with pytest.raises(ValueError):
        economic_fact_from_event(event)


def test_adapter_does_not_normalize_or_default_payment_method():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    for payment_method in (None, 7, "", " cash", "cash ", "CASH"):
        event = _event(context={"payment_method": payment_method})
        with pytest.raises((TypeError, ValueError)):
            economic_fact_from_event(event)


def test_event_amount_constraints_for_legacy_fact_are_delegated_not_reinvented():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    for amount in (Decimal("0"), Decimal("-1.00")):
        event = _event(amount=amount)
        with pytest.raises(ValueError):
            economic_fact_from_event(event)


def test_extra_context_is_opaque_and_event_is_not_mutated():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    marker = object()
    context = {
        "payment_method": "cash",
        "program": "education",
        "bank": "unresolved-reference",
        "opaque": marker,
    }
    event = _event(context=context)
    before = dict(event.context)

    fact = economic_fact_from_event(event)

    assert fact.payment_method == "cash"
    assert event.context == before
    assert event.context["opaque"] is marker
    assert event.context is context


def test_date_description_third_party_and_identity_do_not_change_mapping():
    from aqorath.economic_event_fact_adapter import economic_fact_from_event

    first = _event(
        id=None,
        date=datetime(2026, 1, 1, 8, 0, 0),
        description="Primera descripción",
        third_party=None,
    )
    second = _event(
        id=99,
        date=datetime(2025, 12, 31, 23, 59, 59),
        description="Otra descripción",
        third_party="Otro tercero",
    )

    assert economic_fact_from_event(first) == economic_fact_from_event(second)


def test_adapter_does_not_resolve_the_economic_fact_to_an_accounting_proposal(monkeypatch):
    import aqorath.economic_event_fact_adapter as adapter

    monkeypatch.setattr(
        adapter._economic_facts,
        "resolve_economic_fact",
        lambda fact: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )

    fact = adapter.economic_fact_from_event(_event())
    assert isinstance(fact, adapter._economic_facts.EconomicFact)


def test_adapter_is_deterministic_without_ambient_inputs_or_hidden_defaults():
    import aqorath.economic_event_fact_adapter as adapter

    event = _event()
    assert adapter.economic_fact_from_event(event) == adapter.economic_fact_from_event(event)

    source = inspect.getsource(adapter.economic_fact_from_event).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "setdefault",
        ".get(\"payment_method\"",
    ):
        assert forbidden not in source


def test_adapter_does_not_resolve_accounts_apply_fiscal_logic_persist_post_report_or_enter_application():
    import aqorath.economic_event_fact_adapter as adapter

    source = inspect.getsource(adapter.economic_fact_from_event).lower()
    for forbidden in (
        "resolve_account",
        "account_role",
        "journalentry",
        "journalline",
        "accountingdecision",
        "posting",
        "fiscal",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "application",
        "core",
    ):
        assert forbidden not in source
