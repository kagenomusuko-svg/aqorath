from decimal import Decimal
from aqorath.accounting_rules import compute_resultado_ejercicio

def test_resultado_simple():
    catalog = {
        "4000": {"tipo": "Ingreso"},
        "5000": {"tipo": "Gasto"},
    }
    balances = {
        "4000": Decimal("1000.00"),
        "5000": Decimal("300.00"),
        "9999": Decimal("50.00")
    }
    resultado, totals = compute_resultado_ejercicio(balances, catalog)
    assert totals["Ingreso"] == Decimal("1000.00")
    assert totals["Gasto"] == Decimal("300.00")
    assert resultado == Decimal("700.00")
