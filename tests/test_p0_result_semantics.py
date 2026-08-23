"""
P0-1: SEMÁNTICA DE SIGNOS / RESULTADO DEL EJERCICIO

Defecto: El sistema obtiene saldo algebraico como:
  LedgerSignedBalance = Debe - Haber

Ejemplo:
  Ingreso: Debe=0, Haber=100 → LedgerSignedBalance = -100
  Gasto: Debe=40, Haber=0 → LedgerSignedBalance = +40

El cálculo actual suma esos saldos algebraicamente:
  Resultado = -100 - 40 = -140 (INCORRECTO)

Pero el resultado económico correcto es:
  Resultado = 100 (Ingresos) - 40 (Gastos) = +60

Debería normalizar saldos según naturaleza:
  Ingreso (nature=credit): Normal = +100
  Gasto (nature=debit): Normal = +40
  Resultado = 100 - 40 = +60
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import Session, select
from aqorath.models import JournalEntry, JournalLine, Account
from aqorath.accounting_rules import compute_resultado_ejercicio, compute_totals_by_tipo


def test_resultado_ejercicio_normaliza_saldos_segun_naturaleza(setup_accounts_in_session, minimal_catalog):
    """
    Verifica que el cálculo de resultado del ejercicio distinga:
    - LedgerSignedBalance: saldo algebraico (Debe - Haber)
    - NormalBalanceAmount: magnitud según naturaleza de cuenta
    
    Caso:
      Ingreso: 100 (Debe=0, Haber=100) → saldo algebraico = -100, normal = +100
      Gasto: 40 (Debe=40, Haber=0) → saldo algebraico = +40, normal = +40
      Resultado esperado: 100 - 40 = +60
    
    Este test DEBE FALLAR hoy porque compute_resultado_ejercicio
    suma saldos algebraicamente sin normalizarlos.
    """
    session = setup_accounts_in_session
    catalog = minimal_catalog
    
    # Crear JournalEntry
    entry = JournalEntry(
        date=datetime.now(timezone.utc),
        concept="Prueba de semántica de signos",
        state="posted"
    )
    session.add(entry)
    session.flush()
    
    # JournalLine 1: Ingreso (100)
    # Naturaleza: credit, por lo que en el debe-haber es: Debe=0, Haber=100
    ingreso_line = JournalLine(
        entry_id=entry.id,
        account_code="3000",  # Ventas, tipo Ingreso
        debit=0.0,
        credit=100.0,
        description="Ingreso de 100"
    )
    session.add(ingreso_line)
    
    # JournalLine 2: Gasto (40)
    # Naturaleza: debit, por lo que es: Debe=40, Haber=0
    gasto_line = JournalLine(
        entry_id=entry.id,
        account_code="4000",  # Gastos, tipo Gasto
        debit=40.0,
        credit=0.0,
        description="Gasto de 40"
    )
    session.add(gasto_line)
    
    session.commit()
    
    # Obtener saldos (trial_balance equivalente)
    # Manualmente construimos saldos como sí lo hace trial_balance: Debe - Haber
    balances = {
        "3000": Decimal(str(0.0 - 100.0)),     # Ingreso: LedgerSignedBalance = -100
        "4000": Decimal(str(40.0 - 0.0)),      # Gasto: LedgerSignedBalance = +40
    }
    
    # Calcular resultado usando la función actual
    resultado, totals = compute_resultado_ejercicio(balances, catalog["accounts"])
    
    # Resultado esperado correcto: Ingresos (100) - Gastos (40) = +60
    # Pero hoy suma saldos algebraicos: -100 - 40 = -140
    # o puede sumarlos de otra forma incorrecta.
    
    # La assertion debe verificar el comportamiento CORRECTO:
    # Resultado DEBE ser +60
    assert resultado == Decimal("60"), (
        f"Resultado incorrecto: {resultado}. "
        f"Esperado: 60. "
        f"Totals: {totals}. "
        f"Esto indica que los saldos NO se normalizan según naturaleza. "
        f"Balances algebraicos usados: {balances}"
    )


def test_resultado_incluye_costos_adecuadamente(setup_accounts_in_session, minimal_catalog):
    """
    Verifica que costos se resten correctamente del resultado.
    
    Caso: Ingresos=100, Costos=25, Gastos=15
    Resultado esperado: 100 - 25 - 15 = 60
    """
    session = setup_accounts_in_session
    catalog = minimal_catalog
    
    # Crear JournalEntry
    entry = JournalEntry(
        date=datetime.now(timezone.utc),
        concept="Test costos",
        state="posted"
    )
    session.add(entry)
    session.flush()
    
    # Ingreso: 100 (Debe=0, Haber=100)
    session.add(JournalLine(
        entry_id=entry.id,
        account_code="3000",
        debit=0.0,
        credit=100.0
    ))
    
    # Costo: 25 (Debe=25, Haber=0)
    session.add(JournalLine(
        entry_id=entry.id,
        account_code="3100",
        debit=25.0,
        credit=0.0
    ))
    
    # Gasto: 15 (Debe=15, Haber=0)
    session.add(JournalLine(
        entry_id=entry.id,
        account_code="4000",
        debit=15.0,
        credit=0.0
    ))
    
    session.commit()
    
    # Saldos algebraicos
    balances = {
        "3000": Decimal("-100"),  # Ingreso
        "3100": Decimal("25"),    # Costo
        "4000": Decimal("15"),    # Gasto
    }
    
    resultado, totals = compute_resultado_ejercicio(balances, catalog["accounts"])
    
    # Esperado: 100 - 25 - 15 = 60
    assert resultado == Decimal("60"), (
        f"Resultado incorrecto: {resultado}. "
        f"Esperado: 60 (Ingresos 100 - Costos 25 - Gastos 15). "
        f"Totals: {totals}"
    )
