import pytest
from modelos.libro import Libro
from modelos.registro import Registro

def test_retencion_isr_autogenerada():
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    # mapeo fiscal: cuenta 4202 retiene ISR 10% y destino 2160
    libro.mapeo_fiscal = {
        "4202": {
            "codigo": "4202",
            "tipo_operacion": "Egreso",
            "aplica_iva": "Si",
            "iva_tasa": "16",
            "aplica_isr": "Si",
            "retencion_isr": 10,
            "codigo_destino_isr": "2160",
            "codigo_destino_iva": "1180"
        }
    }
    # catálogo: destino ISR como acreedora (pasivo)
    libro.catalogo._catalogo["4202"] = {"Codigo": "4202", "Nombre": "Honorarios", "Tipo_cuenta": "Gasto", "Naturaleza": "Deudora"}
    libro.catalogo._catalogo["2160"] = {"Codigo": "2160", "Nombre": "ISR retenido a terceros", "Tipo_cuenta": "Pasivo", "Naturaleza": "Acreedora"}
    libro.catalogo._catalogo["1180"] = {"Codigo": "1180", "Nombre": "IVA acreditable", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"}
    # poliza simplificada para Egreso
    libro.polizas.mapeo = {
        "Egreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo"},
            {"CuentaDestino": "4202", "Rol": "Abono"}
        ]
    }
    libro.new_hoja("Movimientos")
    reg = Registro.create("2025-10-28", "4202", 1000.00, descripcion="Pago honorarios", tipo_operacion="Egreso")
    ok, msgs = libro.add_registro_to_hoja("Movimientos", reg, aplicar_impuestos=True)
    assert ok
    res = libro.generar_movimientos_desde_poliza("Movimientos")
    assert res["status"] == "ok"
    hoja = libro.hojas.get("Movimientos_Movimientos")
    assert hoja is not None
    # verificar que exista movimiento a 2160 (ISR retenido) con importe 100 (10% de 1000)
    regs_isr = [r for r in hoja.registros if r.cuenta == "2160"]
    assert len(regs_isr) >= 1
    assert any(float(r.cantidad) == pytest.approx(100.0) for r in regs_isr)

def test_compra_egreso_iva_acreditable():
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    # mapeo fiscal: 5101 compra con IVA acreditable, destino 1180
    libro.mapeo_fiscal = {
        "5101": {
            "codigo": "5101",
            "tipo_operacion": "Egreso",
            "aplica_iva": "Si",
            "iva_tasa": 16,
            "codigo_destino_iva": "1180"
        }
    }
    libro.catalogo._catalogo["5101"] = {"Codigo": "5101", "Nombre": "Materiales", "Tipo_cuenta": "Gasto", "Naturaleza": "Deudora"}
    libro.catalogo._catalogo["1180"] = {"Codigo": "1180", "Nombre": "IVA acreditable", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"}
    libro.catalogo._catalogo["1101"] = {"Codigo": "1101", "Nombre": "Bancos", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"}
    libro.polizas.mapeo = {
        "Egreso": [
            {"CuentaDestino": "5101", "Rol": "Cargo"},
            {"CuentaDestino": "1101", "Rol": "Abono"}
        ]
    }
    libro.new_hoja("Movimientos")
    reg = Registro.create("2025-10-28", "5101", 200.00, descripcion="Compra insumos", tipo_operacion="Egreso")
    ok, msgs = libro.add_registro_to_hoja("Movimientos", reg, aplicar_impuestos=True)
    assert ok
    res = libro.generar_movimientos_desde_poliza("Movimientos")
    assert res["status"] == "ok"
    hoja = libro.hojas.get("Movimientos_Movimientos")
    assert hoja is not None
    regs_iva = [r for r in hoja.registros if r.cuenta == "1180"]
    assert len(regs_iva) >= 1
    # IVA acreditable = 200 * 0.16 = 32.0 (cargo, porque 1180 es Deudora)
    assert any((not r.extra.get("es_abono", False)) and float(r.cantidad) == pytest.approx(32.0) for r in regs_iva)

def test_fallback_sin_mapeo_no_impuestos():
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    # poliza para Ingreso simple
    libro.polizas.mapeo = {
        "Ingreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo"},
            {"CuentaDestino": "4101", "Rol": "Abono"}
        ]
    }
    reg = Registro.create("2025-10-28", "9999", 150.00, descripcion="Operacion sin mapeo", tipo_operacion="Ingreso")
    # catálogo vacío (simula inicio rápido) -> registro permitido
    ok, msgs = libro.add_registro_to_hoja("Movimientos", reg, aplicar_impuestos=True)
    assert ok
    # generar movimientos (no debería crear líneas fiscales adicionales)
    res = libro.generar_movimientos_desde_poliza("Movimientos")
    assert res["status"] == "ok"
    hoja = libro.hojas.get("Movimientos_Movimientos")
    assert hoja is not None
    # no debe haber cuentas de impuestos 1180/2080/2160 si no hay mapeo
    cuentas = set(r.cuenta for r in hoja.registros)
    assert "1180" not in cuentas and "2080" not in cuentas and "2160" not in cuentas