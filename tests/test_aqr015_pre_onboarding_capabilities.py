"""Regression coverage for the clean-install capabilities handshake.

The Android shell validates /api/capabilities before onboarding. A fresh product
therefore needs a useful capabilities projection even though no active Entity,
third parties or analytical dimensions exist yet.
"""


def _fresh_db(tmp_path, monkeypatch):
    import aqorath.storage as storage

    if storage._engine is not None:
        storage._engine.dispose()
    storage._engine = None
    storage._DB_PATH = None

    db_path = tmp_path / "pre-onboarding-capabilities.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    storage.init_db(str(db_path))
    return db_path


def test_capabilities_are_available_before_first_entity_exists(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)

    from aqorath.presentation_controller import LocalPresentationController

    capabilities = LocalPresentationController().capabilities()

    assert capabilities["entity"] is None
    assert capabilities["third_parties"] == []
    assert capabilities["reporting_dimensions"] == []
    assert capabilities["operations"]
    assert capabilities["fiscal_v1_operations"]
    assert capabilities["reporting"]["definitions"]
    assert capabilities["views"] == ("common", "professional")
