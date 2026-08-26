"""
Account Role Resolution — Phase 2B.2

Resuelve roles de cuenta semánticos a identidades concretas.

Arquitectura:
  AccountingProposal (semántica, roles)
    ↓ resolve_proposal_accounts(session, proposal, account_bindings)
    ↓ ResolvedAccountingProposal (identidades concretas)

Separación de responsabilidades:
  - economic_facts: ¿QUÉ significa el hecho?
  - account_resolution: ¿EN QUÉ cuentas concretas cae?
  - [posting futuro]: ¿CÓMO se registra?
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from . import catalog as _catalog

__all__ = [
    "ResolvedProposalLine",
    "ResolvedAccountingProposal",
    "resolve_proposal_accounts",
]


@dataclass(frozen=True)
class ResolvedProposalLine:
    """
    Una línea de propuesta contable RESUELTA a identidad concreta.

    Campos:
      - account_role: str — rol semántico preservado (ej: "cash")
      - account_id: int — identidad concreta de cuenta (del catálogo)
      - account_code: str — código de cuenta (del catálogo)
      - account_name: str — nombre de cuenta (del catálogo)
      - side: str — lado ("debit" o "credit"), preservado
      - amount: Decimal — cantidad exacta, preservada sin conversión

    PRE-POSTING: No contiene entry_id ni campos de persistencia.
    """

    account_role: str
    account_id: int
    account_code: str
    account_name: str
    side: str
    amount: Decimal


@dataclass(frozen=True)
class ResolvedAccountingProposal:
    """
    Una propuesta contable RESUELTA a identidades concretas.

    Campos:
      - lines: List[ResolvedProposalLine] — líneas con identidades concretas
      - explanation: str — explicación original, preservada sin modificación

    PRE-POSTING: No es JournalEntry. No tiene state, entry_id, timestamps.
    """

    lines: List[ResolvedProposalLine]
    explanation: str


def resolve_proposal_accounts(session, proposal, account_bindings):
    """
    Resuelve una propuesta semántica a identidades concretas de cuenta.

    Parámetros:
      - session: sesión SQLite explícita para lookups
      - proposal: AccountingProposal semántica (de economic_facts)
      - account_bindings: dict que mapea role → account_code configurado
        Ejemplo: {"cash": "TEST-CASH-001", "sales_revenue": "TEST-SALES-900"}

    Retorna:
      - ResolvedAccountingProposal con líneas materializadas a identidades concretas

    Comportamiento:
      1. Para cada ProposalLine de la propuesta:
         - Obtener account_role
         - Exigir que exista en account_bindings
         - Obtener el código configurado
         - Consultar catálogo: catalog.resolve_account_by_code(session, code)
         - Exigir que la Account existe (no None)
         - Construir ResolvedProposalLine con identidad del Account

      2. Retornar ResolvedAccountingProposal con todas las líneas resueltas
         y explanation original sin modificación.

      3. ALL-OR-NOTHING: Si alguna línea falla, lanzar excepción.
         No retornar propuesta parcial.

    Levanta:
      - ValueError si un role no tiene binding
      - ValueError si una Account no existe
    """
    resolved_lines = []

    for line in proposal.lines:
        role = line.account_role

        # Verificar que existe binding para este role
        if role not in account_bindings:
            raise ValueError(
                f"No account binding configured for role '{role}'"
            )

        # Obtener el código configurado
        bound_code = account_bindings[role]

        # Consultar catálogo
        account = _catalog.resolve_account_by_code(session, bound_code)

        # Verificar que la cuenta existe
        if account is None:
            raise ValueError(
                f"Account '{bound_code}' configured for role '{role}' does not exist"
            )

        # Construir ResolvedProposalLine
        resolved_line = ResolvedProposalLine(
            account_role=line.account_role,
            account_id=account.id,
            account_code=account.code,
            account_name=account.name,
            side=line.side,
            amount=line.amount,
        )

        resolved_lines.append(resolved_line)

    # Retornar propuesta resuelta
    return ResolvedAccountingProposal(
        lines=resolved_lines,
        explanation=proposal.explanation,
    )
