from decimal import Decimal
from aqorath.accounting_rules import compute_resultado_ejercicio

def test_resultado_simple():
    # P0-1: P0-2: Agregar naturaleza (requerida por P0-1)
    catalog = {
        "4000": {"tipo": "Ingreso", "naturaleza": "Acreedora"},
        "5000": {"tipo": "Gasto", "naturaleza": "Deudora"},
    }
    balances = {
        "4000": Decimal("-1000.00"),  # Ingreso: saldo algebraico negativo (Acreedora)
        "5000": Decimal("300.00"),    # Gasto: saldo algebraico positivo (Deudora)
        "9999": Decimal("50.00")      # Desconocida: será ignorada por compute_totals_by_tipo
    }
    resultado, totals = compute_resultado_ejercicio(balances, catalog)
    # Normalización:
    # Ingreso (Acreedora): -1000 → +1000
    # Gasto (Deudora): +300 → +300
    # Resultado = 1000 - 300 = 700
    assert totals["Ingreso"] == Decimal("1000.00")
    assert totals["Gasto"] == Decimal("300.00")
    assert resultado == Decimal("700.00")
