# tests/test_cfdi_timbrado.py
import pytest
from modelos.libro import Libro
from modelos.registro import Registro
from modelos.cfdi import generate_cfdi_from_asiento, import_timbrado
from pathlib import Path
import xml.etree.ElementTree as ET

def test_import_timbrado_roundtrip(tmp_path):
    libro = Libro(contabilidad_tipo="OSC", ejercicio=2025)
    libro.new_hoja("Movimientos")
    r1 = Registro.create("2025-10-01", "1101", 500.00, descripcion="Ingreso A", tipo_operacion="Ingreso")
    r2 = Registro.create("2025-10-01", "4101", 500.00, descripcion="Ingreso B", tipo_operacion="Ingreso")
    r2.extra["es_abono"] = True
    libro.add_registro_to_hoja("Movimientos", r1, aplicar_impuestos=False)
    libro.add_registro_to_hoja("Movimientos", r2, aplicar_impuestos=False)
    libro.polizas.mapeo = {
        "Ingreso": [
            {"CuentaDestino": "1101", "Rol": "Cargo"},
            {"CuentaDestino": "4101", "Rol": "Abono"}
        ]
    }
    libro.generar_movimientos_desde_poliza("Movimientos")
    assert len(libro.asientos) >= 1
    id_as = list(libro.asientos.keys())[0]
    outdir = tmp_path / "cfdi"
    res = generate_cfdi_from_asiento(libro, id_as, str(outdir))
    assert res["status"] == "ok"
    xml = Path(res["xml"])
    assert xml.exists()
    # crear un timbrado de ejemplo (agregar TimbreFiscalDigital)
    tree = ET.parse(str(xml))
    root = tree.getroot()
    # agregar complemento -> TimbreFiscalDigital
    complemento = ET.SubElement(root, "Complemento")
    tfd = ET.SubElement(complemento, "{http://www.sat.gob.mx/TimbreFiscalDigital}TimbreFiscalDigital")
    tfd.set("UUID", "1111-2222-3333-4444")
    tfd.set("SelloSAT", "SELLOSATEXAMPLE")
    timbrado_path = tmp_path / "timbrado.xml"
    tree.write(str(timbrado_path), encoding="utf-8", xml_declaration=True)
    # importar timbrado
    imp = import_timbrado(libro, id_as, str(timbrado_path), out_dir=str(outdir/"timbrados"))
    assert imp["status"] == "ok"
    assert "uuid" in imp and imp["uuid"] == "1111-2222-3333-4444"
    # asiento debe tener metadata timbrado
    assert "timbrado" in libro.asientos[id_as]
    assert libro.asientos[id_as]["timbrado"]["uuid"] == "1111-2222-3333-4444"
    # archivo copiado existe
    copied = Path(libro.asientos[id_as]["timbrado"]["xml_path"])
    assert copied.exists()