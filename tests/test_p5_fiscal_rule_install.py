"""Phase 5D.1 — atomic fiscal rule-set installation contracts.

A reviewed manifest must install as one transaction: all governed rule versions
are committed together or none are. This phase still does not supply legal tax
values, calculate taxes, choose accounts, or migrate legacy templates.
"""

from datetime import date
from decimal import Decimal
from inspect import signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


def _session(tmp_path, name="install.db"):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    db = tmp_path / name
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _context(**overrides):
    from aqorath.fiscal_rules import FiscalContext

    values = {"jurisdiction": "MX", "regime": "general", "entity_type": "comercial"}
    values.update(overrides)
    return FiscalContext(**values)


def _entry(**overrides):
    from aqorath.fiscal_rule_set import FiscalRuleSetEntry

    values = {
        "rule_key": "iva.general_rate",
        "effective_from": date(2024, 1, 1),
        "value": Decimal("0.160000"),
        "unit": "rate",
        "source_ref": "DOF:test-2024",
    }
    values.update(overrides)
    return FiscalRuleSetEntry(**values)


def _manifest(**overrides):
    from aqorath.fiscal_rule_set import FiscalRuleSetManifest

    values = {
        "set_key": "mx.general.comercial",
        "version": "2025.1",
        "context": _context(),
        "entries": (
            _entry(),
            _entry(
                effective_from=date(2025, 1, 1),
                value=Decimal("0.170000"),
                source_ref="DOF:test-2025",
            ),
            _entry(
                rule_key="isr.retention_rate",
                value=Decimal("0.100000"),
                source_ref="DOF:isr-2024",
            ),
        ),
    }
    values.update(overrides)
    return FiscalRuleSetManifest(**values)


def _rows(session):
    from aqorath.models import FiscalRuleVersion

    return list(
        session.exec(
            select(FiscalRuleVersion).order_by(
                FiscalRuleVersion.rule_key,
                FiscalRuleVersion.effective_from,
            )
        ).all()
    )


def test_atomic_install_public_contract_and_exact_signatures_exist():
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rule_registry as registry

    assert list(signature(registry.register_fiscal_rule_versions).parameters) == [
        "session", "registrations"
    ]
    assert list(signature(installer.install_fiscal_rule_set).parameters) == [
        "session", "manifest"
    ]


def test_batch_registry_commits_once_returns_immutable_results_and_preserves_authored_order(tmp_path, monkeypatch):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_versions
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    engine, session = _session(tmp_path)
    calls = []
    real_commit = session.commit

    def counted_commit():
        calls.append("commit")
        return real_commit()

    try:
        monkeypatch.setattr(session, "commit", counted_commit)
        registrations = materialize_fiscal_rule_set(_manifest())
        result = register_fiscal_rule_versions(session, registrations)

        assert calls == ["commit"]
        assert isinstance(result, tuple)
        assert [item.rule_key for item in result] == [
            "iva.general_rate",
            "iva.general_rate",
            "isr.retention_rate",
        ]
        assert [item.source_ref for item in result] == [
            "DOF:test-2024",
            "DOF:test-2025",
            "DOF:isr-2024",
        ]
    finally:
        session.close()
        engine.dispose()


def test_batch_registry_builds_exact_contiguous_history_for_multiple_versions_same_rule(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_versions, get_fiscal_rule_history
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_versions(session, materialize_fiscal_rule_set(_manifest()))
        history = get_fiscal_rule_history(session, "iva.general_rate", _context())

        assert len(history) == 2
        assert history[0].effective_from == date(2024, 1, 1)
        assert history[0].effective_to == date(2024, 12, 31)
        assert history[0].value == Decimal("0.160000")
        assert history[1].effective_from == date(2025, 1, 1)
        assert history[1].effective_to is None
        assert history[1].value == Decimal("0.170000")
    finally:
        session.close()
        engine.dispose()


def test_batch_registry_keeps_distinct_rule_histories_independent(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_versions, get_fiscal_rule_history
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_versions(session, materialize_fiscal_rule_set(_manifest()))
        iva = get_fiscal_rule_history(session, "iva.general_rate", _context())
        isr = get_fiscal_rule_history(session, "isr.retention_rate", _context())
        assert len(iva) == 2
        assert len(isr) == 1
        assert isr[0].effective_to is None
        assert isr[0].value == Decimal("0.100000")
    finally:
        session.close()
        engine.dispose()


def test_batch_registry_requires_nonempty_tuple_of_nominal_registrations_before_writing(tmp_path):
    from types import SimpleNamespace
    from aqorath.fiscal_rule_registry import register_fiscal_rule_versions

    engine, session = _session(tmp_path)
    try:
        with pytest.raises(TypeError):
            register_fiscal_rule_versions(session, [])
        with pytest.raises(ValueError):
            register_fiscal_rule_versions(session, ())
        with pytest.raises(TypeError):
            register_fiscal_rule_versions(session, (SimpleNamespace(),))
        assert _rows(session) == []
    finally:
        session.close()
        engine.dispose()


def test_batch_registry_rolls_back_all_prior_staging_when_later_registration_conflicts_with_database(tmp_path):
    from aqorath.fiscal_rule_registry import (
        FiscalRuleRegistration,
        register_fiscal_rule_version,
        register_fiscal_rule_versions,
    )

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(
            session,
            FiscalRuleRegistration(
                "iva.general_rate", _context(), date(2024, 1, 1),
                Decimal("0.160000"), "rate", "DOF:base"
            ),
        )

        batch = (
            FiscalRuleRegistration(
                "iva.general_rate", _context(), date(2025, 1, 1),
                Decimal("0.170000"), "rate", "DOF:valid-first"
            ),
            FiscalRuleRegistration(
                "iva.general_rate", _context(), date(2024, 6, 1),
                Decimal("0.180000"), "rate", "DOF:invalid-later"
            ),
        )
        with pytest.raises(ValueError):
            register_fiscal_rule_versions(session, batch)

        session.close()
        verify = Session(engine)
        try:
            rows = _rows(verify)
            assert len(rows) == 1
            assert rows[0].effective_from == date(2024, 1, 1)
            assert rows[0].effective_to is None
            assert rows[0].value == "0.160000"
            assert rows[0].source_ref == "DOF:base"
        finally:
            verify.close()
    finally:
        engine.dispose()


def test_batch_registry_rolls_back_every_row_and_prior_closure_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.fiscal_rule_registry import (
        FiscalRuleRegistration,
        register_fiscal_rule_version,
        register_fiscal_rule_versions,
    )
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(
            session,
            FiscalRuleRegistration(
                "iva.general_rate", _context(), date(2023, 1, 1),
                Decimal("0.150000"), "rate", "DOF:preexisting"
            ),
        )

        def failing_commit():
            session.flush()
            raise RuntimeError("commit failed")

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            register_fiscal_rule_versions(
                session, materialize_fiscal_rule_set(_manifest())
            )

        session.close()
        verify = Session(engine)
        try:
            rows = _rows(verify)
            assert len(rows) == 1
            assert rows[0].effective_from == date(2023, 1, 1)
            assert rows[0].effective_to is None
            assert rows[0].source_ref == "DOF:preexisting"
        finally:
            verify.close()
    finally:
        engine.dispose()


def test_installer_materializes_once_then_batches_exact_registration_tuple_once(monkeypatch):
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rule_registry as registry
    import aqorath.fiscal_rule_set as rule_set

    manifest = _manifest()
    registrations = object()
    installed = object()
    calls = []

    def fake_materialize(received):
        calls.append(("materialize", received))
        assert received is manifest
        return registrations

    def fake_batch(session, received):
        calls.append(("batch", session, received))
        assert session == "SESSION"
        assert received is registrations
        return installed

    monkeypatch.setattr(rule_set, "materialize_fiscal_rule_set", fake_materialize)
    monkeypatch.setattr(registry, "register_fiscal_rule_versions", fake_batch)

    result = installer.install_fiscal_rule_set("SESSION", manifest)
    assert result is installed
    assert calls == [
        ("materialize", manifest),
        ("batch", "SESSION", registrations),
    ]


def test_installer_propagates_materialization_failure_without_registry_call(monkeypatch):
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rule_registry as registry
    import aqorath.fiscal_rule_set as rule_set

    def fail_manifest(*args, **kwargs):
        raise ValueError("invalid manifest")

    def forbidden(*args, **kwargs):
        raise AssertionError("batch registry must not run")

    monkeypatch.setattr(rule_set, "materialize_fiscal_rule_set", fail_manifest)
    monkeypatch.setattr(registry, "register_fiscal_rule_versions", forbidden)

    with pytest.raises(ValueError, match="invalid manifest"):
        installer.install_fiscal_rule_set("SESSION", _manifest())


def test_installer_propagates_registry_failure_without_retry_or_fallback(monkeypatch):
    import aqorath.fiscal_rule_install as installer
    import aqorath.fiscal_rule_registry as registry
    import aqorath.fiscal_rule_set as rule_set

    calls = []

    def fake_materialize(manifest):
        return ("R1", "R2")

    def fail_batch(session, registrations):
        calls.append((session, registrations))
        raise RuntimeError("registry failed")

    monkeypatch.setattr(rule_set, "materialize_fiscal_rule_set", fake_materialize)
    monkeypatch.setattr(registry, "register_fiscal_rule_versions", fail_batch)

    with pytest.raises(RuntimeError, match="registry failed"):
        installer.install_fiscal_rule_set("SESSION", _manifest())
    assert calls == [("SESSION", ("R1", "R2"))]


def test_real_installer_persists_manifest_atomically_and_remains_resolvable_by_5a(tmp_path):
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        installed = install_fiscal_rule_set(session, _manifest())
        assert isinstance(installed, tuple)
        assert len(installed) == 3

        old_iva = resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 12, 31), _context()
        )
        new_iva = resolve_fiscal_rule(
            session, "iva.general_rate", date(2025, 1, 1), _context()
        )
        isr = resolve_fiscal_rule(
            session, "isr.retention_rate", date(2026, 1, 1), _context()
        )
        assert old_iva.value == Decimal("0.160000")
        assert old_iva.source_ref == "DOF:test-2024"
        assert new_iva.value == Decimal("0.170000")
        assert new_iva.source_ref == "DOF:test-2025"
        assert isr.value == Decimal("0.100000")
    finally:
        session.close()
        engine.dispose()


def test_batch_and_installer_use_only_supplied_session_without_legacy_fiscal_paths(tmp_path, monkeypatch):
    import aqorath.config as config
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("atomic install must use only supplied authorities")

    try:
        monkeypatch.setattr(storage, "get_session", forbidden)
        monkeypatch.setattr(tax, "calculate_taxes", forbidden)
        monkeypatch.setattr(templates, "get_template", forbidden)
        monkeypatch.setattr(config, "get_accounting_model", forbidden)

        result = install_fiscal_rule_set(session, _manifest())
        assert len(result) == 3
    finally:
        session.close()
        engine.dispose()
