from datetime import date


def _seed_reporting_data(tmp_path, monkeypatch):
    from test_aqr012_inventory import _purchase, _setup
    from aqorath.inventory_operations import execute_inventory_operation
    from sqlmodel import Session

    engine, entity, supplier, _customer, product, _other = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "2", "10", date(2026, 9, 10)
        )
    execute_inventory_operation(confirmed)
    return engine, entity


def test_preset_surface_crud_reopen_execute_and_delete(tmp_path, monkeypatch):
    from aqorath import report_preset_surface_application as surface

    _engine, _entity = _seed_reporting_data(tmp_path, monkeypatch)
    created = surface.create_report_preset_surface(
        {
            "name": "Consejo mensual",
            "format": "json",
            "reports": [
                {"definition_id": 1301, "parameters": {}},
                {"definition_id": 1304, "parameters": {}},
            ],
        }
    )
    preset_id = created["id"]
    assert created["name"] == "Consejo mensual"
    assert [item["definition_id"] for item in created["reports"]] == [1301, 1304]
    assert surface.list_report_presets_surface() == [created]

    updated = surface.update_report_preset_surface(
        preset_id,
        {
            "name": "Consejo reordenado",
            "format": "json",
            "reports": [
                {"definition_id": 1304, "parameters": {}},
                {"definition_id": 1301, "parameters": {}},
            ],
        },
    )
    assert [item["definition_id"] for item in updated["reports"]] == [1304, 1301]
    assert surface.get_report_preset_surface(preset_id) == updated

    generated = surface.execute_report_preset_surface(
        preset_id, {"from_date": "2026-09-01", "to_date": "2026-09-30"}
    )
    assert generated["preset"] == "Consejo reordenado"
    assert generated["included_reports"] == ["Diario por período", "Balanza por período"]
    trial = generated["document"][1]["content"]
    assert trial["total_debit"] == trial["total_credit"] == "20.00"
    assert "document_base64" not in generated

    professional = surface.professional_report_preset_surface(
        preset_id, {"from_date": "2026-09-01", "to_date": "2026-09-30"}
    )
    assert professional["entity_id"] == _entity.id
    assert [item["definition"]["id"] for item in professional["requests"]] == [1304, 1301]
    assert all(item["source_authorities"] for item in professional["requests"])

    assert surface.delete_report_preset_surface(preset_id) == {
        "preset_id": preset_id,
        "deleted": True,
    }
    assert surface.list_report_presets_surface() == []


def test_controller_exposes_preset_surface_without_own_persistence(monkeypatch):
    import aqorath.presentation_controller as presentation

    calls = []

    class FakePresetSurface:
        @staticmethod
        def list_report_presets_surface():
            calls.append(("list",))
            return [{"id": 7}]

        @staticmethod
        def get_report_preset_surface(preset_id):
            calls.append(("get", preset_id))
            return {"id": preset_id}

        @staticmethod
        def create_report_preset_surface(payload):
            calls.append(("create", payload))
            return {"id": 8}

        @staticmethod
        def update_report_preset_surface(preset_id, payload):
            calls.append(("update", preset_id, payload))
            return {"id": preset_id}

        @staticmethod
        def delete_report_preset_surface(preset_id):
            calls.append(("delete", preset_id))
            return {"preset_id": preset_id, "deleted": True}

        @staticmethod
        def execute_report_preset_surface(preset_id, payload):
            calls.append(("execute", preset_id, payload))
            return {"preset": "X"}

        @staticmethod
        def professional_report_preset_surface(preset_id, payload):
            calls.append(("professional", preset_id, payload))
            return {"preset": {"id": preset_id}}

    monkeypatch.setattr(presentation, "_report_presets", FakePresetSurface)
    controller = presentation.LocalPresentationController()
    assert controller.report_presets() == [{"id": 7}]
    assert controller.report_preset(7) == {"id": 7}
    assert controller.create_report_preset({"name": "X"}) == {"id": 8}
    assert controller.update_report_preset(7, {"name": "Y"}) == {"id": 7}
    assert controller.delete_report_preset(7)["deleted"] is True
    assert controller.execute_report_preset(7, {"from_date": "2026-09-01"}) == {"preset": "X"}
    assert controller.professional_report_preset(7, {}) == {"preset": {"id": 7}}
    assert [item[0] for item in calls] == [
        "list", "get", "create", "update", "delete", "execute", "professional"
    ]


def test_http_preset_handlers_are_thin_delegates_without_testclient(monkeypatch):
    import aqorath.web_surface as web

    class FakeController:
        def report_presets(self):
            return [{"id": 1}]

        def report_preset(self, preset_id):
            return {"id": preset_id}

        def create_report_preset(self, payload):
            return {"created": payload}

        def update_report_preset(self, preset_id, payload):
            return {"updated": preset_id, "payload": payload}

        def delete_report_preset(self, preset_id):
            return {"deleted": preset_id}

        def execute_report_preset(self, preset_id, payload):
            return {"executed": preset_id, "payload": payload}

        def professional_report_preset(self, preset_id, payload):
            return {"professional": preset_id, "payload": payload}

    monkeypatch.setattr(web, "controller", FakeController())
    assert web.report_presets() == [{"id": 1}]
    assert web.report_preset(4) == {"id": 4}
    assert web.create_report_preset({"name": "X"}) == {"created": {"name": "X"}}
    assert web.update_report_preset(4, {"name": "Y"})["updated"] == 4
    assert web.delete_report_preset(4) == {"deleted": 4}
    assert web.execute_report_preset(4, {"from_date": "2026-09-01"})["executed"] == 4
    assert web.professional_report_preset(4, {}) == {"professional": 4, "payload": {}}


def test_common_ui_exposes_human_preset_editor_without_accounting_or_sql_fields():
    from aqorath.web_assets import APP_HTML

    assert 'id="reportPresetFlow"' in APP_HTML
    assert "Mis paquetes de reportes" in APP_HTML
    assert "Guardar paquete" in APP_HTML
    assert "Generar paquete" in APP_HTML
    assert "Ver trazabilidad profesional" in APP_HTML
    assert "data-preset-up" in APP_HTML
    assert "data-preset-down" in APP_HTML
    assert "/api/reports/presets" in APP_HTML
    start = APP_HTML.index('id="reportPresetFlow"')
    end = APP_HTML.index('</div>\n</div></section>', start)
    preset_markup = APP_HTML[start:end]
    for forbidden in ("account_code", "debit", "credit", "Debe", "Haber", "SQL", "sql"):
        assert forbidden not in preset_markup
