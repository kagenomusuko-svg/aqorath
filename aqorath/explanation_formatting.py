"""Pure display formatting for already-selected explanation view data."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .explanation_delivery import PreparedExplanationPresentation
from .user_knowledge_state import UserKnowledgeState


_FACT_LABELS = {
    "en": {
        "sale": "Sale",
        "utility_expense": "Utility expense",
        "utility_expense_incurred": "Utility expense incurred",
        "receivable_collection": "Receivable collection",
        "supplier_payment": "Supplier payment",
    },
    "es": {
        "sale": "Venta",
        "utility_expense": "Gasto de servicios",
        "utility_expense_incurred": "Gasto de servicios devengado",
        "receivable_collection": "Cobro de cuenta por cobrar",
        "supplier_payment": "Pago a proveedor",
    },
}

_PAYMENT_LABELS = {
    "en": {"cash": "Cash", "credit": "Credit", "bank": "Bank"},
    "es": {"cash": "Efectivo", "credit": "Crédito", "bank": "Banco"},
}

_ACCOUNT_LABELS = {
    "en": {
        "cash": "Cash",
        "sales_revenue": "Sales revenue",
        "accounts_receivable": "Accounts receivable",
        "utilities_expense": "Utilities expense",
        "bank": "Bank",
        "accounts_payable": "Accounts payable",
    },
    "es": {
        "cash": "Efectivo",
        "sales_revenue": "Ingresos por ventas",
        "accounts_receivable": "Cuentas por cobrar",
        "utilities_expense": "Gastos de servicios",
        "bank": "Banco",
        "accounts_payable": "Cuentas por pagar",
    },
}

_SIDE_LABELS = {
    "en": {"debit": "Debit", "credit": "Credit"},
    "es": {"debit": "Debe", "credit": "Haber"},
}

_CONCEPT_LABELS = {
    "en": {
        "economic_fact": "Economic fact",
        "double_entry": "Double-entry accounting",
    },
    "es": {
        "economic_fact": "Hecho económico",
        "double_entry": "Partida doble",
    },
}


@dataclass(frozen=True)
class FormattedExplanationEffect:
    """One immutable visible effect rendered as display text."""

    account_label: str
    side_label: str
    amount_text: str


@dataclass(frozen=True)
class FormattedExplanationPresentation:
    """Immutable display-ready fields for one selected explanation view."""

    ui_language: str
    fact_type_label: Optional[str]
    payment_method_label: Optional[str]
    amount_text: Optional[str]
    effects: tuple[FormattedExplanationEffect, ...]
    concept_labels: tuple[str, ...]
    professional_summary: Optional[str]


def _label(table, language, code, field_name):
    if code is None:
        return None
    try:
        return table[language][code]
    except KeyError as exc:
        raise ValueError(f"unknown visible {field_name}: {code!r}") from exc


def _money_text(amount, decimal_separator, currency_symbol):
    if amount is None:
        return None
    if type(amount) is not Decimal:
        raise TypeError("visible amount must be Decimal")
    text = str(amount)
    if decimal_separator == ",":
        text = text.replace(".", ",")
    return f"{currency_symbol} {text}"


def format_explanation_presentation(prepared, user_state):
    """Render one selected view using explicit display preferences."""
    if not isinstance(prepared, PreparedExplanationPresentation):
        raise TypeError("prepared must be PreparedExplanationPresentation")
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")

    language = user_state.ui_language
    if language not in {"es", "en"}:
        raise ValueError("ui_language must be exactly 'es' or 'en'")

    view = prepared.presentation_view
    effects = tuple(
        FormattedExplanationEffect(
            account_label=_label(
                _ACCOUNT_LABELS,
                language,
                effect.account_role,
                "account role",
            ),
            side_label=_label(_SIDE_LABELS, language, effect.side, "side"),
            amount_text=_money_text(
                effect.amount,
                user_state.decimal_separator,
                user_state.currency_symbol,
            ),
        )
        for effect in view.effects
    )
    concepts = tuple(
        _label(_CONCEPT_LABELS, language, concept, "concept")
        for concept in view.concepts
    )

    return FormattedExplanationPresentation(
        ui_language=language,
        fact_type_label=_label(
            _FACT_LABELS,
            language,
            view.fact_type,
            "fact type",
        ),
        payment_method_label=_label(
            _PAYMENT_LABELS,
            language,
            view.payment_method,
            "payment method",
        ),
        amount_text=_money_text(
            view.amount,
            user_state.decimal_separator,
            user_state.currency_symbol,
        ),
        effects=effects,
        concept_labels=concepts,
        professional_summary=view.professional_summary,
    )
