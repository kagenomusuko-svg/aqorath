from sqlmodel import Session, select


PROFESSIONAL_ACTIVITY_KEY = "professional_service_paid"


def _surface_runtime(tmp_path, monkeypatch):
    from test_aqr011_fiscal_v1_operation import _session
    import aqorath.storage as storage

    engine, session, entity, pf_party, pm_party = _session(tmp_path)
    session.close()
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    return engine, entity, pf_party, pm_party


def test_controller_exposes_factual_fiscal_v1_operations_without_tax_selectors(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController

    engine, _, _, _ = _surface_runtime(tmp_path, monkeypatch)
    try:
        controller = LocalPresentationController()
        capabilities = controller.capabilities()
        keys = {item["key"] for item in capabilities["fiscal_v1_operations"]}
        assert keys == {
            "sale_general_paid",
            "sale_own_publication_paid",
            "professional_service_paid",
            "freight_goods_paid",
        }
        serialized = str(capabilities["fiscal_v1_operations"])
        assert "rule_key" not in serialized
        assert "rate" not in serialized.lower()
    finally:
        engine.dispose()


def test_common_prepare_is_non_persistent_and_professional_preview_exposes_provenance(tmp_path, monkeypatch):
    from aqorath.models import JournalEntry
    from aqorath.presentation_controller import LocalPresentationController

    engine, _, _, _ = _surface_runtime(tmp_path, monkeypatch)
    try:
        controller = LocalPresentationController()
        response = controller.prepare_fiscal_v1({
            "operation_key": "sale_general_paid",
            "amount": "1000.00",
            "operation_date": "2026-09-10",
        })
        common = response["preview"]
        assert common["coverage_version"] == "mx-fiscal-v1.2026-09-10"
        assert common["base"] == "1000.00"
        assert common["treatments"][0]["amount"] == "160.00"
        assert "account_role" not in str(common)
        assert "side" not in str(common)
        with Session(engine) as session:
            assert session.exec(select(JournalEntry)).all() == []

        professional = controller.professional_preview(response["token"])
        assert professional["treatments"][0]["rule_key"] == "iva.general_rate"
        assert professional["treatments"][0]["rounded_amount"] == "160.00"
        assert professional["accounting"] == [
            {"account_role": "cash", "side": "debit", "amount": "1160.00"},
            {"account_role": "sales_revenue", "side": "credit", "amount": "1000.00"},
            {"account_role": "tax_payable", "side": "credit", "amount": "160.00"},
        ]
        assert controller.cancel(response["token"]) == {"cancelled": True}
        with Session(engine) as session:
            assert session.exec(select(JournalEntry)).all() == []
    finally:
        engine.dispose()


def test_confirm_posts_same_truth_and_professional_read_reconstructs_it(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController

    engine, _, _, _ = _surface_runtime(tmp_path, monkeypatch)
    try:
        controller = LocalPresentationController()
        prepared = controller.prepare_fiscal_v1({
            "operation_key": "sale_own_publication_paid",
            "amount": "500.00",
            "operation_date": "2026-09-10",
        })
        result = controller.confirm(prepared["token"])
        assert result["state"] == "posted"
        assert result["coverage_version"] == "mx-fiscal-v1.2026-09-10"
        assert result["cfdi_source_link_id"] is None

        professional = controller.professional_fiscal_v1(result["entry_id"])
        assert professional["coverage_version"] == "mx-fiscal-v1.2026-09-10"
        assert professional["treatments"][0]["rule_key"] == "iva.zero_rate"
        assert professional["treatments"][0]["rounded_amount"] == "0.00"
        assert professional["entry_state"] == "posted"
    finally:
        engine.dispose()


def test_paid_professional_service_uses_persisted_third_party_authority(tmp_path, monkeypatch):
    from aqorath.presentation_controller import LocalPresentationController

    engine, _, pf_party, _ = _surface_runtime(tmp_path, monkeypatch)
    try:
        controller = LocalPresentationController()
        response = controller.prepare_fiscal_v1({
            "operation_key": PROFESSIONAL_ACTIVITY_KEY,
            "amount": "1000.00",
            "operation_date": "2026-09-10",
            "third_party_id": pf_party.id,
            "counterparty_fiscal_regime": "general",
        })
        professional = controller.professional_preview(response["token"])
        assert professional["facts"]["counterparty_legal_personality"] == "persona_fisica"
        assert professional["third_party_id"] == pf_party.id
        assert [item["rule_key"] for item in professional["treatments"]] == [
            "iva.general_rate",
            "isr.professional_services_retention_rate",
            "iva.professional_services_retention_fraction",
        ]
        result = controller.confirm(response["token"])
        read = controller.professional_fiscal_v1(result["entry_id"])
        assert read["counterparty"]["third_party_id"] == pf_party.id
        assert read["facts"]["effectively_paid"] is True
    finally:
        engine.dispose()
