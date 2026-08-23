"""
P0-3: trial_balance(as_of) DEBE RESPETAR FECHA DE CORTE

Defecto: La función trial_balance(as_of=...) recibe el parámetro pero no lo usa.
Incluye TODOS los movimientos, ignorando la fecha de corte.

Requisito:
  trial_balance(as_of="2026-03-31") debe incluir SOLO movimientos hasta esa fecha
  Movimientos posteriores (ej: 2026-04-15) NO deben incluirse
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from aqorath.models import JournalEntry, JournalLine, Account
from aqorath.core import trial_balance


def test_trial_balance_as_of_excluye_movimientos_posteriores(
    setup_accounts_in_session, 
    env_with_temp_db
):
    """
    Verifica que trial_balance(as_of=fecha) excluya movimientos posteriores.
    
    AISLADO DE P0-1: Solo compara saldos algebraicos en la misma cuenta.
    
    Caso:
      Movimiento A: 2026-03-15, debit=100 en cuenta 1000
      Movimiento B: 2026-04-15, credit=50 en cuenta 1000
      
      trial_balance() sin as_of:
        Saldo 1000 = 100 - 50 = +50 (ambos movimientos)
      
      trial_balance(as_of="2026-03-31"):
        Saldo 1000 DEBERÍA ser = 100 - 0 = +100 (solo marzo, excluir abril)
        
      Si retorna +50 (igual que sin as_of), es porque as_of es IGNORADO.
    
    Este test DEBE FALLAR hoy porque as_of no se implementó.
    """
    session = setup_accounts_in_session
    db_path = env_with_temp_db
    
    # Ambos movimientos en la MISMA cuenta para demostrar aislamiento
    # Movimiento A: 2026-03-15
    entry_a = JournalEntry(
        date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        concept="Movimiento marzo",
        state="posted"
    )
    session.add(entry_a)
    session.flush()
    
    line_a = JournalLine(
        entry_id=entry_a.id,
        account_code="1000",  # Bancos
        debit=100.0,
        credit=0.0
    )
    session.add(line_a)
    
    # Movimiento B: 2026-04-15
    entry_b = JournalEntry(
        date=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
        concept="Movimiento abril",
        state="posted"
    )
    session.add(entry_b)
    session.flush()
    
    line_b = JournalLine(
        entry_id=entry_b.id,
        account_code="1000",  # Misma cuenta
        debit=0.0,
        credit=50.0
    )
    session.add(line_b)
    
    session.commit()
    
    # Sin as_of (referencia)
    balances_all = trial_balance()
    saldo_all = balances_all.get("1000", Decimal("0"))
    
    # Con as_of="2026-03-31" (fecha de corte)
    balances_as_of_march = trial_balance(as_of="2026-03-31")
    saldo_as_of = balances_as_of_march.get("1000", Decimal("0"))
    
    # Contrato explícito:
    # Sin as_of: incluye AMBOS movimientos (marzo 100, abril -50) = +50
    # Con as_of=2026-03-31: incluye SOLO marzo (100 - 0) = +100
    
    assert saldo_all == Decimal("50"), (
        f"Sin as_of debe retornar saldo completo = 100 (marzo) - 50 (abril) = 50. "
        f"Actual: {saldo_all}"
    )
    
    assert saldo_as_of == Decimal("100"), (
        f"Con as_of=2026-03-31 debe retornar saldo solo hasta marzo = 100 - 0 = 100. "
        f"Actual: {saldo_as_of}. "
        f"Esto demuestra que as_of está siendo IGNORADO."
    )


def test_trial_balance_sin_as_of_incluye_todos_los_movimientos(
    setup_accounts_in_session,
    env_with_temp_db
):
    """
    Verifica que trial_balance() SIN as_of incluya TODOS los movimientos.
    
    AISLADO DE P0-1: Solo verifica presencia/ausencia, NO normalización.
    
    Caso:
      Movimiento A: 2026-03-15, debit=100 en cuenta 1000
      Movimiento B: 2026-04-15, credit=50 en cuenta 1000
      
      trial_balance() sin parámetro DEBE retornar el saldo completo
      incluyendo AMBOS movimientos:
      Saldo algebraico: 100 (marzo) - 50 (abril) = +50
    
    Este test DEBE PASAR actualmente — demuestra baseline.
    """
    session = setup_accounts_in_session
    db_path = env_with_temp_db
    
    # Ambos movimientos en la MISMA cuenta para aislamiento
    # Movimiento A: 2026-03-15
    entry_a = JournalEntry(
        date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        concept="Movimiento marzo",
        state="posted"
    )
    session.add(entry_a)
    session.flush()
    
    line_a = JournalLine(
        entry_id=entry_a.id,
        account_code="1000",  # Bancos
        debit=100.0,
        credit=0.0
    )
    session.add(line_a)
    
    # Movimiento B: 2026-04-15
    entry_b = JournalEntry(
        date=datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc),
        concept="Movimiento abril",
        state="posted"
    )
    session.add(entry_b)
    session.flush()
    
    line_b = JournalLine(
        entry_id=entry_b.id,
        account_code="1000",  # Misma cuenta
        debit=0.0,
        credit=50.0
    )
    session.add(line_b)
    
    session.commit()
    
    try:
        # Sin parámetro as_of
        balances_all = trial_balance()
        
        saldo_1000 = balances_all.get("1000", Decimal("0"))
        
        # Saldo algebraico esperado: 100 (debit) - 50 (credit) = +50
        # Este test DEBE PASAR porque no hay ningún problema con trial_balance()
        # sin parámetro. Solo falla si as_of está en la firma pero no implementado.
        assert saldo_1000 == Decimal("50"), (
            f"trial_balance() sin as_of debería incluir ambos movimientos. "
            f"Saldo 1000: {saldo_1000}, esperado: 50 "
            f"(100 debit en marzo - 50 credit en abril). "
            f"Este test DEBE PASAR — demuestra que trial_balance() base funciona."
        )
    except Exception as e:
        pytest.fail(
            f"trial_balance() sin parámetros falló: {e}. "
            f"Pero esto debería funcionar — P0-3 es sobre as_of ignorado, no trial_balance() roto."
        )
