"""
Exercise closing (cierre de ejercicio) functionality.

Handles the year-end closing process:
1. Transfer balance from account 3103 (Resultado del ejercicio) to 3104
2. Create backup of database
3. Create journal entries for the transfer
"""
import os
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

from sqlalchemy import select, text
from sqlmodel import Session

from .models import Account, JournalEntry, JournalLine
from .storage import get_engine, get_db_path, get_session
from .core import trial_balance


def close_exercise() -> Dict[str, Any]:
    """
    Perform end-of-year closing (cierre del ejercicio).
    
    Steps:
    1. Get balance from account 3103 (Resultado del ejercicio)
    2. Verify accounts 3103 and 3104 exist
    3. Create database backup
    4. Create journal entry to transfer balance from 3103 to 3104
    
    Returns:
        Dict with status, message, backup_path, entry_id, and amount_transferred
    """
    try:
        # Get trial balance
        balance = trial_balance()
        
        if "3103" not in balance:
            return {
                "status": "error",
                "message": "Cuenta 3103 (Resultado del ejercicio) no encontrada en el balance."
            }
        
        # Get the balance (remember our convention: negative = credit)
        balance_3103 = Decimal(str(balance.get("3103", 0)))
        
        if balance_3103 == Decimal("0.00"):
            return {
                "status": "error",
                "message": "La cuenta 3103 no tiene saldo. No es necesario cerrar el ejercicio."
            }
        
        # Verify accounts exist and get their IDs
        with get_session() as session:
            acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
            acc_3104 = session.exec(select(Account).where(Account.code == "3104")).first()
            
            if not acc_3103:
                return {
                    "status": "error",
                    "message": "Cuenta 3103 (Resultado del ejercicio) no existe en la tabla de cuentas."
                }
            
            if not acc_3104:
                return {
                    "status": "error",
                    "message": "Cuenta 3104 no existe en la tabla de cuentas. "
                              "Por favor, cree esta cuenta antes de cerrar el ejercicio."
                }
            
            # Get proper Account objects with IDs
            if not hasattr(acc_3103, 'id'):
                acc_3103 = session.get(Account, session.exec(select(Account.id).where(Account.code == "3103")).first())
            if not hasattr(acc_3104, 'id'):
                acc_3104 = session.get(Account, session.exec(select(Account.id).where(Account.code == "3104")).first())
            
            acc_3103_id = acc_3103.id
            acc_3104_id = acc_3104.id
        
        # Create backup
        backup_result = create_backup()
        if not backup_result.get("success"):
            return {
                "status": "error",
                "message": f"Error al crear respaldo: {backup_result.get('message', 'Error desconocido')}"
            }
        
        # Create journal entry for transfer
        entry_result = create_transfer_entry(balance_3103, acc_3103_id, acc_3104_id)
        
        if entry_result.get("success"):
            return {
                "status": "success",
                "message": "Cierre del ejercicio completado exitosamente.",
                "backup_path": backup_result.get("backup_path"),
                "entry_id": entry_result.get("entry_id"),
                "amount_transferred": float(abs(balance_3103))
            }
        else:
            return {
                "status": "error",
                "message": f"Error al crear asiento de transferencia: {entry_result.get('message')}"
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error inesperado durante el cierre del ejercicio: {str(e)}"
        }


def create_backup() -> Dict[str, Any]:
    """
    Create a backup of the database before closing exercise.
    
    Returns:
        Dict with success status, backup_path, and optional message
    """
    try:
        db_path = Path(get_db_path())
        
        if not db_path.exists():
            return {
                "success": False,
                "message": "Base de datos no encontrada."
            }
        
        # Create backups directory
        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{db_path.stem}_cierre_{timestamp}{db_path.suffix}"
        backup_path = backup_dir / backup_filename
        
        # Copy database file
        shutil.copy2(str(db_path), str(backup_path))
        
        return {
            "success": True,
            "backup_path": str(backup_path)
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


def create_transfer_entry(balance_3103: Decimal, acc_3103_id: int, acc_3104_id: int) -> Dict[str, Any]:
    """
    Create journal entry to transfer balance from 3103 to 3104.
    
    If balance_3103 is negative (credit), we need to:
    - Debit 3103 to close it
    - Credit 3104 to transfer the result
    
    Args:
        balance_3103: Current balance of account 3103 (negative = credit)
        acc_3103_id: ID of account 3103
        acc_3104_id: ID of account 3104
    
    Returns:
        Dict with success status, entry_id, and optional message
    """
    try:
        with get_session() as session:
            # Create journal entry
            entry = JournalEntry(
                date=datetime.now(timezone.utc),
                concept="Cierre del ejercicio - Transferencia 3103 a 3104",
                doc_ref="CIERRE_AUTO",
                state="posted",
                posted_by="system"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            
            # Determine debit/credit amounts
            # If balance_3103 is negative (credit balance), we debit 3103 and credit 3104
            # If balance_3103 is positive (debit balance), we credit 3103 and debit 3104
            amount_abs = abs(balance_3103)
            
            if balance_3103 < 0:
                # Credit balance in 3103 -> debit 3103, credit 3104
                debit_3103 = float(amount_abs)
                credit_3103 = 0.0
                debit_3104 = 0.0
                credit_3104 = float(amount_abs)
            else:
                # Debit balance in 3103 -> credit 3103, debit 3104
                debit_3103 = 0.0
                credit_3103 = float(amount_abs)
                debit_3104 = float(amount_abs)
                credit_3104 = 0.0
            
            # Create line for 3103
            line_3103 = JournalLine(
                entry_id=entry.id,
                account_code="3103",
                account_id=acc_3103_id,
                debit=debit_3103,
                credit=credit_3103,
                description="Cierre del ejercicio - Cerrar cuenta 3103"
            )
            session.add(line_3103)
            
            # Create line for 3104
            line_3104 = JournalLine(
                entry_id=entry.id,
                account_code="3104",
                account_id=acc_3104_id,
                debit=debit_3104,
                credit=credit_3104,
                description="Cierre del ejercicio - Transferir a 3104"
            )
            session.add(line_3104)
            
            session.commit()
            
            return {
                "success": True,
                "entry_id": entry.id
            }
    
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


def verify_accounts_exist() -> Dict[str, bool]:
    """
    Verify that accounts 3103 and 3104 exist in the database.
    
    Returns:
        Dict with keys "3103" and "3104" indicating if each account exists
    """
    with get_session() as session:
        acc_3103 = session.exec(select(Account).where(Account.code == "3103")).first()
        acc_3104 = session.exec(select(Account).where(Account.code == "3104")).first()
        
        return {
            "3103": acc_3103 is not None,
            "3104": acc_3104 is not None
        }
