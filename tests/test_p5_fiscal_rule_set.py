"""Phase 5C.1 — fiscal rule-set manifest contracts.

A rule-set manifest is reviewable/versionable source data. This phase remains
pure: no database installation, tax calculation, templates, posting, or legal
rule values are supplied by production code.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import Decimal
from inspect import signature

import pytest


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
        "version": "2024.1",
        "context": _context(),
        "entries": (_entry(),),
    }
    values.update(overrides)
    return FiscalRuleSetManifest(**values)


def test_fiscal_rule_set_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_rule_set as rule_set

    assert [f.name for f in fields(rule_set.FiscalRuleSetEntry)] == [
        "rule_key", "effective_from", "value", "unit", "source_ref"
    ]
    assert [f.name for f in fields(rule_set.FiscalRuleSetManifest)] == [
        "set_key", "version", "context", "entries"
    ]
    assert list(signature(rule_set.materialize_fiscal_rule_set).parameters) == ["manifest"]

    entry = _entry()
    manifest = _manifest()
    with pytest.raises(FrozenInstanceError):
        entry.value = Decimal("9")
    with pytest.raises(FrozenInstanceError):
        manifest.version = "changed"


def test_materialization_returns_ordered_governed_registrations_with_shared_exact_context():
    from aqorath.fiscal_rule_registry import FiscalRuleRegistration
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    context = _context()
    entries = (
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
    )
    registrations = materialize_fiscal_rule_set(
        _manifest(context=context, entries=entries)
    )

    assert isinstance(registrations, tuple)
    assert len(registrations) == 3
    assert all(isinstance(item, FiscalRuleRegistration) for item in registrations)
    assert [item.rule_key for item in registrations] == [
        "iva.general_rate", "iva.general_rate", "isr.retention_rate"
    ]
    assert registrations[0].context is context
    assert registrations[1].context is context
    assert registrations[2].context is context
    assert registrations[1].value == Decimal("0.170000")
    assert registrations[1].source_ref == "DOF:test-2025"


def test_manifest_preserves_decimal_precision_and_provenance_without_float_conversion():
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    exact = Decimal("0.1234567890123456789012345678")
    result = materialize_fiscal_rule_set(
        _manifest(entries=(_entry(value=exact, source_ref="DOF:exact"),))
    )
    assert result[0].value == exact
    assert str(result[0].value) == "0.1234567890123456789012345678"
    assert result[0].source_ref == "DOF:exact"


def test_manifest_requires_nominal_manifest_context_tuple_entries_and_nonempty_identity():
    from types import SimpleNamespace
    from aqorath.fiscal_rule_set import FiscalRuleSetManifest, materialize_fiscal_rule_set

    with pytest.raises(TypeError):
        materialize_fiscal_rule_set(SimpleNamespace())
    with pytest.raises((TypeError, ValueError)):
        materialize_fiscal_rule_set(_manifest(context=SimpleNamespace(
            jurisdiction="MX", regime="general", entity_type="comercial"
        )))
    with pytest.raises(TypeError):
        materialize_fiscal_rule_set(_manifest(entries=[_entry()]))
    with pytest.raises(ValueError):
        materialize_fiscal_rule_set(_manifest(entries=()))
    for field_name in ("set_key", "version"):
        with pytest.raises(ValueError):
            materialize_fiscal_rule_set(_manifest(**{field_name: "   "}))

    assert isinstance(_manifest(), FiscalRuleSetManifest)


def test_manifest_validates_entry_nominal_dates_decimal_and_provenance():
    from types import SimpleNamespace
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    with pytest.raises(TypeError):
        materialize_fiscal_rule_set(_manifest(entries=(SimpleNamespace(),)))
    with pytest.raises(TypeError):
        materialize_fiscal_rule_set(_manifest(entries=(_entry(effective_from="2024-01-01"),)))
    with pytest.raises(TypeError):
        materialize_fiscal_rule_set(_manifest(entries=(_entry(value="0.16"),)))
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01")):
        with pytest.raises(ValueError):
            materialize_fiscal_rule_set(_manifest(entries=(_entry(value=bad),)))
    for field_name in ("rule_key", "unit", "source_ref"):
        with pytest.raises(ValueError):
            materialize_fiscal_rule_set(
                _manifest(entries=(_entry(**{field_name: "   "}),))
            )


def test_manifest_rejects_duplicate_rule_start_and_non_monotonic_versions():
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    duplicate = (
        _entry(),
        _entry(value=Decimal("0.170000"), source_ref="DOF:duplicate"),
    )
    with pytest.raises(ValueError, match="duplicate|start"):
        materialize_fiscal_rule_set(_manifest(entries=duplicate))

    backwards = (
        _entry(effective_from=date(2025, 1, 1), value=Decimal("0.170000")),
        _entry(effective_from=date(2024, 1, 1)),
    )
    with pytest.raises(ValueError, match="order|monotonic|increasing"):
        materialize_fiscal_rule_set(_manifest(entries=backwards))


def test_manifest_rejects_unit_drift_within_same_rule_but_allows_distinct_rule_units():
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    with pytest.raises(ValueError, match="unit"):
        materialize_fiscal_rule_set(
            _manifest(
                entries=(
                    _entry(unit="rate"),
                    _entry(
                        effective_from=date(2025, 1, 1),
                        value=Decimal("16"),
                        unit="percent",
                        source_ref="DOF:changed-unit",
                    ),
                )
            )
        )

    ok = materialize_fiscal_rule_set(
        _manifest(
            entries=(
                _entry(unit="rate"),
                _entry(
                    rule_key="subsidy.threshold",
                    value=Decimal("1000.00"),
                    unit="currency",
                    source_ref="DOF:threshold",
                ),
            )
        )
    )
    assert [item.unit for item in ok] == ["rate", "currency"]


def test_manifest_preserves_author_review_order_and_does_not_silently_sort_rules():
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    entries = (
        _entry(rule_key="z.rule", source_ref="Z"),
        _entry(rule_key="a.rule", source_ref="A"),
    )
    result = materialize_fiscal_rule_set(_manifest(entries=entries))
    assert [item.rule_key for item in result] == ["z.rule", "a.rule"]
    assert [item.source_ref for item in result] == ["Z", "A"]


def test_manifest_is_pure_and_does_not_query_install_calculate_or_touch_legacy_paths(monkeypatch):
    import aqorath.fiscal_rule_registry as registry
    import aqorath.fiscal_rules as fiscal_rules
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    def forbidden(*args, **kwargs):
        raise AssertionError("rule-set materialization must be pure")

    monkeypatch.setattr(registry, "register_fiscal_rule_version", forbidden)
    monkeypatch.setattr(fiscal_rules, "resolve_fiscal_rule", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(tax, "calculate_taxes", forbidden)
    monkeypatch.setattr(templates, "get_template", forbidden)

    result = materialize_fiscal_rule_set(_manifest())
    assert len(result) == 1
    assert result[0].value == Decimal("0.160000")


def test_manifest_materialization_does_not_mutate_manifest_entries_or_context():
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    context = _context()
    entries = (
        _entry(),
        _entry(
            effective_from=date(2025, 1, 1),
            value=Decimal("0.170000"),
            source_ref="DOF:2025",
        ),
    )
    manifest = _manifest(context=context, entries=entries)
    before = (manifest.context, manifest.entries, tuple(manifest.entries))

    result = materialize_fiscal_rule_set(manifest)

    assert manifest.context is before[0]
    assert manifest.entries is before[1]
    assert tuple(manifest.entries) == before[2]
    assert result[0].context is context
