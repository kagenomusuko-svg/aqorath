"""Phase 5B.1 — governed fiscal-rule registry contracts.

5B governs writes to the versioned fiscal authority introduced in 5A. It does
not seed legal/tax values, calculate taxes, choose accounts, build proposals,
or migrate legacy templates.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import Decimal
from inspect import signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


def _session(tmp_path, name="registry.db"):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    db = tmp_path / name
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _context(**overrides):
    from aqorath.fiscal_rules import FiscalContext

    values = {
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "comercial",
    }
    values.update(overrides)
    return FiscalContext(**values)


def _registration(**overrides):
    from aqorath.fiscal_rule_registry import FiscalRuleRegistration

    values = {
        "rule_key": "iva.general_rate",
        "context": _context(),
        "effective_from": date(2024, 1, 1),
        "value": Decimal("0.160000"),
        "unit": "rate",
        "source_ref": "DOF:test-2024",
    }
    values.update(overrides)
    return FiscalRuleRegistration(**values)


def _records(session):
    from aqorath.models import FiscalRuleVersion

    return list(
        session.exec(
            select(FiscalRuleVersion).order_by(FiscalRuleVersion.effective_from)
        ).all()
    )


def test_fiscal_rule_registry_public_contract_and_exact_signatures_exist():
    import aqorath.fiscal_rule_registry as registry

    assert [f.name for f in fields(registry.FiscalRuleRegistration)] == [
        "rule_key",
        "context",
        "effective_from",
        "value",
        "unit",
        "source_ref",
    ]
    assert list(signature(registry.register_fiscal_rule_version).parameters) == [
        "session",
        "registration",
    ]
    assert list(signature(registry.get_fiscal_rule_history).parameters) == [
        "session",
        "rule_key",
        "context",
    ]

    registration = _registration()
    with pytest.raises(FrozenInstanceError):
        registration.value = Decimal("9")


def test_first_registration_persists_open_ended_exact_rule_and_returns_resolved_rule(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version
    from aqorath.fiscal_rules import ResolvedFiscalRule

    engine, session = _session(tmp_path)
    try:
        result = register_fiscal_rule_version(session, _registration())
        assert isinstance(result, ResolvedFiscalRule)
        assert result.rule_key == "iva.general_rate"
        assert result.value == Decimal("0.160000")
        assert result.unit == "rate"
        assert result.effective_from == date(2024, 1, 1)
        assert result.effective_to is None
        assert result.source_ref == "DOF:test-2024"

        rows = _records(session)
        assert len(rows) == 1
        assert rows[0].value == "0.160000"
        assert rows[0].effective_to is None
        assert rows[0].jurisdiction == "MX"
        assert rows[0].regime == "general"
        assert rows[0].entity_type == "comercial"
    finally:
        session.close()
        engine.dispose()


def test_appending_new_version_closes_only_previous_open_version_and_preserves_history(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration())
        new = register_fiscal_rule_version(
            session,
            _registration(
                effective_from=date(2025, 1, 1),
                value=Decimal("0.170000"),
                source_ref="DOF:test-2025",
            ),
        )

        rows = _records(session)
        assert len(rows) == 2
        assert rows[0].effective_from == date(2024, 1, 1)
        assert rows[0].effective_to == date(2024, 12, 31)
        assert rows[0].value == "0.160000"
        assert rows[0].source_ref == "DOF:test-2024"
        assert rows[1].effective_from == date(2025, 1, 1)
        assert rows[1].effective_to is None
        assert rows[1].value == "0.170000"
        assert rows[1].source_ref == "DOF:test-2025"
        assert new.value == Decimal("0.170000")
        assert new.effective_to is None
    finally:
        session.close()
        engine.dispose()


def test_history_is_immutable_ordered_exact_and_context_scoped(tmp_path):
    from aqorath.fiscal_rule_registry import (
        get_fiscal_rule_history,
        register_fiscal_rule_version,
    )

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration())
        register_fiscal_rule_version(
            session,
            _registration(
                effective_from=date(2025, 1, 1),
                value=Decimal("0.170000"),
                source_ref="DOF:test-2025",
            ),
        )
        register_fiscal_rule_version(
            session,
            _registration(
                context=_context(regime="resico"),
                value=Decimal("0.080000"),
                source_ref="DOF:resico",
            ),
        )

        history = get_fiscal_rule_history(
            session, "iva.general_rate", _context()
        )
        assert isinstance(history, tuple)
        assert [item.value for item in history] == [
            Decimal("0.160000"),
            Decimal("0.170000"),
        ]
        assert [item.source_ref for item in history] == [
            "DOF:test-2024",
            "DOF:test-2025",
        ]
        assert history[0].effective_to == date(2024, 12, 31)
        assert history[1].effective_to is None
    finally:
        session.close()
        engine.dispose()


def test_registry_history_remains_compatible_with_historical_5a_resolution(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration())
        register_fiscal_rule_version(
            session,
            _registration(
                effective_from=date(2025, 1, 1),
                value=Decimal("0.170000"),
                source_ref="DOF:test-2025",
            ),
        )

        old = resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 12, 31), _context()
        )
        new = resolve_fiscal_rule(
            session, "iva.general_rate", date(2025, 1, 1), _context()
        )
        assert old.value == Decimal("0.160000")
        assert old.source_ref == "DOF:test-2024"
        assert new.value == Decimal("0.170000")
        assert new.source_ref == "DOF:test-2025"
    finally:
        session.close()
        engine.dispose()


def test_registry_rejects_equal_or_backdated_append_without_mutating_history(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(
            session,
            _registration(effective_from=date(2025, 1, 1)),
        )
        for bad_date in (date(2025, 1, 1), date(2024, 12, 31)):
            with pytest.raises(ValueError):
                register_fiscal_rule_version(
                    session,
                    _registration(
                        effective_from=bad_date,
                        value=Decimal("0.170000"),
                        source_ref="DOF:bad",
                    ),
                )

        rows = _records(session)
        assert len(rows) == 1
        assert rows[0].effective_from == date(2025, 1, 1)
        assert rows[0].effective_to is None
        assert rows[0].value == "0.160000"
    finally:
        session.close()
        engine.dispose()


def test_registry_rejects_corrupt_or_ambiguous_existing_history_before_writing(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version
    from aqorath.models import FiscalRuleVersion

    engine, session = _session(tmp_path)
    try:
        session.add(
            FiscalRuleVersion(
                rule_key="iva.general_rate",
                jurisdiction="MX",
                regime="general",
                entity_type="comercial",
                effective_from=date(2024, 1, 1),
                effective_to=None,
                value="0.160000",
                unit="rate",
                source_ref="DOF:A",
            )
        )
        session.add(
            FiscalRuleVersion(
                rule_key="iva.general_rate",
                jurisdiction="MX",
                regime="general",
                entity_type="comercial",
                effective_from=date(2024, 6, 1),
                effective_to=None,
                value="0.170000",
                unit="rate",
                source_ref="DOF:B",
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="ambiguous|overlap|corrupt|multiple"):
            register_fiscal_rule_version(
                session,
                _registration(
                    effective_from=date(2025, 1, 1),
                    value=Decimal("0.180000"),
                    source_ref="DOF:C",
                ),
            )
        assert len(_records(session)) == 2
    finally:
        session.close()
        engine.dispose()


def test_registry_rejects_unit_drift_for_same_rule_scope(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration(unit="rate"))
        with pytest.raises(ValueError, match="unit"):
            register_fiscal_rule_version(
                session,
                _registration(
                    effective_from=date(2025, 1, 1),
                    value=Decimal("16.000000"),
                    unit="percent",
                    source_ref="DOF:unit-change",
                ),
            )
        rows = _records(session)
        assert len(rows) == 1
        assert rows[0].effective_to is None
        assert rows[0].unit == "rate"
    finally:
        session.close()
        engine.dispose()


def test_registry_keeps_contexts_independent_and_never_closes_other_scope(tmp_path):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration())
        register_fiscal_rule_version(
            session,
            _registration(
                context=_context(regime="resico"),
                value=Decimal("0.080000"),
                source_ref="DOF:resico-2024",
            ),
        )
        register_fiscal_rule_version(
            session,
            _registration(
                effective_from=date(2025, 1, 1),
                value=Decimal("0.170000"),
                source_ref="DOF:general-2025",
            ),
        )

        rows = _records(session)
        general = [r for r in rows if r.regime == "general"]
        resico = [r for r in rows if r.regime == "resico"]
        assert len(general) == 2
        assert general[0].effective_to == date(2024, 12, 31)
        assert general[1].effective_to is None
        assert len(resico) == 1
        assert resico[0].effective_to is None
        assert resico[0].value == "0.080000"
    finally:
        session.close()
        engine.dispose()


def test_registry_validates_nominal_registration_decimal_dates_and_nonempty_provenance(tmp_path):
    from types import SimpleNamespace
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version

    engine, session = _session(tmp_path)
    try:
        with pytest.raises(TypeError):
            register_fiscal_rule_version(session, SimpleNamespace())
        with pytest.raises(TypeError):
            register_fiscal_rule_version(session, _registration(value="0.16"))
        for bad_value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01")):
            with pytest.raises(ValueError):
                register_fiscal_rule_version(session, _registration(value=bad_value))
        with pytest.raises(TypeError):
            register_fiscal_rule_version(
                session, _registration(effective_from="2024-01-01")
            )
        for field_name in ("rule_key", "unit", "source_ref"):
            with pytest.raises(ValueError):
                register_fiscal_rule_version(
                    session, _registration(**{field_name: "   "})
                )
        with pytest.raises((TypeError, ValueError)):
            register_fiscal_rule_version(
                session, _registration(context=SimpleNamespace(
                    jurisdiction="MX", regime="general", entity_type="comercial"
                ))
            )
        assert _records(session) == []
    finally:
        session.close()
        engine.dispose()


def test_registry_uses_only_supplied_session_and_does_not_call_legacy_fiscal_paths(tmp_path, monkeypatch):
    import aqorath.config as config
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates
    from aqorath.fiscal_rule_registry import (
        get_fiscal_rule_history,
        register_fiscal_rule_version,
    )

    engine, session = _session(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("registry must use only its supplied session and authority")

    try:
        monkeypatch.setattr(storage, "get_session", forbidden)
        monkeypatch.setattr(tax, "calculate_taxes", forbidden)
        monkeypatch.setattr(templates, "get_template", forbidden)
        monkeypatch.setattr(config, "get_accounting_model", forbidden)

        result = register_fiscal_rule_version(session, _registration())
        history = get_fiscal_rule_history(session, "iva.general_rate", _context())
        assert result.value == Decimal("0.160000")
        assert len(history) == 1
        assert history[0].source_ref == "DOF:test-2024"
    finally:
        session.close()
        engine.dispose()


def test_registry_rolls_back_atomic_close_and_insert_when_commit_fails(tmp_path, monkeypatch):
    from aqorath.fiscal_rule_registry import register_fiscal_rule_version
    from aqorath.models import FiscalRuleVersion

    engine, session = _session(tmp_path)
    try:
        register_fiscal_rule_version(session, _registration())

        real_commit = session.commit

        def failing_commit():
            session.flush()
            raise RuntimeError("commit failed")

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            register_fiscal_rule_version(
                session,
                _registration(
                    effective_from=date(2025, 1, 1),
                    value=Decimal("0.170000"),
                    source_ref="DOF:test-2025",
                ),
            )
        monkeypatch.setattr(session, "commit", real_commit)

        session.close()
        verify = Session(engine)
        try:
            rows = list(
                verify.exec(
                    select(FiscalRuleVersion).order_by(FiscalRuleVersion.effective_from)
                ).all()
            )
            assert len(rows) == 1
            assert rows[0].effective_from == date(2024, 1, 1)
            assert rows[0].effective_to is None
            assert rows[0].value == "0.160000"
            assert rows[0].source_ref == "DOF:test-2024"
        finally:
            verify.close()
    finally:
        engine.dispose()
