"""Phase 6BO.1 — frozen EconomicEvent fiscalized posting-preparation contracts.

6BN established the explicit EconomicEvent fiscalized confirmation act. The existing
fiscalized posting authority transforms one explicitly confirmed fiscalized proposal into
an immutable posting instruction under one explicit zero-fiscal-line policy. This phase
freezes only their composition: preserve the confirmed proposal and policy by identity,
delegate exactly once to create_fiscalized_posting_instruction(), and return its exact
result. No event/account/fiscal re-resolution, confirmation preparation or confirmation
act, persistence, posting execution, Journal construction, reporting, or Application
behavior is added here.
"""

import inspect

import pytest


def test_public_signature_is_exactly_two_explicit_parameters():
    import aqorath.economic_event_fiscalized_posting as preparation

    assert tuple(
        inspect.signature(
            preparation.create_fiscalized_economic_event_posting_instruction
        ).parameters
    ) == ("confirmed_proposal", "zero_fiscal_line_policy")


def test_delegates_exact_arguments_once_to_fiscalized_posting_authority(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    confirmed = object()
    policy = object()
    instruction = object()
    calls = []

    def fake(got_confirmed, got_policy):
        calls.append((got_confirmed, got_policy))
        return instruction

    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        fake,
    )

    result = preparation.create_fiscalized_economic_event_posting_instruction(
        confirmed,
        policy,
    )

    assert calls == [(confirmed, policy)]
    assert result is instruction


def test_same_confirmed_proposal_object_is_delegated_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    confirmed = object()
    seen = []
    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        lambda got_confirmed, policy: seen.append(got_confirmed) or object(),
    )

    preparation.create_fiscalized_economic_event_posting_instruction(
        confirmed,
        object(),
    )

    assert seen == [confirmed]
    assert seen[0] is confirmed


def test_same_zero_policy_object_is_delegated_without_normalization(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    policy = object()
    seen = []
    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        lambda confirmed, got_policy: seen.append(got_policy) or object(),
    )

    preparation.create_fiscalized_economic_event_posting_instruction(
        object(),
        policy,
    )

    assert seen == [policy]
    assert seen[0] is policy


def test_returns_exact_posting_authority_result_without_copying(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    marker = object()
    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        lambda confirmed, policy: marker,
    )

    assert preparation.create_fiscalized_economic_event_posting_instruction(
        object(),
        object(),
    ) is marker


def test_posting_authority_errors_propagate_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    error = ValueError("posting preparation failed")

    def fail(confirmed, policy):
        raise error

    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        fail,
    )

    with pytest.raises(ValueError) as excinfo:
        preparation.create_fiscalized_economic_event_posting_instruction(
            object(),
            object(),
        )

    assert excinfo.value is error


def test_does_not_prepare_or_repeat_explicit_confirmation_act():
    import aqorath.economic_event_fiscalized_posting as preparation

    source = inspect.getsource(
        preparation.create_fiscalized_economic_event_posting_instruction
    )
    for forbidden in (
        "prepare_fiscalized_economic_event_confirmation",
        "confirm_fiscalized_economic_event",
        "create_fiscalized_confirmation_snapshot",
        "confirm_fiscalized_snapshot",
    ):
        assert forbidden not in source


def test_does_not_construct_posting_or_confirmation_types_directly():
    import aqorath.economic_event_fiscalized_posting as preparation

    source = inspect.getsource(
        preparation.create_fiscalized_economic_event_posting_instruction
    )
    assert "create_fiscalized_posting_instruction" in source
    for forbidden in (
        "FiscalizedPostingInstruction(",
        "FiscalizedPostingLine(",
        "ConfirmedFiscalizedProposal(",
        "FiscalizedConfirmationSnapshot(",
    ):
        assert forbidden not in source


def test_does_not_inspect_confirmed_or_snapshot_truth():
    import aqorath.economic_event_fiscalized_posting as preparation

    source = inspect.getsource(
        preparation.create_fiscalized_economic_event_posting_instruction
    ).lower()
    for forbidden in (
        ".snapshot",
        ".lines",
        ".provenance",
        ".description",
        ".account_role",
        ".account_id",
        ".account_code",
        ".account_name",
        ".side",
        ".amount",
        "decimal(",
        "sum(",
        "ledger_signed_balance",
    ):
        assert forbidden not in source


def test_does_not_default_validate_or_translate_zero_policy_locally(monkeypatch):
    import aqorath.economic_event_fiscalized_posting as preparation

    confirmed = object()
    policy = object()
    seen = []
    monkeypatch.setattr(
        preparation._posting,
        "create_fiscalized_posting_instruction",
        lambda got_confirmed, got_policy: seen.append(
            (got_confirmed, got_policy)
        ) or object(),
    )

    preparation.create_fiscalized_economic_event_posting_instruction(
        confirmed,
        policy,
    )

    assert seen == [(confirmed, policy)]


def test_does_not_reenter_event_account_or_fiscal_resolution():
    import aqorath.economic_event_fiscalized_posting as preparation

    source = inspect.getsource(
        preparation.create_fiscalized_economic_event_posting_instruction
    ).lower()
    for forbidden in (
        "resolve_fiscalized_economic_event_accounts",
        "compose_fiscal_economic_accounting_from_event",
        "resolve_fiscalized_proposal_accounts",
        "resolve_account",
        "calculate_fiscal",
        "fiscal_effect",
        "account_bindings",
    ):
        assert forbidden not in source


def test_preparation_adds_no_ambient_persistence_execution_reporting_or_application():
    import aqorath.economic_event_fiscalized_posting as preparation

    source = inspect.getsource(
        preparation.create_fiscalized_economic_event_posting_instruction
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
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "commit(",
        "rollback(",
        "execute_fiscalized_posting",
        "post_entry",
        "journalentry",
        "journalline",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert forbidden not in source

    assert "aqorath.application" not in module_source
