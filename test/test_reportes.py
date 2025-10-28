# tests/test_reportes.py
import pytest
from modelos.libro import Libro
from modelos.registro import Registro
from modelos.reportes import export_report
from pathlib import Path

def test_export_balance_pdf(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    r1 = Registro.create("2025-10-01", "1101", 1000.00, descripcion="Ingreso banco", tipo_operacion="Ingreso")
    r2 = Registro.create("2025-10-02", "4101", 1000.00, descripcion="Ingreso venta", tipo_operacion="Ingreso")
    libro.add_registro_to_hoja("Movimientos", r1, aplicar_impuestos=False)
    libro.add_registro_to_hoja("Movimientos", r2, aplicar_impuestos=False)

    out = tmp_path / "balance.pdf"
    res = export_report(libro, "balance", str(out))
    assert res["status"] == "ok"
    assert out.exists() and out.stat().st_size > 0

def test_export_mayor_pdf(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    r1 = Registro.create("2025-10-01", "1101", 500.00, descripcion="Depósito", tipo_operacion="Ingreso")
    r2 = Registro.create("2025-10-02", "1101", 200.00, descripcion="Depósito 2", tipo_operacion="Ingreso")
    libro.add_registro_to_hoja("Movimientos", r1, aplicar_impuestos=False)
    libro.add_registro_to_hoja("Movimientos", r2, aplicar_impuestos=False)

    out = tmp_path / "mayor.pdf"
    res = export_report(libro, "mayor", str(out))
    assert res["status"] == "ok"
    assert out.exists() and out.stat().st_size > 0

def test_export_estado_resultados_pdf(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    # preparar registros de ingresos y gastos
    libro.new_hoja("Movimientos")
    ingreso = Registro.create("2025-10-05", "4101", 1200.00, descripcion="Venta", tipo_operacion="Ingreso")
    gasto = Registro.create("2025-10-06", "5101", 700.00, descripcion="Compra", tipo_operacion="Egreso")
    libro.add_registro_to_hoja("Movimientos", ingreso, aplicar_impuestos=False)
    libro.add_registro_to_hoja("Movimientos", gasto, aplicar_impuestos=False)

    out = tmp_path / "er.pdf"
    res = export_report(libro, "estado_resultados", str(out))
    assert res["status"] == "ok"
    assert out.exists() and out.stat().st_size > 0