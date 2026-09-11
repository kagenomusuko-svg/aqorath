"""AQR-012 Application use cases for perpetual inventory and moving-average cost.

One confirmed inventory operation stages ledger, physical movement, source document,
subledger relation when applicable, CFDI evidence when supplied, and audit in one
transaction. JournalEntry/JournalLine remain the sole monetary authority.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import uuid4

from sqlmodel import select

from . import audit_event_repository as _audit
from . import cfdi_source_repository as _cfdi
from . import core as _core
from . import document_reference_repository as _documents
from . import inventory_fiscal_composition as _inventory_fiscal
from . import inventory_repository as _inventory
from . import open_item_repository as _open_items
from . import storage as _storage
from .account_bindings import get_account_bindings
from .accounting_period_repository import require_open_period
from .audit_event import AuditEvent
from .banking_models import BankAccountRecord
from .document_reference import DocumentReference
from .inventory import (
    InventoryState,
    MerchandisePurchaseFact,
    MerchandiseSaleFact,
    apply_purchase,
    apply_sale,
    money,
)
from .inventory_models import InventoryMovementRecord
from .models import Account, JournalEntry, JournalLine, ThirdPartyRecord


@dataclass(frozen=True)
class InventoryDocumentInput:
    document_type: str
    document_number: str
    document_date: date
    issuer_name: str | None = None

    def __post_init__(self):
        if type(self.document_type) is not str or not self.document_type.strip():
            raise ValueError("document_type must be nonblank")
        if type(self.document_number) is not str or not self.document_number.strip():
            raise ValueError("document_number must be nonblank")
        if type(self.document_date) is not date:
            raise TypeError("document_date must be date")
        if self.issuer_name is not None and (
            type(self.issuer_name) is not str or not self.issuer_name.strip()
        ):
            raise ValueError("issuer_name must be nonblank or None")


@dataclass(frozen=True)
class PreparedInventoryOperation:
    operation_id: str
    kind: str
    fact: object
    product_name: str
    before: InventoryState
    after: InventoryState
    revenue_or_purchase_amount: Decimal
    inventory_cost: Decimal
    document: InventoryDocumentInput | None
    cfdi_source_id: int | None
    due_date: date | None
    explanation: str
    bank_account_id: int | None = None
    fiscal_prepared: object | None = None


@dataclass(frozen=True)
class ConfirmedInventoryOperation:
    prepared: PreparedInventoryOperation
    fiscal_confirmed: object | None = None


_SETTLEMENT_PURCHASE = {"bank": "bank", "cash": "cash", "credit": "accounts_payable"}
_SETTLEMENT_SALE = {"bank": "bank", "cash": "cash", "credit": "accounts_receivable"}


def _party(session, entity_id, party_id, kind):
    party = session.get(ThirdPartyRecord, party_id)
    if party is None or party.entity_id != entity_id:
        raise LookupError(f"{kind} ThirdParty does not belong to active Entity")
    if party.is_active is not True:
        raise ValueError(f"{kind} ThirdParty must be active")
    allowed = {"supplier", "creditor", "other"} if kind == "supplier" else {"customer", "debtor", "other"}
    if party.party_type not in allowed:
        raise ValueError(f"ThirdParty type is not compatible with {kind}")
    return party


def _check_open_period(session, entity_id, operation_date):
    entity = _inventory.require_inventory_entity(session, entity_id)
    moment = datetime.combine(operation_date, time.min, tzinfo=timezone.utc)
    require_open_period(session, moment, None)
    return entity


def _bank_account(session, entity_id, settlement_method, bank_account_id):
    if bank_account_id is None:
        return None
    if settlement_method != "bank":
        raise ValueError("bank_account_id is only valid for bank settlement")
    if type(bank_account_id) is not int or bank_account_id <= 0:
        raise ValueError("bank_account_id must be a positive integer or None")
    row = session.get(BankAccountRecord, bank_account_id)
    if row is None or row.entity_id != entity_id:
        raise LookupError("bank account does not belong to active Entity")
    if row.is_active is not True:
        raise ValueError("bank account must be active")
    if row.currency != "MXN":
        raise ValueError("AQR-012 V1 bank settlement requires MXN bank account")
    account = session.get(Account, row.ledger_account_id)
    if account is None:
        raise LookupError("bank account ledger Account not found")
    return row, account


def _validate_cfdi(
    session,
    entity_id,
    source_id,
    party_id,
    operation_date,
    position,
    *,
    expected_total=None,
):
    if source_id is None:
        return None
    if type(source_id) is not int or source_id <= 0:
        raise ValueError("cfdi_source_id must be a positive integer or None")
    source = _cfdi.load_cfdi_source(session, entity_id, source_id)
    if source.third_party_id != party_id:
        raise ValueError("CFDI factual counterparty differs from inventory operation")
    if source.document_position != position:
        raise ValueError("CFDI document position conflicts with inventory operation")
    if source.parsed.issued_at.date() != operation_date:
        raise ValueError("CFDI issue date differs from inventory operation date")
    if expected_total is not None and source.parsed.total != expected_total:
        raise ValueError("CFDI total differs from inventory commercial amount")
    return source


def _credit_due(settlement_method, due_date, operation_date):
    if settlement_method == "credit":
        if type(due_date) is not date:
            raise ValueError("credit inventory operation requires due_date")
        if due_date < operation_date:
            raise ValueError("due_date cannot precede operation_date")
    elif due_date is not None:
        raise ValueError("due_date is only valid for credit inventory operations")


def _source_choice(document, cfdi_source_id):
    if document is not None and not isinstance(document, InventoryDocumentInput):
        raise TypeError("document must be InventoryDocumentInput or None")
    if document is not None and cfdi_source_id is not None:
        raise ValueError("use either InventoryDocumentInput or CfdiSource, not both")


def prepare_inventory_purchase(
    session,
    fact,
    *,
    document=None,
    cfdi_source_id=None,
    due_date=None,
    bank_account_id=None,
):
    """Prepare a merchandise receipt without writing inventory or ledger state."""
    if not isinstance(fact, MerchandisePurchaseFact):
        raise TypeError("fact must be MerchandisePurchaseFact")
    _check_open_period(session, fact.entity_id, fact.operation_date)
    product = _inventory.load_product(session, fact.entity_id, fact.product_id)
    if not product.is_active:
        raise ValueError("product must be active")
    _party(session, fact.entity_id, fact.supplier_third_party_id, "supplier")
    _bank_account(session, fact.entity_id, fact.settlement_method, bank_account_id)
    _credit_due(fact.settlement_method, due_date, fact.operation_date)
    _source_choice(document, cfdi_source_id)
    if fact.settlement_method == "credit" and document is None and cfdi_source_id is None:
        raise ValueError("credit purchase requires source document or CFDI")
    _inventory.require_append_date(session, fact.entity_id, fact.product_id, fact.operation_date)
    before = _inventory.inventory_state(session, fact.entity_id, fact.product_id)
    transition = apply_purchase(before, fact.quantity, fact.unit_price)
    amount = transition.value_delta
    _validate_cfdi(
        session,
        fact.entity_id,
        cfdi_source_id,
        fact.supplier_third_party_id,
        fact.operation_date,
        "receiver",
        expected_total=amount,
    )
    explanation = (
        f"Purchase {fact.quantity} {product.unit} of {product.name} at {fact.unit_price}; "
        f"stock {before.quantity} -> {transition.after.quantity}, carrying value "
        f"{before.value} -> {transition.after.value}, moving average {transition.after.average}."
    )
    return PreparedInventoryOperation(
        operation_id=uuid4().hex,
        kind="purchase",
        fact=fact,
        product_name=product.name,
        before=before,
        after=transition.after,
        revenue_or_purchase_amount=amount,
        inventory_cost=amount,
        document=document,
        cfdi_source_id=cfdi_source_id,
        due_date=due_date,
        explanation=explanation,
        bank_account_id=bank_account_id,
        fiscal_prepared=None,
    )


def prepare_inventory_sale(
    session,
    fact,
    *,
    document=None,
    cfdi_source_id=None,
    due_date=None,
    bank_account_id=None,
    fiscal_activity=None,
):
    """Prepare one sale plus its cost release, failing before write on insufficient stock."""
    if not isinstance(fact, MerchandiseSaleFact):
        raise TypeError("fact must be MerchandiseSaleFact")
    entity = _check_open_period(session, fact.entity_id, fact.operation_date)
    product = _inventory.load_product(session, fact.entity_id, fact.product_id)
    if not product.is_active:
        raise ValueError("product must be active")
    if fact.customer_third_party_id is not None:
        _party(session, fact.entity_id, fact.customer_third_party_id, "customer")
    _bank_account(session, fact.entity_id, fact.settlement_method, bank_account_id)
    _credit_due(fact.settlement_method, due_date, fact.operation_date)
    _source_choice(document, cfdi_source_id)
    if fact.settlement_method == "credit" and document is None and cfdi_source_id is None:
        raise ValueError("credit sale requires source document or CFDI")
    if cfdi_source_id is not None and fact.customer_third_party_id is None:
        raise ValueError("CFDI-backed sale requires factual customer ThirdParty")
    _inventory.require_append_date(session, fact.entity_id, fact.product_id, fact.operation_date)
    before = _inventory.inventory_state(session, fact.entity_id, fact.product_id)
    transition = apply_sale(before, fact.quantity)  # DETECT -> EXPLAIN -> STOP before posting.
    revenue = money(fact.quantity * fact.unit_price)
    cost = -transition.value_delta
    _validate_cfdi(
        session,
        fact.entity_id,
        cfdi_source_id,
        fact.customer_third_party_id,
        fact.operation_date,
        "issuer",
        expected_total=None if fiscal_activity is not None else revenue,
    )
    fiscal_prepared = _inventory_fiscal.prepare_inventory_sale_fiscal(
        session,
        entity,
        fact,
        revenue,
        activity=fiscal_activity,
        third_party_id=fact.customer_third_party_id,
        cfdi_source_id=cfdi_source_id,
    )
    explanation = (
        f"Sale {fact.quantity} {product.unit} of {product.name} at {fact.unit_price}; "
        f"revenue {revenue}, cost {cost}, stock {before.quantity} -> {transition.after.quantity}, "
        f"carrying value {before.value} -> {transition.after.value}."
    )
    return PreparedInventoryOperation(
        operation_id=uuid4().hex,
        kind="sale",
        fact=fact,
        product_name=product.name,
        before=before,
        after=transition.after,
        revenue_or_purchase_amount=revenue,
        inventory_cost=cost,
        document=document,
        cfdi_source_id=cfdi_source_id,
        due_date=due_date,
        explanation=explanation,
        bank_account_id=bank_account_id,
        fiscal_prepared=fiscal_prepared,
    )


def confirm_inventory_operation(prepared):
    if not isinstance(prepared, PreparedInventoryOperation):
        raise TypeError("prepared must be PreparedInventoryOperation")
    return ConfirmedInventoryOperation(
        prepared,
        _inventory_fiscal.confirm_inventory_sale_fiscal(prepared.fiscal_prepared),
    )


def _account_codes(session, prepared):
    if prepared.kind == "purchase":
        settlement = _SETTLEMENT_PURCHASE[prepared.fact.settlement_method]
        roles = ["inventory", settlement]
    else:
        settlement = _SETTLEMENT_SALE[prepared.fact.settlement_method]
        roles = [settlement, "sales_revenue", "cost_of_goods_sold", "inventory"]
    selected_bank = None
    if settlement == "bank" and prepared.bank_account_id is not None:
        selected_bank = _bank_account(
            session,
            prepared.fact.entity_id,
            prepared.fact.settlement_method,
            prepared.bank_account_id,
        )
        roles = [role for role in roles if role != "bank"]
    codes = get_account_bindings(session, tuple(dict.fromkeys(roles)))
    if selected_bank is not None:
        codes["bank"] = selected_bank[1].code
    return codes


def _payload(prepared, codes):
    fact = prepared.fact
    if prepared.kind == "purchase":
        settlement = _SETTLEMENT_PURCHASE[fact.settlement_method]
        lines = [
            {"account_code": codes["inventory"], "debit": prepared.inventory_cost, "credit": Decimal("0")},
            {"account_code": codes[settlement], "debit": Decimal("0"), "credit": prepared.inventory_cost},
        ]
    else:
        settlement = _SETTLEMENT_SALE[fact.settlement_method]
        lines = [
            {"account_code": codes[settlement], "debit": prepared.revenue_or_purchase_amount, "credit": Decimal("0")},
            {"account_code": codes["sales_revenue"], "debit": Decimal("0"), "credit": prepared.revenue_or_purchase_amount},
            {"account_code": codes["cost_of_goods_sold"], "debit": prepared.inventory_cost, "credit": Decimal("0")},
            {"account_code": codes["inventory"], "debit": Decimal("0"), "credit": prepared.inventory_cost},
        ]
    return {
        "date": fact.operation_date,
        "description": prepared.explanation,
        "state": "posted",
        "lines": lines,
    }


def _fiscal_cost_lines(prepared, codes):
    return [
        {
            "account_code": codes["cost_of_goods_sold"],
            "debit": prepared.inventory_cost,
            "credit": Decimal("0"),
        },
        {
            "account_code": codes["inventory"],
            "debit": Decimal("0"),
            "credit": prepared.inventory_cost,
        },
    ]


def _line(session, entry_id, account_code, side, amount):
    rows = session.exec(
        select(JournalLine).where(
            JournalLine.entry_id == entry_id,
            JournalLine.account_code == account_code,
        )
    ).all()
    matches = []
    for row in rows:
        debit, credit = Decimal(row.debit), Decimal(row.credit)
        if side == "debit" and debit == amount and credit == 0:
            matches.append(row)
        if side == "credit" and credit == amount and debit == 0:
            matches.append(row)
    if len(matches) != 1 or matches[0].id is None:
        raise RuntimeError(f"expected one canonical {side} line for {account_code}")
    return matches[0]


def _stage_document(session, prepared, entry_id, party):
    if prepared.cfdi_source_id is not None:
        link = _cfdi.stage_cfdi_source_link(
            session,
            prepared.fact.entity_id,
            prepared.cfdi_source_id,
            entry_id,
        )
        return link.document_reference_id
    if prepared.document is None:
        return None
    issuer_name = prepared.document.issuer_name
    if issuer_name is None:
        issuer_name = party.name if prepared.kind == "purchase" and party is not None else None
    ref = DocumentReference(
        id=None,
        entry_id=entry_id,
        third_party_id=None if party is None else party.id,
        document_type=prepared.document.document_type,
        document_number=prepared.document.document_number,
        issuer_name=issuer_name,
        date=datetime.combine(prepared.document.document_date, time.min, tzinfo=timezone.utc),
        file_hash=None,
        file_path=None,
        external_url=None,
        is_validated=False,
        validation_notes=None,
    )
    return _documents.stage_document_reference(session, ref).id


def _existing_result(session, operation_id):
    movement = _inventory.find_operation(session, operation_id)
    if movement is None:
        return None
    _inventory.validate_movement_reconciliation(session, movement)
    return {
        "entry_id": movement.entry_id,
        "movement_id": movement.id,
        "document_reference_id": movement.document_reference_id,
        "quantity_after": movement.quantity_after,
        "value_after": movement.value_after,
        "moving_average_after": movement.moving_average_after,
        "idempotent": True,
    }


def execute_inventory_operation(confirmed):
    """Atomically commit one already-confirmed inventory purchase or sale."""
    if not isinstance(confirmed, ConfirmedInventoryOperation):
        raise TypeError("confirmed must be ConfirmedInventoryOperation")
    prepared = confirmed.prepared
    session = None
    try:
        with _storage.get_session() as session:
            existing = _existing_result(session, prepared.operation_id)
            if existing is not None:
                return existing
            entity = _inventory.require_inventory_entity(session, prepared.fact.entity_id)
            product = _inventory.load_product(session, entity.id, prepared.fact.product_id)
            if not product.is_active:
                raise ValueError("product is no longer active")
            _inventory.require_append_date(session, entity.id, product.id, prepared.fact.operation_date)
            current = _inventory.inventory_state(session, entity.id, product.id)
            if current != prepared.before:
                raise ValueError("inventory changed after prepare; prepare again before confirming")

            party_id = (
                prepared.fact.supplier_third_party_id
                if prepared.kind == "purchase"
                else prepared.fact.customer_third_party_id
            )
            party = None if party_id is None else _party(
                session,
                entity.id,
                party_id,
                "supplier" if prepared.kind == "purchase" else "customer",
            )
            _bank_account(
                session,
                entity.id,
                prepared.fact.settlement_method,
                prepared.bank_account_id,
            )
            if prepared.cfdi_source_id is not None:
                _validate_cfdi(
                    session,
                    entity.id,
                    prepared.cfdi_source_id,
                    party_id,
                    prepared.fact.operation_date,
                    "receiver" if prepared.kind == "purchase" else "issuer",
                    expected_total=(
                        None
                        if prepared.fiscal_prepared is not None
                        else prepared.revenue_or_purchase_amount
                    ),
                )

            codes = _account_codes(session, prepared)
            fiscal_result = None
            if confirmed.fiscal_confirmed is not None:
                if prepared.kind != "sale":
                    raise RuntimeError("AQR-012 fiscal composition is only declared for sale")
                fiscal_result = _inventory_fiscal.stage_inventory_fiscal_sale(
                    session,
                    confirmed.fiscal_confirmed,
                    additional_balanced_lines=_fiscal_cost_lines(prepared, codes),
                )
                entry = session.get(JournalEntry, fiscal_result["entry_id"])
                if entry is None or entry.id is None:
                    raise RuntimeError("fiscal inventory posting did not assign JournalEntry identity")
            else:
                entry, error = _core._stage_entry_in_session(session, _payload(prepared, codes))
                if error is not None:
                    raise ValueError(error)
                if entry is None or entry.id is None:
                    raise RuntimeError("inventory posting did not assign JournalEntry identity")
            session.flush()

            if prepared.kind == "purchase":
                inventory_line = _line(session, entry.id, codes["inventory"], "debit", prepared.inventory_cost)
                cogs_line = None
                settlement_role = _SETTLEMENT_PURCHASE[prepared.fact.settlement_method]
                control_side = "credit"
            else:
                inventory_line = _line(session, entry.id, codes["inventory"], "credit", prepared.inventory_cost)
                cogs_line = _line(session, entry.id, codes["cost_of_goods_sold"], "debit", prepared.inventory_cost)
                settlement_role = _SETTLEMENT_SALE[prepared.fact.settlement_method]
                control_side = "debit"

            if fiscal_result is not None and prepared.cfdi_source_id is not None:
                document_id = fiscal_result["document_reference_id"]
            else:
                document_id = _stage_document(session, prepared, entry.id, party)
            if prepared.fact.settlement_method == "credit":
                if document_id is None:
                    raise ValueError("credit inventory operation requires persisted source document")
                control = _line(
                    session,
                    entry.id,
                    codes[settlement_role],
                    control_side,
                    prepared.revenue_or_purchase_amount,
                )
                _open_items.stage_open_item(
                    session,
                    entity_id=entity.id,
                    third_party_id=party_id,
                    kind="payable" if prepared.kind == "purchase" else "receivable",
                    source_entry_id=entry.id,
                    source_line_id=control.id,
                    source_document_reference_id=document_id,
                    due_date=prepared.due_date,
                )

            quantity_delta = prepared.after.quantity - prepared.before.quantity
            value_delta = prepared.after.value - prepared.before.value
            movement = InventoryMovementRecord(
                operation_id=prepared.operation_id,
                entity_id=entity.id,
                product_id=product.id,
                entry_id=entry.id,
                movement_kind=prepared.kind,
                occurred_on=prepared.fact.operation_date,
                quantity_delta=str(quantity_delta),
                value_delta=str(value_delta),
                unit_price=str(prepared.fact.unit_price),
                unit_cost_basis=str(money(prepared.inventory_cost / prepared.fact.quantity)),
                quantity_after=str(prepared.after.quantity),
                value_after=str(prepared.after.value),
                moving_average_after=str(prepared.after.average),
                third_party_id=party_id,
                document_reference_id=document_id,
                inventory_line_id=inventory_line.id,
                cogs_line_id=None if cogs_line is None else cogs_line.id,
            )
            session.add(movement)
            session.flush()
            if movement.id is None:
                raise RuntimeError("inventory movement did not assign identity")
            _inventory.validate_movement_reconciliation(session, movement)

            audit = _audit.stage_audit_event(
                session,
                AuditEvent(
                    None,
                    entity.id,
                    "inventory_operation_posted",
                    datetime.now(timezone.utc),
                    {
                        "operation_id": prepared.operation_id,
                        "kind": prepared.kind,
                        "product_id": product.id,
                        "entry_id": entry.id,
                        "movement_id": movement.id,
                        "quantity_before": str(prepared.before.quantity),
                        "quantity_after": str(prepared.after.quantity),
                        "value_before": str(prepared.before.value),
                        "value_after": str(prepared.after.value),
                        "moving_average_after": str(prepared.after.average),
                        "document_reference_id": document_id,
                        "bank_account_id": prepared.bank_account_id,
                        "fiscal_audit_event_id": (
                            None if fiscal_result is None else fiscal_result["audit_event_id"]
                        ),
                    },
                ),
            )
            session.commit()
            return {
                "entry_id": entry.id,
                "movement_id": movement.id,
                "audit_event_id": audit.id,
                "document_reference_id": document_id,
                "quantity_after": str(prepared.after.quantity),
                "value_after": str(prepared.after.value),
                "moving_average_after": str(prepared.after.average),
                "fiscal_audit_event_id": (
                    None if fiscal_result is None else fiscal_result["audit_event_id"]
                ),
                "idempotent": False,
            }
    except Exception:
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
        raise


__all__ = [
    "InventoryDocumentInput", "PreparedInventoryOperation", "ConfirmedInventoryOperation",
    "prepare_inventory_purchase", "prepare_inventory_sale", "confirm_inventory_operation",
    "execute_inventory_operation",
]
