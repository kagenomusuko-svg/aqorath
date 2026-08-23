"""
P0-2: EXACTITUD MONETARIA / FLOAT EN RUTA PRODUCTIVA

DEFECTO DOCUMENTADO: JournalLine.debit y credit usan float en persistencia.
Asset.value también usa float.

Float binario introduce pérdida de precisión en aritmética (0.1 + 0.2 != 0.3).

PRUEBA PRODUCTIVA: Entrada Decimal → API pública Aqorath → persistencia real → 
trial_balance() → comparación exacta sin transformación manual.
"""

import pytest
from decimal import Decimal
from aqorath.core import post_entry, trial_balance


def test_money_round_trip_current_path_preserves_tested_values(env_with_temp_db):
    """
    Prueba productiva de round-trip a través de API pública de Aqorath.
    
    Escenario: Dos asientos balanceados con valores problemáticos para float.
      Asiento A: Debe 1000 = 0.10, Haber 3000 = 0.10
      Asiento B: Debe 1000 = 0.20, Haber 3000 = 0.20
      
      Suma esperada: 1000 debe tener 0.10 + 0.20 = 0.30 exacto
                     3000 debe tener -(0.10 + 0.20) = -0.30 exacto
    
    Flujo: Decimal de entrada → post_entry() (ruta pública) → persistencia 
           (conversión a float en JournalLine.debit/credit) → SQLite → 
           trial_balance() agregación → Decimal resultado
    
    Contrato: Si exactitud se preserva, valores deben ser EXACTAMENTE Decimal("0.30")
    
    SIN: pytest.approx, math.isclose, epsilon, ni str(float) realizado por test.
    """
    
    # Asiento A: Debe 1000 = 0.10, Haber 3000 = 0.10
    entry_a = {
        "description": "Asiento A: 0.10",
        "lines": [
            {
                "account_code": "1000",
                "debit": Decimal("0.10"),  # Entrada Decimal
                "credit": Decimal("0"),
                "description": "Debe 1000"
            },
            {
                "account_code": "3000",
                "debit": Decimal("0"),
                "credit": Decimal("0.10"),
                "description": "Haber 3000"
            }
        ]
    }
    
    # Asiento B: Debe 1000 = 0.20, Haber 3000 = 0.20
    entry_b = {
        "description": "Asiento B: 0.20",
        "lines": [
            {
                "account_code": "1000",
                "debit": Decimal("0.20"),
                "credit": Decimal("0"),
                "description": "Debe 1000"
            },
            {
                "account_code": "3000",
                "debit": Decimal("0"),
                "credit": Decimal("0.20"),
                "description": "Haber 3000"
            }
        ]
    }
    
    # Persistir usando API pública
    result_a = post_entry(entry_a)
    result_b = post_entry(entry_b)
    
    # Verificar que persistieron
    assert result_a.get("ok"), f"Asiento A no persistió: {result_a}"
    assert result_b.get("ok"), f"Asiento B no persistió: {result_b}"
    
    # Recuperar saldos usando trial_balance
    balances = trial_balance()
    
    saldo_1000 = balances.get("1000", Decimal("0"))
    saldo_3000 = balances.get("3000", Decimal("0"))
    
    # Contrato: suma exacta de Decimal
    # Esperado: 0.10 + 0.20 = 0.30 EXACTAMENTE
    expected_1000 = Decimal("0.30")
    expected_3000 = Decimal("-0.30")
    
    # Comparación EXACTA sin tolerancia
    if saldo_1000 != expected_1000:
        pytest.fail(
            f"Cuenta 1000: Esperado {expected_1000}, actual {saldo_1000}. "
            f"Pérdida: {saldo_1000 - expected_1000}. "
            f"CLASIFICACIÓN: P0-2 REPRODUCIBLE — float introduce pérdida"
        )
    
    if saldo_3000 != expected_3000:
        pytest.fail(
            f"Cuenta 3000: Esperado {expected_3000}, actual {saldo_3000}. "
            f"Pérdida: {saldo_3000 - expected_3000}. "
            f"CLASIFICACIÓN: P0-2 REPRODUCIBLE — float introduce pérdida"
        )
    
    # Si llegó aquí, ambos se preservaron exactamente
    assert saldo_1000 == expected_1000, "Saldo 1000 no preservó exactitud"
    assert saldo_3000 == expected_3000, "Saldo 3000 no preservó exactitud"



