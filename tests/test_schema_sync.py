"""
Tests for schema sync helper.
Verifies that select(JournalLine) does not raise OperationalError after running the helper.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from aqorath.models import JournalLine, Account, JournalEntry
from aqorath.storage import get_engine


def test_schema_sync_journalline_selectable():
    """
    Test that JournalLine can be selected without OperationalError.
    This verifies the schema is in sync with the model.
    """
    engine = get_engine()
    
    # Try to select from JournalLine - should not raise OperationalError
    with Session(engine) as session:
        try:
            result = session.exec(select(JournalLine)).all()
            # If we get here, the schema is compatible
            assert isinstance(result, list)
        except OperationalError as e:
            pytest.fail(f"OperationalError when selecting JournalLine: {e}")


def test_schema_sync_all_models_selectable():
    """
    Test that all main models can be selected without errors.
    """
    engine = get_engine()
    models = [Account, JournalEntry, JournalLine]
    
    with Session(engine) as session:
        for model in models:
            try:
                result = session.exec(select(model)).all()
                assert isinstance(result, list), f"Expected list for {model.__name__}"
            except OperationalError as e:
                pytest.fail(f"OperationalError when selecting {model.__name__}: {e}")


def test_journalline_basic_crud():
    """
    Test basic CRUD operations on JournalLine to verify schema compatibility.
    """
    engine = get_engine()
    
    with Session(engine) as session:
        # Create a JournalEntry first
        entry = JournalEntry(
            date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            concept="Test entry",
            state="draft"
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Create a JournalLine
        line = JournalLine(
            entry_id=entry.id,
            account_code="1105",
            debit=100.0,
            credit=0.0,
            description="Test line"
        )
        session.add(line)
        session.commit()
        session.refresh(line)
        
        # Verify we can query it back
        result = session.get(JournalLine, line.id)
        
        assert result is not None
        assert result.account_code == "1105"
        assert result.debit == 100.0
        assert result.description == "Test line"
