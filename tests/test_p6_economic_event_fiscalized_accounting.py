"""Phase 6BG.1 — frozen EconomicEvent fiscalized-accounting composition contracts.

6BF established EconomicEvent -> FiscalEconomicCompositionDeclaration through existing
resolution and fiscal-composition authorities. The existing fiscalized accounting
proposal authority owns materialization of that declaration into a balanced semantic
FiscalizedAccountingProposal. This phase freezes only their composition: delegate the
explicit event and fiscal inputs to 6BF, then pass the exact declaration to
compose_fiscal_economic_accounting. No fiscal recalculation, line construction, account
resolution, confirmation, persistence, posting, reporting, or Application behavior may
be added here.
"""

import inspect

import pytest


def test_public_signature_is_exactly_four_explicit_parameters():
    from aqorath.economic_event_fiscalized_accounting import (
        compose_fiscal_economic_accounting_from_event,
    )

    assert tuple(
        inspect.signature(compose_fiscal_economic_accounting_from_event).parameters
    ) == (
        "event",
        "fiscal_effect",
        "amount_basis",
        "adjustment_role",
    )


def test_delegates_in_order_with_exact_object_identities(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    event = object()
    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    declaration = object()
    proposal = object()
    calls = []

    def fake_declaration(received_event, received_effect, received_basis, received_role):
        calls.append(
            (
                "declaration",
                received_event,
                received_effect,
                received_basis,
                received_role,
            )
        )
        return declaration

    def fake_compose(received_declaration):
        calls.append(("compose", received_declaration))
        return proposal

    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        fake_declaration,
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        fake_compose,
    )

    result = composition.compose_fiscal_economic_accounting_from_event(
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
    )

    assert result is proposal
    assert calls == [
        (
            "declaration",
            event,
            fiscal_effect,
            amount_basis,
            adjustment_role,
        ),
        ("compose", declaration),
    ]
    assert calls[1][1] is declaration


def test_same_event_object_is_delegated_to_6bf(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    event = object()
    seen = []
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda received_event, effect, basis, role: seen.append(received_event) or object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: object(),
    )

    composition.compose_fiscal_economic_accounting_from_event(
        event, object(), object(), object()
    )

    assert seen == [event]
    assert seen[0] is event


def test_same_fiscal_effect_object_is_delegated_to_6bf(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    fiscal_effect = object()
    seen = []
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda event, effect, basis, role: seen.append(effect) or object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: object(),
    )

    composition.compose_fiscal_economic_accounting_from_event(
        object(), fiscal_effect, object(), object()
    )

    assert seen == [fiscal_effect]
    assert seen[0] is fiscal_effect


def test_same_amount_basis_object_is_delegated_to_6bf_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    amount_basis = object()
    seen = []
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda event, effect, basis, role: seen.append(basis) or object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: object(),
    )

    composition.compose_fiscal_economic_accounting_from_event(
        object(), object(), amount_basis, object()
    )

    assert seen == [amount_basis]
    assert seen[0] is amount_basis


def test_same_adjustment_role_object_is_delegated_to_6bf_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    adjustment_role = object()
    seen = []
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda event, effect, basis, role: seen.append(role) or object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: object(),
    )

    composition.compose_fiscal_economic_accounting_from_event(
        object(), object(), object(), adjustment_role
    )

    assert seen == [adjustment_role]
    assert seen[0] is adjustment_role


def test_returns_exact_fiscalized_authority_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    marker = object()
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: marker,
    )

    assert composition.compose_fiscal_economic_accounting_from_event(
        object(), object(), object(), object()
    ) is marker


def test_6bf_errors_propagate_and_prevent_fiscalized_composition(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    marker_error = RuntimeError("6BF failed")
    compose_calls = []

    def fail(*args):
        raise marker_error

    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        fail,
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: compose_calls.append(declaration),
    )

    with pytest.raises(RuntimeError) as captured:
        composition.compose_fiscal_economic_accounting_from_event(
            object(), object(), object(), object()
        )

    assert captured.value is marker_error
    assert compose_calls == []


def test_fiscalized_composition_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    marker_error = ValueError("fiscalized composition failed")
    declaration = object()
    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda *args: declaration,
    )

    def fail(received_declaration):
        assert received_declaration is declaration
        raise marker_error

    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        fail,
    )

    with pytest.raises(ValueError) as captured:
        composition.compose_fiscal_economic_accounting_from_event(
            object(), object(), object(), object()
        )

    assert captured.value is marker_error


def test_invalid_event_fails_closed_before_fiscalized_composition(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    compose_calls = []
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: compose_calls.append(declaration),
    )

    with pytest.raises(TypeError):
        composition.compose_fiscal_economic_accounting_from_event(
            object(), object(), "net_before_fiscal", "cash"
        )

    assert compose_calls == []


def test_composition_does_not_construct_declaration_or_fiscalized_types_directly():
    import aqorath.economic_event_fiscalized_accounting as composition

    source = inspect.getsource(
        composition.compose_fiscal_economic_accounting_from_event
    )
    assert "FiscalEconomicCompositionDeclaration(" not in source
    assert "FiscalizedAccountingProposal(" not in source
    assert "FiscalizedProposalLine(" not in source
    assert "EconomicFactAccountingResolution(" not in source


def test_composition_does_not_bypass_6bf_or_fiscalized_authorities():
    import aqorath.economic_event_fiscalized_accounting as composition

    source = inspect.getsource(
        composition.compose_fiscal_economic_accounting_from_event
    )
    assert "declare_fiscal_economic_composition_from_event" in source
    assert "compose_fiscal_economic_accounting" in source
    for forbidden in (
        "resolve_economic_event_with_provenance",
        "economic_fact_from_event",
        "resolve_economic_fact_with_provenance",
        ".resolve_economic_fact(",
        "declare_fiscal_economic_composition(",
    ):
        assert forbidden not in source


def test_composition_does_not_inspect_declaration_or_materialize_lines_itself():
    import aqorath.economic_event_fiscalized_accounting as composition

    source = inspect.getsource(
        composition.compose_fiscal_economic_accounting_from_event
    ).lower()
    for forbidden in (
        ".accounting_resolution",
        ".fiscal_effect",
        ".fiscal_effects",
        ".amount_basis",
        ".adjustment_role",
        ".lines",
        ".line",
        ".side",
        ".account_role",
        ".amount",
        "decimal(",
        "sum(",
        "quantize",
        "round(",
    ):
        assert forbidden not in source


def test_composition_does_not_prevalidate_or_default_inputs(monkeypatch):
    import aqorath.economic_event_fiscalized_accounting as composition

    event = object()
    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    seen = []

    monkeypatch.setattr(
        composition._event_fiscal_composition,
        "declare_fiscal_economic_composition_from_event",
        lambda received_event, effect, basis, role: seen.append(
            (received_event, effect, basis, role)
        ) or object(),
    )
    monkeypatch.setattr(
        composition._fiscalized,
        "compose_fiscal_economic_accounting",
        lambda declaration: object(),
    )

    composition.compose_fiscal_economic_accounting_from_event(
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
    )

    assert seen == [(event, fiscal_effect, amount_basis, adjustment_role)]


def test_composition_is_deterministic_without_ambient_inputs():
    import aqorath.economic_event_fiscalized_accounting as composition

    source = inspect.getsource(
        composition.compose_fiscal_economic_accounting_from_event
    ).lower()
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


def test_composition_does_not_resolve_accounts_confirm_persist_post_report_or_enter_application():
    import aqorath.economic_event_fiscalized_accounting as composition

    source = inspect.getsource(
        composition.compose_fiscal_economic_accounting_from_event
    ).lower()
    for forbidden in (
        "resolve_account",
        "account_bindings",
        "confirm",
        "posting",
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
