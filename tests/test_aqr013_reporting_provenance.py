from contextlib import contextmanager
from datetime import date


def test_fiscal_professional_provenance_uses_current_aqr010_chain(monkeypatch):
    from aqorath import report_product_catalog as catalog
    from aqorath import report_product_runtime as runtime
    from aqorath.report_request import ReportRequest

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(runtime, "_require_active_owner", lambda request, definition: object())
    monkeypatch.setattr(runtime._storage, "get_session", fake_session)
    monkeypatch.setattr(
        runtime._authority_views,
        "build_fiscal_evidence_period_view",
        lambda session, from_date, to_date: (),
    )

    request = ReportRequest(
        id=None,
        report_definition_id=catalog.FISCAL_EVIDENCE_PERIOD.id,
        entity_id=1,
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 30),
        as_of_date=None,
        filters=(),
        dimensions_to_group=(),
        format="json",
    )
    generated = runtime.generate_report(request)

    assert generated.source_authorities == (
        "AQR-011.FiscalPostingAuditRecord",
        "AQR-011.load_fiscal_posting_audit_snapshot",
        "AQR-010.CfdiSourceRecord",
        "AQR-010.CfdiSourceLinkRecord",
        "AQR-010.DocumentReferenceRecord",
    )
    assert "AQR-010.CfdiImportMetadataRecord" not in generated.source_authorities
