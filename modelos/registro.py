# modelos/registro.py
"""
Clase Registro que representa una línea/operación contable y lógica para aplicar impuestos.
Provee:
- Registro.create(fecha, cuenta, cantidad, descripcion=None, tipo_operacion=None, cfdi=False)
- aplicar_impuestos(parametros, mapeo_fiscal_row=None) -> dict con {'iva','isr','iva_retencion'}
- validate() -> (ok: bool, mensajes: List[str]) o lanza ValueError para fecha inválida
- to_dict() -> dict (útil para polizas/generadores)
- atributos públicos usados por el resto del sistema:
  fecha (datetime.date), cuenta (str), cantidad (Decimal), descripcion (str),
  tipo_operacion (str), iva/isr/iva_retencion (Decimal), extra (dict)
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal, getcontext, ROUND_HALF_UP
from datetime import datetime, date

# asegurar precisión razonable
getcontext().prec = 12


def _normalize_keys(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normaliza las claves de un mapeo fiscal a minúsculas sin espacios/guiones para acceso tolerante.
    """
    if not d:
        return {}
    out: Dict[str, Any] = {}
    for k, v in d.items():
        try:
            kn = str(k).strip().lower().replace(" ", "_").replace("-", "_")
        except Exception:
            kn = k
        out[kn] = v
    return out


class Registro:
    """
    Representa un registro / línea de movimiento contable.
    Campos principales:
      - fecha: datetime.date
      - cuenta: str
      - cantidad: Decimal
      - descripcion: str
      - tipo_operacion: str (p. ej. 'Ingreso', 'Egreso')
      - iva, isr, iva_retencion: Decimal (calculados por aplicar_impuestos)
      - documento, folio: opcionales
      - extra: dict libre para metadatos (ej. es_abono, id_asiento, etc.)
      - cfdi: bool indicando si el registro requiere datos CFDI (opcional)
    """

    def __init__(
        self,
        fecha: date,
        cuenta: str,
        cantidad: Decimal,
        descripcion: str = "",
        tipo_operacion: Optional[str] = None,
        documento: Optional[str] = None,
        folio: Optional[str] = None,
        cfdi: bool = False,
    ):
        self.fecha: date = fecha
        self.cuenta: str = str(cuenta) if cuenta is not None else ""
        self.cantidad: Decimal = Decimal(cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.descripcion: str = str(descripcion) if descripcion is not None else ""
        self.tipo_operacion: Optional[str] = tipo_operacion
        self.documento: Optional[str] = documento
        self.folio: Optional[str] = folio
        self.cfdi: bool = bool(cfdi)

        # impuestos (valores calculados)
        self.iva: Decimal = Decimal("0.00")
        self.isr: Decimal = Decimal("0.00")
        self.iva_retencion: Decimal = Decimal("0.00")

        # datos auxiliares
        self.extra: Dict[str, Any] = {}

    @classmethod
    def create(
        cls,
        fecha: Any,
        cuenta: str,
        cantidad: Any,
        descripcion: str = "",
        tipo_operacion: Optional[str] = None,
        documento: Optional[str] = None,
        folio: Optional[str] = None,
        cfdi: bool = False,
    ) -> "Registro":
        """
        Factory para crear un Registro desde valores comunes (fecha en ISO o YYYY-MM-DD).
        Si la fecha no es parseable, levanta ValueError (los tests esperan esto en validaciones).
        cantidad puede ser str, float, Decimal, int.
        """
        # Parse fecha; si no es parseable, propagar ValueError para que el test capture el error.
        if isinstance(fecha, date):
            dt = fecha
        else:
            try:
                dt = datetime.fromisoformat(str(fecha)).date()
            except Exception:
                try:
                    dt = datetime.strptime(str(fecha), "%Y-%m-%d").date()
                except Exception as e:
                    raise ValueError(f"Fecha inválida: {fecha}") from e

        # Normalizar cantidad a Decimal
        try:
            cantidad_dec = Decimal(str(cantidad)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            cantidad_dec = Decimal("0.00")

        return cls(
            fecha=dt,
            cuenta=cuenta,
            cantidad=cantidad_dec,
            descripcion=descripcion,
            tipo_operacion=tipo_operacion,
            documento=documento,
            folio=folio,
            cfdi=cfdi,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Representación serializable del registro (útil para polizas y export).
        """
        return {
            "fecha": self.fecha.isoformat() if isinstance(self.fecha, date) else str(self.fecha),
            "cuenta": self.cuenta,
            "cantidad": float(self.cantidad),
            "descripcion": self.descripcion,
            "tipo_operacion": self.tipo_operacion,
            "iva": float(self.iva),
            "isr": float(self.isr),
            "iva_retencion": float(self.iva_retencion),
            "documento": self.documento,
            "folio": self.folio,
            "extra": dict(self.extra),
            "cfdi": self.cfdi,
        }

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Valida reglas básicas del registro:
         - fecha válida (create ya asegura o lanza ValueError)
         - cantidad > 0
         - cuenta no vacía
         - si cfdi=True, valida que exista método de pago en extra (claves aceptadas)
         - si has_invoice/has_cfdi, valida campos fiscales requeridos
        Devuelve (ok, mensajes).
        """
        msgs: List[str] = []
        ok = True

        # fecha: debe ser date (create ya asegura o lanza ValueError)
        if not isinstance(self.fecha, date):
            raise ValueError("Fecha inválida en el registro.")

        # cuenta no vacía
        if not self.cuenta or not str(self.cuenta).strip():
            ok = False
            msgs.append("Cuenta vacía o inválida.")

        # cantidad > 0
        try:
            if self.cantidad is None or Decimal(self.cantidad) <= Decimal("0.00"):
                ok = False
                # Mensaje esperado por tests: contiene 'importe es cero'
                msgs.append("Importe es cero o menor (importe es cero).")
        except Exception:
            ok = False
            msgs.append("Cantidad inválida.")

        # Si cfdi == True, requerir método de pago (en registro.extra)
        if self.cfdi:
            metodo_keys = ("metodo_pago", "metodoPago", "metodo", "MetodoPago")
            has_metodo = any(k in self.extra for k in metodo_keys)
            if not has_metodo:
                ok = False
                msgs.append("Falta método de pago para CFDI (metodo_pago).")

        # Validar campos fiscales si está marcado como factura/invoice
        has_invoice = self.extra.get("has_cfdi") or self.extra.get("has_invoice") or self.cfdi
        if has_invoice:
            fiscal_ok, fiscal_msgs = self.validate_fiscal_fields()
            if not fiscal_ok:
                ok = False
                msgs.extend(fiscal_msgs)

        return ok, msgs
    
    def validate_fiscal_fields(self) -> Tuple[bool, List[str]]:
        """
        Valida que los campos fiscales requeridos estén presentes cuando
        un movimiento está marcado como has_cfdi/has_invoice.
        
        Campos requeridos:
        - emitter_rfc (RFC del emisor)
        - receiver_rfc (RFC del receptor)
        - serie (Serie del comprobante)
        - folio (Folio del comprobante)
        - subtotal (Subtotal antes de impuestos)
        - total (Total incluyendo impuestos)
        - tax_breakdown (Desglose de impuestos)
        
        Returns:
            Tuple[bool, List[str]]: (ok, mensajes de error)
        """
        msgs: List[str] = []
        ok = True
        
        required_fields = {
            "emitter_rfc": "RFC del emisor",
            "receiver_rfc": "RFC del receptor",
            "serie": "Serie del comprobante",
            "folio": "Folio del comprobante",
            "subtotal": "Subtotal",
            "total": "Total",
            "tax_breakdown": "Desglose de impuestos"
        }
        
        for field_key, field_name in required_fields.items():
            # Check in multiple possible locations: extra dict, or direct attributes
            value = self.extra.get(field_key)
            if value is None or value == "":
                ok = False
                msgs.append(f"Falta campo fiscal requerido: {field_name} ({field_key})")
        
        # Validate RFC format (basic check)
        emitter_rfc = self.extra.get("emitter_rfc", "")
        if emitter_rfc and len(str(emitter_rfc)) < 12:
            ok = False
            msgs.append(f"RFC del emisor inválido: debe tener al menos 12 caracteres")
        
        receiver_rfc = self.extra.get("receiver_rfc", "")
        if receiver_rfc and len(str(receiver_rfc)) < 12:
            ok = False
            msgs.append(f"RFC del receptor inválido: debe tener al menos 12 caracteres")
        
        # Validate numeric fields
        try:
            subtotal = self.extra.get("subtotal")
            if subtotal is not None:
                subtotal_dec = Decimal(str(subtotal))
                if subtotal_dec <= Decimal("0.00"):
                    ok = False
                    msgs.append("Subtotal debe ser mayor a cero")
        except Exception:
            ok = False
            msgs.append("Subtotal inválido")
        
        try:
            total = self.extra.get("total")
            if total is not None:
                total_dec = Decimal(str(total))
                if total_dec <= Decimal("0.00"):
                    ok = False
                    msgs.append("Total debe ser mayor a cero")
        except Exception:
            ok = False
            msgs.append("Total inválido")
        
        return ok, msgs

    def aplicar_impuestos(self, parametros, mapeo_fiscal_row: Optional[Dict[str, Any]] = None) -> Dict[str, Decimal]:
        """
        Calcula IVA/ISR/retenciones usando ParametroFiscal y la fila del Mapeo_Fiscal.
        - parametros: instancia de ParametroFiscal (debe proveer helpers como get_iva_general())
        - mapeo_fiscal_row: fila del mapeo (opcional) con claves tipo 'aplica_iva','iva_tasa','aplica_isr','retencion_isr', etc.

        Actualiza self.iva, self.isr, self.iva_retencion y devuelve un dict con esos valores.
        """
        mf = _normalize_keys(mapeo_fiscal_row) if mapeo_fiscal_row else {}

        # Defaults
        aplica_iva = False
        aplica_isr = False

        # Usar Decimal para tasas
        try:
            iva_tasa = Decimal(str(parametros.get_iva_general()))
        except Exception:
            iva_tasa = Decimal("16.00")

        iva_retencion_porcentaje = Decimal("0.00")
        isr_retencion_porcentaje = Decimal("0.00")

        # Interpretar mapeo si existe
        if mf:
            if "aplica_iva" in mf:
                val = str(mf.get("aplica_iva") or "").strip().lower()
                aplica_iva = val in ("si", "sí", "s", "true", "1", "yes")
            if "iva_tasa" in mf and mf.get("iva_tasa") not in (None, ""):
                try:
                    iva_tasa = Decimal(str(mf.get("iva_tasa"))).quantize(Decimal("0.01"))
                except Exception:
                    iva_tasa = Decimal(str(parametros.get_iva_general()))
            if "aplica_isr" in mf:
                val = str(mf.get("aplica_isr") or "").strip().lower()
                aplica_isr = val in ("si", "sí", "s", "true", "1", "yes")
            for k in ("retencion_iva", "iva_retencion", "retencion_iva_porcentaje"):
                if k in mf and mf.get(k) not in (None, "", 0):
                    try:
                        iva_retencion_porcentaje = Decimal(str(mf.get(k))).quantize(Decimal("0.01"))
                    except Exception:
                        iva_retencion_porcentaje = Decimal("0.00")
            for k in ("retencion_isr", "isr_retencion", "retencion_isr_porcentaje"):
                if k in mf and mf.get(k) not in (None, "", 0):
                    try:
                        isr_retencion_porcentaje = Decimal(str(mf.get(k))).quantize(Decimal("0.01"))
                    except Exception:
                        isr_retencion_porcentaje = Decimal("0.00")
        else:
            # Sin mapeo, usar parámetros generales si existen
            try:
                iva_tasa = Decimal(str(parametros.get_iva_general()))
            except Exception:
                iva_tasa = Decimal("16.00")
            aplica_iva = False
            aplica_isr = False

        # Cálculos usando Decimal
        if aplica_iva:
            self.iva = (self.cantidad * iva_tasa / Decimal("100")).quantize(Decimal("0.01"))
        else:
            self.iva = Decimal("0.00")

        if aplica_isr:
            # Preferir retención ISR por mapeo; si no existe, usar parámetro general
            if isr_retencion_porcentaje and isr_retencion_porcentaje > 0:
                isr_pct = isr_retencion_porcentaje
            else:
                try:
                    isr_pct = Decimal(str(parametros.get_isr_retencion_pf()))
                except Exception:
                    isr_pct = Decimal("0.00")
            self.isr = (self.cantidad * isr_pct / Decimal("100")).quantize(Decimal("0.01"))
        else:
            self.isr = Decimal("0.00")

        if iva_retencion_porcentaje and iva_retencion_porcentaje > 0:
            self.iva_retencion = (self.cantidad * iva_retencion_porcentaje / Decimal("100")).quantize(Decimal("0.01"))
        else:
            self.iva_retencion = Decimal("0.00")

        # Devolver resumen numérico
        return {"iva": self.iva, "isr": self.isr, "iva_retencion": self.iva_retencion}

    def __repr__(self) -> str:
        return f"<Registro fecha={self.fecha} cuenta={self.cuenta} cantidad={self.cantidad} desc={self.descripcion[:20]}>"