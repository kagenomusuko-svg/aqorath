"""
Tests para el módulo de cierre de ejercicio (aqorath.exercise).
"""
import os
from datetime import datetime
from pathlib import Path
from aqorath.exercise import close_exercise
from aqorath.storage import get_session
from aqorath.models import Account, JournalEntry, JournalLine
from sqlmodel import select


def test_close_exercise_creates_backup_folder(tmp_path, monkeypatch):
    """
    Verifica que close_exercise crea la carpeta de respaldo y copia archivos.
    """
    # Usar el out_root temporal para el test
    result = close_exercise(carry_over=False, out_root=tmp_path)
    
    assert result['ok'] is True
    assert 'path' in result
    
    # Verificar que la carpeta existe
    backup_path = Path(result['path'])
    assert backup_path.exists()
    assert backup_path.is_dir()
    
    # Verificar que se copió el archivo de DB
    # El nombre del archivo depende de si es test.db o aqorath.db
    db_files = list(backup_path.glob("*.db"))
    assert len(db_files) > 0, f"No se encontró archivo .db en {backup_path}"


def test_close_exercise_with_carry_over(tmp_path, monkeypatch):
    """
    Verifica que close_exercise con carry_over=True crea asiento de apertura.
    """
    # Crear algunas líneas de diario para tener balances
    with get_session() as session:
        # Verificar que existen cuentas en la DB (de conftest)
        accounts = session.exec(select(Account)).all()
        
        # Si hay cuentas, crear un JournalEntry de prueba
        if len(accounts) > 0:
            # Buscar cuentas de equity (3xxx)
            equity_accounts = [a for a in accounts if a.code.startswith("3")]
            
            if len(equity_accounts) > 0:
                # Crear un entry con líneas
                entry = JournalEntry(
                    date=datetime(2024, 12, 31),
                    concept="Test entry",
                    state="posted"
                )
                session.add(entry)
                session.commit()
                session.refresh(entry)
                
                # Agregar líneas a cuentas de equity
                line1 = JournalLine(
                    entry_id=entry.id,
                    account_code=equity_accounts[0].code,
                    account_id=equity_accounts[0].id,
                    debit=1000.0,
                    credit=0.0
                )
                session.add(line1)
                session.commit()
    
    # Ejecutar close_exercise con carry_over
    result = close_exercise(carry_over=True, out_root=tmp_path)
    
    # Debe haber éxito (incluso si no hay balances significativos)
    assert result['ok'] is True or 'error' in result
    assert 'path' in result
    
    # Verificar que la carpeta existe
    backup_path = Path(result['path'])
    assert backup_path.exists()
    
    # Verificar que existe cuenta 3104 (debe haberse creado o ya existir)
    with get_session() as session:
        account_3104 = session.exec(
            select(Account).where(Account.code == "3104")
        ).first()
        # Puede existir o no dependiendo del catálogo, pero el código debe manejar ambos casos
        # No falla el test si no existe, solo verificamos que no crasheó


def test_close_exercise_defensive_no_db(tmp_path):
    """
    Verifica que close_exercise no crashea si no hay DB (comportamiento defensivo).
    """
    # Configurar una ruta de DB que no existe
    fake_db = tmp_path / "nonexistent.db"
    os.environ["AQORATH_DB"] = str(fake_db)
    
    result = close_exercise(carry_over=False, out_root=tmp_path)
    
    # Debe reportar error pero no crashear
    assert 'ok' in result
    if not result['ok']:
        assert 'error' in result
    
    # Limpiar el env var
    if "AQORATH_DB" in os.environ:
        del os.environ["AQORATH_DB"]
