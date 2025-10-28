# tests/test_cfdi.py
import pytest
from modelos.libro import Libro
from modelos.registro import Registro
from modelos.cfdi import generate_cfdi_from_asiento
from pathlib import Path

def test_generate_cfdi_basic(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    r1 = Registro.create("2025-10-01", "1101", 1000.00, descripcion="Venta banco", tipo_operacion="Ingreso")
    r2 = Registro.create("2025-10-01", "4101", 1000.00, descripcion="Ingreso venta", tipo_operacion="Ingreso")
    # marcar r2 as abono to simulate income
    r2.extra["es_abono"] = True
    libro.add_registro_to_hoja("Movimientos", r1, aplicar_impuestos=False)
    libro.add_registro_to_hoja("Movimientos", r2, aplicar_impuestos=False)
    # generar movimientos desde poliza to create an asiento
    libro.polizas.mapeo = {
        "Ingreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo"},
            {"CuentaDestino": "4101", "Rol": "Abono"}
        ]
    }
    libro.generar_movimientos_desde_poliza("Movimientos")
    # ensure there's at least one asiento
    assert len(libro.asientos) >= 1
    id_as = list(libro.asientos.keys())[0]
    outdir = tmp_path / "cfdi"
    emisor = {"rfc": "ACME010101ABC", "nombre": "ACME AC"}
    receptor = {"rfc": "XAXX010101000", "nombre": "Publico en general"}
    res = generate_cfdi_from_asiento(libro, id_as, str(outdir), emisor, receptor)
    assert res["status"] == "ok"
    assert Path(res["xml"]).exists()
    assert Path(res["csv"]).exists()
    assert Path(res["pdf"]).exists()
    # simple XML check
    xml_text = Path(res["xml"]).read_text(encoding="utf-8")
    assert "<Comprobante" in xml_text