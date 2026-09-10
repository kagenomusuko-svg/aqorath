from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


PROFESSIONAL_ACTIVITY = "business_consulting_professional_service"


def _session(tmp_path):
    from aqorath import fiscal_rule_data_mx as data
    from aqorath.account_bindings import set_account_binding
    from aqorath.entity import Entity, EntityProfile, FiscalProfile
    from aqorath.entity_repository import create_entity, register_fiscal_profile
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.models import Account
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party

    engine = create_engine(f"sqlite:///{tmp_path / 'aqr011-operation.db'}")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    entity = create_entity(
        session,
        Entity(
            id=None,
            name="Entidad de prueba AQR-011",
            rfc="MER260101AB1",
            legal_personality="persona_moral",
            legal_form="sociedad civil",
            profile=EntityProfile(
                economic_purpose="no_lucrativo",
                is_donor_authorized=False,
                special_capabilities=(),
                modules_enabled=(),
            ),
            is_active=True,
        ),
    )
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    register_fiscal_profile(
        session,
        FiscalProfile(
            id=None,
            entity_id=entity.id,
            jurisdiction="MX",
            fiscal_regime_code="603",
            tax_characteristics=(),
            effective_from=date(2026, 1, 1),
            effective_to=None,
        ),
    )
    pf_party = create_third_party(
        session,
        ThirdParty(
            None, entity.id, "Proveedor PF", "COSC8001137NA", None, None,
            "supplier", None, None, None, True,
        ),
    )
    pm_party = create_third_party(
        session,
        ThirdParty(
            None, entity.id, "Proveedor PM", "AAA010101AAA", None, None,
            "supplier", None, None, None, True,
        ),
    )

    accounts = (
        Account(code="1102", name="Caja chica", nature="DEBIT"),
        Account(code="1101", name="Bancos", nature="DEBIT"),
        Account(code="1182", name="IVA pendiente de acreditar", nature="DEBIT"),
        Account(code="2080", name="IVA trasladado", nature="CREDIT"),
        Account(code="2160", name="ISR retenido a terceros", nature="CREDIT"),
        Account(code="2170", name="IVA retenido a terceros", nature="CREDIT"),
        Account(code="4101", name="Ventas al contado", nature="CREDIT"),
        Account(code="5303", name="Servicios profesionales", nature="DEBIT"),
        Account(code="5105", name="Transporte y mensajería", nature="DEBIT"),
    )
    session.add_all(accounts)
    session.commit()

    bindings = {
        "cash": "1102",
        "bank": "1101",
        "vat_pending_credit": "1182",
        "tax_payable": "2080",
        "isr_withholding_payable": "2160",
        "vat_withholding_payable": "2170",
        "sales_revenue": "4101",
        "professional_services_expense": "5303",
        "freight_expense": "5105",
    }
    for role, code in bindings.items():
        set_account_binding(session, role, code)

    for manifest in (
        data.MX_GENERAL_COMMERCIAL_IVA,
        data.MX_GENERAL_COMMERCIAL_IVA_ZERO,
        data.MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION,
        data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION,
        data.MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_IVA_RETENTION,
        data.MX_RESICO_PERSONA_FISICA_ISR_RETENTION,
    ):
        install_fiscal_rule_set(session, manifest)
    return engine, session, entity, pf_party, pm_party


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
        base=fact.amount,
        effectively_paid=True,
        cfdi_transferred_vat=None,
    )
    values.update(overrides)
    return FiscalV1Facts(**values)


def _lines(snapshot):
    return tuple((line.account_role, line.side, line.amount) for line in snapshot.lines)


def _assert_no_posting(session):
    from aqorath.models import AuditEventRecord, FiscalPostingAuditRecord, JournalEntry, JournalLine

    assert session.exec(select(JournalEntry)).all() == []
    assert session.exec(select(JournalLine)).all() == []
    assert session.exec(select(FiscalPostingAuditRecord)).all() == []
    # ThirdParty creation is not a general AuditEvent in the existing authority.
    assert session.exec(select(AuditEventRecord)).all() == []


def test_prepare_general_sale_uses_existing_pipeline_and_writes_nothing(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, _, _ = _session(tmp_path)
    try:
        fact = EconomicFact("sale", Decimal("1000.00"), "cash")
        prepared = prepare_fiscal_v1_operation(session, _facts(fact))

        assert _lines(prepared.snapshot) == (
            ("cash", "debit", Decimal("1160.00")),
            ("sales_revenue", "credit", Decimal("1000.00")),
            ("tax_payable", "credit", Decimal("160.00")),
        )
        assert prepared.snapshot.provenance.amount_basis == "net_before_fiscal"
        assert prepared.treatments[0].rule_set_version == "2010.1"
        assert "fuente" in prepared.common_explanation[0]
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_prepare_zero_rate_keeps_positive_rule_truth_and_zero_line_for_explicit_omission(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, _, _ = _session(tmp_path)
    try:
        fact = EconomicFact("sale", Decimal("500.00"), "cash")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(fact, activity="own_edited_publication_sale"),
        )
        assert _lines(prepared.snapshot) == (
            ("cash", "debit", Decimal("500.00")),
            ("sales_revenue", "credit", Decimal("500.00")),
            ("tax_payable", "credit", Decimal("0.00")),
        )
        assert prepared.treatments[0].treatment_key == "iva.zero_rate"
        assert prepared.treatments[0].rule.unit == "rate"
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_prepare_professional_general_composes_three_effects_and_exact_settlement(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, pf_party, _ = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(
                fact,
                entity_role="recipient",
                counterparty_legal_personality=None,
                counterparty_fiscal_regime="general",
                activity=PROFESSIONAL_ACTIVITY,
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
            third_party_id=pf_party.id,
        )
        assert prepared.third_party_id == pf_party.id
        assert prepared.facts.counterparty_legal_personality == "persona_fisica"
        assert _lines(prepared.snapshot) == (
            ("professional_services_expense", "debit", Decimal("1000.00")),
            ("bank", "credit", Decimal("953.33")),
            ("vat_pending_credit", "debit", Decimal("160.00")),
            ("isr_withholding_payable", "credit", Decimal("100.00")),
            ("vat_withholding_payable", "credit", Decimal("106.67")),
        )
        assert prepared.snapshot.provenance.amount_basis == "base_before_fiscal_settlement"
        assert [item.treatment_key for item in prepared.treatments] == [
            "iva.general_rate",
            "isr.professional_services_retention_rate",
            "iva.professional_services_retention_fraction",
        ]
        fraction = prepared.treatments[-1]
        assert fraction.rule.value == Decimal("2")
        assert fraction.rule.unit == "fraction_2_3_of_transferred_vat"
        assert prepared.snapshot.provenance.fiscal_effects[-1].rounded_fiscal_amount == Decimal("106.67")
        assert "0.666666" not in prepared.common_explanation[-1]
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_prepare_professional_resico_substitutes_isr_retention_without_integral_regime(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, pf_party, _ = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(
                fact,
                entity_role="recipient",
                counterparty_legal_personality=None,
                counterparty_fiscal_regime="resico",
                activity=PROFESSIONAL_ACTIVITY,
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
            third_party_id=pf_party.id,
        )
        assert _lines(prepared.snapshot) == (
            ("professional_services_expense", "debit", Decimal("1000.00")),
            ("bank", "credit", Decimal("1040.83")),
            ("vat_pending_credit", "debit", Decimal("160.00")),
            ("isr_withholding_payable", "credit", Decimal("12.50")),
            ("vat_withholding_payable", "credit", Decimal("106.67")),
        )
        keys = [item.treatment_key for item in prepared.treatments]
        assert "isr.resico_retention_rate" in keys
        assert "isr.professional_services_retention_rate" not in keys
        assert any("no el ISR integral" in item.explanation for item in prepared.treatments)
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_prepare_freight_composes_vat_pending_and_four_percent_retention(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, _, pm_party = _session(tmp_path)
    try:
        fact = EconomicFact("freight_expense", Decimal("1000.00"), "bank")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(
                fact,
                entity_role="recipient",
                counterparty_legal_personality=None,
                activity="land_freight_goods",
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
            third_party_id=pm_party.id,
        )
        assert prepared.facts.counterparty_legal_personality == "persona_moral"
        assert _lines(prepared.snapshot) == (
            ("freight_expense", "debit", Decimal("1000.00")),
            ("bank", "credit", Decimal("1120.00")),
            ("vat_pending_credit", "debit", Decimal("160.00")),
            ("vat_withholding_payable", "credit", Decimal("40.00")),
        )
        retention = prepared.treatments[1]
        assert retention.treatment_key == "iva.freight_transport_retention_rate"
        assert retention.base == Decimal("1000.00")
        assert retention.exact_amount == Decimal("40.0000")
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_recipient_fiscal_operation_requires_persisted_third_party_and_rfc_controls_personality(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import FiscalV1EvidenceConflict, UnsupportedFiscalV1Case
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, pf_party, _ = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        facts = _facts(
            fact,
            entity_role="recipient",
            counterparty_legal_personality=None,
            counterparty_fiscal_regime="general",
            activity=PROFESSIONAL_ACTIVITY,
            cfdi_transferred_vat=Decimal("160.0000"),
        )
        with pytest.raises(UnsupportedFiscalV1Case, match="ThirdParty persistido"):
            prepare_fiscal_v1_operation(session, facts)
        with pytest.raises(FiscalV1EvidenceConflict, match="RFC persistido"):
            prepare_fiscal_v1_operation(
                session,
                _facts(
                    fact,
                    entity_role="recipient",
                    counterparty_legal_personality="persona_moral",
                    counterparty_fiscal_regime="general",
                    activity=PROFESSIONAL_ACTIVITY,
                    cfdi_transferred_vat=Decimal("160.0000"),
                ),
                third_party_id=pf_party.id,
            )
    finally:
        session.close()
        engine.dispose()


def test_confirm_and_cancel_are_explicit_and_write_nothing(tmp_path):
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import confirm_fiscal_v1_operation, prepare_fiscal_v1_operation

    engine, session, _, _, _ = _session(tmp_path)
    try:
        fact = EconomicFact("sale", Decimal("1000.00"), "cash")
        prepared = prepare_fiscal_v1_operation(session, _facts(fact))
        _assert_no_posting(session)
        confirmed = confirm_fiscal_v1_operation(prepared)
        assert confirmed.prepared is prepared
        assert confirmed.confirmed_proposal.snapshot == prepared.snapshot
        _assert_no_posting(session)
    finally:
        session.close()
        engine.dispose()


def test_execute_professional_is_one_posted_entry_with_fiscal_and_general_audit(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import (
        confirm_fiscal_v1_operation,
        execute_fiscal_v1_operation,
        load_fiscal_v1_operation,
        prepare_fiscal_v1_operation,
    )
    from aqorath.models import AuditEventRecord, FiscalPostingAuditEffectRecord, FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, session, entity, pf_party, _ = _session(tmp_path)
    try:
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(
                fact,
                entity_role="recipient",
                counterparty_legal_personality=None,
                counterparty_fiscal_regime="general",
                activity=PROFESSIONAL_ACTIVITY,
                cfdi_transferred_vat=Decimal("160.0000"),
            ),
            third_party_id=pf_party.id,
        )
        confirmed = confirm_fiscal_v1_operation(prepared)
        session.close()
        monkeypatch.setattr(storage, "get_session", lambda: Session(engine))

        result = execute_fiscal_v1_operation(confirmed)
        with Session(engine) as check:
            entries = check.exec(select(JournalEntry)).all()
            assert len(entries) == 1
            assert entries[0].id == result.entry_id
            assert entries[0].state == "posted"
            assert entries[0].date.date() == date(2026, 9, 10)
            assert len(check.exec(select(JournalLine)).all()) == 5
            assert len(check.exec(select(FiscalPostingAuditRecord)).all()) == 1
            assert len(check.exec(select(FiscalPostingAuditEffectRecord)).all()) == 2
            assert len(check.exec(select(AuditEventRecord)).all()) == 1

            view = load_fiscal_v1_operation(check, entity.id, result.entry_id)
            assert view["coverage_version"] == "mx-fiscal-v1.2026-09-10"
            assert view["entry_state"] == "posted"
            assert view["posting_date"] == "2026-09-10"
            assert view["audit_event_id"] == result.audit_event_id
            assert view["counterparty"]["third_party_id"] == pf_party.id
            assert view["counterparty"]["rfc"] == "COSC8001137NA"
            assert [item["rule_key"] for item in view["treatments"]] == [
                "iva.general_rate",
                "isr.professional_services_retention_rate",
                "iva.professional_services_retention_fraction",
            ]
            assert view["treatments"][0]["account_role"] == "vat_pending_credit"
            assert view["treatments"][1]["rule_set_version"] == "2014.1"
            assert view["treatments"][2]["formula"].startswith("2/3")
            assert view["treatments"][2]["rounded_amount"] == "106.67"
            assert view["fiscal_audit"]["effect_count"] == 3
            assert view["limitations"]
    finally:
        if session.is_active:
            session.close()
        engine.dispose()


def test_execute_zero_rate_omits_zero_line_but_audits_positive_zero_rate_decision(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import confirm_fiscal_v1_operation, execute_fiscal_v1_operation, load_fiscal_v1_operation, prepare_fiscal_v1_operation
    from aqorath.models import JournalLine

    engine, session, entity, _, _ = _session(tmp_path)
    try:
        fact = EconomicFact("sale", Decimal("500.00"), "cash")
        prepared = prepare_fiscal_v1_operation(
            session,
            _facts(fact, activity="own_edited_publication_sale"),
        )
        confirmed = confirm_fiscal_v1_operation(prepared)
        session.close()
        monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
        result = execute_fiscal_v1_operation(confirmed)

        with Session(engine) as check:
            assert len(check.exec(select(JournalLine)).all()) == 2
            view = load_fiscal_v1_operation(check, entity.id, result.entry_id)
            assert view["treatments"][0]["rule_key"] == "iva.zero_rate"
            assert view["treatments"][0]["rounded_amount"] == "0.00"
            assert view["fiscal_audit"]["zero_fiscal_line_policy"] == "omit_confirmed_zero_fiscal_line"
    finally:
        if session.is_active:
            session.close()
        engine.dispose()


def test_aqr011_audit_failure_rolls_back_entry_fiscal_audit_and_general_event(tmp_path, monkeypatch):
    import aqorath.audit_event_repository as audit_repository
    import aqorath.storage as storage
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import confirm_fiscal_v1_operation, execute_fiscal_v1_operation, prepare_fiscal_v1_operation
    from aqorath.models import AuditEventRecord, FiscalPostingAuditEffectRecord, FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, session, _, pf_party, _ = _session(tmp_path)
    fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
    prepared = prepare_fiscal_v1_operation(
        session,
        _facts(
            fact,
            entity_role="recipient",
            counterparty_legal_personality=None,
            counterparty_fiscal_regime="general",
            activity=PROFESSIONAL_ACTIVITY,
            cfdi_transferred_vat=Decimal("160.0000"),
        ),
        third_party_id=pf_party.id,
    )
    confirmed = confirm_fiscal_v1_operation(prepared)
    session.close()
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    monkeypatch.setattr(
        audit_repository,
        "stage_audit_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced AQR-011 audit failure")),
    )
    try:
        with pytest.raises(RuntimeError, match="forced AQR-011 audit failure"):
            execute_fiscal_v1_operation(confirmed)

        with Session(engine) as check:
            assert check.exec(select(JournalEntry)).all() == []
            assert check.exec(select(JournalLine)).all() == []
            assert check.exec(select(FiscalPostingAuditRecord)).all() == []
            assert check.exec(select(FiscalPostingAuditEffectRecord)).all() == []
            assert check.exec(select(AuditEventRecord)).all() == []
    finally:
        engine.dispose()
