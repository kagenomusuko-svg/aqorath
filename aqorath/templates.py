from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional
from datetime import date, datetime
from decimal import Decimal
from .models import Account, AppConfig
from .storage import get_session
from .money import to_decimal_exact
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

# Expresiones para cálculos de montos — P0-2: usar Decimal exacto, no float
def fixed_amount_expr(amount_fixed: float):
    return lambda amount, ctx: to_decimal_exact(amount_fixed)

def base_amount_expr():
    return lambda amount, ctx: to_decimal_exact(amount)

def percent_expr(rate: float | Decimal):
    def fn(amount, ctx):
        amt = to_decimal_exact(amount)
        r = to_decimal_exact(rate)
        result = amt * r
        # Redondear a 2 decimales
        return result.quantize(Decimal("0.01"))
    return fn

def total_with_vat_expr(vat_key: str = "vat_rate", amount_is_net: bool = True):
    def fn(amount, ctx):
        vat = to_decimal_exact(ctx.get(vat_key, 0.0))
        amt = to_decimal_exact(amount)
        if amount_is_net:
            result = amt + (amt * vat)
        else:
            result = amt
        return result.quantize(Decimal("0.01"))
    return fn

def gross_base_expr(vat_key: str = "vat_rate"):
    def fn(amount, ctx):
        vat = to_decimal_exact(ctx.get(vat_key, 0.0))
        amt = to_decimal_exact(amount)
        if vat == 0:
            return amt.quantize(Decimal("0.01"))
        result = amt / (Decimal("1") + vat)
        return result.quantize(Decimal("0.01"))
    return fn

def gross_vat_expr(vat_key: str = "vat_rate"):
    def fn(amount, ctx):
        vat = to_decimal_exact(ctx.get(vat_key, 0.0))
        amt = to_decimal_exact(amount)
        if vat == 0:
            return Decimal("0")
        base = amt / (Decimal("1") + vat)
        result = amt - base
        return result.quantize(Decimal("0.01"))
    return fn

# P0-2: Auxiliary function for net amount calculation (amount * (1 - rate))
def net_amount_expr(retention_rate: float | Decimal):
    """
    Returns a lambda that calculates: amount * (1 - retention_rate) using Decimal exactness.
    """
    rate_dec = to_decimal_exact(retention_rate)
    return lambda a, c: (to_decimal_exact(a) * (Decimal("1") - rate_dec)).quantize(Decimal("0.01"))

# P0-2: Auxiliary function for net amount with two retention rates
def net_amount_dual_expr(rate1: float | Decimal, rate2: float | Decimal):
    """
    Returns a lambda that calculates: amount * (1 - rate1 - rate2) using Decimal exactness.
    """
    r1_dec = to_decimal_exact(rate1)
    r2_dec = to_decimal_exact(rate2)
    return lambda a, c: (to_decimal_exact(a) * (Decimal("1") - r1_dec - r2_dec)).quantize(Decimal("0.01"))

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

# ---------- Templates ----------

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
        # P0-2: Use Decimal exacto, no float
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_tr"),
                              side="credit",
                              amount_expr=percent_expr(vat_rate),
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
        # P0-2: Use Decimal exacto via percent_expr
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_ac"),
                              side="debit",
                              amount_expr=percent_expr(vat_rate),
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
    # P0-2: Convert to Decimal for exact calculations
    amt_dec = to_decimal_exact(amount)
    vat_rate_dec = to_decimal_exact(ctx.get("vat_rate", 0.0))
    vat_ret_rate_dec = to_decimal_exact(ctx.get("vat_ret_rate", 0.0))
    
    vat = (amt_dec * vat_rate_dec).quantize(Decimal("0.01"))
    vat_ret = (vat * vat_ret_rate_dec).quantize(Decimal("0.01"))

    acct = ctx.get("account_codes", {})
    lines = []
    # Reconocimiento factura
    lines.append(LineSpec(account_code=_get_account_code(ctx, "expense"), side="debit",
                          amount_expr=base_amount_expr(), description=ctx.get("desc")))
    if vat > 0:
        # P0-2: Use percent_expr for exact VAT (pass Decimal directly)
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_ac"), side="debit",
                              amount_expr=percent_expr(vat_rate_dec),
                              description="IVA acreditable"))
    lines.append(LineSpec(account_code=_get_account_code(ctx, "payable"), side="credit",
                          amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True),
                          description=ctx.get("desc")))
    # Pago
    lines.append(LineSpec(account_code=_get_account_code(ctx, "payable"), side="debit",
                          amount_expr=total_with_vat_expr("vat_rate", amount_is_net=True),
                          description="Liquidación proveedor"))
    # P0-2: Bank payment with exact VAT and retention
    def bank_payment_expr():
        return lambda a, c: (
            to_decimal_exact(a) + (to_decimal_exact(a) * to_decimal_exact(c.get("vat_rate", 0.0))) - vat_ret
        ).quantize(Decimal("0.01"))
    
    lines.append(LineSpec(account_code=_get_account_code(ctx, "bank"), side="credit",
                          amount_expr=bank_payment_expr(),
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
        # P0-2: Use percent_expr for exact VAT
        lines.append(LineSpec(account_code=_get_account_code(ctx, "vat_tr"),
                              side="debit",
                              amount_expr=percent_expr(vat_rate),
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

# Honorarios (retención ISR)
def honorarios_create(amount: float, ctx: Dict[str, Any]):
    """
    Honorarios: gasto / banco neto + ISR retenido (si aplica)
    - amount is gross (base) by convention here
    """
    # P0-2: Use Decimal exactness for retention rates
    isr_rate = to_decimal_exact(ctx.get("isr_ret_rate", 0.0))
    acct = ctx.get("account_codes", {})
    lines = []
    # gasto (cargo = base)
    lines.append(LineSpec(account_code=_get_account_code(ctx, "expense"),
                          side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")))
    # banco (abono = base * (1 - isr_rate)) — P0-2: use Decimal exactness
    lines.append(LineSpec(account_code=_get_account_code(ctx, "bank"),
                          side="credit", amount_expr=net_amount_expr(isr_rate), description=ctx.get("desc")))
    # ISR retenido (si aplica)
    if isr_rate and isr_rate > 0:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "isr_ret"),
                              side="credit", amount_expr=percent_expr(isr_rate),
                              description="Retención ISR"))
    return lines

register_template(OperationTemplate(
    key="honorarios",
    description="Honorarios: gasto / banco neto + ISR retenido",
    create_lines=honorarios_create
))

# Nómina básica: sueldo bruto, retenciones ISR e IMSS, carga patronal (simplificada)
def nomina_create(amount: float, ctx: Dict[str, Any]):
    """
    amount: sueldo bruto por trabajador / periodo
    ctx expects account_codes:
      - salary_expense
      - employer_social_expense
      - bank
      - isr_ret
      - imss_obrero_payable
      - imss_patronal_payable (optional)
    and rates:
      - isr_ret_rate
      - imss_obrero_rate
      - imss_patronal_rate
    """
    # P0-2: Use Decimal exactness for retention rates
    isr = to_decimal_exact(ctx.get("isr_ret_rate", 0.15))
    imss_obr = to_decimal_exact(ctx.get("imss_obrero_rate", 0.0275))
    imss_pat = to_decimal_exact(ctx.get("imss_patronal_rate", 0.10))
    lines = []

    # Gasto por sueldos (cargo = bruto)
    lines.append(LineSpec(account_code=_get_account_code(ctx, "salary_expense"),
                          side="debit", amount_expr=base_amount_expr(), description=ctx.get("desc")))

    # Carga patronal: registrar como gasto (DEBIT) en employer_social_expense
    # y como pasivo (CREDIT) en imss_patronal_payable si está configurada
    if imss_pat and imss_pat > 0:
        # Debitar gasto patronal (employer_social_expense)
        try:
            acct_employer = _get_account_code(ctx, "employer_social_expense")
            lines.append(LineSpec(account_code=acct_employer,
                                  side="debit", amount_expr=percent_expr(imss_pat),
                                  description="IMSS patronal (gasto patronal)"))
        except ValueError:
            acct_employer = None

    # Pago neto al trabajador (abono = bruto * (1 - isr - imss_obr)) — P0-2: use Decimal exactness
    lines.append(LineSpec(account_code=_get_account_code(ctx, "bank"),
                          side="credit", amount_expr=net_amount_dual_expr(isr, imss_obr), description=ctx.get("desc")))

    # ISR retenido (abono)
    if isr and isr > 0:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "isr_ret"),
                              side="credit", amount_expr=percent_expr(isr), description="ISR retenido"))

    # IMSS obrero (retenido, abono)
    if imss_obr and imss_obr > 0:
        lines.append(LineSpec(account_code=_get_account_code(ctx, "imss_obrero_payable"),
                              side="credit", amount_expr=percent_expr(imss_obr), description="IMSS obrero retenido"))

    # IMSS patronal (pasivo): si existe cuenta de pasivo la acreditamos (CREDIT)
    if imss_pat and imss_pat > 0:
        try:
            acct_pat_payable = _get_account_code(ctx, "imss_patronal_payable")
            lines.append(LineSpec(account_code=acct_pat_payable,
                                  side="credit", amount_expr=percent_expr(imss_pat),
                                  description="IMSS patronal (por pagar)"))
        except ValueError:
            # si no hay cuenta pasivo para IMSS patronal, omitimos la línea del pasivo
            pass

    return lines

register_template(OperationTemplate(
    key="nomina",
    description="Asiento de nómina básico: sueldo bruto, retenciones ISR e IMSS, carga patronal",
    create_lines=nomina_create
))