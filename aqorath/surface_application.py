"""Application-facing service for the local presentation.

Presentation receives JSON-compatible projections and delegates all accounting to
existing Application authorities. AQR-006 adds operational CxC/CxP workflows here
without moving account, period, reversal, fiscal or persistence rules into UI code.

Generic AQR-004 credit/collection/payment facts remain valid internal foundations,
but the common surface no longer exposes them directly: new CxC/CxP movements must
carry ThirdParty/document/open-item provenance through the AQR-006 use cases.
"""

from dataclasses import dataclass, asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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
from .fund import Fund, FundingSource
from .fund_models import FundRecord, FundingSourceRecord
from .models import AccountRoleBinding
from sqlmodel import select


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


# Only immediate operations may use the generic surface path. Credit origins and
# settlements require the dedicated AQR-006 provenance workflow below.
_OPERATION_KINDS = (
    CommonOperationKind("sale_cash", "Venta cobrada en efectivo", "sale", "cash"),
    CommonOperationKind("utility_bank", "Pago de servicios desde banco", "utility_expense", "bank"),
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


def get_surface_fund_balance(fund_id, as_of=None):
    with _storage.get_session() as session:
        entity = _application.get_active_entity(session)
        if entity is None or entity.id is None: raise LookupError("active Entity is required")
        return _json_value(_funds.load_fund_balance(session, entity.id, fund_id, _date(as_of, "as_of")))


__all__ = [
    "CommonOperationKind",
    "PreparedSurfaceOperation",
    "PreparedSurfaceSubledgerAction",
    "list_common_operation_kinds",
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
    "get_surface_fund_balance",
]
