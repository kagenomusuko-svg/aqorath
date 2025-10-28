# validate_run.py
from modelos.xsdutils import validate_xml_against_schema
r = validate_xml_against_schema(
    xml_path="datos/cfdi/asiento_1.xml",
    xsd_path="datos/xsds/sitio_internet/cfd/4/cfdv40.xsd",
    xsds_dir="datos/xsds"
)
print(r)