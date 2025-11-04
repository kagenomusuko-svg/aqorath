"""
Módulo para operaciones de fin de ejercicio (cierre fiscal).
Implementa respaldo de la DB y traslado de saldos a reservas patrimoniales.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Defensive imports: wrap in try/except to handle missing dependencies gracefully
try:
    from sqlmodel import select
    from aqorath.storage import get_session, get_db_path
    from aqorath.models import Account, JournalEntry, JournalLine
    SQLMODEL_AVAILABLE = True
except Exception:
    SQLMODEL_AVAILABLE = False


def close_exercise(carry_over: bool = True, out_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Cierra el ejercicio fiscal creando respaldo de la DB y opcionalmente
    trasladando saldos a la cuenta 3104 (Reservas patrimoniales).
    
    Args:
        carry_over: Si True, crea asiento de apertura trasladando saldos a 3104
        out_root: Directorio raíz donde crear carpeta de respaldo. 
                 Si None, usa ~/.local/share/aqorath/ejercicios/
    
    Returns:
        Dict con:
        - 'ok': bool indicando éxito
        - 'path': str con ruta de la carpeta de respaldo
        - 'error': str con mensaje de error si ok=False
    """
    try:
        # 1. Crear carpeta de destino
        if out_root is None:
            out_root = Path.home() / ".local" / "share" / "aqorath" / "ejercicios"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_folder = out_root / timestamp
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        # 2. Copiar archivo de DB
        try:
            if SQLMODEL_AVAILABLE:
                db_path = get_db_path()
            else:
                # Fallback si storage no está disponible
                db_path = os.environ.get("AQORATH_DB", "datos/aqorath.db")
                if not os.path.exists(db_path):
                    db_path = "tests/test.db"
            
            db_file = Path(db_path)
            if db_file.exists():
                shutil.copy2(db_file, dest_folder / db_file.name)
            else:
                return {
                    'ok': False,
                    'error': f'Archivo de DB no encontrado: {db_path}',
                    'path': str(dest_folder)
                }
        except Exception as e:
            return {
                'ok': False,
                'error': f'Error al copiar DB: {str(e)}',
                'path': str(dest_folder)
            }
        
        # 3. Copiar catálogo si existe
        try:
            # Buscar catalogo_base.json en diferentes ubicaciones posibles
            catalog_paths = [
                Path("aqorath/data/catalogo_base.json"),
                Path(__file__).parent / "data" / "catalogo_base.json",
            ]
            for cat_path in catalog_paths:
                if cat_path.exists():
                    shutil.copy2(cat_path, dest_folder / "catalogo_base.json")
                    break
        except Exception as e:
            # No crítico si no se puede copiar el catálogo
            pass
        
        # 4. Carry-over (traslado a reservas patrimoniales)
        if carry_over:
            if not SQLMODEL_AVAILABLE:
                return {
                    'ok': False,
                    'error': 'SQLModel no disponible para operaciones de carry-over',
                    'path': str(dest_folder)
                }
            
            try:
                with get_session() as session:
                    # 4.1 Verificar/crear cuenta 3104
                    account_3104 = session.exec(
                        select(Account).where(Account.code == "3104")
                    ).first()
                    
                    if not account_3104:
                        # Crear cuenta 3104 si no existe (debe estar en catálogo)
                        account_3104 = Account(
                            code="3104",
                            name="Reservas patrimoniales",
                            nature="CREDIT"
                        )
                        session.add(account_3104)
                        session.commit()
                        session.refresh(account_3104)
                    
                    # 4.2 Calcular saldos de cuentas patrimoniales (equity: 3000-3999)
                    # Simplificación: computar balance neto de todas las líneas de diario
                    # Balance = sum(debit) - sum(credit) por cuenta
                    # Para cuentas de capital/equity (3xxx): queremos el saldo neto
                    
                    # Obtener todas las líneas de diario
                    all_lines = session.exec(select(JournalLine)).all()
                    
                    # Agrupar por account_code y sumar debits - credits
                    balances = {}
                    for line in all_lines:
                        code = line.account_code
                        if code:
                            if code not in balances:
                                balances[code] = 0.0
                            balances[code] += line.debit - line.credit
                    
                    # Filtrar cuentas de equity (3000-3999) excepto 3104
                    equity_balance = 0.0
                    for code, balance in balances.items():
                        try:
                            code_int = int(code)
                            if 3000 <= code_int < 4000 and code != "3104":
                                equity_balance += balance
                        except ValueError:
                            continue
                    
                    # 4.3 Crear JournalEntry de apertura
                    if abs(equity_balance) > 0.01:  # Solo si hay saldo significativo
                        entry = JournalEntry(
                            date=datetime.now(),
                            concept="Apertura ejercicio - traslado a reservas patrimoniales",
                            doc_ref=f"CIERRE_{timestamp}",
                            state="posted",
                            posted_by="system"
                        )
                        session.add(entry)
                        session.commit()
                        session.refresh(entry)
                        
                        # Crear líneas de diario: transferir equity_balance a 3104
                        # Si equity_balance > 0 (debe), creditamos 3104 y debitamos cuenta de ajuste
                        # Si equity_balance < 0 (haber), debitamos 3104 y creditamos cuenta de ajuste
                        
                        # Línea 1: 3104 recibe el saldo (acreditar si positivo, debitar si negativo)
                        line1 = JournalLine(
                            entry_id=entry.id,
                            account_code="3104",
                            account_id=account_3104.id,
                            debit=abs(equity_balance) if equity_balance < 0 else 0.0,
                            credit=abs(equity_balance) if equity_balance > 0 else 0.0,
                            description="Traslado saldo ejercicio anterior"
                        )
                        session.add(line1)
                        
                        # Línea 2: Contrapartida (usar cuenta 3103 - Resultado del ejercicio como balancing)
                        # Buscar cuenta 3103 para contrapartida
                        account_3103 = session.exec(
                            select(Account).where(Account.code == "3103")
                        ).first()
                        
                        if not account_3103:
                            # Si no existe 3103, crear o usar una cuenta genérica de equity
                            account_3103 = session.exec(
                                select(Account).where(Account.code.startswith("31"))
                            ).first()
                            if not account_3103:
                                # Fallback: usar la misma 3104 (self-balancing entry - no ideal pero defensivo)
                                account_3103 = account_3104
                        
                        line2 = JournalLine(
                            entry_id=entry.id,
                            account_code=account_3103.code,
                            account_id=account_3103.id,
                            debit=abs(equity_balance) if equity_balance > 0 else 0.0,
                            credit=abs(equity_balance) if equity_balance < 0 else 0.0,
                            description="Contrapartida traslado a reservas"
                        )
                        session.add(line2)
                        
                        session.commit()
            
            except Exception as e:
                return {
                    'ok': False,
                    'error': f'Error en carry-over: {str(e)}',
                    'path': str(dest_folder)
                }
        
        return {
            'ok': True,
            'path': str(dest_folder)
        }
    
    except Exception as e:
        return {
            'ok': False,
            'error': f'Error general: {str(e)}',
            'path': ''
        }
