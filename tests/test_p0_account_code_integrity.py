"""
P0-4: account_code INEXISTENTE DEBE SER RECHAZADO

Defecto: Una JournalLine puede persistirse con account_code que no existe en Account.
El asiento está PERFECTO BALANCEADO (Debe=Haber), pero ESTRUCTURALMENTE INVÁLIDO.

Requisito:
  Un account_code que no existe en catálogo NO debe permitirse en persistencia.
  La validación debe ocurrir ANTES de persistencia (o rechazar la transacción).
  Atomicidad: ninguna escritura parcial si la validación falla.
"""

import pytest
from decimal import Decimal
from sqlmodel import select
from aqorath.models import JournalEntry, JournalLine
from aqorath.core import post_entry, _persist_entry


def test_post_rechaza_account_code_inexistente_aunque_asiento_cuadre(env_with_temp_db, session_from_temp_db):
    """
    Verifica que post_entry() (API pública) rechace un asiento con account_code inexistente.
    
    RUTA PÚBLICA: post_entry(entry_dict) → _persist_entry() (delegación)
    
    Caso:
      Asiento PERFECTO algebraicamente:
        Línea 1: account_code="9999-INVALIDA" (NO existe) debit=100
        Línea 2: account_code="1000" (existe) credit=100
      Suma: 100 = 100 ✓
      Estructura: ✗ (código inválido)
      
    Contrato esperado: Rechazo antes de persistencia, sin escritura parcial
    
    Este test DEBE FALLAR porque _verify_accounts() NO valida account_code.
    """
    session = session_from_temp_db
    
    # Contar registros ANTES para verificar atomicidad
    before_entries = len(session.exec(select(JournalEntry)).all())
    before_lines = len(session.exec(select(JournalLine)).all())
    
    # Construir entry dict con account_code inválido
    entry_dict = {
        "description": "Asiento balanceado pero con account_code inválido",
        "lines": [
            {
                "account_code": "9999-INVALIDA",  # NO EXISTE
                "debit": 100.0,
                "credit": 0.0
            },
            {
                "account_code": "1000",  # EXISTE
                "debit": 0.0,
                "credit": 100.0
            }
        ]
    }
    
    # Intenta persistir usando API pública
    result = post_entry(entry_dict)
    
    # Verificar rechazo
    assert not result.get("ok"), (
        f"Asiento con account_code inexistente fue aceptado. "
        f"post_entry() debería rechazar antes de persistencia. "
        f"Resultado: {result}"
    )
    
    # Verificar atomicidad: sin escritura parcial
    after_entries = len(session.exec(select(JournalEntry)).all())
    after_lines = len(session.exec(select(JournalLine)).all())
    
    assert after_entries == before_entries, (
        f"Validación rechazó pero quedó JournalEntry huérfana. "
        f"Antes: {before_entries}, Después: {after_entries}"
    )
    assert after_lines == before_lines, (
        f"Validación rechazó pero quedaron JournalLine parciales. "
        f"Antes: {before_lines}, Después: {after_lines}"
    )


def test_persist_entry_directo_con_codigo_inexistente(env_with_temp_db):
    """
    Verifica que _persist_entry() (ruta interna) también rechace 
    account_code inexistente.
    
    Caso alternativo con múltiples cuentas inválidas.
    Demuestra que la validación de account_code no ocurre.
    """
    entry_dict = {
        "description": "Test P0-4: múltiples códigos inválidos",
        "lines": [
            {
                "account_code": "9999-INVALID-1",
                "debit": 30.0,
                "credit": 0.0
            },
            {
                "account_code": "9999-INVALID-2",
                "debit": 0.0,
                "credit": 30.0
            }
        ]
    }
    
    # Llamar _persist_entry
    result = _persist_entry(entry_dict)
    
    # Comportamiento esperado: rechazo
    # Comportamiento actual: aceptación (BUG)
    assert not result.get("ok"), (
        f"_persist_entry() aceptó asiento con códigos inválidos. "
        f"Resultado: {result}. "
        f"_verify_accounts() no valida account_code inexistente."
    )
