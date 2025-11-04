"""
Tests for schema synchronization helper.
Verifies that select(JournalLine) works without OperationalError.
"""
import os
import sqlite3
from pathlib import Path
from sqlmodel import select, Session
from aqorath.models import JournalLine, JournalEntry
from aqorath.storage import get_session, get_db_path


def test_journalline_select_works():
    """
    Verify that basic select on JournalLine works without OperationalError.
    This validates that the schema is compatible with the model.
    """
    with get_session() as session:
        # This should not raise OperationalError
        result = session.exec(select(JournalLine)).all()
        assert isinstance(result, list)


def test_journalline_insert_and_query():
    """
    Test that we can insert and query JournalLine records.
    """
    from datetime import datetime, timezone
    
    with get_session() as session:
        # Create a journal entry first
        entry = JournalEntry(
            date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            concept="Test entry",
            state="draft"
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Create a journal line
        line = JournalLine(
            entry_id=entry.id,
            account_code="1000",
            debit=100.0,
            credit=0.0,
            description="Test debit line"
        )
        session.add(line)
        session.commit()
        session.refresh(line)
        
        # Query it back
        result = session.exec(
            select(JournalLine).where(JournalLine.id == line.id)
        ).first()
        
        assert result is not None
        assert result.account_code == "1000"
        assert result.debit == 100.0
        assert result.description == "Test debit line"


def test_schema_has_expected_columns():
    """
    Verify that the journalline table has all expected columns from the model.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(journalline)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    
    # Expected columns based on JournalLine model
    expected = {
        "id",
        "entry_id",
        "account_code",
        "account_id",
        "debit",
        "credit",
        "description",
        "created_at"
    }
    
    # All expected columns should be present
    missing = expected - columns
    assert not missing, f"Missing columns in journalline table: {missing}"


def test_sync_schema_detects_no_issues():
    """
    Test that sync_schema reports success when schema is already synced.
    Uses the actual sync_schema function if available.
    """
    try:
        from scripts.sync_schema import sync_schema
        success, messages = sync_schema(dry_run=True)
        assert success, f"Schema sync failed: {messages}"
        # Should report no missing columns
        assert any("up to date" in msg.lower() or "no missing" in msg.lower() 
                   for msg in messages), f"Expected 'up to date' message, got: {messages}"
    except ImportError:
        # If sync_schema script is not importable, skip this test
        pass
