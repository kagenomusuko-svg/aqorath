"""
P1-2 REGRESSION TESTS: Configuration must read/write to SQLite, not JSON fallback.

P1-2: Lectura de config: DEBE venir de SQLite, no JSON fallback.
P1-2: Escritura de config: DEBE ir a SQLite, no JSON fallback.
"""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select
from aqorath.models import AppConfig
import aqorath.config as config
from unittest.mock import patch
import json


def test_accounting_model_reads_sqlite_not_json_fallback(tmp_path, monkeypatch):
    """
    P1-2: get_accounting_model debe leer de SQLite, no JSON.

    ESTADO ACTUAL: EXPECTED FAIL
    - AppConfig.select() no existe en SQLModel
    - Cae a JSON fallback
    - Lee valor "sin_fines" en lugar de "comercial" de SQLite

    CONTRATO FUTURO:
    - Lee de SQLite: "comercial"
    - Ignora JSON conflictivo
    """
    import aqorath.storage as storage

    # Setup SQLite with AppConfig (engine temporal)
    db_file = tmp_path / "config_read_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Insert value into SQLite via ORM
    with Session(engine) as session:
        cfg = AppConfig(key="accounting_model", value="comercial")
        session.add(cfg)
        session.commit()

    # Create conflicting JSON fallback
    json_file = tmp_path / "fallback_config.json"
    json_file.write_text(json.dumps({"accounting_model": "sin_fines"}))

    # Configure environment
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    # Isolate storage.get_session to use temporary engine
    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(storage, "get_session", isolated_get_session)

    # Patch fallback path
    with patch("aqorath.config.FALLBACK_PATH", json_file):
        result = config.get_accounting_model()

    # FUTURE CONTRACT: SQLite wins (comercial)
    # CURRENT STATE: JSON fallback wins (sin_fines)
    # because AppConfig.select() fails, falls back to JSON
    assert result == "comercial", (
        f"P1-2 Config read authority: expected 'comercial' from SQLite, got '{result}'"
    )


def test_accounting_model_write_uses_sqlite_without_json_fallback(tmp_path, monkeypatch):
    """
    P1-2: set_accounting_model debe escribir en SQLite, no JSON.

    ESTADO ACTUAL: EXPECTED FAIL
    - AppConfig.select() no existe
    - Intenta JSON fallback

    CONTRATO FUTURO:
    - Escribe en SQLite
    - Verifiable por ORM
    - JSON NO es utilizado
    """
    import aqorath.storage as storage

    # Setup SQLite (engine temporal)
    db_file = tmp_path / "config_write_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Create dummy JSON that should NOT be used
    json_file = tmp_path / "fallback_config.json"
    json_file.write_text(json.dumps({}))

    monkeypatch.setenv("AQORATH_DB", str(db_file))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    # Isolate storage.get_session to use temporary engine
    def isolated_get_session():
        return Session(engine)

    monkeypatch.setattr(storage, "get_session", isolated_get_session)

    # Track if fallback file write is called
    fallback_called = [False]

    def fake_write_fallback(value):
        fallback_called[0] = True
        return True

    # Patch the fallback write function
    with patch("aqorath.config.FALLBACK_PATH", json_file):
        with patch("aqorath.config._write_fallback_file", side_effect=fake_write_fallback):
            result = config.set_accounting_model("comercial")

    # Verify operation completed
    assert result is True, "set_accounting_model failed"

    # FUTURE CONTRACT: Value is in SQLite, NOT in JSON fallback
    # CURRENT STATE: AppConfig.select() fails, writes to JSON instead
    with Session(engine) as session:
        configs = session.exec(
            select(AppConfig).where(AppConfig.key == "accounting_model")
        ).all()

        if not configs:
            pytest.fail(
                f"P1-2 Config write: value NOT in SQLite; fallback_called={fallback_called[0]}"
            )

        assert configs[0].value == "comercial", (
            f"P1-2 Config write: SQLite has '{configs[0].value}', expected 'comercial'"
        )
