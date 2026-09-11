"""Pure AQR-012 inventory identity and moving weighted-average semantics.

JournalEntry/JournalLine remain the monetary authority.  This module owns only
product identity, physical quantities and deterministic cost allocation.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Optional

MONEY_QUANTUM = Decimal("0.01")
AVERAGE_QUANTUM = Decimal("0.000000000001")


def _require_positive_id(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_optional_id(value, name):
    if value is not None:
        _require_positive_id(value, name)


def _require_text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_decimal(value, name, *, positive=False, nonnegative=False):
    if type(value) is not Decimal:
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be non-negative")


def money(value: Decimal) -> Decimal:
    """AQR-012 currency policy: cent precision, ROUND_HALF_UP."""
    _require_decimal(value, "value")
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def moving_average(value: Decimal, quantity: Decimal) -> Decimal:
    """Display/reproduction average at 12 decimals; carrying value remains authoritative."""
    _require_decimal(value, "value", nonnegative=True)
    _require_decimal(quantity, "quantity", nonnegative=True)
    if quantity == 0:
        return Decimal("0")
    with localcontext() as ctx:
        ctx.prec = 50
        return (value / quantity).quantize(AVERAGE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Product:
    id: Optional[int]
    entity_id: int
    sku: str
    name: str
    unit: str
    is_active: bool = True

    def __post_init__(self):
        _require_optional_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_text(self.sku, "sku")
        _require_text(self.name, "name")
        _require_text(self.unit, "unit")
        if type(self.is_active) is not bool:
            raise TypeError("is_active must be bool")


@dataclass(frozen=True)
class InventoryState:
    quantity: Decimal
    value: Decimal
    average: Decimal

    def __post_init__(self):
        _require_decimal(self.quantity, "quantity", nonnegative=True)
        _require_decimal(self.value, "value", nonnegative=True)
        _require_decimal(self.average, "average", nonnegative=True)
        expected = moving_average(self.value, self.quantity)
        if self.average != expected:
            raise ValueError("average must equal value / quantity under AQR-012 precision policy")
        if self.quantity == 0 and self.value != Decimal("0"):
            raise ValueError("zero quantity must have zero carrying value")


ZERO_STATE = InventoryState(Decimal("0"), Decimal("0"), Decimal("0"))


@dataclass(frozen=True)
class MerchandisePurchaseFact:
    entity_id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    operation_date: date
    supplier_third_party_id: int
    settlement_method: str

    def __post_init__(self):
        _require_positive_id(self.entity_id, "entity_id")
        _require_positive_id(self.product_id, "product_id")
        _require_decimal(self.quantity, "quantity", positive=True)
        _require_decimal(self.unit_price, "unit_price", positive=True)
        if type(self.operation_date) is not date:
            raise TypeError("operation_date must be date")
        _require_positive_id(self.supplier_third_party_id, "supplier_third_party_id")
        if self.settlement_method not in {"bank", "cash", "credit"}:
            raise ValueError("settlement_method must be bank, cash or credit")


@dataclass(frozen=True)
class MerchandiseSaleFact:
    entity_id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    operation_date: date
    settlement_method: str
    customer_third_party_id: Optional[int] = None

    def __post_init__(self):
        _require_positive_id(self.entity_id, "entity_id")
        _require_positive_id(self.product_id, "product_id")
        _require_decimal(self.quantity, "quantity", positive=True)
        _require_decimal(self.unit_price, "unit_price", positive=True)
        if type(self.operation_date) is not date:
            raise TypeError("operation_date must be date")
        if self.settlement_method not in {"cash", "bank", "credit"}:
            raise ValueError("settlement_method must be cash, bank or credit")
        _require_optional_id(self.customer_third_party_id, "customer_third_party_id")
        if self.settlement_method == "credit" and self.customer_third_party_id is None:
            raise ValueError("credit sale requires customer_third_party_id")


@dataclass(frozen=True)
class InventoryTransition:
    before: InventoryState
    after: InventoryState
    quantity_delta: Decimal
    value_delta: Decimal
    unit_cost_basis: Decimal


def apply_purchase(state: InventoryState, quantity: Decimal, unit_price: Decimal) -> InventoryTransition:
    if not isinstance(state, InventoryState):
        raise TypeError("state must be InventoryState")
    _require_decimal(quantity, "quantity", positive=True)
    _require_decimal(unit_price, "unit_price", positive=True)
    added_value = money(quantity * unit_price)
    new_quantity = state.quantity + quantity
    new_value = money(state.value + added_value)
    after = InventoryState(new_quantity, new_value, moving_average(new_value, new_quantity))
    return InventoryTransition(state, after, quantity, added_value, money(unit_price))


def apply_sale(state: InventoryState, quantity: Decimal) -> InventoryTransition:
    if not isinstance(state, InventoryState):
        raise TypeError("state must be InventoryState")
    _require_decimal(quantity, "quantity", positive=True)
    if quantity > state.quantity:
        raise ValueError(
            f"insufficient inventory: requested {quantity}, available {state.quantity}"
        )
    if state.quantity == 0:
        raise ValueError("insufficient inventory: no stock available")
    if quantity == state.quantity:
        cost = state.value
    else:
        with localcontext() as ctx:
            ctx.prec = 50
            cost = money(state.value * quantity / state.quantity)
    new_quantity = state.quantity - quantity
    new_value = Decimal("0") if new_quantity == 0 else money(state.value - cost)
    after = InventoryState(new_quantity, new_value, moving_average(new_value, new_quantity))
    basis = money(cost / quantity)
    return InventoryTransition(state, after, -quantity, -cost, basis)


__all__ = [
    "MONEY_QUANTUM", "AVERAGE_QUANTUM", "Product", "InventoryState", "ZERO_STATE",
    "MerchandisePurchaseFact", "MerchandiseSaleFact", "InventoryTransition",
    "money", "moving_average", "apply_purchase", "apply_sale",
]
