# modelos/parametros.py
"""
ParametroFiscal - estructura simple para guardar parámetros fiscales / plantilla mínima.
Incluye helpers utilizados por registros y cálculo de impuestos.
"""
from typing import Dict, Any
from copy import deepcopy

class ParametroFiscal:
    """
    Contenedor simple para parámetros fiscales. .valores es un dict accesible.
    Proporciona helpers para obtener valores fiscales comunes (IVA, ISR, cuentas).
    """
    def __init__(self, valores: Dict[str, Any] = None):
        # Plantilla de valores mínimos recomendados para CFDI y cálculos
        defaults = {
            # Emisor
            "Emisor_RFC": "",
            "Emisor_Nombre": "",
            "Emisor_Regimen": "601",
            # Receptor
            "Receptor_RFC": "XAXX010101000",
            "Receptor_Nombre": "",
            "Receptor_UsoCFDI": "P01",
            "Receptor_DomicilioFiscalReceptor": "",  # código postal
            "Receptor_RegimenFiscal": "",
            # CFDI / pagos
            "FormaPago": "",   # e.g. '03'
            "MetodoPago": "PUE",
            "TipoDeComprobante": "I",
            "Moneda": "MXN",
            "LugarExpedicion": "",  # Código postal emisor (CP)
            # IVA / cuentas
            "IVA_general": 16,
            "IVA_trasladado_cuenta": "2080",
            # Concepto defaults
            "ObjetoImp_default": "01",
            # ISR defaults
            "ISR_retencion_pf": 0,
            "ISR_retencion_pm": 0,
        }
        if valores is None:
            valores = {}
        merged = deepcopy(defaults)
        # allow passing either ParametroFiscal instance, dict, or pandas row
        try:
            items = valores.items()
        except Exception:
            items = []
        for k, v in items:
            merged[k] = v
        self.valores: Dict[str, Any] = merged

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(valores=d)

    def get(self, key: str, default=None):
        return self.valores.get(key, default)

    def set(self, key: str, value: Any):
        self.valores[key] = value

    def to_dict(self):
        return dict(self.valores)

    # Helper convenience methods used by registro.aplicar_impuestos and others
    def get_iva_general(self) -> float:
        """Devuelve la tasa de IVA general en porcentaje (ej. 16)."""
        v = self.valores.get("IVA_general", 16)
        try:
            return float(v)
        except Exception:
            return 16.0

    def get_iva_trasladado_cuenta(self) -> str:
        return str(self.valores.get("IVA_trasladado_cuenta", "2080"))

    def get_isr_retencion_pf(self) -> float:
        v = self.valores.get("ISR_retencion_pf", 0)
        try:
            return float(v)
        except Exception:
            return 0.0

    def get_isr_retencion_pm(self) -> float:
        v = self.valores.get("ISR_retencion_pm", 0)
        try:
            return float(v)
        except Exception:
            return 0.0

    # Backwards compatibility: allow attribute-style access for existing code that used .valores
    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, key):
        return key in self.valores