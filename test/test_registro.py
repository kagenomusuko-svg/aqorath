# tests/test_registro.py
import pytest
from modelos.registro import Registro
from modelos.parametros import ParametroFiscal
from decimal import Decimal

def test_validate_missing_fields():
    # fecha inválida
    with pytest.raises(ValueError):
        Registro.create(123, "1101", 100)

    # cuenta vacía
    reg = Registro.create("2025-10-28", "", 100)
    ok, msgs = reg.validate()
    assert not ok
    assert any("Cuenta" in m for m in msgs)

def test_validate_zero_amount():
    reg = Registro.create("2025-10-28", "1101", 0)
    ok, msgs = reg.validate()
    assert not ok
    assert any("importe es cero" in m.lower() for m in msgs)

def test_cfdi_requires_metodo_pago():
    reg = Registro.create("2025-10-28", "1101", 100, cfdi=True)
    ok, msgs = reg.validate()
    assert not ok
    assert any("CFDI" in m or "método de pago" in m.lower() for m in msgs)

def test_aplicar_impuestos_from_mapeo():
    parametros = ParametroFiscal.from_dict({"IVA_general": 16, "ISR_retencion_pf": 10})
    reg = Registro.create("2025-10-28", "4101", 100.00, tipo_operacion="Ingreso")
    # mapeo fiscal simple: aplica_iva yes, iva_tasa 16, aplica_isr no
    mapeo = {"aplica_iva": "Si", "iva_tasa": "16", "aplica_isr": "", "retencion_iva": "", "retencion_isr": ""}
    res = reg.aplicar_impuestos(parametros, mapeo)
    # IVA debe ser 16.00
    assert isinstance(res["iva"], Decimal) or isinstance(res["iva"], float)
    # comparar con 16.00 (acepta float/Decimal)
    assert float(res["iva"]) == pytest.approx(16.0, rel=1e-6)
    assert float(res["isr"]) == pytest.approx(0.0)