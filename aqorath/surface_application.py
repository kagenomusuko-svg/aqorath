"""Application-facing service for the local presentation.

Presentation receives JSON-compatible projections and delegates all accounting to
existing Application authorities. AQR-006 adds operational CxC/CxP workflows here
without moving account, period, reversal, fiscal or persistence rules into UI code.

Generic AQR-004 credit/collection/payment facts remain valid internal foundations,
but the common surface no longer exposes them directly: new CxC/CxP movements must
carry ThirdParty/document/open-item provenance through the AQR-006 use cases.
"""

from dataclasses import dataclass, asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import base64
import binascii

from . import accounting_operation as _operations
from . import accounting_operation_read as _operation_read
from . import application as _application
from . import economic_facts as _facts
from . import open_item_repository as _open_items
from . import storage as _storage
from . import subledger_operations as _subledger
from . import bank_repository as _banks
from . import reconciliation_repository as _reconciliations
from .banking import BankAccount
from . import bank_transfer as _bank_transfer
from . import fund_repository as _funds
from .fund import Fund, FundingSource, FundReceipt, FundApplication
from .fund_models import FundReceiptRecord, FundRecord, FundingSourceRecord
from .models import JournalEntry, JournalLine, AuditEventRecord, DonationRecord, ProgramRecord, ThirdPartyRecord, InKindDonationRecord, FixedAssetRecord, DocumentReferenceRecord
from .banking_models import BankAccountRecord
from .models import AccountRoleBinding
from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
from sqlmodel import select


def list_surface_donations():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None:
            return []
        return [asdict(item) for item in _application.list_donations(session, entity.id)]


def create_surface_donation(payload):
    from .donation import Donation
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None:
            raise LookupError("active Entity not configured")
        item = Donation(None, entity.id, datetime.fromisoformat(payload["date"]), _amount(payload["amount"]), payload.get("donor_third_party_id"), payload.get("purpose"), bool(payload.get("is_restricted", False)))
        return asdict(_application.create_donation(session, item))


def create_surface_inkind_donation(payload):
    from .inkind_donation import InKindDonation
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None:
            raise LookupError("active Entity not configured")
        item = InKindDonation(None, entity.id, payload.get("donor_third_party_id"), payload.get("document_reference_id"), payload.get("fund_id"), payload.get("program_id"), payload.get("journal_line_id"), payload.get("fixed_asset_id"), datetime.fromisoformat(payload["received_at"]), payload["description"], None if payload.get("quantity") is None else _amount(payload["quantity"]), _amount(payload["valuation_amount"]), payload.get("valuation_currency", "MXN"), payload["valuation_method"], payload["valuation_evidence"], payload["external_reference"])
        return asdict(_application.create_inkind_donation(session, item))


@dataclass(frozen=True)
class CommonOperationKind:
    key: str
    label: str
    fact_type: str
    payment_method: str


@dataclass(frozen=True)
class PreparedSurfaceOperation:
    kind: CommonOperationKind
    decision: object


@dataclass(frozen=True)
class PreparedSurfaceSubledgerAction:
    action: str
    prepared: object
    summary: dict


@dataclass(frozen=True)
class PreparedSurfaceDonationOperation:
    kind: str
    prepared: object
    preview: dict


@dataclass(frozen=True)
class PreparedSurfaceCfdiOperation:
    kind: str
    prepared: object
    preview: dict


_CFDI_OPERATION_LABELS = {
    "purchase_utility_bank": "Compra de servicios pagada por banco",
    "sale_cash": "Venta cobrada en efectivo",
    "donation_bank": "Donativo recibido por banco",
}


def _cfdi_summary(source):
    parsed = source.parsed
    return {
        "id": source.id,
        "uuid": parsed.uuid,
        "document_number": parsed.document_number,
        "document_position": source.document_position,
        "issuer": {"rfc": parsed.issuer_rfc, "name": parsed.issuer_name},
        "receiver": {"rfc": parsed.receiver_rfc, "name": parsed.receiver_name},
        "issued_at": parsed.issued_at.isoformat(),
        "stamped_at": parsed.stamped_at.isoformat(),
        "currency": parsed.currency,
        "subtotal": str(parsed.subtotal),
        "discount": None if parsed.discount is None else str(parsed.discount),
        "total": str(parsed.total),
        "total_transferred": str(parsed.total_transferred),
        "total_withheld": str(parsed.total_withheld),
        "payment_form": parsed.payment_form,
        "payment_method": parsed.payment_method,
        "file_hash": parsed.sha256,
        "taxes": [
            {
                "direction": item.direction,
                "base": str(item.base),
                "tax_code": item.tax_code,
                "factor_type": item.factor_type,
                "rate_or_quota": None if item.rate_or_quota is None else str(item.rate_or_quota),
                "amount": None if item.amount is None else str(item.amount),
            }
            for item in parsed.taxes
        ],
        "imported_at": source.imported_at.isoformat(),
        "coverage": "CFDI 4.0 de ingreso en MXN; validación estructural local, sin consulta SAT ni timbrado.",
    }


def import_surface_cfdi(payload):
    encoded = payload.get("xml_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("an XML file is required")
    try:
        xml_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("xml_base64 must be valid base64") from exc
    with _storage.get_session() as session:
        result = _application.import_cfdi_source(session, xml_bytes)
    return {"duplicate": result.duplicate, "source": _cfdi_summary(result.source)}


def list_surface_cfdi_sources():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        ids = session.exec(
            select(CfdiSourceRecord.id)
            .where(CfdiSourceRecord.entity_id == entity.id)
            .order_by(CfdiSourceRecord.issued_at, CfdiSourceRecord.id)
        ).all()
        return [
            _cfdi_summary(_application.load_cfdi_source(session, entity.id, source_id))
            for source_id in ids
        ]


def prepare_surface_cfdi(payload):
    uuid = payload.get("uuid")
    operation_kind = payload.get("operation_kind")
    if operation_kind not in _CFDI_OPERATION_LABELS:
        raise ValueError("select a supported economic operation")
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        matches = session.exec(
            select(CfdiSourceRecord).where(
                CfdiSourceRecord.entity_id == entity.id,
                CfdiSourceRecord.uuid == uuid,
            )
        ).all()
        if len(matches) != 1:
            raise LookupError("CFDI UUID must identify exactly one imported source")
        source = _application.load_cfdi_source(session, entity.id, matches[0].id)
        if operation_kind == "donation_bank":
            donor = session.get(ThirdPartyRecord, source.third_party_id)
            if donor is None:
                raise LookupError("CFDI counterparty is no longer available")
            if payload.get("donor_name") not in (None, donor.name):
                raise ValueError("selected donor differs from the RFC-identified counterparty")
            donation_payload = {**payload, "donor_name": donor.name}
            entity, donor, bank, program, fund, funding_source = _surface_donation_context(
                session, donation_payload, kind="monetary"
            )
            prepared = _application.prepare_cfdi_monetary_donation(
                session,
                source.id,
                donor_third_party_id=donor.id,
                bank_account_id=bank.id,
                fund_id=fund.id,
                funding_source_id=funding_source.id,
                program_id=program.id,
                purpose=payload.get("purpose"),
                is_restricted=(fund.restriction == "restricted"),
            )
            preview = {
                "operation": _CFDI_OPERATION_LABELS[operation_kind],
                "uuid": source.parsed.uuid,
                "document_number": source.parsed.document_number,
                "donor": donor.name,
                "posting_date": prepared.donation.decision.posting_date.isoformat(),
                "amount": str(prepared.donation.decision.fact.amount),
                "document_total": str(source.parsed.total),
                "tax_from_document": str(
                    source.parsed.total_transferred - source.parsed.total_withheld
                ),
                "extracted_from_xml": {
                    "donor": donor.name,
                    "amount": str(source.parsed.total),
                    "date": source.parsed.issued_at.date().isoformat(),
                    "document_number": source.parsed.document_number,
                    "uuid": source.parsed.uuid,
                    "payment_form": source.parsed.payment_form,
                },
                "completed_by_user": {
                    "bank": f"{bank.institution_name} · {bank.account_identifier}",
                    "fund": fund.name,
                    "funding_source": funding_source.name,
                    "program": program.name,
                    "restriction": fund.restriction,
                    "purpose": payload.get("purpose"),
                },
                "explanation": (
                    "Se reconocerá una sola operación AQR-009: banco e ingreso por "
                    "donativo; el CFDI será su único documento fuente."
                ),
                "requires_confirmation": True,
                "warning": "Importar no contabiliza. Confirmar usará exactamente esta evidencia y decisión.",
                "fiscality": "Impuestos del XML conservados como evidencia; tratamiento fiscal específico pendiente/no cubierto por la cobertura fiscal declarada.",
            }
            return PreparedSurfaceCfdiOperation(operation_kind, prepared, preview)
        prepared = _application.prepare_cfdi_accounting(session, source.id, operation_kind)
    preview = {
        "operation": _CFDI_OPERATION_LABELS[operation_kind],
        "uuid": source.parsed.uuid,
        "document_number": source.parsed.document_number,
        "counterparty": (
            source.parsed.issuer_name
            if source.document_position == "receiver"
            else source.parsed.receiver_name
        ),
        "posting_date": prepared.decision.posting_date.isoformat(),
        "amount": str(prepared.decision.fact.amount),
        "document_total": str(source.parsed.total),
        "tax_from_document": str(source.parsed.total_transferred - source.parsed.total_withheld),
        "explanation": prepared.decision.explanation.professional_summary,
        "requires_confirmation": True,
        "warning": "Importar no contabiliza. Confirmar usará exactamente esta evidencia y decisión.",
        "fiscality": "Importes fiscales extraídos como evidencia; tratamiento fiscal específico pendiente/no cubierto por la cobertura fiscal declarada.",
    }
    return PreparedSurfaceCfdiOperation(operation_kind, prepared, preview)


def cfdi_professional_preview(value):
    if not isinstance(value, PreparedSurfaceCfdiOperation):
        raise TypeError("value must be PreparedSurfaceCfdiOperation")
    result = dict(value.preview)
    decision = (
        value.prepared.donation.decision
        if value.kind == "donation_bank"
        else value.prepared.decision
    )
    result["decision"] = _decision_professional_preview(value.kind, decision)
    return result


def confirm_surface_cfdi(value):
    if not isinstance(value, PreparedSurfaceCfdiOperation):
        raise TypeError("value must be PreparedSurfaceCfdiOperation")
    if value.kind == "donation_bank":
        return _application.confirm_cfdi_monetary_donation(value.prepared)
    return _application.confirm_cfdi_accounting(value.prepared)


def load_surface_cfdi_professional(uuid):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        source_row = session.exec(
            select(CfdiSourceRecord).where(
                CfdiSourceRecord.entity_id == entity.id,
                CfdiSourceRecord.uuid == uuid,
            )
        ).one_or_none()
        if source_row is None:
            raise LookupError("CFDI source not found")
        source = _application.load_cfdi_source(session, entity.id, source_row.id)
        link = session.exec(
            select(CfdiSourceLinkRecord).where(CfdiSourceLinkRecord.cfdi_source_id == source.id)
        ).one_or_none()
        document_id = None if link is None else link.document_reference_id
        document = None if document_id is None else session.get(DocumentReferenceRecord, document_id)
        entry_id = None if document is None else document.entry_id
        donation_id = None
        if entry_id is not None:
            line_ids = session.exec(
                select(JournalLine.id).where(JournalLine.entry_id == entry_id)
            ).all()
            receipt = session.exec(
                select(FundReceiptRecord).where(
                    FundReceiptRecord.journal_line_id.in_(line_ids)
                )
            ).first()
            donation_id = None if receipt is None else receipt.donation_id
        ledger_amount = None
        if entry_id is not None:
            ledger_amount = str(sum(
                (Decimal(line.debit) for line in session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()),
                Decimal("0"),
            ))
    donation = (
        None
        if donation_id is None
        else load_surface_donation_professional("monetary", donation_id)
    )
    return {
        "source": _cfdi_summary(source),
        "document_reference_id": document_id,
        "accounting": None if entry_id is None else load_professional_operation(entry_id),
        "donation": donation,
        "evidence_vs_accounting": {
            "document_amount": str(source.parsed.total),
            "ledger_amount": ledger_amount,
            "same_document_reference_id": (
                donation is not None and donation["document"]["id"] == document_id
            ),
        },
        "fiscality": {
            "supported": False,
            "declared_xml_taxes": _cfdi_summary(source)["taxes"],
            "limitation": "La evidencia XML no determina por sí sola el tratamiento fiscal aplicable.",
        },
        "status": "imported_unposted" if entry_id is None else "linked_to_posted_accounting",
        "distinction": "El XML es evidencia externa; JournalEntry/JournalLine son la autoridad contable; la clasificación económica fue confirmada por el usuario.",
    }


# Only immediate operations may use the generic surface path. Credit origins and
# settlements require the dedicated AQR-006 provenance workflow below.
_OPERATION_KINDS = (
    CommonOperationKind("sale_cash", "Venta cobrada en efectivo", "sale", "cash"),
    CommonOperationKind("utility_bank", "Pago de servicios desde banco", "utility_expense", "bank"),
    CommonOperationKind("donation_bank", "Donativo monetario recibido por banco", "donation", "bank"),
    CommonOperationKind("donation_inkind", "Donativo en especie: activo durable", "inkind_donation", "noncash"),
)
_OPERATION_BY_KEY = {item.key: item for item in _OPERATION_KINDS}


def list_common_operation_kinds():
    return _OPERATION_KINDS


def _amount(value):
    if type(value) is Decimal:
        result = value
    elif type(value) is str:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount must be exact decimal text") from exc
    else:
        raise TypeError("amount must be exact decimal text")
    if not result.is_finite() or result <= Decimal("0"):
        raise ValueError("amount must be finite and greater than zero")
    return result


def _date(value, field_name="posting_date"):
    if type(value) is date:
        return value
    if type(value) is not str:
        raise TypeError(f"{field_name} must be ISO date text")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _datetime(value, field_name):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be ISO date text") from exc
    else:
        raise TypeError(f"{field_name} must be ISO date text")
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def _named_one(rows, value, label, attribute="name"):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    matches = [row for row in rows if getattr(row, attribute) == value.strip()]
    if len(matches) != 1:
        raise LookupError(f"{label} must identify exactly one registered choice")
    return matches[0]


def list_surface_donation_options():
    """Return human-readable choices; this projection performs no writes."""
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        donors = session.exec(
            select(ThirdPartyRecord).where(
                ThirdPartyRecord.entity_id == entity.id,
                ThirdPartyRecord.is_active.is_(True),
            ).order_by(ThirdPartyRecord.name, ThirdPartyRecord.id)
        ).all()
        banks = session.exec(
            select(BankAccountRecord).where(
                BankAccountRecord.entity_id == entity.id,
                BankAccountRecord.is_active.is_(True),
            ).order_by(BankAccountRecord.institution_name, BankAccountRecord.account_identifier)
        ).all()
        programs = session.exec(
            select(ProgramRecord).where(ProgramRecord.entity_id == entity.id).order_by(ProgramRecord.name, ProgramRecord.id)
        ).all()
        funds = session.exec(
            select(FundRecord).where(FundRecord.entity_id == entity.id).order_by(FundRecord.name, FundRecord.id)
        ).all()
        sources = session.exec(
            select(FundingSourceRecord).where(FundingSourceRecord.entity_id == entity.id).order_by(FundingSourceRecord.name, FundingSourceRecord.id)
        ).all()
    return {
        "donors": [_party_dict(item) for item in donors],
        "banks": [
            {
                "id": item.id,
                "institution_name": item.institution_name,
                "account_identifier": item.account_identifier,
                "currency": item.currency,
            }
            for item in banks
        ],
        "programs": [{"id": item.id, "name": item.name} for item in programs],
        "funds": [
            {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "restriction": item.restriction,
                "program_id": item.program_id,
            }
            for item in funds
        ],
        "funding_sources": [{"id": item.id, "name": item.name} for item in sources],
    }


def _surface_donation_context(session, payload, *, kind):
    entity = _application.get_active_entity(session)
    if entity is None or entity.id is None:
        raise LookupError("active Entity is required")
    donor = _named_one(
        session.exec(select(ThirdPartyRecord).where(ThirdPartyRecord.entity_id == entity.id, ThirdPartyRecord.is_active.is_(True))).all(),
        payload.get("donor_name"),
        "donor name",
    )
    programs = session.exec(select(ProgramRecord).where(ProgramRecord.entity_id == entity.id)).all()
    program = _named_one(programs, payload.get("program_name"), "program name")
    funds = session.exec(select(FundRecord).where(FundRecord.entity_id == entity.id)).all()
    fund = _named_one(funds, payload.get("fund_name"), "fund name") if payload.get("fund_name") else None
    if kind == "monetary" and fund is None:
        raise ValueError("fund name is required for a monetary donation")
    if fund is not None and fund.program_id not in (None, program.id):
        raise ValueError("selected fund does not allow the selected program")
    if fund is not None and payload.get("restriction") and fund.restriction != payload["restriction"]:
        raise ValueError("selected restriction does not match the selected fund")
    sources = session.exec(select(FundingSourceRecord).where(FundingSourceRecord.entity_id == entity.id)).all()
    source = _named_one(sources, payload.get("funding_source_name"), "funding source name") if kind == "monetary" else None
    bank = None
    if kind == "monetary":
        banks = session.exec(select(BankAccountRecord).where(BankAccountRecord.entity_id == entity.id, BankAccountRecord.is_active.is_(True))).all()
        bank = _named_one(banks, payload.get("bank_account_identifier"), "bank account", "account_identifier") if payload.get("bank_account_identifier") else None
        if bank is None:
            raise ValueError("bank account is required")
        if bank.currency != "MXN":
            raise ValueError("AQR-009 surface supports MXN bank accounts only")
    return entity, donor, bank, program, fund, source


def _surface_donation_preview(kind, prepared, context):
    amount = str(prepared.decision.fact.amount)
    common = {
        "operation": "Donativo monetario recibido por banco" if kind == "monetary" else "Donativo en especie: activo durable",
        "kind": kind,
        "amount": amount,
        "posting_date": prepared.decision.posting_date.isoformat(),
        "donor": context["donor"].name,
        "document_type": prepared.document_type,
        "document_number": prepared.document_number,
        "document_date": prepared.document_date.date().isoformat(),
        "fund": None if context["fund"] is None else context["fund"].name,
        "funding_source": None if context["source"] is None else context["source"].name,
        "program": context["program"].name,
        "restriction": None if context["fund"] is None else context["fund"].restriction,
        "requires_confirmation": True,
        "fiscality": "Tratamiento contable determinado. Tratamiento fiscal específico pendiente/no cubierto por la cobertura fiscal declarada.",
    }
    if kind == "monetary":
        common.update({
            "bank": f"{context['bank'].institution_name} · {context['bank'].account_identifier}",
            "cash_or_bank": "Banco",
            "explanation": f"Se reconocerá un donativo monetario de {amount} por banco para {context['program'].name}.",
        })
    else:
        common.update({
            "asset": prepared.asset_name,
            "quantity": None if prepared.quantity is None else str(prepared.quantity),
            "valuation_method": prepared.valuation_method,
            "evidence": prepared.valuation_evidence,
            "cash_or_bank": "Sin efectivo ni banco",
            "explanation": f"Se reconocerá un activo durable por {amount} y un ingreso por donativo; no habrá movimiento de efectivo ni banco.",
        })
    return common


def prepare_surface_monetary_donation(payload):
    with _storage.get_session() as session:
        entity, donor, bank, program, fund, source = _surface_donation_context(session, payload, kind="monetary")
        for field in ("document_type", "document_number"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError(f"{field} is required")
        prepared = _application.prepare_monetary_donation(
            session,
            _amount(payload.get("amount")),
            _datetime(payload.get("date"), "date"),
            donor_third_party_id=donor.id,
            document_type=payload.get("document_type"),
            document_number=payload.get("document_number"),
            document_date=_datetime(payload.get("document_date"), "document_date"),
            fund_id=fund.id if fund is not None else None,
            funding_source_id=source.id,
            program_id=program.id,
            purpose=payload.get("purpose"),
            is_restricted=(fund is not None and fund.restriction == "restricted"),
            bank_account_id=bank.id,
        )
        context = {"entity": entity, "donor": donor, "bank": bank, "program": program, "fund": fund, "source": source}
    return PreparedSurfaceDonationOperation("monetary", prepared, _surface_donation_preview("monetary", prepared, context))


def prepare_surface_inkind_donation(payload):
    with _storage.get_session() as session:
        entity, donor, _bank, program, fund, _source = _surface_donation_context(session, payload, kind="inkind")
        for field in ("description", "valuation_method", "valuation_evidence", "document_type", "document_number", "asset_code", "asset_name"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError(f"{field} is required")
        prepared = _application.prepare_inkind_donation(
            session,
            _amount(payload.get("valuation_amount")),
            _datetime(payload.get("date"), "date"),
            donor_third_party_id=donor.id,
            document_type=payload.get("document_type"),
            document_number=payload.get("document_number"),
            document_date=_datetime(payload.get("document_date"), "document_date"),
            received_at=_datetime(payload.get("date"), "date"),
            description=payload.get("description"),
            quantity=None if payload.get("quantity") in (None, "") else _amount(payload.get("quantity")),
            valuation_method=payload.get("valuation_method"),
            valuation_evidence=payload.get("valuation_evidence"),
            external_reference=payload.get("external_reference") or payload.get("document_number"),
            asset_code=payload.get("asset_code"),
            asset_name=payload.get("asset_name") or payload.get("description"),
            useful_life_months=int(payload.get("useful_life_months")),
            program_id=program.id,
            fund_id=None if fund is None else fund.id,
        )
        context = {"entity": entity, "donor": donor, "bank": None, "program": program, "fund": fund, "source": None}
    return PreparedSurfaceDonationOperation("inkind", prepared, _surface_donation_preview("inkind", prepared, context))


def donation_professional_preview(value):
    if not isinstance(value, PreparedSurfaceDonationOperation):
        raise TypeError("value must be PreparedSurfaceDonationOperation")
    result = _decision_professional_preview(
        "donation" if value.kind == "monetary" else "inkind_donation",
        value.prepared.decision,
    )
    result["common"] = value.preview
    result["donation" if value.kind == "monetary" else "inkind_donation"] = value.preview
    result["provenance"] = "canonical JournalLine after confirmation"
    return result


def confirm_surface_donation(value):
    if not isinstance(value, PreparedSurfaceDonationOperation):
        raise TypeError("value must be PreparedSurfaceDonationOperation")
    if value.kind == "monetary":
        return _json_value(_application.confirm_monetary_donation(value.prepared))
    if value.kind == "inkind":
        return _json_value(_application.confirm_inkind_donation(value.prepared))
    raise ValueError("unsupported donation kind")


def _named_record(record, name_fields=("name",)):
    if record is None:
        return None
    return {"id": record.id, **{field: getattr(record, field) for field in name_fields}}


def load_surface_donation_professional(kind, donation_id):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        if kind == "monetary":
            trace = _application.load_monetary_donation_trace(session, entity.id, donation_id)
            operation = load_professional_operation(trace["ledger"]["entry_id"])
            receipt = trace["fund_receipt"]
            fund = session.get(FundRecord, receipt["fund_id"])
            source = session.get(FundingSourceRecord, receipt["funding_source_id"])
            program = None if fund is None or fund.program_id is None else session.get(ProgramRecord, fund.program_id)
            donor_id = trace["donation"]["donor_third_party_id"]
            donor = None if donor_id is None else session.get(ThirdPartyRecord, donor_id)
            document = operation["documents"][0] if operation["documents"] else trace["document"]
            return {
                "kind": "monetary",
                "donation": trace["donation"],
                "donor": _named_record(donor),
                "document": document,
                "fund": _named_record(fund, ("name", "code", "restriction")),
                "funding_source": _named_record(source),
                "program": _named_record(program),
                "restriction": None if fund is None else fund.restriction,
                "fund_receipt": receipt,
                "ledger": {
                    "entry_id": operation["entry_id"],
                    "state": operation["state"],
                    "lines": operation["lines"],
                    "reversal_entry_id": None if operation["reversal"] is None else operation["reversal"]["reversal_entry_id"],
                },
                "audit": operation["audit"],
                "reversal": operation["reversal"],
                "fiscality": {
                    "supported": False,
                    "limitation": "Tratamiento contable determinado. Tratamiento fiscal específico pendiente/no cubierto por la cobertura fiscal declarada.",
                },
            }
        if kind == "inkind":
            trace = _application.load_inkind_donation_trace(session, entity.id, donation_id)
            operation = load_professional_operation(trace["ledger"]["entry_id"])
            item = session.get(InKindDonationRecord, donation_id)
            fund = None if item.fund_id is None else session.get(FundRecord, item.fund_id)
            program = None if item.program_id is None else session.get(ProgramRecord, item.program_id)
            donor = None if item.donor_third_party_id is None else session.get(ThirdPartyRecord, item.donor_third_party_id)
            document = operation["documents"][0] if operation["documents"] else trace["document"]
            cash_or_bank = [line for line in operation["lines"] if line["account_code"] in ("1101", "1102")]
            inkind = {
                "id": item.id,
                "entity_id": item.entity_id,
                "donor_third_party_id": item.donor_third_party_id,
                "document_reference_id": item.document_reference_id,
                "fund_id": item.fund_id,
                "program_id": item.program_id,
                "journal_line_id": item.journal_line_id,
                "fixed_asset_id": item.fixed_asset_id,
                "received_at": item.received_at,
                "description": item.description,
                "quantity": item.quantity,
                "valuation_amount": item.valuation_amount,
                "valuation_currency": item.valuation_currency,
                "valuation_method": item.valuation_method,
                "valuation_evidence": item.valuation_evidence,
                "external_reference": item.external_reference,
            }
            asset = trace["fixed_asset"]
            if asset is not None:
                persisted_asset = session.get(FixedAssetRecord, item.fixed_asset_id)
                asset = {
                    "id": persisted_asset.id,
                    "entity_id": persisted_asset.entity_id,
                    "code": persisted_asset.code,
                    "name": persisted_asset.name,
                    "acquisition_date": persisted_asset.acquisition_date.isoformat(),
                    "in_service_date": persisted_asset.in_service_date.isoformat(),
                    "acquisition_cost": persisted_asset.acquisition_cost,
                    "residual_value": persisted_asset.residual_value,
                    "useful_life_months": persisted_asset.useful_life_months,
                    "depreciation_method": persisted_asset.depreciation_method,
                    "is_active": persisted_asset.is_active,
                }
            return {
                "kind": "inkind",
                "inkind_donation": inkind,
                "donor": _named_record(donor),
                "document": document,
                "valuation": {
                    "amount": trace["inkind_donation"]["valuation_amount"],
                    "method": trace["inkind_donation"]["valuation_method"],
                    "evidence": trace["inkind_donation"]["valuation_evidence"],
                },
                "evidence": {"valuation": trace["inkind_donation"]["valuation_evidence"]},
                "fixed_asset": asset,
                "fund": _named_record(fund, ("name", "code", "restriction")),
                "program": _named_record(program),
                "restriction": None if fund is None else fund.restriction,
                "ledger": {
                    "entry_id": operation["entry_id"],
                    "state": operation["state"],
                    "lines": operation["lines"],
                    "cash_or_bank_lines": cash_or_bank,
                    "reversal_entry_id": None if operation["reversal"] is None else operation["reversal"]["reversal_entry_id"],
                },
                "cash_or_bank": cash_or_bank,
                "audit": operation["audit"],
                "reversal": operation["reversal"],
                "fiscality": {
                    "supported": False,
                    "limitation": "Tratamiento contable determinado. Tratamiento fiscal específico pendiente/no cubierto por la cobertura fiscal declarada.",
                },
            }
    raise ValueError("unsupported donation kind")


def prepare_common_operation(operation_key, amount, posting_date):
    """Prepare one immediate AQR-004 decision without persistence knowledge."""
    if type(operation_key) is not str or operation_key not in _OPERATION_BY_KEY:
        raise ValueError("unsupported operation_key")
    kind = _OPERATION_BY_KEY[operation_key]
    fact = _facts.EconomicFact(
        type=kind.fact_type,
        amount=_amount(amount),
        payment_method=kind.payment_method,
    )
    with _storage.get_session() as session:
        decision = _operations.prepare_accounting_operation(
            session,
            fact,
            _date(posting_date),
        )
    return PreparedSurfaceOperation(kind=kind, decision=decision)


def common_preview(prepared):
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    decision = prepared.decision
    return {
        "operation_key": prepared.kind.key,
        "operation": prepared.kind.label,
        "amount": str(decision.fact.amount),
        "posting_date": decision.posting_date.isoformat(),
        "explanation": decision.explanation.professional_summary,
        "concepts": list(decision.explanation.concepts),
        "requires_confirmation": True,
    }


def _decision_professional_preview(operation_key, decision):
    return {
        "operation_key": operation_key,
        "posting_date": decision.posting_date.isoformat(),
        "rule_id": decision.rule_id,
        "rule_version": decision.rule_version,
        "explanation": decision.explanation.professional_summary,
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "side": line.side,
                "amount": str(line.amount),
            }
            for line in decision.resolved_proposal.lines
        ],
    }


def professional_preview(prepared):
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    return _decision_professional_preview(prepared.kind.key, prepared.decision)


def confirm_and_post(prepared):
    if not isinstance(prepared, PreparedSurfaceOperation):
        raise TypeError("prepared must be PreparedSurfaceOperation")
    confirmed = _operations.confirm_accounting_operation(prepared.decision)
    return _operations.execute_accounting_operation(confirmed)


def _party_dict(party):
    return {
        "id": party.id,
        "name": party.name,
        "rfc": party.rfc,
        "party_type": party.party_type,
        "is_active": party.is_active,
    }


def list_surface_third_parties():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or type(entity.id) is not int:
            raise LookupError("active Entity is required")
        parties = _application.list_third_parties(session, entity.id)
    return [_party_dict(party) for party in parties]


def create_surface_third_party(name, party_type, rfc=None):
    from .third_party import ThirdParty
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None:
            raise LookupError("active Entity is required")
        party = ThirdParty(None, entity.id, name, rfc or None, None, None,
                           party_type, None, None, None, True)
        return _party_dict(_application.create_third_party(session, party))


def reverse_surface_operation(entry_id, reason, reversal_date):
    with _storage.get_session() as session:
        result = _application.reverse_posted_journal_entry(
            session, entry_id, reason, _date(reversal_date, "reversal_date"),
        )
        session.commit()
    return _json_value(result)


def _party_name(session, third_party_id):
    entity = _application.get_active_entity(session)
    if entity is None or type(entity.id) is not int:
        raise LookupError("active Entity is required")
    return _application.get_third_party(session, entity.id, third_party_id).name


def prepare_surface_open_item_origin(
    operation_key,
    amount,
    posting_date,
    third_party_id,
    due_date,
    document_type,
    document_number,
    document_date,
):
    with _storage.get_session() as session:
        prepared = _subledger.prepare_open_item_origin(
            session,
            operation_key,
            _amount(amount),
            _date(posting_date),
            third_party_id,
            _date(due_date, "due_date"),
            document_type,
            document_number,
            _date(document_date, "document_date"),
        )
        party_name = _party_name(session, third_party_id)
    label = "Venta a crédito" if prepared.kind == "receivable" else "Compra/gasto a crédito"
    return PreparedSurfaceSubledgerAction(
        action="origin",
        prepared=prepared,
        summary={
            "operation": label,
            "kind": prepared.kind,
            "third_party_id": third_party_id,
            "third_party_name": party_name,
            "amount": str(prepared.decision.fact.amount),
            "posting_date": prepared.decision.posting_date.isoformat(),
            "due_date": prepared.due_date.isoformat(),
            "document_type": prepared.document.document_type,
            "document_number": prepared.document.document_number,
        },
    )


def prepare_surface_open_item_application(
    open_item_id,
    amount,
    posting_date,
    document_type,
    document_number,
    document_date,
):
    with _storage.get_session() as session:
        item = _open_items.load_open_item(session, open_item_id, as_of=_date(posting_date))
        prepared = _subledger.prepare_open_item_application(
            session,
            open_item_id,
            _amount(amount),
            _date(posting_date),
            document_type,
            document_number,
            _date(document_date, "document_date"),
        )
    return PreparedSurfaceSubledgerAction(
        action="application",
        prepared=prepared,
        summary={
            "operation": "Cobro" if item.kind == "receivable" else "Pago",
            "kind": item.kind,
            "third_party_id": item.third_party_id,
            "third_party_name": item.third_party_name,
            "open_item_id": item.id,
            "document_origin": f"{item.document_type} {item.document_number}",
            "amount": str(prepared.decision.fact.amount),
            "open_balance_before": str(item.open_balance),
            "posting_date": prepared.decision.posting_date.isoformat(),
            "document_type": prepared.document.document_type,
            "document_number": prepared.document.document_number,
        },
    )


def prepare_surface_open_item_application_batch(
    allocations,
    posting_date,
    document_type,
    document_number,
    document_date,
):
    with _storage.get_session() as session:
        prepared = _subledger.prepare_open_item_application_batch(
            session,
            allocations,
            _date(posting_date),
            document_type,
            document_number,
            _date(document_date, "document_date"),
        )
        party_name = _party_name(session, prepared.third_party_id)
        item_summaries = []
        for allocation in prepared.allocations:
            item = _open_items.load_open_item(
                session,
                allocation.open_item_id,
                as_of=prepared.decision.posting_date,
            )
            item_summaries.append(
                {
                    "open_item_id": item.id,
                    "document_origin": f"{item.document_type} {item.document_number}",
                    "amount": str(allocation.amount),
                    "open_balance_before": str(item.open_balance),
                }
            )
    return PreparedSurfaceSubledgerAction(
        action="application_batch",
        prepared=prepared,
        summary={
            "operation": "Cobro aplicado a varias obligaciones" if prepared.kind == "receivable" else "Pago aplicado a varias obligaciones",
            "kind": prepared.kind,
            "third_party_id": prepared.third_party_id,
            "third_party_name": party_name,
            "amount": str(prepared.decision.fact.amount),
            "posting_date": prepared.decision.posting_date.isoformat(),
            "document_type": prepared.document.document_type,
            "document_number": prepared.document.document_number,
            "allocations": item_summaries,
        },
    )


def subledger_common_preview(value):
    if not isinstance(value, PreparedSurfaceSubledgerAction):
        raise TypeError("value must be PreparedSurfaceSubledgerAction")
    return {
        **value.summary,
        "explanation": value.prepared.decision.explanation.professional_summary,
        "requires_confirmation": True,
    }


def subledger_professional_preview(value):
    if not isinstance(value, PreparedSurfaceSubledgerAction):
        raise TypeError("value must be PreparedSurfaceSubledgerAction")
    result = _decision_professional_preview(value.action, value.prepared.decision)
    result["subledger"] = value.summary
    return result


def confirm_and_post_subledger(value):
    if not isinstance(value, PreparedSurfaceSubledgerAction):
        raise TypeError("value must be PreparedSurfaceSubledgerAction")
    if value.action == "origin":
        confirmed = _subledger.confirm_open_item_origin(value.prepared)
        return _json_value(_subledger.execute_open_item_origin(confirmed))
    if value.action == "application":
        confirmed = _subledger.confirm_open_item_application(value.prepared)
        return _json_value(_subledger.execute_open_item_application(confirmed))
    if value.action == "application_batch":
        confirmed = _subledger.confirm_open_item_application_batch(value.prepared)
        return _json_value(_subledger.execute_open_item_application_batch(confirmed))
    raise ValueError("unsupported subledger action")


def _document_dict(document):
    return {
        "id": document.id,
        "third_party_id": document.third_party_id,
        "document_type": document.document_type,
        "document_number": document.document_number,
        "issuer_name": document.issuer_name,
        "date": document.date.isoformat(),
        "file_hash": document.file_hash,
        "file_path": document.file_path,
        "external_url": document.external_url,
        "is_validated": document.is_validated,
        "validation_notes": document.validation_notes,
    }


def _fiscal_effect_dict(effect):
    return {
        "rule_key": effect.rule_key,
        "base": str(effect.base),
        "rate": str(effect.rate),
        "unit": effect.unit,
        "rule_effective_from": effect.rule_effective_from.isoformat(),
        "rule_effective_to": None if effect.rule_effective_to is None else effect.rule_effective_to.isoformat(),
        "rule_source_ref": effect.rule_source_ref,
        "exact_fiscal_amount": str(effect.exact_fiscal_amount),
        "rounding_policy_key": effect.rounding_policy_key,
        "rounding_quantizer": str(effect.rounding_quantizer),
        "rounding_mode": effect.rounding_mode,
        "rounding_source_ref": effect.rounding_source_ref,
        "rounded_fiscal_amount": str(effect.rounded_fiscal_amount),
        "fiscal_role": effect.fiscal_role,
        "fiscal_side": effect.fiscal_side,
    }


def _fiscal_dict(snapshot):
    if snapshot is None:
        return None
    provenance = snapshot.provenance
    omitted = snapshot.omitted_zero_fiscal_line
    return {
        "description": snapshot.description,
        "fact_type": provenance.fact_type,
        "fact_amount": str(provenance.fact_amount),
        "payment_method": provenance.payment_method,
        "effective_date": provenance.effective_date.isoformat(),
        "jurisdiction": provenance.jurisdiction,
        "regime": provenance.regime,
        "entity_type": provenance.entity_type,
        "amount_basis": provenance.amount_basis,
        "adjustment_role": provenance.adjustment_role,
        "effects": [_fiscal_effect_dict(effect) for effect in provenance.fiscal_effects],
        "zero_fiscal_line_policy": snapshot.zero_fiscal_line_policy,
        "omitted_zero_fiscal_line": None if omitted is None else {
            "account_role": omitted.account_role,
            "account_id": omitted.account_id,
            "account_code": omitted.account_code,
            "account_name": omitted.account_name,
            "side": omitted.side,
            "amount": str(omitted.amount),
        },
    }


def list_professional_operations(limit=50):
    with _storage.get_session() as session:
        rows = _operation_read.list_professional_accounting_operations(session, limit)
    return [
        {
            "entry_id": row.entry_id,
            "posting_date": row.posting_date.isoformat(),
            "concept": row.concept,
            "state": row.state,
            "period_id": row.period_id,
        }
        for row in rows
    ]


def load_professional_operation(entry_id):
    with _storage.get_session() as session:
        view = _operation_read.load_professional_accounting_operation(session, entry_id)
    return {
        "entry_id": view.entry_id,
        "posting_date": view.posting_date.isoformat(),
        "concept": view.concept,
        "state": view.state,
        "period": {
            "id": view.period.id,
            "year": view.period.year,
            "month": view.period.month,
            "start": view.period.start.isoformat(),
            "end": view.period.end.isoformat(),
            "state": view.period.state,
            "fiscal_year_state": view.period.fiscal_year_state,
        },
        "lines": [
            {
                "id": line.id,
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "debit": str(line.debit),
                "credit": str(line.credit),
                "description": line.description,
            }
            for line in view.lines
        ],
        "documents": [_document_dict(document) for document in view.documents],
        "audit": None if view.audit is None else {
            "id": view.audit.id,
            "event_type": view.audit.event_type,
            "timestamp": view.audit.timestamp.isoformat(),
            "details": view.audit.details,
        },
        "reversal": None if view.reversal is None else {
            "original_entry_id": view.reversal.original_entry_id,
            "reversal_entry_id": view.reversal.reversal_entry_id,
            "reason": view.reversal.reason,
        },
        "fiscal_audit": _fiscal_dict(view.fiscal_audit),
    }


def _application_view_dict(application):
    return {
        "id": application.id,
        "entry_id": application.entry_id,
        "line_id": application.line_id,
        "document_reference_id": application.document_reference_id,
        "posting_date": application.posting_date.isoformat(),
        "amount": str(application.amount),
        "is_effective": application.is_effective,
    }


def _open_item_dict(item):
    return {
        "id": item.id,
        "third_party_id": item.third_party_id,
        "third_party_name": item.third_party_name,
        "kind": item.kind,
        "source_entry_id": item.source_entry_id,
        "source_line_id": item.source_line_id,
        "source_document_reference_id": item.source_document_reference_id,
        "document_type": item.document_type,
        "document_number": item.document_number,
        "posting_date": item.posting_date.isoformat(),
        "due_date": item.due_date.isoformat(),
        "original_amount": str(item.original_amount),
        "applied_amount": str(item.applied_amount),
        "open_balance": str(item.open_balance),
        "status": item.status,
        "aging_bucket": item.aging_bucket,
        "applications": [_application_view_dict(app) for app in item.applications],
    }


def list_surface_open_items(kind=None, as_of=None, include_settled=True):
    value = None if as_of in (None, "") else _date(as_of, "as_of")
    with _storage.get_session() as session:
        items = _open_items.list_open_items(
            session,
            kind=kind,
            as_of=value,
            include_settled=include_settled,
        )
    return [_open_item_dict(item) for item in items]


def load_surface_open_item(open_item_id, as_of=None):
    value = None if as_of in (None, "") else _date(as_of, "as_of")
    with _storage.get_session() as session:
        item = _open_items.load_open_item(session, open_item_id, as_of=value)
    return _open_item_dict(item)


def get_surface_subledger_reconciliation(kind, as_of=None):
    value = None if as_of in (None, "") else _date(as_of, "as_of")
    with _storage.get_session() as session:
        result = _open_items.reconcile_subledger(session, kind, as_of=value)
    return _json_value(result.__dict__ | {"is_reconciled": result.is_reconciled})


def load_professional_open_item(open_item_id, as_of=None):
    item = load_surface_open_item(open_item_id, as_of=as_of)
    source = load_professional_operation(item["source_entry_id"])
    applications = [
        {
            "application": application,
            "operation": load_professional_operation(application["entry_id"]),
        }
        for application in item["applications"]
    ]
    reconciliation = get_surface_subledger_reconciliation(item["kind"], as_of=as_of)
    return {
        "open_item": item,
        "source_operation": source,
        "application_operations": applications,
        "reconciliation": reconciliation,
    }


def _json_value(value):
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def get_professional_trial_balance(as_of=None):
    value = None if as_of in (None, "") else _date(as_of, "as_of")
    return _json_value(_application.get_trial_balance(as_of=value))


def get_surface_entity():
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
    if entity is None:
        return None
    return {
        "id": entity.id,
        "name": entity.name,
        "rfc": entity.rfc,
        "legal_personality": entity.legal_personality,
        "legal_form": entity.legal_form,
        "economic_purpose": entity.profile.economic_purpose,
        "is_donor_authorized": entity.profile.is_donor_authorized,
    }


def list_surface_bank_accounts():
    from .banking_models import BankAccountRecord
    with _storage.get_session() as session:
        rows = session.exec(select(BankAccountRecord).order_by(BankAccountRecord.id)).all()
    return [_json_value(row.__dict__) for row in rows]


def create_surface_bank_account(institution_name, account_identifier, currency):
    from .banking_models import BankAccountRecord
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None:
            raise LookupError("active Entity is required")
        binding = session.exec(select(AccountRoleBinding).where(AccountRoleBinding.role == "bank")).first()
        if binding is None or binding.account_id is None:
            raise LookupError("bank account binding is required")
        account = _banks.create_bank_account(session, BankAccount(
            None, entity.id, binding.account_id, institution_name, account_identifier, currency,
        ))
    return _json_value(account)


def import_surface_bank_csv(bank_account_id, source_name, content):
    with _storage.get_session() as session:
        statement_id = _banks.import_bank_csv(session, bank_account_id, source_name, content)
    return {"statement_id": statement_id, "bank_account_id": bank_account_id}


def create_surface_reconciliation(bank_account_id, statement_id, as_of):
    with _storage.get_session() as session:
        reconciliation_id = _reconciliations.create_reconciliation(
            session, bank_account_id, statement_id, _date(as_of, "as_of"),
        )
    return {"reconciliation_id": reconciliation_id}


def match_surface_bank_transaction(reconciliation_id, bank_transaction_id, journal_line_id):
    with _storage.get_session() as session:
        match_id = _reconciliations.match_transaction(
            session, reconciliation_id, bank_transaction_id, journal_line_id,
        )
    return {"match_id": match_id, "reconciliation_id": reconciliation_id}


def revoke_surface_bank_match(match_id, reason):
    with _storage.get_session() as session:
        revocation_id = _reconciliations.revoke_match(session, match_id, reason)
    return {"revocation_id": revocation_id, "match_id": match_id}


def load_surface_reconciliation(reconciliation_id):
    with _storage.get_session() as session:
        return _json_value(_reconciliations.load_reconciliation(session, reconciliation_id))


def execute_surface_bank_transfer(source_bank_account_id, destination_bank_account_id, amount, posting_date, description):
    with _storage.get_session() as session:
        return _json_value(_bank_transfer.execute_bank_transfer(
            session, source_bank_account_id, destination_bank_account_id,
            _amount(amount), _date(posting_date), description,
        ))


def list_surface_funds():
    with _storage.get_session() as session:
        rows = session.exec(select(FundRecord).order_by(FundRecord.id)).all()
    return [_json_value(row.__dict__) for row in rows]


def create_surface_fund(payload):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        program_id = payload.get("program_id")
        if program_id is None and payload.get("program_name"):
            from .models import ProgramRecord
            programs = session.exec(select(ProgramRecord).where(ProgramRecord.entity_id == entity.id, ProgramRecord.name == payload["program_name"])).all()
            if len(programs) != 1: raise LookupError("program name must identify exactly one Program")
            program_id = programs[0].id
        fund = _funds.create_fund(session, Fund(None, entity.id, payload.get("code"), payload.get("name"), payload.get("restriction"), payload.get("purpose"), program_id))
    return _json_value(fund)


def create_surface_funding_source(payload):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        source = _funds.create_funding_source(session, FundingSource(None, entity.id, payload.get("name"), payload.get("donor_third_party_id"), payload.get("external_reference")))
    return _json_value(source)


def list_surface_funding_sources():
    with _storage.get_session() as session:
        rows = session.exec(select(FundingSourceRecord).order_by(FundingSourceRecord.id)).all()
    return [_json_value(row.__dict__) for row in rows]


def list_surface_fund_candidates(kind):
    if kind not in ("receipt", "application"): raise ValueError("kind must be receipt or application")
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        result = []
        for entry in session.exec(select(JournalEntry).where(JournalEntry.state == "posted").order_by(JournalEntry.date, JournalEntry.id)).all():
            context = _funds._posting_context(session, entry.id)
            if context[0] != "active": continue
            if kind == "receipt" and context[1] != "donation": continue
            if kind == "application" and context[1] not in {"utility_expense", "utility_expense_incurred", "supplier_payment"}: continue
            for line in session.exec(select(JournalLine).where(JournalLine.entry_id == entry.id).order_by(JournalLine.id)).all():
                if kind == "receipt" and Decimal(line.credit) <= 0: continue
                if kind == "application" and Decimal(line.debit) <= 0: continue
                amount = Decimal(line.debit) if Decimal(line.debit) else Decimal(line.credit)
                if amount <= 0: continue
                donation = session.exec(select(DonationRecord).where(DonationRecord.entity_id == entity.id, DonationRecord.date == entry.date.isoformat(), DonationRecord.amount == str(amount))).first() if kind == "receipt" else None
                result.append({"entry_id": entry.id, "journal_line_id": line.id, "date": entry.date.date().isoformat(), "concept": entry.concept, "amount": str(amount), "donation_id": None if donation is None else donation.id})
    return result


def record_surface_fund_receipt(payload):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        line = session.get(JournalLine, payload.get("journal_line_id"))
        if line is None: raise LookupError("selected receipt is not available")
        entry = session.get(JournalEntry, line.entry_id)
        amount = Decimal(line.credit) if Decimal(line.credit) else Decimal(line.debit)
        receipt = _funds.record_fund_receipt(session, FundReceipt(None, entity.id, payload.get("fund_id"), payload.get("funding_source_id"), line.id, amount, entry.date, payload.get("donation_id")))
    return _json_value(receipt)


def record_surface_fund_application(payload):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        line = session.get(JournalLine, payload.get("journal_line_id"))
        if line is None: raise LookupError("selected application is not available")
        entry = session.get(JournalEntry, line.entry_id)
        program_id = payload.get("program_id")
        if program_id is None and payload.get("program_name"):
            programs = session.exec(select(ProgramRecord).where(ProgramRecord.entity_id == entity.id, ProgramRecord.name == payload["program_name"])).all()
            if len(programs) != 1: raise LookupError("program name must identify exactly one Program")
            program_id = programs[0].id
        application = _funds.record_fund_application(session, FundApplication(None, entity.id, payload.get("fund_id"), program_id, line.id, _amount(payload.get("amount")), entry.date, payload.get("receipt_id"), payload.get("purpose")))
    return _json_value(application)


def get_surface_fund_balance(fund_id, as_of=None):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        return _json_value(_funds.load_fund_balance(session, entity.id, fund_id, _date(as_of, "as_of")))


def get_surface_fund_traceability(fund_id, as_of):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        return _json_value(_funds.load_fund_traceability(session, entity.id, fund_id, _date(as_of, "as_of")))


__all__ = [
    "CommonOperationKind",
    "PreparedSurfaceOperation",
    "PreparedSurfaceSubledgerAction",
    "PreparedSurfaceDonationOperation",
    "PreparedSurfaceCfdiOperation",
    "import_surface_cfdi",
    "list_surface_cfdi_sources",
    "prepare_surface_cfdi",
    "cfdi_professional_preview",
    "confirm_surface_cfdi",
    "load_surface_cfdi_professional",
    "list_common_operation_kinds",
    "list_surface_donation_options",
    "prepare_surface_monetary_donation",
    "prepare_surface_inkind_donation",
    "donation_professional_preview",
    "confirm_surface_donation",
    "load_surface_donation_professional",
    "prepare_common_operation",
    "common_preview",
    "professional_preview",
    "confirm_and_post",
    "list_surface_third_parties",
    "prepare_surface_open_item_origin",
    "prepare_surface_open_item_application",
    "prepare_surface_open_item_application_batch",
    "subledger_common_preview",
    "subledger_professional_preview",
    "confirm_and_post_subledger",
    "list_surface_open_items",
    "load_surface_open_item",
    "load_professional_open_item",
    "get_surface_subledger_reconciliation",
    "list_professional_operations",
    "load_professional_operation",
    "get_professional_trial_balance",
    "get_surface_entity",
    "list_surface_bank_accounts",
    "create_surface_bank_account",
    "import_surface_bank_csv",
    "create_surface_reconciliation",
    "match_surface_bank_transaction",
    "revoke_surface_bank_match",
    "load_surface_reconciliation",
    "execute_surface_bank_transfer",
    "list_surface_funds",
    "create_surface_fund",
    "create_surface_funding_source",
    "list_surface_funding_sources",
    "list_surface_fund_candidates",
    "record_surface_fund_receipt",
    "record_surface_fund_application",
    "get_surface_fund_balance",
    "get_surface_fund_traceability",
]
