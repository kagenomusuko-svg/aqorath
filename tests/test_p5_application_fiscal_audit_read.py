"""Phase 5AI.1 — application boundary for persisted fiscal audit reads."""

from inspect import Parameter, signature

import pytest


def _assert_exact_signature(fn):
    sig = signature(fn)
    assert list(sig.parameters) == ["session", "entry_id"]
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def test_application_exposes_persisted_fiscal_audit_read_with_exact_signature():
    import aqorath.application as application

    assert callable(application.load_fiscal_posting_audit_snapshot)
    _assert_exact_signature(application.load_fiscal_posting_audit_snapshot)


def test_application_delegates_exact_session_and_entry_id_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_posting_audit_read as audit_read

    session = object()
    sentinel = object()
    calls = []

    def fake(session_arg, entry_id_arg):
        calls.append((session_arg, entry_id_arg))
        return sentinel

    monkeypatch.setattr(audit_read, "load_fiscal_posting_audit_snapshot", fake)
    result = application.load_fiscal_posting_audit_snapshot(session, 47)

    assert result is sentinel
    assert calls == [(session, 47)]


def test_application_uses_module_lookup_not_captured_function_alias(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_posting_audit_read as audit_read

    replacement = object()
    monkeypatch.setattr(
        audit_read,
        "load_fiscal_posting_audit_snapshot",
        lambda session, entry_id: replacement,
    )
    assert application.load_fiscal_posting_audit_snapshot(object(), 1) is replacement


def test_application_propagates_reader_failure_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_posting_audit_read as audit_read

    calls = []

    def failing(session, entry_id):
        calls.append((session, entry_id))
        raise LookupError("missing fiscal audit")

    monkeypatch.setattr(audit_read, "load_fiscal_posting_audit_snapshot", failing)
    session = object()
    with pytest.raises(LookupError, match="missing fiscal audit"):
        application.load_fiscal_posting_audit_snapshot(session, 9)
    assert calls == [(session, 9)]


def test_application_does_not_open_storage_query_models_or_post(monkeypatch):
    import aqorath.application as application
    import aqorath.core as core
    import aqorath.fiscal_posting_audit_read as audit_read
    import aqorath.storage as storage

    sentinel = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application audit read must only delegate")

    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(core, "post_entry", forbidden)
    monkeypatch.setattr(
        audit_read,
        "load_fiscal_posting_audit_snapshot",
        lambda session, entry_id: sentinel,
    )
    assert application.load_fiscal_posting_audit_snapshot(object(), 5) is sentinel


def test_application_keeps_audit_read_distinct_from_audited_posting(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.fiscal_posting_audit_read as audit_read

    sentinel = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("read boundary cannot execute audited posting")

    monkeypatch.setattr(persistence, "execute_fiscalized_posting_with_audit", forbidden)
    monkeypatch.setattr(
        audit_read,
        "load_fiscal_posting_audit_snapshot",
        lambda session, entry_id: sentinel,
    )
    assert application.load_fiscal_posting_audit_snapshot(object(), 3) is sentinel


def test_application_does_not_recalculate_reround_or_resolve_accounts(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscalized_account_resolution as resolution
    import aqorath.fiscal_posting_audit_read as audit_read

    sentinel = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application audit read cannot reconstruct fiscal truth")

    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)
    monkeypatch.setattr(resolution, "resolve_fiscalized_proposal_accounts", forbidden)
    monkeypatch.setattr(
        audit_read,
        "load_fiscal_posting_audit_snapshot",
        lambda session, entry_id: sentinel,
    )
    assert application.load_fiscal_posting_audit_snapshot(object(), 8) is sentinel


def test_existing_audited_posting_application_api_remains_available():
    import aqorath.application as application

    assert callable(application.execute_fiscalized_posting_with_audit)
    assert callable(application.execute_fiscalized_posting_instruction)
