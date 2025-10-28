# modelos/hoja.py
from typing import List, Optional, Tuple
import pandas as pd
from .registro import Registro
from decimal import Decimal
import datetime


class Hoja:
    """
    Representa una hoja contable dentro de un libro.
    Mantiene una lista de registros (instancias de Registro).
    """

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.registros: List[Registro] = []

    def add_registro(self, registro: Registro) -> Tuple[bool, List[str]]:
        ok, mensajes = registro.validate()
        if not ok:
            return False, mensajes
        self.registros.append(registro)
        return True, [f"Registro agregado en hoja '{self.nombre}'."]

    def to_dataframe(self) -> "pd.DataFrame":
        if not self.registros:
            return pd.DataFrame(columns=[
                "fecha", "cuenta", "cantidad", "descripcion", "metodo_pago", "cfdi",
                "tipo_operacion", "iva", "isr", "iva_retencion", "documento", "folio"
            ])
        rows = [r.to_dict() for r in self.registros]
        df = pd.DataFrame(rows)
        return df

    def save_to_excel_writer(self, writer, sheet_name: Optional[str] = None):
        df = self.to_dataframe()
        name = sheet_name or self.nombre
        df.to_excel(writer, sheet_name=name, index=False)

    @classmethod
    def from_dataframe(cls, nombre: str, df: "pd.DataFrame"):
        hoja = cls(nombre=nombre)
        for _, r in df.fillna("").iterrows():
            try:
                reg = Registro.create(
                    fecha=r.get("fecha") or datetime.date.today().isoformat(),
                    cuenta=r.get("cuenta") or r.get("Codigo") or "",
                    cantidad=r.get("cantidad") or r.get("Cargo") or r.get("Abono") or 0,
                    descripcion=r.get("descripcion") or r.get("Descripcion") or "",
                    metodo_pago=r.get("metodo_pago"),
                    cfdi=bool(r.get("cfdi")) if "cfdi" in r else False,
                    tipo_operacion=r.get("Tipo_operacion") or r.get("tipo_operacion") or None,
                    extra={}
                )
            except Exception:
                # ignorar registros inválidos en carga inicial
                continue
            hoja.registros.append(reg)
        return hoja