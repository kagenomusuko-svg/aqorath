from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional
from datetime import date, datetime
from .models import Account, AppConfig
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

# Expresiones para cálculos de montos
def fixed_amount_expr(amount_fixed: float):
    return lambda amount, ctx: float(amount_fixed)

def base_amount_expr():
    return lambda amount, ctx: float(amount)

def percent_expr(rate: float):
    return lambda amount, ctx: round(float(amount) * float(rate), 2)

def total_with_vat_expr(vat_key: str = "vat_rate", amount_is_net: bool = True):
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if amount_is_net:
            return round(float(amount) + (float(amount) * vat), 2)
        else:
            return round(float(amount), 2)
    return fn

def gross_base_expr(vat_key: str = "vat_rate"):
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if vat == 0:
            return round(float(amount), 2)
        return round(float(amount) / (1.0 + vat), 2)
    return fn

def gross_vat_expr(vat_key: str = "vat_rate"):
    def fn(amount, ctx):
        vat = float(ctx.get(vat_key, 0.0))
        if vat == 0:
            return 0.0
        base = float(amount) / (1.0 + vat)
        return round(float(amount) - base, 2)
    return fn

# Helper para forzar account_codes en ctx
def _get_account_code(ctx: Dict[str, Any], logical: str) -> str:
    """
    Obtiene el código de cuenta del ctx["account_codes"].
    Si no existe, lanza error amigable al usuario.
    """
    if "account_codes" not in ctx or not isinstance(ctx["account_codes"], dict):
        raise ValueError(f"Necesitas pasar 'account_codes' en ctx; falta {logical}")
    code = ctx["account_codes"].get(logical)
    if not code:
        raise ValueError(f"Necesitas especificar 'account_codes.{logical}' en ctx")
    return code

# Templates

# Ingreso venta NETO
def ingreso_venta_create(amount: float, ctx: Dict[str, Any]):
    lines = [
        LineSpec(account_code=_get_account_code(ctx, "bank"),
                 side="debit",
                 amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True),
                 description=ctx.get("desc")),
        LineSpec(account_code=_get_account_code(ctx, "sales"),
                 side="credit",
                 amount_expr=base_amount_expr(),
                 description=ctx.get("desc"))
    ]
    vat_rate = ctx.get("vat_rate", 0.0)
    if vat_rate:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_tr"),
                              side="credit",
                              amount_expr=lambda a,c: round(a * float(c.get("vat_rate",0.0)),2),
                              description="IVA trasladado"))
    return lines

register_template(OperationTemplate(
    key="ingreso_venta",
    description="Ingreso por venta: banco (debit = base+vat) / ventas (credit = base) + IVA trasladado",
    create_lines=ingreso_venta_create
))

# Ingreso venta BRUTO
def ingreso_venta_bruto_create(amount: float, ctx: Dict[str, Any]):
    lines = [
        LineSpec(account_code=_get_account_code(ctx, "bank"),
                 side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
        LineSpec(account_code=_get_account_code(ctx, "sales"),
                 side="credit", amount_expr=gross_base_expr("vat_rate"), description=ctx.get("desc"))
    ]
    vat_rate = ctx.get("vat_rate", 0.0)
    if vat_rate:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_tr"),
                              side="credit",
                              amount_expr=gross_vat_expr("vat_rate"),
                              description="IVA trasladado"))
    return lines

register_template(OperationTemplate(
    key="ingreso_venta_bruto",
    description="Ingreso por venta (importe bruto; incluye IVA): banco / ventas + IVA trasladado",
    create_lines=ingreso_venta_bruto_create
))

# Egreso compra NETO
def egreso_compra_create(amount: float, ctx: Dict[str, Any]):
    lines = [
        LineSpec(account_code=_get_account_code(ctx, "expense"),
                 side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
        LineSpec(account_code=_get_account_code(ctx, "bank"),
                 side="credit", amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True), description=ctx.get("desc"))
    ]
    vat_rate = ctx.get("vat_rate", 0.0)
    if vat_rate:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_ac"),
                              side="debit",
                              amount_expr=lambda a,c: round(a * float(c.get("vat_rate",0.0)),2),
                              description="IVA acreditable"))
    return lines

register_template(OperationTemplate(
    key="egreso_compra",
    description="Egreso compra: gasto / banco + IVA acreditable",
    create_lines=egreso_compra_create
))

# Pago a proveedor simple
def pago_proveedor_create(amount: float, ctx: Dict[str, Any]):
    lines = [
        LineSpec(account_code=_get_account_code(ctx, "payable"),
                 side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")),
        LineSpec(account_code=_get_account_code(ctx, "bank"),
                 side="credit", amount_expr=base_amount_expr(), description=ctx.get("desc"))
    ]
    return lines

register_template(OperationTemplate(
    key="pago_proveedor",
    description="Pago a proveedor: pago de pasivo / banco",
    create_lines=pago_proveedor_create
))

# Pago a proveedor con retención IVA
def pago_con_retencion_create(amount: float, ctx: Dict[str, Any]):
    vat_rate = float(ctx.get("vat_rate", 0.0))
    vat_ret_rate = float(ctx.get("vat_ret_rate", 0.0))
    vat = round(amount * vat_rate, 2)
    vat_ret = round(vat * vat_ret_rate, 2)

    acct = ctx.get("account_codes", {})
    lines = []
    # Reconocimiento factura
    lines.append(LineSpec(account_code=_get_account_code(ctx, "expense"), side="debit",
                          amount_expr=base_amount_expr(), description=ctx.get("desc")))
    if vat > 0:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_ac"), side="debit",
                              amount_expr=lambda a,c: round(a*float(c.get("vat_rate",0.0)),2),
                              description="IVA acreditable"))
    lines.append(LineSpec(account_code=_get_account_code(ctx, "payable"), side="credit",
                          amount_expr=lambda a,c: round(a + (a * float(c.get("vat_rate",0.0))),2),
                          description=ctx.get("desc")))
    # Pago
    lines.append(LineSpec(account_code=_get_account_code(ctx, "payable"), side="debit",
                          amount_expr=lambda a,c: round(a + (a * float(c.get("vat_rate",0.0))),2),
                          description="Liquidación proveedor"))
    lines.append(LineSpec(account_code=_get_account_code(ctx, "bank"), side="credit",
                          amount_expr=lambda a,c: round(a + (a * float(c.get("vat_rate",0.0))) - vat_ret,2),
                          description="Pago proveedor"))
    if vat_ret > 0:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_ret"), side="credit",
                              amount_expr=lambda a,c: vat_ret, description="Retención IVA"))
    return lines

register_template(OperationTemplate(
    key="pago_proveedor_con_retencion_iva",
    description="Registro de compra + pago con retención de IVA integrada",
    create_lines=pago_con_retencion_create
))

# Nota de crédito
def nota_credito_create(amount: float, ctx: Dict[str, Any]):
    lines = [
        LineSpec(account_code=_get_account_code(ctx, "sales"),
                 side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc"))
    ]
    vat_rate = ctx.get("vat_rate", 0.0)
    if vat_rate:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_tr"),
                              side="debit",
                              amount_expr=lambda a,c: round(a*float(c.get("vat_rate",0.0)),2),
                              description="Reversión IVA"))
    lines.append(LineSpec(account_code=_get_account_code(ctx, "receivable"),
                          side="credit", amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True),
                          description=ctx.get("desc")))
    return lines

register_template(OperationTemplate(
    key="nota_credito",
    description="Nota de crédito: reduce ventas y cuenta por cobrar/banco",
    create_lines=nota_credito_create
))
