# tests/test_asientos.py
import pytest
from modelos.libro import Libro
from modelos.registro import Registro
from pathlib import Path
import tempfile
import os

def test_asientos_persisten_guardar_y_cargar(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    # mapeo y poliza simples para crear asientos
    libro.mapeo_fiscal = {
        "4101": {"codigo": "4101", "tipo_operacion": "Ingreso", "aplica_iva": "Si", "iva_tasa": 16, "codigo_destino_iva": "2080"}
    }
    libro.polizas.mapeo = {
        "Ingreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo"},
            {"CuentaDestino": "4101", "Rol": "Abono"}
        ]
    }
    # catalogo (para signos)
    libro.catalogo._catalogo["1101"] = {"Codigo": "1101", "Nombre": "Bancos", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"}
    libro.catalogo._catalogo["4101"] = {"Codigo": "4101", "Nombre": "Donativos", "Tipo_cuenta": "Ingreso", "Naturaleza": "Acreedora"}
    libro.catalogo._catalogo["2080"] = {"Codigo": "2080", "Nombre": "IVA trasladado", "Tipo_cuenta": "Pasivo", "Naturaleza": "Acreedora"}

    libro.new_hoja("Movimientos")
    reg = Registro.create("2025-10-28", "4101", 100.00, descripcion="Venta prueba", tipo_operacion="Ingreso")
    ok, msgs = libro.add_registro_to_hoja("Movimientos", reg, aplicar_impuestos=True)
    assert ok
    res = libro.generar_movimientos_desde_poliza("Movimientos")
    assert res["status"] == "ok"
    # guardar en tmp file
    file_path = tmp_path / "test_libro_asientos.xlsx"
    libro.save_xlsx(str(file_path))
    # cargar nuevo libro desde archivo
    nuevo = Libro.load_xlsx(str(file_path))
    # verificar que haya asientos cargados
    assert len(nuevo.asientos) >= 1
    # verificar línea de IVA 2080 presente en asientos
    found_2080 = False
    for asi in nuevo.asientos.values():
        for linea in asi["lineas"]:
            if linea["cuenta"] == "2080" and abs(float(linea.get("abono") or 0.0) - 16.0) < 0.001:
                found_2080 = True
    assert found_2080

def test_export_asiento_csv_and_xlsx(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.asientos[1] = {
        "id": 1,
        "fecha": "2025-10-28",
        "descripcion": "Prueba",
        "lineas": [
            {"cuenta": "1101", "cargo": 100.0, "abono": 0.0, "descripcion": "Banco", "es_abono": False},
            {"cuenta": "4101", "cargo": 0.0, "abono": 100.0, "descripcion": "Ingreso", "es_abono": True}
        ],
        "total_cargo": 100.0,
        "total_abono": 100.0
    }
    csv_path = tmp_path / "asiento_1.csv"
    xlsx_path = tmp_path / "asiento_1.xlsx"
    r1 = libro.export_asiento(1, str(csv_path), fmt="csv")
    assert r1["status"] == "ok" and csv_path.exists()
    r2 = libro.export_asiento(1, str(xlsx_path), fmt="xlsx")
    assert r2["status"] == "ok" and xlsx_path.exists()