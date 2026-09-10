from sqlmodel import Session


def _http_runtime(tmp_path, monkeypatch):
    from test_aqr011_fiscal_v1_operation import _session
    import aqorath.storage as storage
    import aqorath.web_surface as web_surface

    engine, session, entity, pf_party, pm_party = _session(tmp_path)
    session.close()
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    web_surface.controller._pending.clear()
    return engine, web_surface


def test_http_capabilities_feed_supported_fiscal_sales_to_existing_common_ui(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    engine, web_surface = _http_runtime(tmp_path, monkeypatch)
    try:
        client = TestClient(web_surface.app)
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        body = response.json()
        operation_keys = {item["key"] for item in body["operations"]}
        assert "sale_general_paid" in operation_keys
        assert "sale_own_publication_paid" in operation_keys
        assert {item["key"] for item in body["fiscal_v1_operations"]} == {
            "sale_general_paid",
            "sale_own_publication_paid",
            "professional_service_paid",
            "freight_goods_paid",
        }
        assert "rule_key" not in str(body["operations"])
    finally:
        engine.dispose()


def test_http_common_prepare_confirm_posts_aqr011_without_tax_inputs(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    engine, web_surface = _http_runtime(tmp_path, monkeypatch)
    try:
        client = TestClient(web_surface.app)
        prepared = client.post(
            "/api/operations/prepare",
            json={
                "operation_key": "sale_general_paid",
                "amount": "1000.00",
                "posting_date": "2026-09-10",
            },
        )
        assert prepared.status_code == 200
        payload = prepared.json()
        assert payload["preview"]["amount"] == "1000.00"
        assert payload["preview"]["posting_date"] == "2026-09-10"
        assert payload["preview"]["coverage_version"] == "mx-fiscal-v1.2026-09-10"
        assert payload["preview"]["treatments"][0]["amount"] == "160.00"

        professional_preview = client.get(
            f"/api/operations/{payload['token']}/professional-preview"
        )
        assert professional_preview.status_code == 200
        assert professional_preview.json()["treatments"][0]["rule_key"] == "iva.general_rate"

        confirmed = client.post(f"/api/operations/{payload['token']}/confirm")
        assert confirmed.status_code == 200
        result = confirmed.json()
        assert result["state"] == "posted"
        assert result["coverage_version"] == "mx-fiscal-v1.2026-09-10"

        ledger = client.get(f"/api/operations/{result['entry_id']}/professional")
        assert ledger.status_code == 200
        assert ledger.json()["fiscal_audit"] is not None
    finally:
        engine.dispose()


def test_browser_shell_uses_capability_driven_operation_select_and_preview_fields():
    from aqorath.web_assets import APP_HTML

    assert "/api/capabilities" in APP_HTML
    assert "cap.operations" in APP_HTML
    assert "/api/operations/prepare" in APP_HTML
    assert "out.preview.explanation" in APP_HTML
    assert "/professional-preview" in APP_HTML
