from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


PROFESSIONAL_ACTIVITY = "business_consulting_professional_service"


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401
    from aqorath import fiscal_rule_data_mx as data
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine = create_engine(f"sqlite:///{tmp_path / 'aqr011-coverage.db'}")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    for manifest in (
        data.MX_GENERAL_COMMERCIAL_IVA,
        data.MX_GENERAL_COMMERCIAL_IVA_ZERO,
        data.MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION,
        data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION,
        data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_IVA_RETENTION,
        data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION,
    ):
        install_fiscal_rule_set(session, manifest)
    return engine, session


def _facts(fact, **overrides):
    from aqorath.fiscal_v1_coverage import FiscalV1Facts

    values = dict(
        fact=fact,
        operation_date=date(2026, 9, 10),
        entity_role="provider",
        entity_legal_personality="persona_moral",
        counterparty_legal_personality="persona_moral",
        counterparty_fiscal_regime="general",
        activity="ordinary_taxable_sale",
        territory="MX",
        base=Decimal("1000.00"),
        effectively_paid=True,
        cfdi_transferred_vat=None,
    )
    values.update(overrides)
    return FiscalV1Facts(**values)


def test_general_iva_is_positive_fact_gated_versioned_and_not_selected_from_cfdi(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import (
        COVERAGE_VERSION,
        UnsupportedFiscalV1Case,
        resolve_fiscal_v1_treatments,
    )

    engine, session = _session(tmp_path)
    try:
        sale = EconomicFact("sale", Decimal("1000.00"), "cash")
        treatment = resolve_fiscal_v1_treatments(session, _facts(sale))[0]
        assert treatment.coverage_version == COVERAGE_VERSION
        assert treatment.treatment_key == "iva.general_rate"
        assert treatment.rule_set_key == "mx.general.comercial.iva-general"
        assert treatment.rule_set_version == "2010.1"
        assert treatment.rule.value == Decimal("0.16")
        assert treatment.rule.effective_from == date(2010, 1, 1)
        assert "LIVA:ART1" in treatment.rule.source_ref
        assert treatment.base == Decimal("1000.00")
        assert treatment.exact_amount == Decimal("160.0000")
        assert treatment.fiscal_role == "tax_payable"
        assert treatment.fiscal_side == "credit"
        assert "no del CFDI" in treatment.explanation

        utility = EconomicFact("utility_expense", Decimal("1000.00"), "bank")
        with pytest.raises(UnsupportedFiscalV1Case, match="no tiene una regla fiscal V1"):
            resolve_fiscal_v1_treatments(
                session,
                _facts(
                    utility,
                    entity_role="recipient",
                    activity="ordinary_taxable_sale",
                    cfdi_transferred_vat=Decimal("160.00"),
                ),
            )
    finally:
        session.close()
        engine.dispose()


def test_zero_rate_is_positive_own_edited_publication_treatment_not_fallback_or_exemption(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case, resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        sale = EconomicFact("sale", Decimal("500.00"), "cash")
        treatment = resolve_fiscal_v1_treatments(
            session,
            _facts(
                sale,
                activity="own_edited_publication_sale",
                base=Decimal("500.00"),
                cfdi_transferred_vat=Decimal("0"),
            ),
        )[0]
        assert treatment.treatment_key == "iva.zero_rate"
        assert treatment.rule_set_version == "1981.1"
        assert treatment.rule.unit == "rate"
        assert treatment.rule.value == Decimal("0.00")
        assert treatment.exact_amount == Decimal("0.0000")
        assert treatment.treatment_key != "iva.exempt.sale.land"
        assert "2-A" in treatment.explanation

        with pytest.raises(UnsupportedFiscalV1Case):
            _facts(sale, activity="land_sale")
    finally:
        session.close()
        engine.dispose()


def test_freight_retention_uses_four_percent_of_paid_consideration_not_vat(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        fact = EconomicFact("freight_expense", Decimal("1000.00"), "bank")
        treatments = resolve_fiscal_v1_treatments(
            session,
            _facts(
                fact,
                entity_role="recipient",
                entity_legal_personality="persona_moral",
                counterparty_legal_personality="persona_moral",
                activity="land_freight_goods",
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
        )
        by_key = {item.treatment_key: item for item in treatments}
        assert by_key["iva.general_rate"].exact_amount == Decimal("160.0000")
        assert by_key["iva.general_rate"].fiscal_role == "vat_pending_credit"
        assert "no certifica su acreditamiento" in by_key["iva.general_rate"].explanation
        retention = by_key["iva.freight_transport_retention_rate"]
        assert retention.base == Decimal("1000.00")
        assert retention.rule.value == Decimal("0.04")
        assert retention.rule_set_version == "2006.1"
        assert retention.exact_amount == Decimal("40.0000")
        assert retention.formula == "base × 0.04"
        assert "contraprestación" in retention.explanation
    finally:
        session.close()
        engine.dispose()


def test_persona_fisica_freight_requires_regime_before_resico_can_be_excluded(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case, resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        fact = EconomicFact("freight_expense", Decimal("1000.00"), "bank")
        with pytest.raises(UnsupportedFiscalV1Case, match="régimen"):
            resolve_fiscal_v1_treatments(
                session,
                _facts(
                    fact,
                    entity_role="recipient",
                    counterparty_legal_personality="persona_fisica",
                    counterparty_fiscal_regime=None,
                    activity="land_freight_goods",
                ),
            )
    finally:
        session.close()
        engine.dispose()


def test_professional_consulting_keeps_iva_isr_and_two_thirds_retention_separate(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        treatments = resolve_fiscal_v1_treatments(
            session,
            _facts(
                fact,
                entity_role="recipient",
                entity_legal_personality="persona_moral",
                counterparty_legal_personality="persona_fisica",
                counterparty_fiscal_regime="general",
                activity=PROFESSIONAL_ACTIVITY,
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
        )
        assert [item.treatment_key for item in treatments] == [
            "iva.general_rate",
            "isr.professional_services_retention_rate",
            "iva.professional_services_retention_fraction",
        ]
        assert treatments[0].exact_amount == Decimal("160.0000")
        assert treatments[0].fiscal_role == "vat_pending_credit"
        assert treatments[1].exact_amount == Decimal("100.0000")
        two_thirds = treatments[2]
        assert two_thirds.rule.value == Decimal("2")
        assert two_thirds.rule.unit == "fraction_2_3_of_transferred_vat"
        assert two_thirds.rule_set_version == "2006.1"
        assert two_thirds.base == Decimal("160.0000")
        assert two_thirds.formula.startswith("2/3")
        assert "0.666666" not in str(two_thirds.rule.value)
        assert two_thirds.exact_amount.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) == Decimal("106.67")
    finally:
        session.close()
        engine.dispose()


def test_generic_professional_label_is_not_a_taxable_v1_conclusion(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case

    fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
    with pytest.raises(UnsupportedFiscalV1Case, match="no tiene una regla fiscal V1"):
        _facts(
            fact,
            entity_role="recipient",
            counterparty_legal_personality="persona_fisica",
            counterparty_fiscal_regime="general",
            activity="professional_service",
        )


def test_resico_professional_service_is_only_one_point_two_five_withholding_not_integral_isr(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        treatments = resolve_fiscal_v1_treatments(
            session,
            _facts(
                fact,
                entity_role="recipient",
                counterparty_legal_personality="persona_fisica",
                counterparty_fiscal_regime="resico",
                activity=PROFESSIONAL_ACTIVITY,
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
        )
        keys = [item.treatment_key for item in treatments]
        assert "isr.resico_retention_rate" in keys
        assert "isr.professional_services_retention_rate" not in keys
        resico = next(
            item for item in treatments if item.treatment_key == "isr.resico_retention_rate"
        )
        assert resico.rule.value == Decimal("0.0125")
        assert resico.rule_set_version == "2022.1"
        assert resico.exact_amount == Decimal("12.500000")
        assert "no el ISR integral" in resico.explanation
    finally:
        session.close()
        engine.dispose()


def test_coverage_dates_are_deterministic_and_fail_closed_outside_reviewed_window(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case, resolve_fiscal_v1_treatments

    engine, session = _session(tmp_path)
    try:
        sale = EconomicFact("sale", Decimal("100.00"), "cash")
        for boundary in (date(2026, 1, 1), date(2026, 9, 10)):
            result = resolve_fiscal_v1_treatments(
                session,
                _facts(sale, operation_date=boundary, base=Decimal("100.00")),
            )
            assert result[0].exact_amount == Decimal("16.0000")
        for outside in (date(2025, 12, 31), date(2026, 9, 11)):
            with pytest.raises(UnsupportedFiscalV1Case, match="fuera de la ventana"):
                resolve_fiscal_v1_treatments(
                    session,
                    _facts(sale, operation_date=outside, base=Decimal("100.00")),
                )
    finally:
        session.close()
        engine.dispose()


def test_professional_context_must_be_accredited_and_documentary_divergence_stops(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import (
        FiscalV1EvidenceConflict,
        UnsupportedFiscalV1Case,
        resolve_fiscal_v1_treatments,
    )

    engine, session = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        common = dict(
            entity_role="recipient",
            counterparty_legal_personality="persona_fisica",
            activity=PROFESSIONAL_ACTIVITY,
        )
        with pytest.raises(UnsupportedFiscalV1Case, match="Falta acreditar"):
            resolve_fiscal_v1_treatments(
                session,
                _facts(fact, counterparty_fiscal_regime=None, **common),
            )
        with pytest.raises(FiscalV1EvidenceConflict, match="DETECT.*STOP"):
            resolve_fiscal_v1_treatments(
                session,
                _facts(
                    fact,
                    counterparty_fiscal_regime="general",
                    cfdi_transferred_vat=Decimal("159.99"),
                    **common,
                ),
            )
    finally:
        session.close()
        engine.dispose()


def test_new_professional_and_freight_facts_are_accounting_semantics_not_tax_logic():
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    professional = resolve_economic_fact(
        EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
    )
    freight = resolve_economic_fact(
        EconomicFact("freight_expense", Decimal("800.00"), "bank")
    )
    assert [(line.account_role, line.side, line.amount) for line in professional.lines] == [
        ("professional_services_expense", "debit", Decimal("1000.00")),
        ("bank", "credit", Decimal("1000.00")),
    ]
    assert [(line.account_role, line.side, line.amount) for line in freight.lines] == [
        ("freight_expense", "debit", Decimal("800.00")),
        ("bank", "credit", Decimal("800.00")),
    ]
    assert "IVA" not in professional.explanation
    assert "4%" not in freight.explanation
