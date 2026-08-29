"""Phase 6BN.1 — frozen EconomicEvent fiscalized explicit-confirmation contracts.

6BM prepares one exact FiscalizedConfirmationSnapshot from EconomicEvent truth but
intentionally stops before the explicit confirmation act. The existing fiscalized
confirmation authority already owns that act through confirm_fiscalized_snapshot().
This phase freezes only their final composition: accept one already prepared snapshot,
delegate that exact object once to the confirmation authority, and return its exact
ConfirmedFiscalizedProposal result. No event/account re-resolution, snapshot rebuilding,
persistence, posting, Journal construction, reporting, or Application behavior is added.
"""

import inspect

import pytest


def test_public_signature_is_exactly_snapshot_only():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    assert tuple(
        inspect.signature(confirmation.confirm_fiscalized_economic_event).parameters
    ) == ("snapshot",)


def test_delegates_exact_snapshot_identity_once_to_confirmation_authority(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    snapshot = object()
    confirmed = object()
    calls = []

    def fake(got_snapshot):
        calls.append(got_snapshot)
        return confirmed

    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_fiscalized_snapshot",
        fake,
    )

    result = confirmation.confirm_fiscalized_economic_event(snapshot)

    assert calls == [snapshot]
    assert calls[0] is snapshot
    assert result is confirmed


def test_returns_exact_confirmation_authority_result_without_wrapping(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    confirmed = object()
    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_fiscalized_snapshot",
        lambda snapshot: confirmed,
    )

    assert confirmation.confirm_fiscalized_economic_event(object()) is confirmed


def test_confirmation_authority_error_propagates_without_recovery(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    error = ValueError("confirmation failed")

    def fail(snapshot):
        raise error

    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_fiscalized_snapshot",
        fail,
    )

    with pytest.raises(ValueError) as excinfo:
        confirmation.confirm_fiscalized_economic_event(object())

    assert excinfo.value is error


def test_wrapper_does_not_prevalidate_or_normalize_snapshot(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    snapshot = object()
    seen = []
    marker = object()
    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_fiscalized_snapshot",
        lambda got_snapshot: seen.append(got_snapshot) or marker,
    )

    result = confirmation.confirm_fiscalized_economic_event(snapshot)

    assert seen == [snapshot]
    assert result is marker


def test_confirmation_does_not_reenter_6bm_preparation_or_6bl_resolution(monkeypatch):
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    def forbidden(*args, **kwargs):
        raise AssertionError("explicit confirmation must not reprepare or reresolve")

    monkeypatch.setattr(
        confirmation,
        "prepare_fiscalized_economic_event_confirmation",
        forbidden,
    )
    monkeypatch.setattr(
        confirmation._event_resolution,
        "resolve_fiscalized_economic_event_accounts",
        forbidden,
    )
    monkeypatch.setattr(
        confirmation._confirmation,
        "create_fiscalized_confirmation_snapshot",
        forbidden,
    )
    monkeypatch.setattr(
        confirmation._confirmation,
        "confirm_fiscalized_snapshot",
        lambda snapshot: object(),
    )

    confirmation.confirm_fiscalized_economic_event(object())


def test_source_uses_only_explicit_confirmation_authority_for_the_act():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    source = inspect.getsource(confirmation.confirm_fiscalized_economic_event)

    assert "confirm_fiscalized_snapshot" in source
    for forbidden in (
        "prepare_fiscalized_economic_event_confirmation(",
        "resolve_fiscalized_economic_event_accounts(",
        "create_fiscalized_confirmation_snapshot(",
    ):
        assert forbidden not in source


def test_does_not_construct_confirmation_types_directly():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    source = inspect.getsource(confirmation.confirm_fiscalized_economic_event)
    for forbidden in (
        "ConfirmedFiscalizedProposal(",
        "FiscalizedConfirmationSnapshot(",
        "FiscalizedConfirmationLine(",
        "FiscalizedConfirmationProvenance(",
    ):
        assert forbidden not in source


def test_does_not_inspect_or_rebuild_snapshot_truth():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    source = inspect.getsource(
        confirmation.confirm_fiscalized_economic_event
    ).lower()
    for forbidden in (
        ".lines",
        ".provenance",
        ".explanation",
        ".account_role",
        ".account_id",
        ".account_code",
        ".account_name",
        ".side",
        ".amount",
        "decimal(",
        "sum(",
        "quantize",
        "round(",
        "ledger_signed_balance",
    ):
        assert forbidden not in source


def test_explicit_confirmation_adds_no_persistence_posting_journal_or_reporting():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    source = inspect.getsource(
        confirmation.confirm_fiscalized_economic_event
    ).lower()
    for forbidden in (
        "get_session",
        "repository",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "commit(",
        "rollback(",
        "create_fiscalized_posting_instruction",
        "execute_fiscalized_posting",
        "post_entry",
        "journalentry",
        "journalline",
        "trial_balance",
        "income_statement",
        "balance_sheet",
    ):
        assert forbidden not in source


def test_explicit_confirmation_has_no_ambient_inputs():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    source = inspect.getsource(
        confirmation.confirm_fiscalized_economic_event
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


def test_module_does_not_expand_confirmation_into_application_or_posting_layers():
    import aqorath.economic_event_fiscalized_confirmation as confirmation

    module_source = inspect.getsource(confirmation).lower()

    assert "aqorath.application" not in module_source
    assert "from . import application" not in module_source
    assert "from . import fiscalized_posting" not in module_source
    assert "from .fiscalized_posting" not in module_source
