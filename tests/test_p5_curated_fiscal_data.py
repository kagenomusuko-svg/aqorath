"""Phase 5E.1 — curated Mexican fiscal data contracts.

Scope is intentionally narrow: the federal general IVA rate for the explicit
MX/general/comercial Aqorath context, effective from 2010-01-01. No border
stimulus, zero rate, exemptions, retentions, ISR, payroll or other rules are
implied or seeded by this phase.
"""

from datetime import date
from decimal import Decimal
import importlib

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


EXPECTED_SOURCE = "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1"


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'curated.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_curated_fiscal_data_public_manifest_contract_exists():
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_set import FiscalRuleSetManifest

    assert isinstance(data.MX_GENERAL_COMMERCIAL_IVA, FiscalRuleSetManifest)
    assert isinstance(data.CURATED_FISCAL_RULE_SETS, tuple)
    assert data.CURATED_FISCAL_RULE_SETS == (data.MX_GENERAL_COMMERCIAL_IVA,)


def test_curated_iva_manifest_has_exact_reviewable_identity_and_context():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_GENERAL_COMMERCIAL_IVA
    assert manifest.set_key == "mx.general.comercial.iva-general"
    assert manifest.version == "2010.1"
    assert manifest.context.jurisdiction == "MX"
    assert manifest.context.regime == "general"
    assert manifest.context.entity_type == "comercial"


def test_curated_iva_manifest_contains_exact_general_rate_effective_2010():
    import aqorath.fiscal_rule_data_mx as data

    assert len(data.MX_GENERAL_COMMERCIAL_IVA.entries) == 1
    entry = data.MX_GENERAL_COMMERCIAL_IVA.entries[0]
    assert entry.rule_key == "iva.general_rate"
    assert entry.effective_from == date(2010, 1, 1)
    assert entry.value == Decimal("0.16")
    assert str(entry.value) == "0.16"
    assert entry.unit == "rate"
    assert entry.source_ref == EXPECTED_SOURCE


def test_curated_iva_data_does_not_seed_unverified_or_out_of_scope_fiscal_rules():
    import aqorath.fiscal_rule_data_mx as data

    keys = {
        entry.rule_key
        for manifest in data.CURATED_FISCAL_RULE_SETS
        for entry in manifest.entries
    }
    assert keys == {"iva.general_rate"}
    forbidden_fragments = (
        "zero",
        "exempt",
        "border",
        "retention",
        "isr",
        "imss",
        "payroll",
    )
    assert all(not any(fragment in key.lower() for fragment in forbidden_fragments) for key in keys)


def test_curated_iva_manifest_materializes_to_exact_governed_registration():
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    registrations = materialize_fiscal_rule_set(data.MX_GENERAL_COMMERCIAL_IVA)
    assert len(registrations) == 1
    registration = registrations[0]
    assert registration.rule_key == "iva.general_rate"
    assert registration.context is data.MX_GENERAL_COMMERCIAL_IVA.context
    assert registration.effective_from == date(2010, 1, 1)
    assert registration.value == Decimal("0.16")
    assert registration.unit == "rate"
    assert registration.source_ref == EXPECTED_SOURCE


def test_curated_iva_manifest_installs_and_resolves_exactly_from_effective_boundary_forward(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        installed = install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        assert len(installed) == 1
        assert installed[0].value == Decimal("0.16")
        assert installed[0].source_ref == EXPECTED_SOURCE

        at_start = resolve_fiscal_rule(
            session,
            "iva.general_rate",
            date(2010, 1, 1),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
        )
        current_later = resolve_fiscal_rule(
            session,
            "iva.general_rate",
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
        )
        assert at_start.value == Decimal("0.16")
        assert at_start.effective_from == date(2010, 1, 1)
        assert at_start.effective_to is None
        assert current_later.value == Decimal("0.16")
        assert current_later.source_ref == EXPECTED_SOURCE
    finally:
        session.close()
        engine.dispose()


def test_curated_iva_manifest_does_not_invent_pre_2010_history(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        with pytest.raises(LookupError):
            resolve_fiscal_rule(
                session,
                "iva.general_rate",
                date(2009, 12, 31),
                data.MX_GENERAL_COMMERCIAL_IVA.context,
            )
    finally:
        session.close()
        engine.dispose()


def test_curated_iva_manifest_requires_exact_context_and_does_not_wildcard_to_other_entities(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import FiscalContext, resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        for context in (
            FiscalContext("MX", "resico", "comercial"),
            FiscalContext("MX", "general", "sin_fines"),
            FiscalContext("MX", "general", "persona_fisica"),
        ):
            with pytest.raises(LookupError):
                resolve_fiscal_rule(
                    session, "iva.general_rate", date(2026, 1, 1), context
                )
    finally:
        session.close()
        engine.dispose()


def test_curated_fiscal_data_module_is_pure_data_and_never_installs_or_calculates(monkeypatch):
    import aqorath.config as config
    import aqorath.fiscal_rule_data_mx as data
    import aqorath.fiscal_rule_install as installer
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates

    def forbidden(*args, **kwargs):
        raise AssertionError("curated fiscal data module must be pure source data")

    with monkeypatch.context() as m:
        m.setattr(installer, "install_fiscal_rule_set", forbidden)
        m.setattr(storage, "get_session", forbidden)
        m.setattr(tax, "calculate_taxes", forbidden)
        m.setattr(templates, "get_template", forbidden)
        m.setattr(config, "get_accounting_model", forbidden)
        data = importlib.reload(data)
        assert data.MX_GENERAL_COMMERCIAL_IVA.entries[0].value == Decimal("0.16")

    importlib.reload(data)
