from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "aqorath/presentation_controller.py",
    "from . import reporting_surface_application as _reporting\nfrom . import surface_application as _application\n",
    "from . import reporting_surface_application as _reporting\nfrom . import report_preset_surface_application as _report_presets\nfrom . import surface_application as _application\n",
)
replace_once(
    "aqorath/presentation_controller.py",
    '''    def reporting_dimensions(self):
        return _reporting.list_reporting_dimensions()

    def generate_financial_reports(self, payload):
''',
    '''    def reporting_dimensions(self):
        return _reporting.list_reporting_dimensions()

    def report_presets(self):
        return _report_presets.list_report_presets_surface()

    def report_preset(self, preset_id):
        return _report_presets.get_report_preset_surface(preset_id)

    def create_report_preset(self, payload):
        return _report_presets.create_report_preset_surface(payload)

    def update_report_preset(self, preset_id, payload):
        return _report_presets.update_report_preset_surface(preset_id, payload)

    def delete_report_preset(self, preset_id):
        return _report_presets.delete_report_preset_surface(preset_id)

    def execute_report_preset(self, preset_id, payload):
        return _report_presets.execute_report_preset_surface(preset_id, payload)

    def professional_report_preset(self, preset_id, payload):
        return _report_presets.professional_report_preset_surface(preset_id, payload)

    def generate_financial_reports(self, payload):
''',
)

replace_once(
    "aqorath/web_surface.py",
    '''@app.get("/api/reports/dimensions")
def reporting_dimensions():
    try:
        return controller.reporting_dimensions()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/financial")
''',
    '''@app.get("/api/reports/dimensions")
def reporting_dimensions():
    try:
        return controller.reporting_dimensions()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/reports/presets")
def report_presets():
    try:
        return controller.report_presets()
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/reports/presets/{preset_id}")
def report_preset(preset_id: int):
    try:
        return controller.report_preset(preset_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/presets")
def create_report_preset(payload: dict):
    try:
        return controller.create_report_preset(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.put("/api/reports/presets/{preset_id}")
def update_report_preset(preset_id: int, payload: dict):
    try:
        return controller.update_report_preset(preset_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.delete("/api/reports/presets/{preset_id}")
def delete_report_preset(preset_id: int):
    try:
        return controller.delete_report_preset(preset_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/presets/{preset_id}/execute")
def execute_report_preset(preset_id: int, payload: dict):
    try:
        return controller.execute_report_preset(preset_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/presets/{preset_id}/professional")
def professional_report_preset(preset_id: int, payload: dict):
    try:
        return controller.professional_report_preset(preset_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/reports/packages/financial")
''',
)
print("preset controller/HTTP wiring applied")
