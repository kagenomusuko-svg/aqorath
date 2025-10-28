# modelos/cfdi.py
"""
Generador y utilidades CFDI (skeleton) con pre-validación y validación XSD opcional.
- prevalidate_cfdi(libro, id_asiento)
- generate_cfdi_from_asiento(..., prevalidate=False, validate_xsd=None)
- import_timbrado(libro, id_asiento, timbrado_xml_path, out_dir='datos/cfdi/timbrados')
"""
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET
import csv
import shutil
import re

ET.register_namespace('', "http://www.sat.gob.mx/cfd/4")
ET.register_namespace('tfd', "http://www.sat.gob.mx/TimbreFiscalDigital")
ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm

from .parametros import ParametroFiscal
from . import xsdutils

# Optional import of validator helper
try:
    from .xsdutils import validate_xml_against_schema
except Exception:
    validate_xml_against_schema = None  # type: ignore

# -----------------------
# Helpers and validators
# -----------------------
def derive_claves_from_catalog(libro, cuenta: str) -> Tuple[str, str]:
    default_prod = "84111506"
    default_unidad = "ACT"
    if not cuenta:
        return default_prod, default_unidad
    info = libro.catalogo.get(str(cuenta).strip()) or {}
    prod = info.get("ClaveProdServ") or info.get("Clave_Prod_Serv") or info.get("ClaveProd") or info.get("Clave")
    unidad = info.get("ClaveUnidad") or info.get("Clave_Unidad") or info.get("Unidad") or info.get("ClaveUnidadSAT")
    prod = str(prod).strip() if prod not in (None, "") else ""
    unidad = str(unidad).strip() if unidad not in (None, "") else ""
    return (prod if prod else default_prod, unidad if unidad else default_unidad)

RFC_RE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$', re.IGNORECASE)
def is_valid_rfc(rfc: str) -> bool:
    if not rfc:
        return False
    return bool(RFC_RE.match(str(rfc).strip().upper()))

def is_nonempty_string(s) -> bool:
    return bool(s and str(s).strip())

COMMON_USO_CFDI = {"P01","G01","G03","I01","I02","D01","D02"}
def is_valid_uso_cfdi(uso: str) -> bool:
    if not uso:
        return False
    return str(uso).upper() in COMMON_USO_CFDI

def is_valid_clave_prod_serv(clave: str) -> bool:
    if not clave:
        return False
    s = str(clave).strip()
    return s.isdigit() and (6 <= len(s) <= 8)

# -----------------------
# Pre-validation
# -----------------------
def prevalidate_cfdi(libro, id_asiento: int) -> Tuple[bool, List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if id_asiento not in libro.asientos:
        errors.append(f"Asiento {id_asiento} no existe.")
        return False, errors, warnings

    asi = libro.asientos[id_asiento]
    p = getattr(libro, "parametros", ParametroFiscal())

    # Emisor
    em_rfc = p.get("Emisor_RFC", "")
    em_nombre = p.get("Emisor_Nombre", "")
    em_regimen = p.get("Emisor_Regimen", "")
    if not is_valid_rfc(em_rfc):
        errors.append("Emisor_RFC inválido o vacío en ParametrosFiscales.")
    if not is_nonempty_string(em_nombre):
        errors.append("Emisor_Nombre vacío en ParametrosFiscales.")
    if not is_nonempty_string(em_regimen):
        warnings.append("Emisor_Regimen no definido (recomendado).")

    # FormaPago y LugarExpedicion
    forma_pago = p.get("FormaPago", "") or ""
    lugar = p.get("LugarExpedicion", "") or ""
    if not forma_pago or not str(forma_pago).strip():
        errors.append("FormaPago no definido en ParametrosFiscales. Debe ser un código válido (ej. '03').")
    if not lugar or not str(lugar).strip():
        errors.append("LugarExpedicion (Código Postal) no definido en ParametrosFiscales.")

    # Receptor
    rec_rfc = p.get("Receptor_RFC", "") or ""
    rec_nombre = p.get("Receptor_Nombre", "") or ""
    rec_cp = p.get("Receptor_DomicilioFiscalReceptor", "") or p.get("Receptor_DomicilioFiscal", "") or ""
    rec_regimen = p.get("Receptor_RegimenFiscal", "") or ""
    uso = p.get("Receptor_UsoCFDI", "") or ""
    if not is_valid_rfc(rec_rfc):
        warnings.append("Receptor_RFC no válido o vacío. Si es público en general usar 'XAXX010101000'.")
    if not is_nonempty_string(rec_nombre):
        warnings.append("Receptor_Nombre vacío.")
    if not rec_cp or not str(rec_cp).strip():
        errors.append("Receptor DomicilioFiscalReceptor (Código Postal) no definido en ParametrosFiscales.")
    if not rec_regimen:
        warnings.append("Receptor_RegimenFiscal no definido; verificar si aplica.")
    if not is_valid_uso_cfdi(uso):
        warnings.append(f"Receptor_UsoCFDI '{uso}' no es un valor común; verificar si es correcto.")

    # Conceptos
    for l in asi.get("lineas", []):
        importe = 0.0
        if l.get("cargo") not in (None, 0):
            importe = float(l.get("cargo") or 0.0)
        elif l.get("abono") not in (None, 0):
            importe = float(l.get("abono") or 0.0)
        if importe == 0:
            continue
        clave_prod, clave_unid = derive_claves_from_catalog(libro, l.get("cuenta"))
        if not is_valid_clave_prod_serv(clave_prod):
            warnings.append(f"ClaveProdServ no válida/derivada para cuenta {l.get('cuenta')} -> '{clave_prod}'. Se usará genérica.")
        info = libro.catalogo.get(str(l.get("cuenta") or "").strip()) or {}
        noid = info.get("NoIdentificacion") or info.get("No_Identificacion") or l.get("no_identificacion") or ""
        if not noid:
            warnings.append(f"NoIdentificacion ausente para cuenta {l.get('cuenta')} (recomendado para conceptos).")
        objeto = info.get("ObjetoImp") or info.get("Objeto_Imp") or libro.parametros.valores.get("ObjetoImp_default")
        if not objeto:
            warnings.append(f"ObjetoImp no detectado para cuenta {l.get('cuenta')}. Verificar si el concepto está sujeto a impuestos.")
    ok = len(errors) == 0
    return ok, errors, warnings

# -----------------------
# Generation (skeleton) and optional XSD validation
# -----------------------
def generate_cfdi_from_asiento(libro, id_asiento: int, out_dir: str, emisor: Dict[str, str] = None, receptor: Dict[str, str] = None, prevalidate: bool = False, validate_xsd: Optional[str] = None) -> Dict[str, Any]:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {}

    if prevalidate:
        ok, errors, warnings = prevalidate_cfdi(libro, id_asiento)
        result["prevalidation"] = {"ok": ok, "errors": errors, "warnings": warnings}
        if not ok:
            result["status"] = "prevalidation_failed"
            return result

    if id_asiento not in libro.asientos:
        return {"status": "error", "message": f"Asiento {id_asiento} no encontrado."}
    asi = libro.asientos[id_asiento]
    p = getattr(libro, "parametros", ParametroFiscal())

    if not emisor:
        emisor = {
            "rfc": p.get("Emisor_RFC", "XAXX010101000"),
            "nombre": p.get("Emisor_Nombre", "Emisor"),
            "regimen": p.get("Emisor_Regimen", "")
        }
    if not receptor:
        receptor = {
            "rfc": p.get("Receptor_RFC", "XAXX010101000"),
            "nombre": p.get("Receptor_Nombre", "Receptor"),
            "uso_cfdi": p.get("Receptor_UsoCFDI", "P01")
        }

    ns = "http://www.sat.gob.mx/cfd/4"
    ET.register_namespace('', ns)
    ET.register_namespace('xsi', "http://www.w3.org/2001/XMLSchema-instance")
    Comprobante = ET.Element("{%s}Comprobante" % ns)
    Comprobante.set("Version", "4.0")
    Comprobante.set("Fecha", datetime.now().isoformat(timespec='seconds'))
    lugar = p.get("LugarExpedicion", "")
    if lugar:
        Comprobante.set("LugarExpedicion", str(lugar))
    Comprobante.set("FormaPago", str(p.get("FormaPago", "")) or "")
    Comprobante.set("MetodoPago", str(p.get("MetodoPago", "PUE") or "PUE"))
    Comprobante.set("TipoDeComprobante", str(p.get("TipoDeComprobante", "I") or "I"))
    Comprobante.set("Moneda", str(p.get("Moneda", "MXN") or "MXN"))

    conceptos_list = []
    subtotal = 0.0
    iva_total = 0.0

    for linea in asi.get("lineas", []):
        importe = 0.0
        if linea.get("cargo") not in (None, 0):
            importe = float(linea.get("cargo") or 0.0)
        elif linea.get("abono") not in (None, 0):
            importe = float(linea.get("abono") or 0.0)
        if importe == 0:
            continue
        clave_prod, clave_unidad = derive_claves_from_catalog(libro, linea.get("cuenta"))
        conceptos_list.append({
            "clave_prod_serv": clave_prod,
            "no_identificacion": linea.get("no_identificacion") or "",
            "cantidad": 1,
            "clave_unidad": clave_unidad,
            "unidad": linea.get("unidad") or "Actividad",
            "descripcion": str(linea.get("descripcion") or "Movimiento"),
            "valor_unitario": round(importe, 2),
            "importe": round(importe, 2)
        })
        subtotal += float(importe)
        if str(linea.get("cuenta")) == str(p.get("IVA_trasladado_cuenta", "2080")):
            iva_total += float(linea.get("abono") or 0.0)

    total = subtotal + iva_total
    Comprobante.set("SubTotal", f"{subtotal:.2f}")
    Comprobante.set("Total", f"{total:.2f}")

    Emisor = ET.SubElement(Comprobante, "{%s}Emisor" % ns)
    Emisor.set("Rfc", emisor.get("rfc", "XAXX010101000"))
    Emisor.set("Nombre", emisor.get("nombre", "Emisor"))
    Emisor.set("RegimenFiscal", str(emisor.get("regimen") or p.get("Emisor_Regimen", "601")))

    Receptor = ET.SubElement(Comprobante, "{%s}Receptor" % ns)
    Receptor.set("Rfc", receptor.get("rfc", "XAXX010101000"))
    Receptor.set("Nombre", receptor.get("nombre", "Receptor"))
    uso = receptor.get("uso_cfdi") or p.get("Receptor_UsoCFDI", "P01")
    if uso:
        Receptor.set("UsoCFDI", uso)
    df_receptor = p.get("Receptor_DomicilioFiscalReceptor", "") or p.get("Receptor_DomicilioFiscal", "")
    if df_receptor:
        Receptor.set("DomicilioFiscalReceptor", str(df_receptor))

    Conceptos = ET.SubElement(Comprobante, "{%s}Conceptos" % ns)
    for c in conceptos_list:
        concepto = ET.SubElement(Conceptos, "{%s}Concepto" % ns)
        concepto.set("ClaveProdServ", c["clave_prod_serv"])
        concepto.set("NoIdentificacion", c["no_identificacion"] or "NA")
        concepto.set("Cantidad", str(c["cantidad"]))
        concepto.set("ClaveUnidad", c["clave_unidad"])
        concepto.set("Unidad", c["unidad"])
        concepto.set("Descripcion", c["descripcion"])
        concepto.set("ValorUnitario", f"{c['valor_unitario']:.2f}")
        # FIXED: use proper f-string formatting
        concepto.set("Importe", f"{c['importe']:.2f}")
        objimp = p.get("ObjetoImp_default", "01")
        concepto.set("ObjetoImp", str(objimp))

    Impuestos = ET.SubElement(Comprobante, "{%s}Impuestos" % ns)
    if iva_total > 0:
        Traslados = ET.SubElement(Impuestos, "{%s}Traslados" % ns)
        T = ET.SubElement(Traslados, "{%s}Traslado" % ns)
        tasa = float(p.get("IVA_general", 16))
        T.set("Base", f"{subtotal:.2f}")
        T.set("Impuesto", "002")
        T.set("TipoFactor", "Tasa")
        T.set("TasaOCuota", f"{tasa/100:.6f}")
        T.set("Importe", f"{iva_total:.2f}")
        Impuestos.set("TotalImpuestosTrasladados", f"{iva_total:.2f}")

    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    schema_loc = "http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"
    Comprobante.set("{%s}schemaLocation" % xsi, schema_loc)

    xml_path = outp / f"asiento_{id_asiento}.xml"
    tree = ET.ElementTree(Comprobante)
    tree.write(str(xml_path), encoding="utf-8", xml_declaration=True, method="xml")

    csv_path = outp / f"asiento_{id_asiento}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id_asiento", "fecha", "emisor_rfc", "receptor_rfc", "subtotal", "iva", "total"])
        writer.writerow([
            id_asiento,
            asi.get("fecha"),
            emisor.get("rfc"),
            receptor.get("rfc"),
            f"{subtotal:.2f}",
            f"{iva_total:.2f}",
            f"{total:.2f}"
        ])

    pdf_path = outp / f"asiento_{id_asiento}.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Resumen Asiento {id_asiento}", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Emisor: {emisor.get('rfc')} - {emisor.get('nombre')}", styles["Normal"]))
    story.append(Paragraph(f"Receptor: {receptor.get('rfc')} - {receptor.get('nombre')}", styles["Normal"]))
    story.append(Spacer(1, 12))
    data = [["Descripcion", "Importe"]]
    for c in conceptos_list:
        data.append([c["descripcion"], f"{c['importe']:.2f}"])
    data.append(["Subtotal", f"{subtotal:.2f}"])
    if iva_total > 0:
        data.append(["IVA", f"{iva_total:.2f}"])
    data.append(["Total", f"{total:.2f}"])
    t = Table(data, hAlign='LEFT', colWidths=[12*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
    ]))
    story.append(t)
    doc.build(story)

    result.update({"status": "ok", "xml": str(xml_path), "csv": str(csv_path), "pdf": str(pdf_path)})

    if validate_xsd:
        try:
            xsd_report = validate_xml_against_schema(str(xml_path), str(validate_xsd), str(Path(validate_xsd).parent.parent))
        except Exception as e:
            xsd_report = {"status": "error", "message": f"Validación no disponible: {e}"}
        result["xsd_validation"] = xsd_report

    return result

# -----------------------
# Import timbrado
# -----------------------
def import_timbrado(libro, id_asiento: int, timbrado_xml_path: str, out_dir: str = "datos/cfdi/timbrados") -> Dict[str, Any]:
    """
    Importa un XML timbrado y lo asocia al asiento.
    Extrae UUID y SelloSAT desde TimbreFiscalDigital (namespace tfd), copia archivo y guarda metadata.
    """
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    if id_asiento not in libro.asientos:
        return {"status": "error", "message": f"Asiento {id_asiento} no encontrado."}
    try:
        tree = ET.parse(str(timbrado_xml_path))
        root = tree.getroot()
    except Exception as e:
        return {"status": "error", "message": f"No se pudo leer XML: {e}"}
    tfd_ns = "http://www.sat.gob.mx/TimbreFiscalDigital"
    tfd_elem = None
    for elem in root.iter():
        tag = elem.tag
        if isinstance(tag, str) and (tag.endswith("TimbreFiscalDigital") or tag == f"{{{tfd_ns}}}TimbreFiscalDigital"):
            tfd_elem = elem
            break
    if tfd_elem is None:
        return {"status": "error", "message": "No se encontró TimbreFiscalDigital en el XML."}
    uuid = tfd_elem.get("UUID") or tfd_elem.get("uuid") or ""
    sello = tfd_elem.get("SelloSAT") or tfd_elem.get("selloSAT") or ""
    dest = outp / f"asiento_{id_asiento}_timbrado.xml"
    try:
        shutil.copy2(str(timbrado_xml_path), str(dest))
    except Exception as e:
        return {"status": "error", "message": f"No se pudo copiar el XML timbrado: {e}"}
    libro.asientos[id_asiento].setdefault("timbrado", {})
    libro.asientos[id_asiento]["timbrado"].update({
        "uuid": uuid,
        "sello": sello,
        "xml_path": str(dest),
        "importado_en": datetime.now().isoformat(timespec='seconds')
    })
    return {"status": "ok", "id_asiento": id_asiento, "uuid": uuid, "xml": str(dest)}