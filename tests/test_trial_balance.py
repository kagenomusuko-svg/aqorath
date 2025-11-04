"""
Tests for trial_balance API.
Verifies that trial_balance computes correct balances.
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlmodel import select

from aqorath.core import trial_balance
from aqorath.models import Account, JournalEntry, JournalLine
from aqorath.storage import get_session


def test_trial_balance_empty():
    """Test trial_balance structure with any entries."""
    result = trial_balance()
    assert "balances" in result
    assert isinstance(result["balances"], dict)
    assert "total_debit" in result
    assert "total_credit" in result
    # Can't assert empty since tests may share DB - just verify structure


def test_trial_balance_with_entries():
    """Test trial_balance computes correct balances from journal entries."""
    with get_session() as session:
        # Get balance before adding test entry
        result_before = trial_balance()
        balance_1000_before = result_before["balances"].get("1000", Decimal("0.00"))
        balance_3103_before = result_before["balances"].get("3103", Decimal("0.00"))
        
        # Create test accounts if they don't exist
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        if not acc_3103:
            acc_3103 = Account(code="3103", name="Resultado del ejercicio", nature="Acreedora")
            session.add(acc_3103)
            session.commit()
        
        # Create a journal entry
        entry = JournalEntry(
            date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            concept="Test entry for trial balance",
            state="posted"
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Add lines: debit 1000 = 1000, credit 3103 = 1000
        line1 = JournalLine(
            entry_id=entry.id,
            account_code="1000",
            debit=1000.0,
            credit=0.0,
            description="Test debit"
        )
        line2 = JournalLine(
            entry_id=entry.id,
            account_code="3103",
            debit=0.0,
            credit=1000.0,
            description="Test credit"
        )
        session.add(line1)
        session.add(line2)
        session.commit()
        
        # Compute trial balance after
        result_after = trial_balance()
        
        # Check structure
        assert "balances" in result_after
        assert "total_debit" in result_after
        assert "total_credit" in result_after
        
        # Check balances increased by our entry
        balances_after = result_after["balances"]
        assert "1000" in balances_after
        assert "3103" in balances_after
        
        # 1000 should have increased by 1000
        assert balances_after["1000"] == balance_1000_before + Decimal("1000.00")
        
        # 3103 should have decreased by 1000 (credit increases negative balance)
        assert balances_after["3103"] == balance_3103_before - Decimal("1000.00")


def test_trial_balance_3103_with_modelos_libro():
    """
    Test that trial_balance for account 3103 works correctly.
    This test creates entries and verifies the balance changes appropriately.
    """
    from decimal import Decimal
    
    with get_session() as session:
        # Get balance before
        result_before = trial_balance()
        balance_3103_before = result_before["balances"].get("3103", Decimal("0.00"))
        
        # Ensure account 3103 exists
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        if not acc_3103:
            acc_3103 = Account(code="3103", name="Resultado del ejercicio", nature="Acreedora")
            session.add(acc_3103)
            session.commit()
        
        # Create entry with 3103
        entry = JournalEntry(
            date=datetime(2024, 6, 30, tzinfo=timezone.utc),
            concept="Test for 3103",
            state="posted"
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Credit 3103 with 5000
        line = JournalLine(
            entry_id=entry.id,
            account_code="3103",
            debit=0.0,
            credit=5000.0,
            description="Earnings"
        )
        session.add(line)
        session.commit()
    
    # Get trial balance after
    result_after = trial_balance()
    balance_3103_after = result_after["balances"].get("3103", Decimal("0.00"))
    
    # Balance should have decreased by 5000 (credit increases negative balance)
    assert balance_3103_after == balance_3103_before - Decimal("5000.00")
    
    # Note: Full integration with modelos.libro.compute_balance would require
    # loading data into Libro and comparing, which is beyond this unit test scope.
    # The key assertion here is that trial_balance correctly computes from DB.


def test_trial_balance_as_of_date():
    """Test trial_balance with as_of parameter filters by date."""
    with get_session() as session:
        # Create entries on different dates
        entry1 = JournalEntry(
            date=datetime(2024, 1, 10, tzinfo=timezone.utc),
            concept="Early entry",
            state="posted"
        )
        session.add(entry1)
        session.commit()
        session.refresh(entry1)
        
        line1 = JournalLine(
            entry_id=entry1.id,
            account_code="1100",
            debit=500.0,
            credit=0.0
        )
        session.add(line1)
        
        entry2 = JournalEntry(
            date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            concept="Late entry",
            state="posted"
        )
        session.add(entry2)
        session.commit()
        session.refresh(entry2)
        
        line2 = JournalLine(
            entry_id=entry2.id,
            account_code="1100",
            debit=300.0,
            credit=0.0
        )
        session.add(line2)
        session.commit()
        
        # Get balance as of mid-year (should only include entry1)
        result_mid = trial_balance(as_of=datetime(2024, 6, 30, tzinfo=timezone.utc))
        balance_mid = result_mid["balances"].get("1100", Decimal("0.00"))
        
        # Get balance as of end of year (should include both)
        result_end = trial_balance(as_of=datetime(2024, 12, 31, tzinfo=timezone.utc))
        balance_end = result_end["balances"].get("1100", Decimal("0.00"))
        
        # Verify filtering works
        assert balance_mid == Decimal("500.00")
        assert balance_end == Decimal("800.00")
