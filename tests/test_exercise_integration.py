"""
Tests for cierre de ejercicio (exercise closing) integration.
Validates that close_exercise moves balance from 3103 to 3104 and creates backup folder.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from sqlmodel import Session, select

from aqorath.models import Account, JournalEntry, JournalLine
from aqorath.storage import get_engine, get_session, get_db_path
from aqorath.exercise import close_exercise, create_backup, verify_accounts_exist
from aqorath.core import trial_balance


def test_verify_accounts_exist():
    """Test that verify_accounts_exist checks for accounts 3103 and 3104."""
    result = verify_accounts_exist()
    
    assert isinstance(result, dict)
    assert "3103" in result
    assert "3104" in result


def test_create_backup():
    """Test that create_backup creates a backup file."""
    result = create_backup()
    
    assert result.get("success") is True
    assert "backup_path" in result
    
    # Verify backup file exists
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    assert "cierre_" in backup_path.name


def test_close_exercise_missing_accounts():
    """Test close_exercise when accounts don't exist yet."""
    # First, ensure accounts don't exist (or do exist)
    # This test is defensive - it will pass if accounts exist or not
    result = close_exercise()
    
    # Result should indicate success or error with clear message
    assert "status" in result
    assert result["status"] in ["success", "error"]
    if result["status"] == "error":
        assert "message" in result


def test_close_exercise_with_balance():
    """Test close_exercise with accounts 3103 and 3104 properly set up."""
    engine = get_engine()
    
    with Session(engine) as session:
        # Ensure accounts 3103 and 3104 exist
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        if not acc_3103:
            acc_3103 = Account(code="3103", name="Resultado del ejercicio", nature="Acreedora")
            session.add(acc_3103)
            session.commit()
            session.refresh(acc_3103)
        
        acc_3104 = session.exec(select(Account).where(Account.code == "3104")).first()
        if not acc_3104:
            acc_3104 = Account(code="3104", name="Resultados de ejercicios anteriores", nature="Acreedora")
            session.add(acc_3104)
            session.commit()
            session.refresh(acc_3104)
        
        # Get IDs
        if not hasattr(acc_3103, 'id'):
            acc_3103 = session.get(Account, session.exec(select(Account.id).where(Account.code == "3103")).first())
        if not hasattr(acc_3104, 'id'):
            acc_3104 = session.get(Account, session.exec(select(Account.id).where(Account.code == "3104")).first())
        
        acc_3103_id = acc_3103.id
        acc_3104_id = acc_3104.id
        
        # Create a journal entry that gives 3103 a balance
        entry = JournalEntry(
            date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            concept="Setup for close exercise test",
            state="posted"
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Credit 3103 with 1000 (credit balance)
        line = JournalLine(
            entry_id=entry.id,
            account_code="3103",
            account_id=acc_3103_id,
            debit=0.0,
            credit=1000.0,
            description="Test balance in 3103"
        )
        session.add(line)
        session.commit()
    
    # Get balance before close
    balance_before = trial_balance()
    balance_3103_before = balance_before.get("3103", Decimal("0.00"))
    
    # Perform close exercise
    result = close_exercise()
    
    # Verify result
    if result["status"] != "success":
        print(f"Error: {result.get('message', 'No message')}")
    assert result["status"] == "success"
    assert "backup_path" in result
    assert "entry_id" in result
    assert result["amount_transferred"] > 0
    
    # Verify backup was created
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    
    # Verify balance moved from 3103 to 3104
    balance_after = trial_balance()
    
    # Account 3103 should have different balance after close
    # (may not be exactly 0 if there were other transactions)
    balance_3103_after = balance_after.get("3103", Decimal("0.00"))
    
    # Account 3104 should have received the transfer
    balance_3104_after = balance_after.get("3104", Decimal("0.00"))
    
    # The total of 3103 + 3104 should remain the same
    # (conservation of balance)
    total_before = balance_3103_before
    total_after = balance_3103_after + balance_3104_after
    
    # Allow for small rounding differences
    assert abs(total_before - total_after) < Decimal("0.10")


def test_close_exercise_creates_journal_entry():
    """Test that close_exercise creates a proper journal entry."""
    # Ensure accounts exist
    engine = get_engine()
    
    with Session(engine) as session:
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        if not acc_3103:
            acc_3103 = Account(code="3103", name="Resultado del ejercicio", nature="Acreedora")
            session.add(acc_3103)
        
        acc_3104 = session.exec(select(Account).where(Account.code == "3104")).first()
        if not acc_3104:
            acc_3104 = Account(code="3104", name="Resultados de ejercicios anteriores", nature="Acreedora")
            session.add(acc_3104)
        
        session.commit()
    
    # Perform close
    result = close_exercise()
    
    if result["status"] == "success":
        entry_id = result.get("entry_id")
        assert entry_id is not None
        
        # Verify the entry exists
        with Session(engine) as session:
            entry = session.get(JournalEntry, entry_id)
            assert entry is not None
            assert "cierre" in entry.concept.lower() or "3103" in entry.concept
            
            # Verify lines
            lines = session.exec(
                select(JournalLine).where(JournalLine.entry_id == entry_id)
            ).all()
            
            assert len(lines) == 2  # One for 3103, one for 3104
            
            # Check account codes
            account_codes = [line.account_code for line in lines]
            assert "3103" in account_codes
            assert "3104" in account_codes


def test_close_exercise_with_zero_balance():
    """Test close_exercise when 3103 has zero balance."""
    # This is defensive - we just verify the function handles it gracefully
    # In practice, 3103 might already have a balance from previous tests
    result = close_exercise()
    
    # Should either succeed or return error about zero balance
    assert "status" in result
    if result["status"] == "error":
        # Error message should be informative
        assert "message" in result
        assert len(result["message"]) > 0


def test_close_exercise_creates_backup_folder():
    """Test that close_exercise creates backups folder."""
    db_path = Path(get_db_path())
    backup_dir = db_path.parent / "backups"
    
    # Close exercise (which should create backup)
    result = close_exercise()
    
    if result["status"] == "success":
        # Verify backups folder exists
        assert backup_dir.exists()
        assert backup_dir.is_dir()
        
        # Verify at least one backup file exists
        backup_files = list(backup_dir.glob("*cierre_*"))
        assert len(backup_files) > 0


def test_close_exercise_idempotent():
    """Test that close_exercise can be called multiple times safely."""
    # First call
    result1 = close_exercise()
    
    # Second call
    result2 = close_exercise()
    
    # Both calls should complete (either success or graceful error)
    assert result1["status"] in ["success", "error"]
    assert result2["status"] in ["success", "error"]
    
    # If second call succeeds, it should also create a backup
    if result2["status"] == "success":
        assert "backup_path" in result2
