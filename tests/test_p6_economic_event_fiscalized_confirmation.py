"""Phase 6BM.1 — frozen EconomicEvent fiscalized confirmation-preparation contracts.

This phase composes the existing EconomicEvent fiscalized account-resolution boundary
(6BL) with the existing fiscalized confirmation-snapshot authority. The wrapper must
preserve caller-supplied session, event, fiscal inputs, and account bindings by identity,
delegate in that order, and return the exact prepared snapshot. It prepares informed
confirmation content only; it must not perform the explicit confirmation act, inspect or
rebuild resolved/fiscalized truth, persist, post, construct Journal objects, report, or
enter Application.
"""

import inspect

import pytest


def test_public_signature_is_exactly_six_explicit_parameters():
    import aqorath.economic_event_fiscalized_confirmation as preparation

    assert tuple(
        inspect.signature(
            preparation.prepare_fiscalized_economic_event_confirmation
        ).parameters
    ) == (
        "session",
        "event",
        "fiscal_effect",
        "amount_basis",
        "adjustment_role",
        "account_bindings",
    )


def test_delegates_in_order_with_exact_object_identities(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    session = object()
    event = object()
    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    account_bindings = object()
    resolved = object()
    snapshot = object()
    calls = []

    def fake_resolve(got_session, got_event, got_effect, got_basis, got_role, got_bindings):
        calls.append(
            (
                "resolve",
                got_session,
                got_event,
                got_effect,
                got_basis,
                got_role,
                got_bindings,
            )
        )
        return resolved

    def fake_prepare(got_resolved):
        calls.append(("prepare", got_resolved))
        return snapshot

    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        fake_resolve,
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        fake_prepare,
    )

    result = preparation.prepare_fiscalized_economic_event_confirmation(
        session,
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
        account_bindings,
    )

    assert calls == [
        (
            "resolve",
            session,
            event,
            fiscal_effect,
            amount_basis,
            adjustment_role,
            account_bindings,
        ),
        ("prepare", resolved),
    ]
    assert result is snapshot


def test_same_session_object_is_delegated_to_6bl(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    session = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda got_session, *args: seen.append(got_session) or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        session, object(), object(), object(), object(), object()
    )
    assert seen == [session]


def test_same_event_object_is_delegated_to_6bl(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    event = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda session, got_event, *args: seen.append(got_event) or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), event, object(), object(), object(), object()
    )
    assert seen == [event]


def test_same_fiscal_effect_object_is_delegated_without_inspection(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    fiscal_effect = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda session, event, got_effect, basis, role, bindings: seen.append(got_effect)
        or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), fiscal_effect, object(), object(), object()
    )
    assert seen == [fiscal_effect]


def test_same_amount_basis_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    amount_basis = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda session, event, effect, got_basis, role, bindings: seen.append(got_basis)
        or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), object(), amount_basis, object(), object()
    )
    assert seen == [amount_basis]


def test_same_adjustment_role_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    adjustment_role = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda session, event, effect, basis, got_role, bindings: seen.append(got_role)
        or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), object(), object(), adjustment_role, object()
    )
    assert seen == [adjustment_role]


def test_same_account_bindings_object_is_delegated_without_copying(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    account_bindings = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda session, event, effect, basis, role, got_bindings: seen.append(got_bindings)
        or object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), object(), object(), object(), account_bindings
    )
    assert seen == [account_bindings]


def test_exact_resolved_object_is_delegated_to_confirmation_snapshot_authority(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    resolved = object()
    seen = []
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda *args: resolved,
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda got_resolved: seen.append(got_resolved) or object(),
    )

    preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), object(), object(), object(), object()
    )
    assert seen == [resolved]


def test_returns_exact_confirmation_snapshot_authority_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    snapshot = object()
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda resolved: snapshot,
    )

    result = preparation.prepare_fiscalized_economic_event_confirmation(
        object(), object(), object(), object(), object(), object()
    )
    assert result is snapshot


def test_6bl_errors_propagate_and_confirmation_snapshot_is_not_prepared(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    error = RuntimeError("6bl failed")
    calls = []

    def fail(*args):
        raise error

    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        fail,
    )
    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda *args: calls.append(args),
    )

    with pytest.raises(RuntimeError) as excinfo:
        preparation.prepare_fiscalized_economic_event_confirmation(
            object(), object(), object(), object(), object(), object()
        )

    assert excinfo.value is error
    assert calls == []


def test_confirmation_snapshot_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as preparation

    error = ValueError("snapshot failed")
    monkeypatch.setattr(
        preparation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        lambda *args: object(),
    )

    def fail(resolved):
        raise error

    monkeypatch.setattr(
        preparation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        fail,
    )

    with pytest.raises(ValueError) as excinfo:
        preparation.prepare_fiscalized_economic_event_confirmation(
            object(), object(), object(), object(), object(), object()
        )

    assert excinfo.value is error


def test_does_not_construct_resolved_or_confirmation_types_directly():
    import aqorath.economic_event_fiscalized_confirmation as preparation

    source = inspect.getsource(
        preparation.prepare_fiscalized_economic_event_confirmation
    )
    for forbidden in (
        "ResolvedFiscalizedAccountingProposal(",
        "ResolvedFiscalizedProposalLine(",
        "FiscalizedConfirmationSnapshot(",
        "FiscalizedConfirmationLine(",
        "FiscalizedConfirmationProvenance(",
        "ConfirmedFiscalizedProposal(",
    ):
        assert forbidden not in source


def test_uses_6bl_and_snapshot_authority_without_bypass_or_confirmation_act():
    import aqorath.economic_event_fiscalized_confirmation as preparation

    source = inspect.getsource(
        preparation.prepare_fiscalized_economic_event_confirmation
    )
    assert "resolve_fiscalized_economic_event_accounts" in source
    assert "create_fiscalized_confirmation_snapshot" in source
    for forbidden in (
        "compose_fiscal_economic_accounting_from_event",
        "resolve_fiscalized_proposal_accounts(",
        "resolve_account_by_code",
        "confirm_fiscalized_snapshot(",
    ):
        assert forbidden not in source


def test_does_not_inspect_or_recalculate_resolved_or_confirmation_truth():
    import aqorath.economic_event_fiscalized_confirmation as preparation

    source = inspect.getsource(
        preparation.prepare_fiscalized_economic_event_confirmation
    ).lower()
    for forbidden in (
        ".lines",
        ".fiscalized_proposal",
        ".declaration",
        ".provenance",
        ".explanation",
        ".account_role",
        ".side",
        ".amount",
        "decimal(",
        "sum(",
        "quantize",
        "round(",
        "ledger_signed_balance",
    ):
        assert forbidden not in source


def test_preparation_adds_no_ambient_inputs_persistence_posting_reporting_or_application():
    import aqorath.economic_event_fiscalized_confirmation as preparation

    source = inspect.getsource(
        preparation.prepare_fiscalized_economic_event_confirmation
    ).lower()
    module_source = inspect.getsource(preparation).lower()

    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "get_session",
        "account_bindings_repository",
        "load_account_bindings",
        "commit(",
        "rollback(",
        "post_entry",
        "create_fiscalized_posting_instruction",
        "execute_fiscalized_posting",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source

    assert "aqorath.application" not in module_source
