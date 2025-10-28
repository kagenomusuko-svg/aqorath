# tests/test_libro.py
import pytest
from modelos.libro import Libro
from modelos.registro import Registro

def test_compute_libro_mayor_basic():
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    r1 = Registro.create("2025-10-28", "1101", 100.00, descripcion="Ingreso banco", tipo_operacion="Ingreso")
    r2 = Registro.create("2025-10-28", "4101", 100.00, descripcion="Donativo", tipo_operacion="Ingreso")
    r2.extra["es_abono"] = True
    ok, msgs = libro.add_registro_to_hoja("Movimientos", r1, aplicar_impuestos=False)
    assert ok
    ok2, msgs2 = libro.add_registro_to_hoja("Movimientos", r2, aplicar_impuestos=False)
    assert ok2
    mayor = libro.compute_libro_mayor()
    cods = set(mayor["Codigo"].tolist())
    assert "1101" in cods and "4101" in cods
    row_1101 = mayor[mayor["Codigo"] == "1101"].iloc[0]
    row_4101 = mayor[mayor["Codigo"] == "4101"].iloc[0]
    assert float(row_1101["Cargo"]) == pytest.approx(100.0)
    assert float(row_4101["Abono"]) == pytest.approx(100.0)

def test_generar_movimientos_con_impuestos_autogenerados_y_signo_por_catalogo():
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    # Inyectar mapeo fiscal manualmente
    libro.mapeo_fiscal = {
        "4101": {
            "codigo": "4101",
            "tipo_operacion": "Ingreso",
            "aplica_iva": "Si",
            "iva_tasa": "16",
            "codigo_destino_iva": "2080",
            "retencion_isr": "",
            "codigo_destino_isr": ""
        }
    }
    # Definir catálogo con naturaleza para la cuenta destino del IVA
    libro.catalogo._catalogo["1101"] = {"Codigo": "1101", "Nombre": "Bancos", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"}
    libro.catalogo._catalogo["4101"] = {"Codigo": "4101", "Nombre": "Donativos en efectivo", "Tipo_cuenta": "Ingreso", "Naturaleza": "Acreedora"}
    libro.catalogo._catalogo["2080"] = {"Codigo": "2080", "Nombre": "IVA trasladado", "Tipo_cuenta": "Pasivo", "Naturaleza": "Acreedora"}

    libro.polizas.mapeo = {
        "Ingreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo", "Comentario": "Banco"},
            {"CuentaDestino": "4101", "Rol": "Abono", "Comentario": "Ingreso"}
        ]
    }

    libro.new_hoja("Movimientos")
    reg = Registro.create("2025-10-28", "4101", 100.00, descripcion="Venta con IVA", tipo_operacion="Ingreso")
    ok, msgs = libro.add_registro_to_hoja("Movimientos", reg, aplicar_impuestos=True)
    assert ok, msgs
    res = libro.generar_movimientos_desde_poliza("Movimientos")
    assert res["status"] == "ok"
    hoja_mov = libro.hojas.get("Movimientos_Movimientos")
    assert hoja_mov is not None
    cuentas = [r.cuenta for r in hoja_mov.registros]
    assert "1101" in cuentas and "4101" in cuentas and "2080" in cuentas
    regs2080 = [r for r in hoja_mov.registros if r.cuenta == "2080"]
    assert len(regs2080) >= 1
    # la cuenta 2080 debe ser registrada como ABONO (es_acreedora=True => abono)
    assert any(r.extra.get("es_abono", False) and float(r.cantidad) == pytest.approx(16.0) for r in regs2080)