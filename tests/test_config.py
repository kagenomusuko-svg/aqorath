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


def test_set_and_get_accounting_model_db():
    """Test that accounting model can be saved and retrieved from DB."""
    # Initially may or may not be set depending on other tests
    # Let's just test that we can set and get
    
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
    
    # Clean up for other tests
    with get_session() as s:
        row = s.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one_or_none()
        if row:
            s.delete(row)
            s.commit()


def test_set_empty_accounting_model():
    """Test that setting empty accounting model fails."""
    result = config_module.set_accounting_model("")
    assert result is False
