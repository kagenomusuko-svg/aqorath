"""Deterministic, offline extraction of supported CFDI 4.0 source evidence.

This adapter reads external documentary truth only.  It deliberately does not
select accounts, calculate tax treatment, post entries, or contact SAT.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re
from typing import Optional
from uuid import UUID

from lxml import etree


CFDI40_NAMESPACE = "http://www.sat.gob.mx/cfd/4"
TFD11_NAMESPACE = "http://www.sat.gob.mx/TimbreFiscalDigital"
MAX_CFDI_BYTES = 10 * 1024 * 1024
_RFC = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")


@dataclass(frozen=True)
class CfdiTaxEvidence:
    direction: str
    base: Decimal
    tax_code: str
    factor_type: str
    rate_or_quota: Optional[Decimal]
    amount: Optional[Decimal]


@dataclass(frozen=True)
class ParsedCfdi:
    version: str
    uuid: str
    voucher_type: str
    issuer_rfc: str
    issuer_name: str
    issuer_regime: str
    receiver_rfc: str
    receiver_name: str
    receiver_regime: str
    receiver_use: str
    issued_at: datetime
    stamped_at: datetime
    currency: str
    subtotal: Decimal
    discount: Optional[Decimal]
    total: Decimal
    total_transferred: Decimal
    total_withheld: Decimal
    payment_form: Optional[str]
    payment_method: Optional[str]
    place_of_issue: str
    document_number: str
    sello_sat: str
    sat_certificate_number: str
    taxes: tuple[CfdiTaxEvidence, ...]
    sha256: str
    xml_bytes: bytes


@dataclass(frozen=True)
class CfdiSourceEvidence:
    id: int
    entity_id: int
    third_party_id: int
    document_position: str
    parsed: ParsedCfdi
    imported_at: datetime

    @property
    def total(self):
        return self.parsed.total

    @property
    def xml_bytes(self):
        return self.parsed.xml_bytes


@dataclass(frozen=True)
class CfdiImportResult:
    source: CfdiSourceEvidence
    duplicate: bool


def _required(element, name, label):
    value = element.get(name)
    if value is None or not value.strip():
        raise ValueError(f"{label} must be present and non-empty")
    return value.strip()


def _optional(element, name):
    value = element.get(name)
    return None if value is None or not value.strip() else value.strip()


def _decimal(value, label, *, allow_zero=True):
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    if result < 0 or (not allow_zero and result == 0):
        raise ValueError(f"{label} must be greater than{' or equal to' if allow_zero else ''} zero")
    return result


def _datetime(value, label):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO datetime") from exc


def _rfc(element, name, label):
    result = _required(element, name, label).upper()
    if _RFC.fullmatch(result) is None:
        raise ValueError(f"{label} must use the Mexican RFC shape")
    return result


def _exactly_one(root, xpath, namespaces, label):
    matches = root.xpath(xpath, namespaces=namespaces)
    if len(matches) != 1:
        raise ValueError(f"CFDI must contain exactly one {label}")
    return matches[0]


def _taxes(root, namespaces):
    result = []
    paths = (
        ("./cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado", "transfer"),
        ("./cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion", "withholding"),
    )
    for path, direction in paths:
        for node in root.xpath(path, namespaces=namespaces):
            factor = _required(node, "TipoFactor", "tax TipoFactor")
            rate = _optional(node, "TasaOCuota")
            amount = _optional(node, "Importe")
            if factor == "Exento":
                if rate is not None or amount is not None:
                    raise ValueError("Exento tax must not contain rate or amount")
            elif rate is None or amount is None:
                raise ValueError("non-exempt tax requires rate and amount")
            result.append(
                CfdiTaxEvidence(
                    direction=direction,
                    base=_decimal(_required(node, "Base", "tax Base"), "tax Base"),
                    tax_code=_required(node, "Impuesto", "tax Impuesto"),
                    factor_type=factor,
                    rate_or_quota=None if rate is None else _decimal(rate, "tax TasaOCuota"),
                    amount=None if amount is None else _decimal(amount, "tax Importe"),
                )
            )
    return tuple(result)


def parse_cfdi_xml(xml_bytes):
    """Parse the deliberately narrow V1 contract: stamped CFDI 4.0 ingreso, MXN."""
    if type(xml_bytes) is not bytes:
        raise TypeError("xml_bytes must be bytes")
    if not xml_bytes:
        raise ValueError("CFDI XML must not be empty")
    if len(xml_bytes) > MAX_CFDI_BYTES:
        raise ValueError(f"CFDI XML exceeds maximum size of {MAX_CFDI_BYTES} bytes")
    upper_prefix = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
        raise ValueError("CFDI XML must not contain DOCTYPE and ENTITY declarations")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=False,
    )
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("CFDI XML is not well-formed") from exc

    if root.tag != f"{{{CFDI40_NAMESPACE}}}Comprobante":
        raise ValueError("root must be Comprobante in the CFDI 4.0 namespace")
    namespaces = {"cfdi": CFDI40_NAMESPACE, "tfd": TFD11_NAMESPACE}
    version = _required(root, "Version", "Version")
    if version != "4.0":
        raise ValueError("only CFDI 4.0 is supported")
    voucher_type = _required(root, "TipoDeComprobante", "TipoDeComprobante")
    if voucher_type != "I":
        raise ValueError("only CFDI ingreso (TipoDeComprobante I) is supported")
    currency = _required(root, "Moneda", "Moneda")
    if currency != "MXN":
        raise ValueError(f"currency {currency} is outside AQR-010 V1 coverage")

    issuer = _exactly_one(root, "./cfdi:Emisor", namespaces, "Emisor")
    receiver = _exactly_one(root, "./cfdi:Receptor", namespaces, "Receptor")
    stamp = _exactly_one(
        root,
        "./cfdi:Complemento/tfd:TimbreFiscalDigital",
        namespaces,
        "TimbreFiscalDigital",
    )
    raw_uuid = _required(stamp, "UUID", "UUID")
    if len(raw_uuid) != 36 or tuple(raw_uuid[index] for index in (8, 13, 18, 23)) != ("-", "-", "-", "-"):
        raise ValueError("UUID must use canonical hyphenated shape")
    try:
        uuid = str(UUID(raw_uuid)).upper()
    except ValueError as exc:
        raise ValueError("UUID must be a valid UUID") from exc

    taxes = _taxes(root, namespaces)
    concepts = root.xpath("./cfdi:Conceptos/cfdi:Concepto", namespaces=namespaces)
    if not concepts:
        raise ValueError("CFDI must contain at least one concept")
    concept_subtotal = sum(
        (_decimal(_required(node, "Importe", "concept Importe"), "concept Importe") for node in concepts),
        Decimal("0"),
    )
    tax_container = root.find(f"{{{CFDI40_NAMESPACE}}}Impuestos")
    transferred = Decimal("0")
    withheld = Decimal("0")
    if tax_container is not None:
        transferred = _decimal(
            tax_container.get("TotalImpuestosTrasladados", "0"),
            "TotalImpuestosTrasladados",
        )
        withheld = _decimal(
            tax_container.get("TotalImpuestosRetenidos", "0"),
            "TotalImpuestosRetenidos",
        )
    component_transferred = sum(
        (item.amount or Decimal("0") for item in taxes if item.direction == "transfer"),
        Decimal("0"),
    )
    component_withheld = sum(
        (item.amount or Decimal("0") for item in taxes if item.direction == "withholding"),
        Decimal("0"),
    )
    if component_transferred != transferred:
        raise ValueError("transferred tax total does not equal its components")
    if component_withheld != withheld:
        raise ValueError("withheld tax total does not equal its components")

    series = _optional(root, "Serie")
    folio = _optional(root, "Folio")
    document_number = "-".join(item for item in (series, folio) if item) or uuid
    issued_at = _datetime(_required(root, "Fecha", "Fecha"), "Fecha")
    stamped_at = _datetime(_required(stamp, "FechaTimbrado", "FechaTimbrado"), "FechaTimbrado")
    if stamped_at < issued_at:
        raise ValueError("CFDI stamp cannot precede issue datetime")
    subtotal = _decimal(_required(root, "SubTotal", "SubTotal"), "SubTotal")
    discount_raw = _optional(root, "Descuento")
    discount = None if discount_raw is None else _decimal(discount_raw, "Descuento")
    total = _decimal(_required(root, "Total", "Total"), "Total", allow_zero=False)
    if concept_subtotal != subtotal:
        raise ValueError("CFDI subtotal does not equal concept importes")
    expected_total = subtotal - (discount or Decimal("0")) + transferred - withheld
    if expected_total != total:
        raise ValueError("CFDI document total does not reconcile with subtotal, discount, and taxes")
    return ParsedCfdi(
        version=version,
        uuid=uuid,
        voucher_type=voucher_type,
        issuer_rfc=_rfc(issuer, "Rfc", "Emisor Rfc"),
        issuer_name=_required(issuer, "Nombre", "Emisor Nombre"),
        issuer_regime=_required(issuer, "RegimenFiscal", "Emisor RegimenFiscal"),
        receiver_rfc=_rfc(receiver, "Rfc", "Receptor Rfc"),
        receiver_name=_required(receiver, "Nombre", "Receptor Nombre"),
        receiver_regime=_required(receiver, "RegimenFiscalReceptor", "Receptor RegimenFiscalReceptor"),
        receiver_use=_required(receiver, "UsoCFDI", "Receptor UsoCFDI"),
        issued_at=issued_at,
        stamped_at=stamped_at,
        currency=currency,
        subtotal=subtotal,
        discount=discount,
        total=total,
        total_transferred=transferred,
        total_withheld=withheld,
        payment_form=_optional(root, "FormaPago"),
        payment_method=_optional(root, "MetodoPago"),
        place_of_issue=_required(root, "LugarExpedicion", "LugarExpedicion"),
        document_number=document_number,
        sello_sat=_required(stamp, "SelloSAT", "SelloSAT"),
        sat_certificate_number=_required(stamp, "NoCertificadoSAT", "NoCertificadoSAT"),
        taxes=taxes,
        sha256=sha256(xml_bytes).hexdigest(),
        xml_bytes=bytes(xml_bytes),
    )


__all__ = [
    "CFDI40_NAMESPACE",
    "TFD11_NAMESPACE",
    "MAX_CFDI_BYTES",
    "CfdiTaxEvidence",
    "ParsedCfdi",
    "CfdiSourceEvidence",
    "CfdiImportResult",
    "parse_cfdi_xml",
]
