# modelos/catalogo.py
import pandas as pd
from typing import Dict, Optional, Any, Tuple, List


class CatalogoCuenta:
    """
    CatalogoCuenta carga y valida cuentas desde un DataFrame o diccionario.
    Distinción entre contabilidad OSC y Comercial se mantiene en contabilidad_tipo.
    """

    def __init__(self, contabilidad_tipo: str = "OSC"):
        self.contabilidad_tipo = contabilidad_tipo  # "OSC" o "Comercial"
        # almacenamiento por código (string)
        self._catalogo: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def from_excel(cls, xlsx_path: str, sheet_name: str = "Catalogo", contabilidad_tipo: str = "OSC"):
        inst = cls(contabilidad_tipo=contabilidad_tipo)
        try:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, dtype=str)
        except Exception as e:
            raise RuntimeError(f"No se pudo leer la hoja '{sheet_name}' desde {xlsx_path}: {e}")

        inst.load_from_dataframe(df)
        return inst

    def load_from_dataframe(self, df: "pd.DataFrame"):
        for _, row in df.fillna("").iterrows():
            codigo = str(row.get("Codigo", "")).strip()
            if not codigo:
                # intentar detectar variantes de nombre
                for k in row.index:
                    if str(k).strip().lower() in ("codigo", "código", "code"):
                        codigo = str(row.get(k, "")).strip()
                        break
            if not codigo:
                continue
            # guardar toda la fila como dict (convert to primitive types)
            self._catalogo[codigo] = {k: (v if not pd.isna(v) else "") for k, v in dict(row).items()}

    def get(self, codigo: str) -> Optional[Dict[str, Any]]:
        if codigo is None:
            return None
        return self._catalogo.get(str(codigo).strip())

    def exists(self, codigo: str) -> bool:
        return str(codigo).strip() in self._catalogo

    def validate_account(self, codigo: str) -> Tuple[bool, str]:
        """
        Devuelve (es_valida, mensaje_amigable)
        """
        if not codigo:
            return False, "El código de cuenta está vacío."
        if not self.exists(codigo):
            return False, f"La cuenta '{codigo}' no se encontró en el catálogo. Revisa el catálogo de cuentas."
        return True, f"La cuenta '{codigo}' es válida."

    def as_dataframe(self) -> "pd.DataFrame":
        if not self._catalogo:
            return pd.DataFrame()
        df = pd.DataFrame.from_dict(self._catalogo, orient="index")
        df.index.name = "Codigo"
        return df.reset_index()