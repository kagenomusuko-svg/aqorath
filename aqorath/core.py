from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional
from datetime import date, datetime
from .models import JournalEntry, JournalLine, Account
from .storage import get_session
from sqlmodel import select
import math

@dataclass
class LineSpec:
    account_code: str
    side: str  # 'debit' or 'credit'
    amount_expr: Callable[[float, Dict[str, Any]], float]
    description: Optional[str] = None
    cfdi: Optional[bool] = False

@dataclass
class OperationTemplate:
    key: str
    description: str
    create_lines: Callable[[float, Dict[str, Any]], List[LineSpec]]

_TEMPLATES: Dict[str, OperationTemplate] = {}

def register_template(template: OperationTemplate):
    _TEMPLATES[template.key] = template
    return template

def get_template(key: str) -> OperationTemplate:
    return _TEMPLATES[key]

def list_templates() -> List[str]:
    return list(_TEMPLATES.keys())

# Helpers
def fixed_amount_expr(amount_fixed: float):
    return lambda amount, ctx: float(amount_fixed)

def base_amount_expr():
    return lambda amount, ctx: float(amount)

def percent_expr(rate: float):
    def fn(amount, ctx):
        return round(float(amount) * float(rate), 2)
    return fn

def total_with_vat_expr(vat_key: str = "vat_rate", amount_is_net: bool = True):
    """
    Si amount_is_net True: devuelve amount + amount*vat_rate.
    Si amount_is_net False: interpreta amount como bruto y retorna el bruto (caller decidirá base/vat).
    """
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if amount_is_net:
            return round(float(amount) + (float(amount) * vat), 2)
        else:
            return round(float(amount), 2)
    return fn

def gross_base_expr(vat_key: str = "vat_rate"):
    """Si amount es bruto, base = amount / (1 + vat)"""
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if vat == 0:
            return round(float(amount), 2)
        return round(float(amount) / (1.0 + vat), 2)
    return fn

def gross_vat_expr(vat_key: str = "vat_rate"):
    """Si amount es bruto, vat = amount - base"""
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if vat == 0:
            return 0.0
        base = float(amount) / (1.0 + vat)
        return round(float(amount) - base, 2)
    return fn

def net_from_gross_expr(vat_key: str = "vat_rate"):
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if vat == 0:
            return round(float(amount), 2)
        base = float(amount) / (1.0 + vat)
        return round(base, 2)
    return fn

# Templates

# Ingreso: amount param treated as NET by default (base), bank debit = base + vat
register_template(OperationTemplate(
    key="ingreso_venta",
    description="Ingreso por venta: banco (debit = base+vat) / ventas (credit = base) + IVA trasladado",
    create_lines=lambda amount, ctx: (
        ([
            LineSpec(account_code=ctx.get("account_codes", {}).get("bank", "1000"),
                     side="debit", amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True), description=ctx.get("desc")),
            LineSpec(account_code=ctx.get("account_codes", {}).get("sales", "4000"),
                     side="credit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
        ] +
        (
            ([LineSpec(account_code=ctx.get("account_codes", {}).get("vat_tr", "2100"),
                       side="credit", amount_expr=percent_expr(ctx.get("vat_rate", 0.0)),
                       description="IVA trasladado")] if ctx.get("vat_rate", 0.0) else [])
        ))
    )
))

# Ingreso cuando el importe recibido ya es bruto (incluye IVA)
register_template(OperationTemplate(
    key="ingreso_venta_bruto",
    description="Ingreso por venta (importe bruto; incluye IVA): banco (debit = bruto) / ventas (credit = base) + IVA trasladado",
    create_lines=lambda amount, ctx: (
        [
            # banco recibe el bruto (importe tal cual)
            LineSpec(account_code=ctx.get("account_codes", {}).get("bank", "1000"),
                     side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
            # ventas por la base (calculated from gross)
            LineSpec(account_code=ctx.get("account_codes", {}).get("sales", "4000"),
                     side="credit", amount_expr=gross_base_expr("vat_rate"), description=ctx.get("desc")),
        ] + (
            ([LineSpec(account_code=ctx.get("account_codes", {}).get("vat_tr", "2100"),
                       side="credit", amount_expr=gross_vat_expr("vat_rate"),
                       description="IVA trasladado")] if ctx.get("vat_rate", 0.0) else [])
        )
    )
))

# Egreso: amount param NET by default; bank credit = base+vat; expense debit = base; vat_ac debit = vat
register_template(OperationTemplate(
    key="egreso_compra",
    description="Egreso compra: gasto (debit=base) / banco (credit=base+vat) + IVA acreditable (debit=vat)",
    create_lines=lambda amount, ctx: (
        [
            LineSpec(account_code=ctx.get("account_codes", {}).get("expense", "5000"),
                     side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
            LineSpec(account_code=ctx.get("account_codes", {}).get("bank", "1000"),
                     side="credit", amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True), description=ctx.get("desc"))
        ] + (
            ([LineSpec(account_code=ctx.get("account_codes", {}).get("vat_ac", "2200"),
                       side="debit", amount_expr=percent_expr(ctx.get("vat_rate", 0.0)),
                       description="IVA acreditable")] if ctx.get("vat_rate", 0.0) else [])
        )
    )
))

# Pago a proveedor: reducir pasivo/pagar con banco (payment template)
register_template(OperationTemplate(
    key="pago_proveedor",
    description="Pago a proveedor: pago de pasivo (debit proveedor) y salida banco (credit banco)",
    create_lines=lambda amount, ctx: (
        [
            LineSpec(account_code=ctx.get("account_codes", {}).get("payable", "2000"),
                     side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
            LineSpec(account_code=ctx.get("account_codes", {}).get("bank", "1000"),
                     side="credit", amount_expr=base_amount_expr(), description=ctx.get("desc"))
        ]
    )
))

# Honorarios (ya con retención possible)
def honorarios_create(amount, ctx):
    lines = [
        LineSpec(account_code=ctx.get("account_codes", {}).get("expense", "5000"),
                 side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
    ]
    isr_rate = ctx.get("isr_ret_rate", 0.0)
    # net to bank = amount * (1 - isr_rate)
    lines.append(LineSpec(account_code=ctx.get("account_codes", {}).get("bank", "1000"),
                          side="credit", amount_expr=percent_expr(1.0 - isr_rate),
                          description=ctx.get("desc")))
    if isr_rate:
        lines.append(LineSpec(account_code=ctx.get("account_codes", {}).get("isr_ret", "2300"),
                              side="credit", amount_expr=percent_expr(isr_rate),
                              description="Retención ISR"))
    return lines

register_template(OperationTemplate(
    key="honorarios",
    description="Honorarios: gasto / banco neto + ISR retenido",
    create_lines=honorarios_create
))

# Preview & post
def generate_preview(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None):
    ctx = ctx or {}
    tpl = get_template(template_key)
    line_specs = tpl.create_lines(amount, ctx)
    with get_session() as s:
        accounts = {a.code: a for a in s.exec(select(Account)).all()}
    lines_preview = []
    total_debit = 0.0
    total_credit = 0.0
    for ls in line_specs:
        acc = accounts.get(ls.account_code)
        debit = ls.amount_expr(amount, ctx) if ls.side == "debit" else 0.0
        credit = ls.amount_expr(amount, ctx) if ls.side == "credit" else 0.0
        total_debit += debit
        total_credit += credit
        lines_preview.append({
            "account_code": ls.account_code,
            "account_id": acc.id if acc else None,
            "account_name": acc.name if acc else None,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "description": ls.description or ""
        })
    balance_ok = math.isclose(total_debit, total_credit, rel_tol=1e-6)
    return {
        "template": template_key,
        "description": tpl.description,
        "date": datetime.utcnow().date(),
        "lines": lines_preview,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": balance_ok
    }


def post_entry(template_key: str, amount: float, ctx: Optional[Dict[str, Any]] = None, user: Optional[str] = None):
    preview = generate_preview(template_key, amount, ctx)
    if not preview["balanced"]:
        raise ValueError("El asiento no está balanceado. Revisa las reglas del template.")
    with get_session() as s:
        entry = JournalEntry(date=preview["date"], concept=ctx.get("desc"),
                             doc_ref=ctx.get("doc_ref"), period_id=ctx.get("period_id"),
                             posted_by=user, state="posted")
        s.add(entry)
        s.commit()
        s.refresh(entry)
        for l in preview["lines"]:
            acc_id = l["account_id"]
            if acc_id is None:
                q = s.exec(select(Account).where(Account.code == l["account_code"]))
                acc = q.one_or_none()
                if acc:
                    acc_id = acc.id
            jl = JournalLine(entry_id=entry.id, account_id=acc_id or None,
                             debit=l["debit"], credit=l["credit"],
                             description=l["description"])
            s.add(jl)
        s.commit()
        return entry.id