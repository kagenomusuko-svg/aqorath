"""Phase 6BL.1 — frozen EconomicEvent fiscalized account-resolution contracts.

This phase composes the already-frozen EconomicEvent fiscalized accounting boundary
(6BG) with the existing concrete fiscalized account-resolution authority. The wrapper
must preserve caller-supplied session, event, fiscal inputs, and account bindings by
identity, delegate in that order, and return the exact downstream resolution result.
It must not inspect or rebuild fiscalized accounting truth, load configured bindings,
confirm, persist, post, construct Journal objects, report, or enter Application.
"""

import inspect

import pytest


def test_public_signature_is_exactly_six_explicit_parameters():
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    assert tuple(
        inspect.signature(
            resolution.resolve_fiscalized_economic_event_accounts
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
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    session = object()
    event = object()
    fiscal_effect = object()
    amount_basis = object()
    adjustment_role = object()
    account_bindings = object()
    fiscalized_proposal = object()
    resolved = object()
    calls = []

    def fake_compose(got_event, got_effect, got_basis, got_role):
        calls.append(
            ("compose", got_event, got_effect, got_basis, got_role)
        )
        return fiscalized_proposal

    def fake_resolve(got_session, got_proposal, got_bindings):
        calls.append(("resolve", got_session, got_proposal, got_bindings))
        return resolved

    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        fake_compose,
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        fake_resolve,
    )

    result = resolution.resolve_fiscalized_economic_event_accounts(
        session,
        event,
        fiscal_effect,
        amount_basis,
        adjustment_role,
        account_bindings,
    )

    assert calls == [
        ("compose", event, fiscal_effect, amount_basis, adjustment_role),
        ("resolve", session, fiscalized_proposal, account_bindings),
    ]
    assert result is resolved


def test_same_session_object_is_delegated_to_account_resolution(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    session = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda got_session, proposal, bindings: seen.append(got_session) or object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        session, object(), object(), object(), object(), object()
    )
    assert seen == [session]


def test_same_event_object_is_delegated_to_6bg(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    event = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda got_event, *args: seen.append(got_event) or object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        object(), event, object(), object(), object(), object()
    )
    assert seen == [event]


def test_same_fiscal_effect_object_is_delegated_without_inspection(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    fiscal_effect = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda event, got_effect, basis, role: seen.append(got_effect) or object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        object(), object(), fiscal_effect, object(), object(), object()
    )
    assert seen == [fiscal_effect]


def test_same_amount_basis_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    amount_basis = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda event, effect, got_basis, role: seen.append(got_basis) or object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        object(), object(), object(), amount_basis, object(), object()
    )
    assert seen == [amount_basis]


def test_same_adjustment_role_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    adjustment_role = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda event, effect, basis, got_role: seen.append(got_role) or object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        object(), object(), object(), object(), adjustment_role, object()
    )
    assert seen == [adjustment_role]


def test_same_account_bindings_object_is_delegated_without_copying(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    account_bindings = object()
    seen = []
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda session, proposal, got_bindings: seen.append(got_bindings) or object(),
    )

    resolution.resolve_fiscalized_economic_event_accounts(
        object(), object(), object(), object(), object(), account_bindings
    )
    assert seen == [account_bindings]


def test_returns_exact_account_resolution_authority_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    resolved = object()
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: resolved,
    )

    result = resolution.resolve_fiscalized_economic_event_accounts(
        object(), object(), object(), object(), object(), object()
    )
    assert result is resolved


def test_6bg_errors_propagate_and_account_resolution_is_not_called(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    error = RuntimeError("6bg failed")
    calls = []

    def fail(*args):
        raise error

    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        fail,
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda *args: calls.append(args),
    )

    with pytest.raises(RuntimeError) as excinfo:
        resolution.resolve_fiscalized_economic_event_accounts(
            object(), object(), object(), object(), object(), object()
        )

    assert excinfo.value is error
    assert calls == []


def test_account_resolution_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    error = ValueError("resolution failed")
    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda *args: object(),
    )

    def fail(*args):
        raise error

    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        fail,
    )

    with pytest.raises(ValueError) as excinfo:
        resolution.resolve_fiscalized_economic_event_accounts(
            object(), object(), object(), object(), object(), object()
        )

    assert excinfo.value is error


def test_does_not_construct_fiscalized_or_resolved_types_directly():
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    source = inspect.getsource(
        resolution.resolve_fiscalized_economic_event_accounts
    )
    for forbidden in (
        "FiscalizedAccountingProposal(",
        "FiscalizedProposalLine(",
        "ResolvedFiscalizedAccountingProposal(",
        "ResolvedFiscalizedProposalLine(",
    ):
        assert forbidden not in source


def test_uses_6bg_and_canonical_fiscalized_account_resolution_without_bypass():
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    source = inspect.getsource(
        resolution.resolve_fiscalized_economic_event_accounts
    )
    assert "compose_fiscal_economic_accounting_from_event" in source
    assert "resolve_fiscalized_proposal_accounts" in source
    for forbidden in (
        "declare_fiscal_economic_composition_from_event",
        "resolve_economic_event_with_provenance",
        "economic_fact_from_event",
        "resolve_economic_fact_with_provenance",
        "declare_fiscal_economic_composition(",
        "compose_fiscal_economic_accounting(",
        "resolve_account_by_code",
    ):
        assert forbidden not in source


def test_does_not_inspect_or_recalculate_fiscalized_accounting_truth():
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    source = inspect.getsource(
        resolution.resolve_fiscalized_economic_event_accounts
    ).lower()
    for forbidden in (
        ".lines",
        ".declaration",
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


def test_wrapper_does_not_prevalidate_or_load_session_bindings_or_fiscal_inputs(monkeypatch):
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    values = [object() for _ in range(6)]
    proposal = object()
    resolved = object()
    calls = []

    monkeypatch.setattr(
        resolution._event_fiscalized,
        "compose_fiscal_economic_accounting_from_event",
        lambda event, effect, basis, role: calls.append(
            ("compose", event, effect, basis, role)
        ) or proposal,
    )
    monkeypatch.setattr(
        resolution._account_resolution,
        "resolve_fiscalized_proposal_accounts",
        lambda session, got_proposal, bindings: calls.append(
            ("resolve", session, got_proposal, bindings)
        ) or resolved,
    )

    result = resolution.resolve_fiscalized_economic_event_accounts(*values)

    assert result is resolved
    assert calls == [
        ("compose", values[1], values[2], values[3], values[4]),
        ("resolve", values[0], proposal, values[5]),
    ]


def test_composition_adds_no_ambient_inputs_confirmation_persistence_posting_reporting_or_application():
    import aqorath.economic_event_fiscalized_account_resolution as resolution

    source = inspect.getsource(
        resolution.resolve_fiscalized_economic_event_accounts
    ).lower()
    module_source = inspect.getsource(resolution).lower()

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
        "confirm_fiscalized",
        "create_fiscalized_confirmation_snapshot",
        "create_fiscalized_posting_instruction",
        "execute_fiscalized_posting",
        "post_entry",
        "commit(",
        "rollback(",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "journalentry",
        "journalline",
    ):
        assert forbidden not in source

    assert "aqorath.application" not in module_source
