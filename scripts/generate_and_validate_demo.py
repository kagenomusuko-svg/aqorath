# scripts/generate_and_validate_demo.py
# Demo: genera un asiento, rellena parametros mínimos, crea CFDI skeleton y valida si hay XSD.
# Añade la raiz del proyecto a sys.path para poder importar el paquete 'modelos' cuando se ejecuta como script.
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from modelos.libro import Libro
from modelos.registro import Registro
from modelos.cfdi import generate_cfdi_from_asiento
from modelos.xsdutils import validate_xml_against_schema
from pathlib import Path
import json

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
id_as = list(libro.asientos.keys())[0]

# Rellenar parametros mínimos (ajusta para OSC / Comercial)
libro.parametros.set("Emisor_RFC", "ACME010101ABC")
libro.parametros.set("Emisor_Nombre", "ACME AC")
libro.parametros.set("Emisor_Regimen", "601")
libro.parametros.set("FormaPago", "03")
libro.parametros.set("MetodoPago", "PUE")
libro.parametros.set("TipoDeComprobante", "I")
libro.parametros.set("Moneda", "MXN")
libro.parametros.set("LugarExpedicion", "64000")
libro.parametros.set("Receptor_RFC", "XAXX010101000")
libro.parametros.set("Receptor_Nombre", "Público en General")
libro.parametros.set("Receptor_UsoCFDI", "P01")
libro.parametros.set("Receptor_DomicilioFiscalReceptor", "64000")

outdir = "datos/cfdi"
Path(outdir).mkdir(parents=True, exist_ok=True)

res = generate_cfdi_from_asiento(libro, id_as, outdir, prevalidate=True, validate_xsd=None)
print("generate_cfdi_from_asiento ->")
print(json.dumps(res, indent=2, ensure_ascii=False))

# validate against local XSD if present
xsd_path = "datos/xsds/sitio_internet/cfd/4/cfdv40.xsd"
if Path(xsd_path).exists():
    print("\nValidando contra XSD local:", xsd_path)
    try:
        xsd_report = validate_xml_against_schema(res["xml"], xsd_path, "datos/xsds")
        print("XSD validation ->", json.dumps(xsd_report, indent=2, ensure_ascii=False))
    except Exception as e:
        print("Validación XSD no disponible:", e)
else:
    print("\nNo se encontró XSD local en datos/xsds; para validar descarga los XSDs con scripts/fetch_xsds.py")