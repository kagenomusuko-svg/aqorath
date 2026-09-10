from pathlib import Path
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from test_aqr011_fiscal_v1_operation import (
    PROFESSIONAL_ACTIVITY,
    _facts,
    _session,
)


PROFESSIONAL_CFDI = Path(__file__).parent / "fixtures" / "cfdi40_professional_general.xml"


def _prepared_with_cfdi(tmp_path):
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, entity, pf_party, _ = _session(tmp_path)
    imported = import_cfdi_source(session, PROFESSIONAL_CFDI.read_bytes())
    fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
    prepared = prepare_fiscal_v1_operation(
        session,
        _facts(
            fact,
            entity_role="recipient",
            counterparty_legal_personality=None,
            counterparty_fiscal_regime=None,
            activity=PROFESSIONAL_ACTIVITY,
            cfdi_transferred_vat=None,
        ),
        cfdi_source_id=imported.source.id,
    )
    return engine, session, entity, pf_party, imported.source, prepared


def test_prepare_cfdi_uses_persisted_party_regime_and_tax_evidence_without_posting(tmp_path):
    from aqorath.models import DocumentReferenceRecord, JournalEntry

    engine, session, _, pf_party, source, prepared = _prepared_with_cfdi(tmp_path)
    try:
        assert prepared.third_party_id == pf_party.id
        assert prepared.cfdi_source_id == source.id
        assert prepared.cfdi_source_uuid == source.parsed.uuid
        assert prepared.cfdi_source_hash == source.parsed.sha256
        assert prepared.facts.counterparty_legal_personality == "persona_fisica"
        assert prepared.facts.counterparty_fiscal_regime == "general"
        assert prepared.facts.cfdi_transferred_vat == Decimal("160.00")
        assert [item.treatment_key for item in prepared.treatments] == [
            "iva.general_rate",
            "isr.professional_services_retention_rate",
            "iva.professional_services_retention_fraction",
        ]
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_execute_cfdi_fiscal_operation_links_same_entry_and_single_document_atomically(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.cfdi_models import CfdiSourceLinkRecord
    from aqorath.fiscal_v1_operation import (
        confirm_fiscal_v1_operation,
        execute_fiscal_v1_operation,
        load_fiscal_v1_operation,
    )
    from aqorath.models import (
        AuditEventRecord,
        CfdiImportMetadataRecord,
        DocumentReferenceRecord,
        FiscalPostingAuditEffectRecord,
        FiscalPostingAuditRecord,
        JournalEntry,
        JournalLine,
    )

    engine, session, entity, pf_party, source, prepared = _prepared_with_cfdi(tmp_path)
    confirmed = confirm_fiscal_v1_operation(prepared)
    session.close()
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    try:
        result = execute_fiscal_v1_operation(confirmed)
        assert result.cfdi_source_link_id is not None
        assert result.document_reference_id is not None

        with Session(engine) as check:
            entries = check.exec(select(JournalEntry)).all()
            assert len(entries) == 1
            assert entries[0].id == result.entry_id
            lines = check.exec(select(JournalLine)).all()
            assert len(lines) == 5
            assert any(
                Decimal(line.credit) == Decimal("953.33")
                for line in lines
            )
            assert len(check.exec(select(FiscalPostingAuditRecord)).all()) == 1
            assert len(check.exec(select(FiscalPostingAuditEffectRecord)).all()) == 2

            links = check.exec(select(CfdiSourceLinkRecord)).all()
            documents = check.exec(select(DocumentReferenceRecord)).all()
            metadata = check.exec(select(CfdiImportMetadataRecord)).all()
            assert len(links) == 1
            assert len(documents) == 1
            assert len(metadata) == 1
            assert links[0].id == result.cfdi_source_link_id
            assert links[0].cfdi_source_id == source.id
            assert links[0].document_reference_id == result.document_reference_id
            assert documents[0].entry_id == result.entry_id
            assert documents[0].third_party_id == pf_party.id
            assert metadata[0].document_reference_id == documents[0].id

            events = check.exec(select(AuditEventRecord)).all()
            assert [event.event_type for event in events] == [
                "cfdi_source_imported",
                "entry_posted",
                "cfdi_source_linked",
            ]
            view = load_fiscal_v1_operation(check, entity.id, result.entry_id)
            assert view["counterparty"]["third_party_id"] == pf_party.id
            assert view["cfdi_source"]["cfdi_source_id"] == source.id
            assert view["cfdi_source"]["uuid"] == source.parsed.uuid
            assert view["facts"]["cfdi_transferred_vat"] == "160.00"
    finally:
        engine.dispose()


def test_late_cfdi_link_failure_rolls_back_fiscal_posting_but_preserves_prior_import(tmp_path, monkeypatch):
    import aqorath.fiscal_v1_operation as operation
    import aqorath.storage as storage
    from aqorath.cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
    from aqorath.fiscal_v1_operation import confirm_fiscal_v1_operation, execute_fiscal_v1_operation
    from aqorath.models import (
        AuditEventRecord,
        CfdiImportMetadataRecord,
        DocumentReferenceRecord,
        FiscalPostingAuditEffectRecord,
        FiscalPostingAuditRecord,
        JournalEntry,
        JournalLine,
    )

    engine, session, _, _, source, prepared = _prepared_with_cfdi(tmp_path)
    confirmed = confirm_fiscal_v1_operation(prepared)
    session.close()
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    monkeypatch.setattr(
        operation._cfdi_sources,
        "stage_cfdi_source_link",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced AQR-011 CFDI link failure")),
    )
    try:
        with pytest.raises(RuntimeError, match="forced AQR-011 CFDI link failure"):
            execute_fiscal_v1_operation(confirmed)

        with Session(engine) as check:
            assert len(check.exec(select(CfdiSourceRecord)).all()) == 1
            assert check.get(CfdiSourceRecord, source.id) is not None
            assert check.exec(select(JournalEntry)).all() == []
            assert check.exec(select(JournalLine)).all() == []
            assert check.exec(select(FiscalPostingAuditRecord)).all() == []
            assert check.exec(select(FiscalPostingAuditEffectRecord)).all() == []
            assert check.exec(select(CfdiSourceLinkRecord)).all() == []
            assert check.exec(select(DocumentReferenceRecord)).all() == []
            assert check.exec(select(CfdiImportMetadataRecord)).all() == []
            events = check.exec(select(AuditEventRecord)).all()
            assert len(events) == 1
            assert events[0].event_type == "cfdi_source_imported"
    finally:
        engine.dispose()


def test_cfdi_third_party_or_regime_contradiction_fails_before_accounting(tmp_path):
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_v1_coverage import FiscalV1EvidenceConflict
    from aqorath.fiscal_v1_operation import prepare_fiscal_v1_operation

    engine, session, _, _, pm_party = _session(tmp_path)
    try:
        imported = import_cfdi_source(session, PROFESSIONAL_CFDI.read_bytes())
        fact = EconomicFact("professional_services_expense", Decimal("1000.00"), "bank")
        common = _facts(
            fact,
            entity_role="recipient",
            counterparty_legal_personality=None,
            counterparty_fiscal_regime="resico",
            activity=PROFESSIONAL_ACTIVITY,
            cfdi_transferred_vat=None,
        )
        with pytest.raises(FiscalV1EvidenceConflict, match="ThirdParty seleccionado"):
            prepare_fiscal_v1_operation(
                session,
                common,
                third_party_id=pm_party.id,
                cfdi_source_id=imported.source.id,
            )
        with pytest.raises(FiscalV1EvidenceConflict, match="régimen indicado"):
            prepare_fiscal_v1_operation(
                session,
                common,
                cfdi_source_id=imported.source.id,
            )
    finally:
        session.close()
        engine.dispose()
