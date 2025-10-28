# app.py
"""
App orquestador que apunta por defecto a datos/Sistema_Contable.xlsx.
Incluye respaldo con retención, creación de ejemplo y funciones para listar/exportar asientos.
"""

from pathlib import Path
import pandas as pd
from modelos.libro import Libro
from modelos.registro import Registro
from datetime import datetime
from typing import Optional

DEFAULT_DATOS_DIR = Path("datos")
DEFAULT_XLSX = DEFAULT_DATOS_DIR / "Sistema_Contable.xlsx"


class App:
    def __init__(self, datos_path: Path = DEFAULT_XLSX):
        self.datos_path = Path(datos_path)
        self.libro: Optional[Libro] = None

    def load_or_create(self):
        DEFAULT_DATOS_DIR.mkdir(parents=True, exist_ok=True)
        if self.datos_path.exists():
            self.libro = Libro.load_xlsx(str(self.datos_path), contabilidad_tipo="OSC")
            return {"status": "loaded", "path": str(self.datos_path)}
        else:
            self._create_sample_data(self.datos_path)
            self.libro = Libro.load_xlsx(str(self.datos_path), contabilidad_tipo="OSC")
            return {"status": "created", "path": str(self.datos_path)}

    def _create_sample_data(self, path: Path):
        df_catalogo = pd.DataFrame([
            {"Codigo": "1101", "Nombre_OSC": "Bancos", "Tipo_cuenta": "Activo", "Subtipo": "Circulante", "Naturaleza": "Deudora"},
            {"Codigo": "4101", "Nombre_OSC": "Donativos en efectivo", "Tipo_cuenta": "Ingreso", "Naturaleza": "Acreedora"},
            {"Codigo": "2080", "Nombre_OSC": "IVA trasladado", "Tipo_cuenta": "Pasivo", "Naturaleza": "Acreedora"},
            {"Codigo": "1180", "Nombre_OSC": "IVA acreditable", "Tipo_cuenta": "Activo", "Naturaleza": "Deudora"},
            {"Codigo": "2160", "Nombre_OSC": "ISR retenido a terceros", "Tipo_cuenta": "Pasivo", "Naturaleza": "Acreedora"},
        ])

        df_param = pd.DataFrame([{
            "IVA_general": 16,
            "IVA_cero": 0,
            "ISR_retencion_pf": 10,
            "IVA_retencion_general": 66.6667,
            "Metodo_pago_default": "PUE",
            "Dias_pago_maximo": 30,
            "IVA_acreditable_cuenta": "1180",
            "IVA_trasladado_cuenta": "2080",
            "ISR_retenido_cuenta": "2160",
            "IVA_retenido_cuenta": "2170"
        }])

        df_mapeo_fiscal = pd.DataFrame([
            {
                "Codigo": "4101",
                "Nombre": "Donativos en efectivo",
                "Tipo_operacion": "Ingreso",
                "Aplica IVA": "Si",
                "IVA tasa": 16,
                "Aplica ISR": "",
                "retencion IVA": "",
                "retencion ISR": "",
                "Codigo_destino_IVA": "2080",
                "Codigo_destino_ISR": "",
                "Codigo_destino_IVA_retencion": ""
            }
        ])

        df_mapeo_polizas = pd.DataFrame([
            {"Tipo_Poliza": "Ingreso", "Tipo_Cuenta": "Activo", "Naturaleza": "Deudora", "Rol": "Cargo", "Incluir": True, "CuentaDestino": "1101", "Comentario": "Entrada a bancos"},
            {"Tipo_Poliza": "Ingreso", "Tipo_Cuenta": "Ingreso", "Naturaleza": "Acreedora", "Rol": "Abono", "Incluir": True, "CuentaDestino": "4101", "Comentario": "Reconocimiento ingreso"},
        ])

        df_movimientos = pd.DataFrame(columns=[
            "fecha", "cuenta", "cantidad", "descripcion", "metodo_pago", "cfdi", "tipo_operacion"
        ])

        with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
            df_movimientos.to_excel(writer, sheet_name="Movimientos", index=False)
            df_catalogo.to_excel(writer, sheet_name="Catalogo", index=False)
            df_param.to_excel(writer, sheet_name="ParametrosFiscales", index=False)
            df_mapeo_fiscal.to_excel(writer, sheet_name="Mapeo_Fiscal", index=False)
            df_mapeo_polizas.to_excel(writer, sheet_name="Mapeo_Polizas", index=False)

    def save_libro(self):
        if not self.libro:
            return {"status": "error", "message": "No hay libro cargado"}
        self.libro.save_xlsx(str(self.datos_path))
        return {"status": "saved", "path": str(self.datos_path)}

    def add_registro_and_save(self, hoja_nombre: str, registro: Registro, aplicar_impuestos: bool = True):
        if not self.libro:
            return {"status": "error", "message": "No hay libro cargado"}
        ok, msgs = self.libro.add_registro_to_hoja(hoja_nombre, registro, aplicar_impuestos=aplicar_impuestos)
        if ok:
            # generamos asientos automáticamente
            try:
                self.libro.generar_movimientos_desde_poliza(hoja_nombre)
            except Exception:
                pass
            self.libro.save_xlsx(str(self.datos_path))
            # devolver id_asientos creados (lista)
            asientos = [a["id"] for a in self.libro.asientos.values()]
            return {"status": "ok", "messages": msgs, "asientos": asientos}
        else:
            return {"status": "error", "messages": msgs}

    def list_asientos(self):
        if not self.libro:
            return {"status": "error", "message": "No hay libro cargado"}
        return {"status": "ok", "asientos": self.libro.listar_asientos()}

    def export_asiento(self, id_asiento: int, dest_path: Path, fmt: str = "csv"):
        if not self.libro:
            return {"status": "error", "message": "No hay libro cargado"}
        return self.libro.export_asiento(id_asiento, str(dest_path), fmt=fmt)