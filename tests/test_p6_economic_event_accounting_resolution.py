"""Phase 6BE.1 — frozen EconomicEvent accounting-resolution composition contracts.

6BD established the fail-closed EconomicEvent -> EconomicFact adapter. The existing
EconomicFactAccountingResolution boundary already owns deterministic
EconomicFact -> AccountingProposal provenance. This phase freezes only their composition:
resolve one explicit EconomicEvent through the adapter, then through the provenance
factory, returning that exact provenance object. It does not invent AccountingDecision,
fiscal effects, concrete account resolution, posting, persistence, reporting, or
Application behavior.
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
        date=datetime(2026, 8, 28, 12, 45, 0),
        amount=Decimal("125.4500"),
        description="Venta explícita",
        third_party="Cliente Ejemplo",
        context={"payment_method": "cash"},
    )
    values.update(patch)
    return EconomicEvent(**values)


def test_public_signature_is_exactly_one_event_parameter():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    assert tuple(inspect.signature(resolve_economic_event_with_provenance).parameters) == (
        "event",
    )


def test_composition_delegates_in_order_with_exact_object_identities(monkeypatch):
    import aqorath.economic_event_accounting_resolution as composition

    event = _event()
    fact = object()
    resolution = object()
    calls = []

    def fake_adapter(received_event):
        calls.append(("adapter", received_event))
        return fact

    def fake_provenance(received_fact):
        calls.append(("provenance", received_fact))
        return resolution

    monkeypatch.setattr(composition._event_adapter, "economic_fact_from_event", fake_adapter)
    monkeypatch.setattr(
        composition._provenance,
        "resolve_economic_fact_with_provenance",
        fake_provenance,
    )

    result = composition.resolve_economic_event_with_provenance(event)

    assert result is resolution
    assert calls == [("adapter", event), ("provenance", fact)]
    assert calls[0][1] is event
    assert calls[1][1] is fact


def test_nominal_event_requirement_is_delegated_to_frozen_adapter():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    for invalid in (object(), {}, "sale", None):
        with pytest.raises(TypeError):
            resolve_economic_event_with_provenance(invalid)


def test_cash_sale_returns_existing_provenance_type_and_preserves_money_identity():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )
    from aqorath.economic_fact_accounting_provenance import (
        EconomicFactAccountingResolution,
    )

    event = _event(context={"payment_method": "cash"})
    resolution = resolve_economic_event_with_provenance(event)

    assert isinstance(resolution, EconomicFactAccountingResolution)
    assert resolution.fact.type == "sale"
    assert resolution.fact.payment_method == "cash"
    assert resolution.fact.amount is event.amount


def test_credit_sale_uses_existing_fact_resolver_without_new_mapping_rules():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    event = _event(context={"payment_method": "credit"})
    resolution = resolve_economic_event_with_provenance(event)

    assert resolution.fact.type == "sale"
    assert resolution.fact.payment_method == "credit"
    assert resolution.fact.amount is event.amount
    assert resolution.proposal.lines[0].amount is event.amount
    assert resolution.proposal.lines[1].amount is event.amount


def test_missing_payment_method_fails_closed_before_provenance(monkeypatch):
    import aqorath.economic_event_accounting_resolution as composition

    calls = []
    monkeypatch.setattr(
        composition._provenance,
        "resolve_economic_fact_with_provenance",
        lambda fact: calls.append(fact),
    )

    with pytest.raises(ValueError):
        composition.resolve_economic_event_with_provenance(_event(context={}))

    assert calls == []


def test_unsupported_event_type_fails_closed_through_existing_rules():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    event = _event(
        event_type="membership_dues",
        context={"payment_method": "cash"},
    )
    with pytest.raises(ValueError):
        resolve_economic_event_with_provenance(event)


def test_invalid_explicit_payment_method_fails_closed_without_inference():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    event = _event(
        event_type="utility_expense",
        context={"payment_method": "cash"},
    )
    with pytest.raises(ValueError):
        resolve_economic_event_with_provenance(event)


def test_extra_event_context_is_opaque_and_event_is_not_mutated():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

    marker = object()
    context = {
        "payment_method": "cash",
        "program": "education",
        "bank": "unresolved-reference",
        "opaque": marker,
    }
    event = _event(context=context)
    before = dict(context)

    resolution = resolve_economic_event_with_provenance(event)

    assert resolution.fact.payment_method == "cash"
    assert event.context == before
    assert event.context is context
    assert event.context["opaque"] is marker


def test_event_metadata_outside_adapter_inputs_does_not_change_resolution_truth():
    from aqorath.economic_event_accounting_resolution import (
        resolve_economic_event_with_provenance,
    )

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

    first_resolution = resolve_economic_event_with_provenance(first)
    second_resolution = resolve_economic_event_with_provenance(second)

    assert first_resolution.fact == second_resolution.fact
    assert first_resolution.proposal == second_resolution.proposal


def test_composition_returns_exact_provenance_factory_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_accounting_resolution as composition

    marker = object()
    monkeypatch.setattr(
        composition._provenance,
        "resolve_economic_fact_with_provenance",
        lambda fact: marker,
    )

    assert composition.resolve_economic_event_with_provenance(_event()) is marker


def test_composition_does_not_construct_provenance_or_proposal_directly():
    import aqorath.economic_event_accounting_resolution as composition

    source = inspect.getsource(composition.resolve_economic_event_with_provenance)
    assert "EconomicFactAccountingResolution(" not in source
    assert "AccountingProposal(" not in source
    assert "EconomicFact(" not in source


def test_composition_does_not_bypass_provenance_with_direct_fact_resolution():
    import aqorath.economic_event_accounting_resolution as composition

    source = inspect.getsource(composition.resolve_economic_event_with_provenance)
    assert "_economic_facts" not in source
    assert ".resolve_economic_fact(" not in source
    assert "resolve_economic_fact_with_provenance" in source


def test_provenance_errors_propagate_without_recovery_or_substitution(monkeypatch):
    import aqorath.economic_event_accounting_resolution as composition

    marker_error = RuntimeError("provenance authority failed")

    def fail(fact):
        raise marker_error

    monkeypatch.setattr(
        composition._provenance,
        "resolve_economic_fact_with_provenance",
        fail,
    )

    with pytest.raises(RuntimeError) as captured:
        composition.resolve_economic_event_with_provenance(_event())

    assert captured.value is marker_error


def test_composition_is_deterministic_without_ambient_inputs():
    import aqorath.economic_event_accounting_resolution as composition

    event = _event()
    first = composition.resolve_economic_event_with_provenance(event)
    second = composition.resolve_economic_event_with_provenance(event)

    assert first.fact == second.fact
    assert first.proposal == second.proposal

    source = inspect.getsource(composition.resolve_economic_event_with_provenance).lower()
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


def test_composition_does_not_resolve_accounts_apply_fiscal_logic_persist_post_report_or_enter_application():
    import aqorath.economic_event_accounting_resolution as composition

    source = inspect.getsource(composition.resolve_economic_event_with_provenance).lower()
    for forbidden in (
        "resolve_account",
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
