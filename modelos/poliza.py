from typing import Dict, Any, List, Tuple, Optional


class Poliza:
    """
    Representa reglas de pólizas (qué cuentas afectan y cómo).
    """

    def __init__(self, nombre: str = "Default"):
        self.nombre = nombre
        # { Tipo_Poliza: [ {"Tipo_Cuenta": "...", "Naturaleza": "Deudora/Acreedora", "Rol": "Cargo/Abono", "CuentaDestino": "1180"}, ... ] }
        self.mapeo: Dict[str, List[Dict[str, Any]]] = {}

    def load_from_dataframe(self, df):
        """
        Espera un dataframe con columnas: Tipo_Poliza, Tipo_Cuenta, Naturaleza, Rol, Incluir, Comentario, CuentaDestino (opcional)
        """
        for _, r in df.iterrows():
            tp = str(r.get("Tipo_Poliza", "")).strip()
            if tp == "":
                # intentar otras variantes
                tp = str(r.get("Tipo Poliza", "") or r.get("Tipo_Póliza", "")).strip()
                if tp == "":
                    continue
            regla = {
                "Tipo_Cuenta": r.get("Tipo_Cuenta"),
                "Naturaleza": r.get("Naturaleza"),
                "Rol": r.get("Rol"),
                "Incluir": r.get("Incluir", True),
                "Comentario": r.get("Comentario", ""),
                "CuentaDestino": r.get("CuentaDestino") or r.get("Codigo_destino") or None
            }
            self.mapeo.setdefault(tp, []).append(regla)

    def puede_usar_cuenta(self, tipo_poliza: str, codigo_cuenta: str) -> Tuple[bool, Optional[str]]:
        if tipo_poliza not in self.mapeo:
            return False, f"No hay reglas definidas para la póliza '{tipo_poliza}'."
        return True, None

    def generar_movimientos(self, tipo_poliza: str, registro: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Genera movimientos contables básicos (lista de dicts con 'cuenta','cargo','abono','descripcion').
        """
        movimientos = []
        reglas = self.mapeo.get(tipo_poliza, [])
        importe = registro.get("cantidad") or registro.get("cantidad", 0)
        descripcion = registro.get("descripcion", "")
        # Si no hay reglas, generar movimiento simple: guardar el registro tal cual (no separar cargo/abono)
        if not reglas:
            movimientos.append({
                "cuenta": registro.get("cuenta"),
                "cargo": importe if registro.get("tipo_operacion", "").lower() in ("egreso",) else None,
                "abono": importe if registro.get("tipo_operacion", "").lower() in ("ingreso",) else None,
                "descripcion": descripcion
            })
            return movimientos

        for regla in reglas:
            rol = (str(regla.get("Rol") or "")).strip().lower()
            cuenta_dest = regla.get("CuentaDestino") or registro.get("cuenta")
            if rol in ("cargo", "carga", "debe"):
                movimientos.append({
                    "cuenta": cuenta_dest,
                    "cargo": importe,
                    "abono": None,
                    "descripcion": regla.get("Comentario") or descripcion
                })
            else:
                movimientos.append({
                    "cuenta": cuenta_dest,
                    "cargo": None,
                    "abono": importe,
                    "descripcion": regla.get("Comentario") or descripcion
                })
        return movimientos