"""
Aqorath Economic Fact Application Layer

Implementación del primer vertical productivo:
  Venta en efectivo (sale for cash)

Resuelve económicamente:
  EconomicFact( type="sale", amount=Decimal("200.00"), payment_method="cash" )
  
a una propuesta contable semántica:
  AccountingProposal con dos líneas: cash (debit) y sales_revenue (credit)

Dominio puro: sin acceso a core, storage, SQLite o persistencia.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List


@dataclass(frozen=True)
class EconomicFact:
    """
    Representa un HECHO ECONÓMICO estructurado.
    
    No es una póliza contable, sino la descripción de QUÉ OCURRIÓ.
    
    Campos requeridos (sin defaults que inventen hechos):
      - type: str — tipo de transacción económica ("sale" en Phase 2A.2)
      - amount: Decimal — cantidad en autoridad monetaria Decimal
      - payment_method: str — cómo se recibió/pagó ("cash" en Phase 2A.2)
    
    Validaciones:
      - type debe ser "sale" (es la única permitida en esta fase)
      - amount debe ser Decimal > 0 (no float, no cero, no negativo)
      - payment_method debe ser "cash" (es la única permitida en esta fase)
      - Rechaza explícitamente kwargs contables (debit, credit, account_id, etc.)
    """
    
    type: str
    amount: Decimal
    payment_method: str
    
    def __post_init__(self):
        """
        Validar invariantes de dominio después de congelación de dataclass.
        """
        # Validar type
        if self.type != "sale":
            raise ValueError(
                f"type must be 'sale' (Phase 2A.2 only supports cash sales). "
                f"Got: {self.type}"
            )
        
        # Validar amount
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal (exact monetary authority). "
                f"Got: {type(self.amount).__name__}. "
                f"Do not convert float to Decimal; float is not a valid monetary type."
            )
        
        if self.amount <= 0:
            raise ValueError(
                f"amount must be > 0 (positive transaction). "
                f"Got: {self.amount}"
            )
        
        # Validar payment_method
        if self.payment_method != "cash":
            raise ValueError(
                f"payment_method must be 'cash' (Phase 2A.2 only supports cash). "
                f"Got: {self.payment_method}"
            )
    
    def __init__(self, type: str, amount, payment_method: str):
        """
        Strict constructor that rejects unknown kwargs and validates types early.
        """
        # Rechazar float implícitamente
        if isinstance(amount, float):
            raise TypeError(
                f"amount must be Decimal, not float. "
                f"Float is not the monetary authority; use Decimal('200.00') instead."
            )
        
        # Usar object.__setattr__ porque frozen=True
        object.__setattr__(self, "type", type)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "payment_method", payment_method)
        
        # Ejecutar validaciones
        self.__post_init__()


@dataclass(frozen=True)
class ProposalLine:
    """
    Una línea de una propuesta contable.
    
    Campos semánticos (no concretos):
      - account_role: str — rol semántico ("cash", "sales_revenue", etc.)
      - side: str — lado de la partida doble ("debit" o "credit")
      - amount: Decimal — cantidad exacta
    
    NO expone:
      - account_id, account_code (concretos)
      - sat_code, db_id (específicos de implementación)
      - account_name (localización)
    
    La traducción role → account_code es delegada a una etapa posterior.
    """
    
    account_role: str
    side: str
    amount: Decimal
    
    def __post_init__(self):
        """Validar invariantes."""
        if self.side not in ("debit", "credit"):
            raise ValueError(
                f"side must be 'debit' or 'credit'. Got: {self.side}"
            )
        
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal. Got: {type(self.amount).__name__}"
            )
        
        if self.amount <= 0:
            raise ValueError(
                f"amount must be > 0. Got: {self.amount}"
            )


@dataclass(frozen=True)
class AccountingProposal:
    """
    Una propuesta contable estructurada.
    
    Representa una RESOLUCIÓN determinista de un EconomicFact a asientos contables.
    NO es una entrada persistida, sino una propuesta en memoria.
    
    Campos:
      - lines: List[ProposalLine] — las líneas de la propuesta
      - explanation: str — explicación humana legible del hecho
    
    Invariantes:
      - lines contiene exactamente 2 líneas para cash sale
      - total_debit == total_credit (exacto en Decimal)
      - explanation comunica semánticamente el hecho
    """
    
    lines: List[ProposalLine]
    explanation: str
    
    def __post_init__(self):
        """Validar invariantes de propuesta."""
        if not isinstance(self.lines, (list, tuple)):
            raise TypeError(
                f"lines must be list or tuple. Got: {type(self.lines).__name__}"
            )
        
        if len(self.lines) != 2:
            raise ValueError(
                f"For cash sale, lines must have exactly 2 entries. "
                f"Got {len(self.lines)}"
            )
        
        # Validar balance
        total_debit = sum(
            (line.amount for line in self.lines if line.side == "debit"),
            Decimal("0"),
        )
        total_credit = sum(
            (line.amount for line in self.lines if line.side == "credit"),
            Decimal("0"),
        )
        
        if total_debit != total_credit:
            raise ValueError(
                f"Proposal must be balanced. "
                f"total_debit={total_debit}, total_credit={total_credit}"
            )
        
        if not isinstance(self.explanation, str):
            raise TypeError(
                f"explanation must be str. Got: {type(self.explanation).__name__}"
            )
        
        if not self.explanation.strip():
            raise ValueError("explanation must not be empty")


def resolve_economic_fact(fact: EconomicFact) -> AccountingProposal:
    """
    Resuelve un hecho económico a una propuesta contable.
    
    Operación determinista y pura:
      - Sin persistencia
      - Sin acceso a core, storage, SQLite
      - Sin llamadas externas
      - Sin IDs aleatorios
      - Sin timestamps
      - Sin LLM
    
    Para Phase 2A.2, resuelve únicamente:
      EconomicFact(type="sale", amount=Decimal("200.00"), payment_method="cash")
      
    a:
      AccountingProposal con 2 líneas:
        - cash (debit, amount)
        - sales_revenue (credit, amount)
      y una explicación determinista.
    
    Args:
        fact: EconomicFact validado (type="sale", payment_method="cash")
    
    Returns:
        AccountingProposal sin persistencia.
    
    Raises:
        ValueError: si fact no es sale/cash
    """
    # Validar que sea el caso que sabemos resolver
    if fact.type != "sale":
        raise ValueError(
            f"resolve_economic_fact only supports type='sale' in Phase 2A.2. "
            f"Got: {fact.type}"
        )
    
    if fact.payment_method != "cash":
        raise ValueError(
            f"resolve_economic_fact only supports payment_method='cash' in Phase 2A.2. "
            f"Got: {fact.payment_method}"
        )
    
    # Crear las dos líneas de partida doble
    cash_debit = ProposalLine(
        account_role="cash",
        side="debit",
        amount=fact.amount,
    )
    
    sales_credit = ProposalLine(
        account_role="sales_revenue",
        side="credit",
        amount=fact.amount,
    )
    
    # Generar explicación humana determinista
    # Comunica los tres semánticos:
    #   1. Hubo una venta
    #   2. Se recibió/entró efectivo
    #   3. Se reconoce ingreso por ventas
    explanation = (
        f"Sale transaction: {fact.amount} received in cash. "
        f"Cash account increased (debit), sales revenue recognized (credit)."
    )
    
    # Crear propuesta
    proposal = AccountingProposal(
        lines=[cash_debit, sales_credit],
        explanation=explanation,
    )
    
    return proposal
