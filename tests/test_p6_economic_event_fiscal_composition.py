"""Phase 6BF.1 — frozen EconomicEvent fiscal-composition composition contracts.

6BE established EconomicEvent -> EconomicFactAccountingResolution provenance. The existing
fiscal_economic_composition authority owns all compatibility validation for one already-
confirmed fiscal effect, explicit amount basis, and explicit adjustment role. This phase
freezes only their composition: resolve the event through 6BE, then delegate the exact
result plus the caller-supplied fiscal inputs to declare_fiscal_economic_composition.
No fiscal rule calculation, effect construction, accounting composition, account
resolution, confirmation, persistence, posting, reporting, or Application behavior may
be added here.
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
        date=datetime(2026, 8, 28, 13, 0, 0),
        amount=Decimal("125.4500"),
        description="Venta explícita",
        third_party="Cliente Ejemplo",
        context={"payment_method": "cash"},
    )
    values.update(patch)
    return EconomicEvent(**values)


def test_public_signature_is_exactly_four_explicit_parameters():
    from aqorath.economic_event_fiscal_composition import (
        declare_fiscal_economic_composition_from_event,
    )

    assert tuple(
        inspect.signature(declare_fiscal_economic_composition_from_event).parameters
    ) == (
        "event",
        "fiscal_effect",
        "amount_basis",
        "adjustment_role",
    )


def test_delegates_in_order_with_exact_object_identities(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    event = object()
    accounting_resolution = object()
    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    declaration = object()
    calls = []

    def fake_event_resolution(received_event):
        calls.append(("event_resolution", received_event))
        return accounting_resolution

    def fake_declaration(received_resolution, received_effect, received_basis, received_role):
        calls.append(
            (
                "fiscal_composition",
                received_resolution,
                received_effect,
                received_basis,
                received_role,
            )
        )
        return declaration

    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        fake_event_resolution,
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        fake_declaration,
    )

    result = composition.declare_fiscal_economic_composition_from_event(
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
    )

    assert result is declaration
    assert calls == [
        ("event_resolution", event),
        (
            "fiscal_composition",
            accounting_resolution,
            fiscal_effect,
            amount_basis,
            adjustment_role,
        ),
    ]


def test_same_event_object_is_passed_to_6be_resolution_authority(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    event = object()
    seen = []
    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda value: seen.append(value) or object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda *args: object(),
    )

    composition.declare_fiscal_economic_composition_from_event(
        event, object(), object(), object()
    )

    assert seen == [event]
    assert seen[0] is event


def test_same_fiscal_effect_object_is_delegated_without_inspection(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    fiscal_effect = object()
    captured = []
    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda resolution, effect, basis, role: captured.append(effect) or object(),
    )

    composition.declare_fiscal_economic_composition_from_event(
        object(), fiscal_effect, object(), object()
    )

    assert captured == [fiscal_effect]
    assert captured[0] is fiscal_effect


def test_same_amount_basis_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    amount_basis = object()
    captured = []
    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda resolution, effect, basis, role: captured.append(basis) or object(),
    )

    composition.declare_fiscal_economic_composition_from_event(
        object(), object(), amount_basis, object()
    )

    assert captured == [amount_basis]
    assert captured[0] is amount_basis


def test_same_adjustment_role_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    adjustment_role = object()
    captured = []
    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda resolution, effect, basis, role: captured.append(role) or object(),
    )

    composition.declare_fiscal_economic_composition_from_event(
        object(), object(), object(), adjustment_role
    )

    assert captured == [adjustment_role]
    assert captured[0] is adjustment_role


def test_returns_exact_fiscal_composition_authority_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    marker = object()
    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda *args: marker,
    )

    result = composition.declare_fiscal_economic_composition_from_event(
        object(), object(), object(), object()
    )

    assert result is marker


def test_invalid_event_fails_before_fiscal_declaration(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    calls = []
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda *args: calls.append(args),
    )

    with pytest.raises(TypeError):
        composition.declare_fiscal_economic_composition_from_event(
            object(), object(), "net_before_fiscal", "cash"
        )

    assert calls == []


def test_event_resolution_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    marker_error = RuntimeError("event resolution failed")
    fiscal_calls = []

    def fail(event):
        raise marker_error

    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        fail,
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda *args: fiscal_calls.append(args),
    )

    with pytest.raises(RuntimeError) as captured:
        composition.declare_fiscal_economic_composition_from_event(
            object(), object(), object(), object()
        )

    assert captured.value is marker_error
    assert fiscal_calls == []


def test_fiscal_composition_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    marker_error = ValueError("fiscal composition failed")

    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )

    def fail(*args):
        raise marker_error

    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        fail,
    )

    with pytest.raises(ValueError) as captured:
        composition.declare_fiscal_economic_composition_from_event(
            object(), object(), object(), object()
        )

    assert captured.value is marker_error


def test_real_event_resolution_is_preserved_before_fiscal_declaration(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition
    from aqorath.economic_fact_accounting_provenance import (
        EconomicFactAccountingResolution,
    )

    event = _event()
    fiscal_effect = object()
    seen = []
    marker = object()

    def fake_declaration(resolution, effect, basis, role):
        seen.append((resolution, effect, basis, role))
        return marker

    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        fake_declaration,
    )

    result = composition.declare_fiscal_economic_composition_from_event(
        event,
        fiscal_effect,
        "net_before_fiscal",
        "cash",
    )

    assert result is marker
    resolution = seen[0][0]
    assert isinstance(resolution, EconomicFactAccountingResolution)
    assert resolution.fact.amount is event.amount
    assert resolution.proposal.lines[0].amount is event.amount
    assert resolution.proposal.lines[1].amount is event.amount
    assert seen[0][1] is fiscal_effect


def test_composition_does_not_construct_resolution_or_declaration_types_directly():
    import aqorath.economic_event_fiscal_composition as composition

    source = inspect.getsource(
        composition.declare_fiscal_economic_composition_from_event
    )
    assert "EconomicFactAccountingResolution(" not in source
    assert "FiscalEconomicCompositionDeclaration(" not in source
    assert "EconomicFact(" not in source
    assert "AccountingProposal(" not in source


def test_composition_does_not_bypass_6be_or_fiscal_declaration_authorities():
    import aqorath.economic_event_fiscal_composition as composition

    source = inspect.getsource(
        composition.declare_fiscal_economic_composition_from_event
    )
    assert "resolve_economic_event_with_provenance" in source
    assert "declare_fiscal_economic_composition" in source
    for forbidden in (
        "economic_fact_from_event",
        "resolve_economic_fact_with_provenance",
        ".resolve_economic_fact(",
        "build_fiscal_accounting_effect",
        "compose_fiscal_economic_accounting",
    ):
        assert forbidden not in source


def test_composition_does_not_inspect_or_recalculate_fiscal_effect_truth():
    import aqorath.economic_event_fiscal_composition as composition

    source = inspect.getsource(
        composition.declare_fiscal_economic_composition_from_event
    ).lower()
    for forbidden in (
        ".declaration",
        ".line",
        ".snapshot",
        ".side",
        ".account_role",
        ".rounded_amount",
        "decimal(",
        "sum(",
        "quantize",
        "round(",
    ):
        assert forbidden not in source


def test_composition_does_not_prevalidate_or_default_caller_fiscal_inputs(monkeypatch):
    import aqorath.economic_event_fiscal_composition as composition

    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    seen = []

    monkeypatch.setattr(
        composition._event_resolution,
        "resolve_economic_event_with_provenance",
        lambda event: object(),
    )
    monkeypatch.setattr(
        composition._fiscal_composition,
        "declare_fiscal_economic_composition",
        lambda resolution, effect, basis, role: seen.append(
            (effect, basis, role)
        ) or object(),
    )

    composition.declare_fiscal_economic_composition_from_event(
        object(), fiscal_effect, amount_basis, adjustment_role
    )

    assert seen == [(fiscal_effect, amount_basis, adjustment_role)]


def test_composition_is_deterministic_without_ambient_inputs_or_side_effect_layers():
    import aqorath.economic_event_fiscal_composition as composition

    source = inspect.getsource(
        composition.declare_fiscal_economic_composition_from_event
    ).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "commit(",
        "rollback(",
        "posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "application",
        "core",
    ):
        assert forbidden not in source
