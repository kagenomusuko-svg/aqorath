"""
Tests for aqorath.config module.
"""
import json
import tempfile
import os
from pathlib import Path
import pytest

# Import config module
import aqorath.config as config_module
from aqorath.storage import get_session
from aqorath.models import AppConfig
from sqlmodel import select


@pytest.fixture(autouse=True)
def cleanup_accounting_model():
    """Fixture to clean up accounting model config after each test."""
    yield
    # Cleanup: remove accounting_model from DB after test
    try:
        with get_session() as s:
            row = s.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one_or_none()
            if row:
                s.delete(row)
                s.commit()
    except Exception:
        # If cleanup fails, it's okay - next test will overwrite
        pass


def test_set_and_get_accounting_model_db():
    """Test that accounting model can be saved and retrieved from DB."""
    # Set to comercial
    result = config_module.set_accounting_model("comercial")
    assert result is True
    
    # Should be able to retrieve it
    assert config_module.get_accounting_model() == "comercial"
    assert config_module.is_accounting_model_set()
    
    # Change to sin_fines
    result = config_module.set_accounting_model("sin_fines")
    assert result is True
    assert config_module.get_accounting_model() == "sin_fines"
    
    # Verify it's in the DB
    with get_session() as s:
        row = s.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one_or_none()
        assert row is not None
        assert row.value == "sin_fines"


def test_set_empty_accounting_model():
    """Test that setting empty accounting model fails."""
    result = config_module.set_accounting_model("")
    assert result is False
