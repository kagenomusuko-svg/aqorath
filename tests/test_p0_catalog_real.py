"""
P0-1 TEST CON CATÁLOGO REAL: resultado ejercicio con vocabulario Deudora/Acreedora

Verifica que normal_balance_amount() reconoce el vocabulario real del catálogo:
- "Deudora" (naturaleza debit-like)
- "Acreedora" (naturaleza credit-like)
"""

import pytest
from decimal import Decimal
from aqorath.accounting_rules import compute_resultado_ejercicio, load_catalog


def test_resultado_ejercicio_con_catalogo_real_deudora_acreedora():
    """
    Test con vocabulario real del catálogo: Deudora/Acreedora
    
    Usa cuentas reales de aqorath/data/catalogo_base.json:
    Catálogo contiene: Ingreso (Acreedora), Gasto (Deudora)
    
    Escenario:
      Ingreso (Acreedora): LedgerSigned = -100 → Normal = +100
      Gasto (Deudora): LedgerSigned = +40 → Normal = +40
      
      Resultado = Ingresos - Gastos = 100 - 40 = +60
    """
    # Cargar catálogo real
    catalog_dict = load_catalog()
    
    # P0-1: Catálogo obligatorio del repositorio
    assert catalog_dict, "Catálogo real NO puede estar disponible en este repositorio"
    
    # Buscar cuentas por tipo real
    ingresos_code = None
    gastos_code = None
    
    for code, acct_data in catalog_dict.items():
        tipo = acct_data.get("tipo", "").strip()
        if tipo == "Ingreso" and not ingresos_code:
            ingresos_code = code
        elif tipo == "Gasto" and not gastos_code:
            gastos_code = code
    
    # P0-1: Cuentas requeridas de catálogo
    assert ingresos_code is not None, (
        "Catálogo debe contener al menos una cuenta de tipo 'Ingreso'"
    )
    assert gastos_code is not None, (
        "Catálogo debe contener al menos una cuenta de tipo 'Gasto'"
    )
    
    # Construir balances
    # trial_balance retorna LedgerSignedBalance (Debe - Haber)
    balances = {
        ingresos_code: Decimal("-100"),  # Ingreso (Acreedora/credit): saldo algebraico negativo
        gastos_code: Decimal("40"),      # Gasto (Deudora/debit): saldo algebraico positivo
    }
    
    # Ejecutar compute_resultado_ejercicio con catálogo real
    resultado, totals = compute_resultado_ejercicio(balances, catalog_dict)
    
    # Esperado: normalizar según naturaleza real
    # Ingreso (Acreedora): -100 → +100
    # Gastos (Deudora): +40 → +40
    # Resultado = 100 - 40 = +60
    
    assert resultado == Decimal("60"), (
        f"Catálogo real (Deudora/Acreedora): Esperado +60, actual {resultado}. "
        f"Ingresos ({ingresos_code}): {balances[ingresos_code]} → "
        f"Normal {totals.get('Ingreso', 0)}; "
        f"Gastos ({gastos_code}): {balances[gastos_code]} → "
        f"Normal {totals.get('Gasto', 0)}"
    )


def test_naturaleza_desconocida_lanza_error():
    """
    Verifica que una naturaleza desconocida o vacía lanza ValueError.
    
    La invariante P0-1 requiere que no sea posible normalizar sin conocer
    la naturaleza real de la cuenta. Esto previene resultados económicos
    semánticamente inválidos.
    """
    from aqorath.accounting_rules import normal_balance_amount
    
    # Naturaleza desconocida: debe fallar
    with pytest.raises(ValueError, match="Naturaleza de cuenta desconocida"):
        normal_balance_amount(Decimal("100"), "DESCONOCIDA")
    
    # Naturaleza vacía: debe fallar
    with pytest.raises(ValueError, match="Naturaleza de cuenta no puede ser None"):
        normal_balance_amount(Decimal("100"), "")
    
    # Naturaleza None: debe fallar
    with pytest.raises(ValueError, match="Naturaleza de cuenta no puede ser None"):
        normal_balance_amount(Decimal("100"), None)
