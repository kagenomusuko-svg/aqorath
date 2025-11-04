"""
Cierre de ejercicio (fiscal year-end closing) functionality.
Transfers net income (3103) to retained earnings (3104).
"""
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Tuple

from sqlmodel import select

from .storage import get_session, get_db_path
from .models import Account, JournalEntry, JournalLine
from .core import trial_balance


def close_exercise(year: int, concept: str = None) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Close fiscal year by transferring net income (3103) to retained earnings (3104).
    
    This is an irreversible operation that:
    1. Computes the balance of account 3103 (Resultado del ejercicio)
    2. Creates a journal entry to zero out 3103
    3. Transfers the amount to 3104 (Resultados acumulados)
    
    Args:
        year: Fiscal year to close
        concept: Optional concept/description for the closing entry
    
    Returns:
        Tuple of (success: bool, message: str, details: dict)
    """
    # Get trial balance to find 3103 balance
    tb = trial_balance()
    balances = tb.get("balances", {})
    
    balance_3103 = balances.get("3103", Decimal("0.00"))
    
    if balance_3103 == Decimal("0.00"):
        return False, "No hay saldo en cuenta 3103 (Resultado del ejercicio) para transferir.", {}
    
    # Check that accounts 3103 and 3104 exist in account table
    with get_session() as session:
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        acc_3104 = session.exec(select(Account).where(Account.code == "3104")).first()
        
        if not acc_3103:
            return False, "Error: Cuenta 3103 (Resultado del ejercicio) no existe en el catálogo. Por favor, agregue esta cuenta antes de cerrar el ejercicio.", {}
        
        if not acc_3104:
            return False, "Error: Cuenta 3104 (Resultados acumulados) no existe en el catálogo. Por favor, agregue esta cuenta antes de cerrar el ejercicio.", {}
    
    # Prepare closing entry
    if concept is None:
        concept = f"Cierre del ejercicio {year}"
    
    closing_date = datetime(year, 12, 31, tzinfo=timezone.utc)
    
    # Determine debit/credit based on balance
    # If 3103 has negative balance (credit > debit), it's a profit: debit 3103, credit 3104
    # If 3103 has positive balance (debit > credit), it's a loss: credit 3103, debit 3104
    
    if balance_3103 < 0:
        # Profit: balance is negative (more credits than debits)
        # Debit 3103 to zero it out, Credit 3104 to accumulate
        amount_to_transfer = abs(balance_3103)
        line_3103_debit = float(amount_to_transfer)
        line_3103_credit = 0.0
        line_3104_debit = 0.0
        line_3104_credit = float(amount_to_transfer)
    else:
        # Loss: balance is positive (more debits than credits)
        # Credit 3103 to zero it out, Debit 3104
        amount_to_transfer = abs(balance_3103)
        line_3103_debit = 0.0
        line_3103_credit = float(amount_to_transfer)
        line_3104_debit = float(amount_to_transfer)
        line_3104_credit = 0.0
    
    # Create journal entry using SQLModel or sqlite fallback
    try:
        # Try SQLModel approach
        with get_session() as session:
            entry = JournalEntry(
                date=closing_date,
                concept=concept,
                state="posted",
                posted_by="system"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            
            # Create lines
            line1 = JournalLine(
                entry_id=entry.id,
                account_code="3103",
                account_id=acc_3103.id,
                debit=line_3103_debit,
                credit=line_3103_credit,
                description="Cierre: transferencia de resultado del ejercicio"
            )
            
            line2 = JournalLine(
                entry_id=entry.id,
                account_code="3104",
                account_id=acc_3104.id,
                debit=line_3104_debit,
                credit=line_3104_credit,
                description="Cierre: recepción en resultados acumulados"
            )
            
            session.add(line1)
            session.add(line2)
            session.commit()
            
            return True, f"Ejercicio {year} cerrado exitosamente. Monto transferido: {amount_to_transfer}", {
                "entry_id": entry.id,
                "amount": float(amount_to_transfer),
                "balance_3103_before": float(balance_3103),
                "balance_3103_after": 0.0,
                "balance_3104_increase": float(amount_to_transfer)
            }
    
    except Exception as e:
        # Fallback to direct sqlite insertion
        try:
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Insert entry
            cursor.execute("""
                INSERT INTO journalentry (date, concept, state, posted_by, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (closing_date.isoformat(), concept, "posted", "system", datetime.now(timezone.utc).isoformat()))
            entry_id = cursor.lastrowid
            
            # Insert lines
            cursor.execute("""
                INSERT INTO journalline (entry_id, account_code, account_id, debit, credit, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entry_id, "3103", acc_3103.id, line_3103_debit, line_3103_credit, 
                  "Cierre: transferencia de resultado del ejercicio", datetime.now(timezone.utc).isoformat()))
            
            cursor.execute("""
                INSERT INTO journalline (entry_id, account_code, account_id, debit, credit, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entry_id, "3104", acc_3104.id, line_3104_debit, line_3104_credit,
                  "Cierre: recepción en resultados acumulados", datetime.now(timezone.utc).isoformat()))
            
            conn.commit()
            conn.close()
            
            return True, f"Ejercicio {year} cerrado exitosamente (fallback). Monto transferido: {amount_to_transfer}", {
                "entry_id": entry_id,
                "amount": float(amount_to_transfer),
                "balance_3103_before": float(balance_3103),
                "balance_3103_after": 0.0,
                "balance_3104_increase": float(amount_to_transfer)
            }
        
        except Exception as fallback_error:
            return False, f"Error al cerrar ejercicio: {fallback_error}", {}


def finish_exercise(year: int, user_confirmed: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Finish/close fiscal year with user confirmation.
    This is the main entry point that should be called from UI.
    
    Shows warning and requires confirmation before proceeding.
    
    Args:
        year: Fiscal year to close
        user_confirmed: Whether user has confirmed the operation
    
    Returns:
        Tuple of (success: bool, message: str, details: dict)
    """
    if not user_confirmed:
        warning = (
            f"ADVERTENCIA: Está a punto de cerrar el ejercicio {year}.\n\n"
            "Esta operación:\n"
            "1. Transferirá el saldo de la cuenta 3103 (Resultado del ejercicio) "
            "a la cuenta 3104 (Resultados acumulados)\n"
            "2. Es IRREVERSIBLE una vez confirmada\n"
            "3. Debe realizarse solo una vez por ejercicio\n\n"
            "Asegúrese de haber:\n"
            "- Revisado todos los asientos del ejercicio\n"
            "- Generado los reportes necesarios\n"
            "- Realizado un respaldo de la base de datos\n\n"
            "¿Desea continuar?"
        )
        return False, warning, {"requires_confirmation": True}
    
    # User confirmed, proceed with closing
    return close_exercise(year)


# Alias for backward compatibility
def close_fiscal_year(year: int) -> Tuple[bool, str, Dict[str, Any]]:
    """Alias for close_exercise for backward compatibility."""
    return close_exercise(year)
