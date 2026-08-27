"""Phase 5AL.1 — expanded curated Mexican fiscal coverage contracts.

This phase freezes additional source-data coverage only. It deliberately does
not infer applicability from an EconomicFact, counterparty, CFDI, account, or
legacy template. Every manifest remains explicit, reviewable and effective-
dated. Exemption is kept semantically distinct from a 0% rate, and the IVA
"two thirds" withholding is intentionally not approximated with a finite
Decimal because that would violate Aqorath's exact-money/fiscal-truth rules.
"""

from datetime import date
from decimal import Decimal
import importlib

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


ZERO_SOURCE = "DOF:1980-12-30:ART8+TRANSITORIO-PRIMERO;LIVA:ART2-A"
EXEMPT_LAND_SOURCE = "DOF:1978-12-29;LIVA:ART9-I"
FREIGHT_RETENTION_SOURCE = "DOF:2006-12-04;LIVA:ART1-A-II-c;RLIVA:ART3-II"
PROFESSIONAL_ISR_SOURCE = "DOF:2013-12-11;LISR:ART106"
RESICO_ISR_SOURCE = "DOF:2021-11-12;LISR:ART113-J"


def _session(tmp_path, filename="expanded-curated.db"):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / filename}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _single_entry(manifest):
    assert len(manifest.entries) == 1
    return manifest.entries[0]


def test_expanded_curated_mx_public_contract_exists_without_rewriting_phase_5e_legacy_aggregate():
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_set import FiscalRuleSetManifest

    expected = (
        data.MX_GENERAL_COMMERCIAL_IVA,
        data.MX_GENERAL_COMMERCIAL_IVA_ZERO,
        data.MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND,
        data.MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION,
        data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION,
        data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION,
    )

    assert all(isinstance(manifest, FiscalRuleSetManifest) for manifest in expected)
    assert isinstance(data.CURATED_MX_FISCAL_RULE_SETS, tuple)
    assert data.CURATED_MX_FISCAL_RULE_SETS == expected

    # Phase 5E is a frozen historical contract: the old aggregate remains exact.
    assert data.CURATED_FISCAL_RULE_SETS == (data.MX_GENERAL_COMMERCIAL_IVA,)


def test_zero_rate_manifest_is_exact_effective_dated_and_reuses_general_commercial_context():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_GENERAL_COMMERCIAL_IVA_ZERO
    entry = _single_entry(manifest)

    assert manifest.set_key == "mx.general.comercial.iva-zero"
    assert manifest.version == "1981.1"
    assert manifest.context is data.MX_GENERAL_COMMERCIAL_IVA.context
    assert entry.rule_key == "iva.zero_rate"
    assert entry.effective_from == date(1981, 1, 1)
    assert entry.value == Decimal("0.00")
    assert str(entry.value) == "0.00"
    assert entry.unit == "rate"
    assert entry.source_ref == ZERO_SOURCE


def test_exempt_land_manifest_is_not_modeled_as_zero_rate_even_though_amount_factor_is_zero():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND
    entry = _single_entry(manifest)

    assert manifest.set_key == "mx.general.comercial.iva-exempt-land"
    assert manifest.version == "1980.1"
    assert manifest.context is data.MX_GENERAL_COMMERCIAL_IVA.context
    assert entry.rule_key == "iva.exempt.sale.land"
    assert entry.effective_from == date(1980, 1, 1)
    assert entry.value == Decimal("0")
    assert str(entry.value) == "0"
    assert entry.unit == "exempt"
    assert entry.source_ref == EXEMPT_LAND_SOURCE

    zero_entry = _single_entry(data.MX_GENERAL_COMMERCIAL_IVA_ZERO)
    assert zero_entry.rule_key != entry.rule_key
    assert zero_entry.unit == "rate"
    assert entry.unit == "exempt"


def test_exemption_resolves_as_explicit_non_rate_truth_and_rate_calculator_fails_closed(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path, "exempt.db")
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND)
        resolved = resolve_fiscal_rule(
            session,
            "iva.exempt.sale.land",
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND.context,
        )
        assert resolved.value == Decimal("0")
        assert resolved.unit == "exempt"
        assert resolved.source_ref == EXEMPT_LAND_SOURCE
        with pytest.raises(ValueError, match="rule.unit must be 'rate'"):
            calculate_fiscal_rate_amount(Decimal("100.00"), resolved)
    finally:
        session.close()
        engine.dispose()


def test_freight_transport_iva_retention_is_exact_four_percent_for_general_persona_moral_context():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION
    entry = _single_entry(manifest)

    assert manifest.set_key == "mx.general.persona-moral.iva-freight-retention"
    assert manifest.version == "2006.1"
    assert manifest.context.jurisdiction == "MX"
    assert manifest.context.regime == "general"
    assert manifest.context.entity_type == "persona_moral"
    assert entry.rule_key == "iva.freight_transport_retention_rate"
    assert entry.effective_from == date(2006, 12, 5)
    assert entry.value == Decimal("0.04")
    assert str(entry.value) == "0.04"
    assert entry.unit == "rate"
    assert entry.source_ref == FREIGHT_RETENTION_SOURCE


def test_general_professional_isr_retention_manifest_is_exact_ten_percent():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION
    entry = _single_entry(manifest)

    assert manifest.set_key == "mx.general.persona-fisica-profesional.isr-retention"
    assert manifest.version == "2014.1"
    assert manifest.context.jurisdiction == "MX"
    assert manifest.context.regime == "general"
    assert manifest.context.entity_type == "persona_fisica_profesional"
    assert entry.rule_key == "isr.professional_services_retention_rate"
    assert entry.effective_from == date(2014, 1, 1)
    assert entry.value == Decimal("0.10")
    assert str(entry.value) == "0.10"
    assert entry.unit == "rate"
    assert entry.source_ref == PROFESSIONAL_ISR_SOURCE


def test_resico_persona_fisica_isr_retention_manifest_is_exact_one_point_two_five_percent():
    import aqorath.fiscal_rule_data_mx as data

    manifest = data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION
    entry = _single_entry(manifest)

    assert manifest.set_key == "mx.resico.persona-fisica.isr-retention"
    assert manifest.version == "2022.1"
    assert manifest.context.jurisdiction == "MX"
    assert manifest.context.regime == "resico"
    assert manifest.context.entity_type == "persona_fisica"
    assert entry.rule_key == "isr.resico_retention_rate"
    assert entry.effective_from == date(2022, 1, 1)
    assert entry.value == Decimal("0.0125")
    assert str(entry.value) == "0.0125"
    assert entry.unit == "rate"
    assert entry.source_ref == RESICO_ISR_SOURCE


def test_all_expanded_manifests_materialize_and_resolve_exactly_at_their_own_effective_boundary(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path, "all-expanded.db")
    try:
        for manifest in data.CURATED_MX_FISCAL_RULE_SETS:
            registrations = materialize_fiscal_rule_set(manifest)
            assert len(registrations) == len(manifest.entries)
            installed = install_fiscal_rule_set(session, manifest)
            assert len(installed) == len(manifest.entries)

            for entry in manifest.entries:
                resolved = resolve_fiscal_rule(
                    session,
                    entry.rule_key,
                    entry.effective_from,
                    manifest.context,
                )
                assert resolved.rule_key == entry.rule_key
                assert resolved.value.as_tuple() == entry.value.as_tuple()
                assert resolved.unit == entry.unit
                assert resolved.effective_from == entry.effective_from
                assert resolved.source_ref == entry.source_ref
    finally:
        session.close()
        engine.dispose()


def test_expanded_curated_rules_fail_closed_before_authored_coverage_and_in_wrong_context(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import FiscalContext, resolve_fiscal_rule

    new_manifests = data.CURATED_MX_FISCAL_RULE_SETS[1:]
    engine, session = _session(tmp_path, "boundaries.db")
    try:
        for manifest in new_manifests:
            install_fiscal_rule_set(session, manifest)
            entry = _single_entry(manifest)

            with pytest.raises(LookupError):
                resolve_fiscal_rule(
                    session,
                    entry.rule_key,
                    date.fromordinal(entry.effective_from.toordinal() - 1),
                    manifest.context,
                )

            wrong_context = FiscalContext(
                manifest.context.jurisdiction,
                manifest.context.regime,
                manifest.context.entity_type + "_other",
            )
            with pytest.raises(LookupError):
                resolve_fiscal_rule(
                    session,
                    entry.rule_key,
                    entry.effective_from,
                    wrong_context,
                )
    finally:
        session.close()
        engine.dispose()


def test_rate_based_expanded_rules_calculate_exact_decimal_amounts_without_float_conversion(tmp_path):
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.fiscal_calculation import calculate_fiscal_rate_amount
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.fiscal_rules import resolve_fiscal_rule

    expected = {
        "iva.zero_rate": Decimal("0.0000"),
        "iva.freight_transport_retention_rate": Decimal("4.0000"),
        "isr.professional_services_retention_rate": Decimal("10.0000"),
        "isr.resico_retention_rate": Decimal("1.250000"),
    }

    engine, session = _session(tmp_path, "calculations.db")
    try:
        for manifest in data.CURATED_MX_FISCAL_RULE_SETS:
            entry = _single_entry(manifest)
            if entry.unit != "rate" or entry.rule_key == "iva.general_rate":
                continue
            install_fiscal_rule_set(session, manifest)
            resolved = resolve_fiscal_rule(
                session,
                entry.rule_key,
                date(2026, 8, 27),
                manifest.context,
            )
            result = calculate_fiscal_rate_amount(Decimal("100.00"), resolved)
            assert isinstance(result.amount, Decimal)
            assert result.amount.as_tuple() == expected[entry.rule_key].as_tuple()
    finally:
        session.close()
        engine.dispose()


def test_expanded_curated_aggregate_has_exact_reviewable_rule_set_and_preserves_decimal_authorship():
    import aqorath.fiscal_rule_data_mx as data

    entries = [
        entry
        for manifest in data.CURATED_MX_FISCAL_RULE_SETS
        for entry in manifest.entries
    ]
    assert {entry.rule_key for entry in entries} == {
        "iva.general_rate",
        "iva.zero_rate",
        "iva.exempt.sale.land",
        "iva.freight_transport_retention_rate",
        "isr.professional_services_retention_rate",
        "isr.resico_retention_rate",
    }
    assert all(isinstance(entry.value, Decimal) for entry in entries)
    assert all(not isinstance(entry.value, float) for entry in entries)


def test_two_thirds_iva_withholding_is_not_seeded_as_a_fake_finite_decimal_rate():
    import aqorath.fiscal_rule_data_mx as data

    entries = [
        entry
        for manifest in data.CURATED_MX_FISCAL_RULE_SETS
        for entry in manifest.entries
    ]
    forbidden_rule_keys = {
        "iva.personal_services_retention_rate",
        "iva.commission_retention_rate",
        "iva.temporary_use_retention_rate",
        "iva.two_thirds_retention_rate",
    }

    assert forbidden_rule_keys.isdisjoint({entry.rule_key for entry in entries})
    assert all("RLIVA:ART3-I" not in entry.source_ref for entry in entries)
    assert all("2/3" not in entry.source_ref for entry in entries)
    assert all("0.666666" not in str(entry.value) for entry in entries)


def test_expanded_curated_data_module_remains_pure_source_data_on_reload(monkeypatch):
    import aqorath.config as config
    import aqorath.fiscal_rule_data_mx as data
    import aqorath.fiscal_rule_install as installer
    import aqorath.storage as storage
    import aqorath.tax as tax
    import aqorath.templates as templates

    def forbidden(*args, **kwargs):
        raise AssertionError("curated fiscal data module must remain pure source data")

    with monkeypatch.context() as m:
        m.setattr(installer, "install_fiscal_rule_set", forbidden)
        m.setattr(storage, "get_session", forbidden)
        m.setattr(tax, "calculate_taxes", forbidden)
        m.setattr(templates, "get_template", forbidden)
        m.setattr(config, "get_accounting_model", forbidden)
        reloaded = importlib.reload(data)
        assert reloaded.CURATED_MX_FISCAL_RULE_SETS[1].entries[0].value == Decimal("0.00")
        assert reloaded.CURATED_MX_FISCAL_RULE_SETS[-1].entries[0].value == Decimal("0.0125")

    importlib.reload(data)
