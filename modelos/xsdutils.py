"""
modelos/xsdutils.py

Utilidades para crear un XMLSchema con un resolver local (mapea las imports/includes de URLs
a archivos locales en la carpeta datos/xsds). Usa lxml (LET). Si lxml no está instalado,
la función lanza una excepción informativa.

Funciones:
- build_schema_with_local_resolver(xsd_path: str, xsds_dir: str) -> LET.XMLSchema
- validate_xml_against_schema(xml_path: str, xsd_path: str, xsds_dir: str) -> dict
"""
from pathlib import Path
from typing import Any
try:
    from lxml import etree as LET
except Exception as e:
    LET = None

class LocalResolver(LET.Resolver):
    def __init__(self, xsds_dir: str):
        super().__init__()
        self.xsds_dir = Path(xsds_dir)

    def resolve(self, url, pubid, context):
        # Try direct basename match
        from urllib.parse import urlparse
        p = urlparse(url)
        candidates = []
        if p.path:
            # e.g. /sitio_internet/cfd/catalogos/catCFDI.xsd -> use 'catalogos/catCFDI.xsd'
            rel = p.path.lstrip("/")
            candidates.append(self.xsds_dir.joinpath(rel))
            # also try basename only
            candidates.append(self.xsds_dir.joinpath(Path(p.path).name))
        # try fallback: url as-is (maybe local relative)
        candidates.append(self.xsds_dir.joinpath(url))
        for c in candidates:
            if c.exists():
                return self.resolve_filename(str(c), context)
        # no local file found -> return None (let parser try remote)
        return None

def build_schema_with_local_resolver(xsd_path: str, xsds_dir: str):
    if LET is None:
        raise RuntimeError("lxml no está instalado. pip install lxml para habilitar validación XSD.")
    parser = LET.XMLParser()
    resolver = LocalResolver(xsds_dir)
    parser.resolvers.add(resolver)
    # parse using the parser with resolver
    xsd_doc = LET.parse(str(xsd_path), parser)
    schema = LET.XMLSchema(xsd_doc)
    return schema

def validate_xml_against_schema(xml_path: str, xsd_path: str, xsds_dir: str) -> dict:
    schema = build_schema_with_local_resolver(xsd_path, xsds_dir)
    doc = LET.parse(str(xml_path))
    valid = schema.validate(doc)
    if valid:
        return {"status": "ok", "valid": True}
    else:
        errors = []
        for err in schema.error_log:
            errors.append({"line": err.line, "message": err.message})
        return {"status": "error", "valid": False, "errors": errors}