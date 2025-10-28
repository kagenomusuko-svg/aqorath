# modelos/libro.py
import os
import logging
import shutil
import zipfile
from typing import Dict, Optional, List, Any, Tuple
import pandas as pd
from .hoja import Hoja
from .catalogo import CatalogoCuenta
from .parametros import ParametroFiscal
from .poliza import Poliza
from datetime import date, datetime
from pathlib import Path
from .registro import Registro
from decimal import Decimal
import unicodedata
import re
import json


def _normalize_col_name(name: str) -> str:
    if name is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(name))
    only_ascii = "".join([c for c in nfkd if not unicodedata.combining(c)])
    s = only_ascii.lower()
    s = re.sub(r"[ \-\/]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s.strip("_")


_MAPEO_KEYS = {
    "codigo": ["codigo", "code", "cod", "id"],
    "tipo_operacion": ["tipo_operacion", "tipooperacion", "tipo-operación", "tipo-operacion", "tipo"],
    "aplica_iva": ["aplica_iva", "aplicaiva", "aplica_iva?"],
    "iva_tasa": ["iva_tasa", "iva tasa", "iva_tasa%","iva"],
    "aplica_isr": ["aplica_isr", "aplicaisr"],
    "retencion_iva": ["retencion_iva", "iva_retencion", "retencion_iva_porcentaje"],
    "retencion_isr": ["retencion_isr", "isr_retencion", "retencion_isr_porcentaje"],
    "codigo_destino_iva": ["codigo_destino_iva", "codigo_destino_iva", "codigo_destino_iva_retencion", "codigo_destino_iva_destino", "codigo_destino_iva_dest"],
    "codigo_destino_isr": ["codigo_destino_isr", "codigo_destino_isr", "codigo_destino_isr_destino"],
    "codigo_destino_iva_retencion": ["codigo_destino_iva_retencion", "codigo_destino_iva_ret"],
    "nombre": ["nombre", "name"],
    "tipo_operacion_nombre": ["tipo_operacion", "tipo_operacion_nombre"]
}


class Libro:
    """
    Libro contable con soporte de asientos compuestos, export y persistencia mejorada,
    con backups comprimidos (.zip) y retención configurable.
    """

    def __init__(self, contabilidad_tipo: str = "OSC", ejercicio: Optional[int] = None):
        self.contabilidad_tipo = contabilidad_tipo
        self.ejercicio = ejercicio or date.today().year
        self.hojas: Dict[str, Hoja] = {}
        self.catalogo = CatalogoCuenta(contabilidad_tipo=contabilidad_tipo)
        self.parametros = ParametroFiscal()
        self.polizas = Poliza()
        self.mapeo_fiscal: Dict[str, Dict] = {}
        self.locked = False
        self.mapeo_fiscal_warnings: List[str] = []

        # Asientos en memoria
        self.asientos: Dict[int, Dict[str, Any]] = {}
        self.next_asiento_id: int = 1

        # Backup policy (configurable)
        # backup_mode: "always" | "first" | "none"
        self.backup_mode: str = "always"
        self.backup_retention: int = 5  # conservar N backups más recientes
        self.backup_compress: bool = True  # si True, crear backup como ZIP (contiene el .xlsx)

        # logger
        self.logger = logging.getLogger(f"Libro_{self.ejercicio}")
        if not self.logger.handlers:
            self._setup_logger()

    def _setup_logger(self) -> None:
        self.logger.setLevel(logging.INFO)
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"libro_{self.ejercicio}_{ts}.log"
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        fh.setFormatter(fmt)
        self.logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        self.logger.addHandler(ch)
        self.logger.info("Logger inicializado para Libro")

    def new_hoja(self, nombre: str) -> Hoja:
        h = Hoja(nombre)
        self.hojas[nombre] = h
        return h

    def add_hoja(self, hoja: Hoja) -> None:
        self.hojas[hoja.nombre] = hoja

    def _rotate_backups(self, backups_dir: Path, stem: str, suffix: str) -> None:
        """
        Mantiene solo self.backup_retention archivos más recientes en backups_dir para el stem.
        suffix incluye el punto (ej. '.zip' o '.xlsx').
        """
        if not backups_dir.exists():
            return
        files = sorted([p for p in backups_dir.iterdir() if p.is_file() and p.name.startswith(stem) and p.suffix == suffix],
                       key=lambda p: p.stat().st_mtime, reverse=True)
        keep = self.backup_retention
        for p in files[keep:]:
            try:
                p.unlink()
                self.logger.info(f"Backup eliminado por retención: {p}")
            except Exception as e:
                self.logger.warning(f"No se pudo eliminar backup antiguo {p}: {e}")

    def save_xlsx(self, path: str) -> None:
        """
        Guarda todas las hojas y tablas auxiliares en el xlsx.
        Realiza backup según la política y aplica retención.
        Añade hojas: Asientos, Asientos_Lineas, Advertencias.
        """
        pathp = Path(path)
        # hacer backup si existe y si la política lo permite
        if pathp.exists() and self.backup_mode != "none":
            do_backup = False
            if self.backup_mode == "always":
                do_backup = True
            elif self.backup_mode == "first":
                backups_dir = pathp.parent / "backups"
                existing = list(backups_dir.glob(f"{pathp.stem}_*{pathp.suffix}")) if backups_dir.exists() else []
                if not existing:
                    do_backup = True
            if do_backup:
                backups_dir = pathp.parent / "backups"
                backups_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                try:
                    if self.backup_compress:
                        # crear ZIP que contenga el archivo original
                        backup_zip = backups_dir / f"{pathp.stem}_{ts}.zip"
                        with zipfile.ZipFile(backup_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                            zf.write(pathp, arcname=pathp.name)
                        self.logger.info(f"Backup comprimido creado: {backup_zip}")
                        # rotar zips
                        self._rotate_backups(backups_dir, pathp.stem, ".zip")
                    else:
                        backup_path = backups_dir / f"{pathp.stem}_{ts}.bak{pathp.suffix}"
                        shutil.copy2(str(pathp), str(backup_path))
                        self.logger.info(f"Backup creado: {backup_path}")
                        self._rotate_backups(backups_dir, pathp.stem, pathp.suffix)
                except Exception as e:
                    self.logger.warning(f"No se pudo crear backup comprimido, intentando copia directa: {e}")
                    try:
                        backup_path = backups_dir / f"{pathp.stem}_{ts}.bak{pathp.suffix}"
                        shutil.copy2(str(pathp), str(backup_path))
                        self.logger.info(f"Backup creado (fallback): {backup_path}")
                        self._rotate_backups(backups_dir, pathp.stem, pathp.suffix)
                    except Exception as ee:
                        self.logger.error(f"No se pudo crear backup fallback: {ee}")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            # Hojas de registros
            for nombre, hoja in self.hojas.items():
                try:
                    hoja.save_to_excel_writer(writer, sheet_name=nombre)
                except Exception as e:
                    self.logger.warning(f"Error guardando hoja {nombre}: {e}")
            # guardar catálogo
            try:
                df_cat = self.catalogo.as_dataframe()
                df_cat.to_excel(writer, sheet_name="Catalogo", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Catalogo: {e}")
                pd.DataFrame().to_excel(writer, sheet_name="Catalogo", index=False)
            # parámetros
            try:
                df_par = pd.DataFrame([self.parametros.valores])
                df_par.to_excel(writer, sheet_name="ParametrosFiscales", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando ParametrosFiscales: {e}")
                pd.DataFrame().to_excel(writer, sheet_name="ParametrosFiscales", index=False)
            # mapeo fiscal
            try:
                if self.mapeo_fiscal:
                    df_map = pd.DataFrame(list(self.mapeo_fiscal.values()))
                    df_map.to_excel(writer, sheet_name="Mapeo_Fiscal", index=False)
                else:
                    pd.DataFrame().to_excel(writer, sheet_name="Mapeo_Fiscal", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Mapeo_Fiscal: {e}")
                pd.DataFrame().to_excel(writer, sheet_name="Mapeo_Fiscal", index=False)
            # polizas
            try:
                pol_rows = []
                for tipo, reglas in self.polizas.mapeo.items():
                    for r in reglas:
                        row = {"Tipo_Poliza": tipo}
                        row.update(r)
                        pol_rows.append(row)
                pd.DataFrame(pol_rows).to_excel(writer, sheet_name="Mapeo_Polizas", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Mapeo_Polizas: {e}")
                pd.DataFrame().to_excel(writer, sheet_name="Mapeo_Polizas", index=False)

            # Asientos_Lineas
            try:
                filas_lineas = []
                for id_asiento, asi in sorted(self.asientos.items()):
                    for linea in asi.get("lineas", []):
                        filas_lineas.append({
                            "id_asiento": id_asiento,
                            "fecha": asi.get("fecha").isoformat() if isinstance(asi.get("fecha"), date) else str(asi.get("fecha")),
                            "cuenta": linea.get("cuenta"),
                            "cargo": linea.get("cargo") if linea.get("cargo") not in (None, "") else 0.0,
                            "abono": linea.get("abono") if linea.get("abono") not in (None, "") else 0.0,
                            "descripcion": linea.get("descripcion"),
                            "es_abono": bool(linea.get("es_abono", False))
                        })
                if filas_lineas:
                    pd.DataFrame(filas_lineas).to_excel(writer, sheet_name="Asientos_Lineas", index=False)
                else:
                    pd.DataFrame(columns=["id_asiento", "fecha", "cuenta", "cargo", "abono", "descripcion", "es_abono"]).to_excel(writer, sheet_name="Asientos_Lineas", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Asientos_Lineas: {e}")

            # Asientos
            try:
                filas_asientos = []
                for id_asiento, asi in sorted(self.asientos.items()):
                    tim = asi.get("timbrado", {}) or {}
                    filas_asientos.append({
                        "id_asiento": id_asiento,
                        "fecha": asi.get("fecha").isoformat() if isinstance(asi.get("fecha"), date) else str(asi.get("fecha")),
                        "descripcion": asi.get("descripcion"),
                        "lineas_count": len(asi.get("lineas", [])),
                        "total_cargo": float(asi.get("total_cargo", 0.0)),
                        "total_abono": float(asi.get("total_abono", 0.0)),
                        "timbrado_uuid": tim.get("uuid", ""),
                        "timbrado_sello": tim.get("sello", ""),
                        "timbrado_xml": tim.get("xml_path", ""),
                        "timbrado_importado_en": tim.get("importado_en", "")
                    })
                if filas_asientos:
                    pd.DataFrame(filas_asientos).to_excel(writer, sheet_name="Asientos", index=False)
                else:
                    pd.DataFrame(columns=["id_asiento", "fecha", "descripcion", "lineas_count", "total_cargo", "total_abono", "timbrado_uuid", "timbrado_sello", "timbrado_xml", "timbrado_importado_en"]).to_excel(writer, sheet_name="Asientos", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Asientos: {e}")

            # Advertencias
            try:
                advertencias = []
                for w in self.mapeo_fiscal_warnings:
                    advertencias.append({"tipo": "mapeo_fiscal", "mensaje": w})
                if advertencias:
                    pd.DataFrame(advertencias).to_excel(writer, sheet_name="Advertencias", index=False)
                else:
                    pd.DataFrame(columns=["tipo", "mensaje"]).to_excel(writer, sheet_name="Advertencias", index=False)
            except Exception as e:
                self.logger.warning(f"Error guardando Advertencias: {e}")

        self.logger.info(f"Libro guardado en {path}")

    @classmethod
    def load_xlsx(cls, path: str, contabilidad_tipo: str = "OSC"):
        libro = cls(contabilidad_tipo=contabilidad_tipo)
        xls = pd.read_excel(path, sheet_name=None)
        for sheet_name, df in xls.items():
            key = str(sheet_name).strip().lower()
            if key in ("catalogo", "catálogo"):
                libro.catalogo.load_from_dataframe(df)
            elif key in ("parametrosfiscales", "parametros", "parametros_fiscales"):
                if not df.empty:
                    libro.parametros = ParametroFiscal.from_dict(df.iloc[0].to_dict())
            elif key in ("mapeo_polizas", "mapeo_polizas".lower(), "mapeo_poliza", "mapeo_polizas"):
                libro.polizas.load_from_dataframe(df)
            elif key in ("mapeo_fiscal",):
                libro._load_mapeo_fiscal_from_df(df)
            elif key in ("asientos_lineas", "asientos_lineas".lower()):
                for _, r in df.fillna("").iterrows():
                    try:
                        id_as = int(r.get("id_asiento"))
                    except Exception:
                        continue
                    fecha = r.get("fecha")
                    if id_as not in libro.asientos:
                        libro.asientos[id_as] = {"id": id_as, "fecha": fecha, "descripcion": "", "lineas": [], "total_cargo": 0.0, "total_abono": 0.0}
                        libro.next_asiento_id = max(libro.next_asiento_id, id_as + 1)
                    linea = {
                        "cuenta": str(r.get("cuenta") or ""),
                        "cargo": float(r.get("cargo") or 0.0),
                        "abono": float(r.get("abono") or 0.0),
                        "descripcion": r.get("descripcion") or "",
                        "es_abono": bool(r.get("es_abono", False))
                    }
                    libro.asientos[id_as]["lineas"].append(linea)
                    libro.asientos[id_as]["total_cargo"] += linea["cargo"]
                    libro.asientos[id_as]["total_abono"] += linea["abono"]
            elif key in ("asientos",):
                # cargar resumen de asientos y metadatos (incluye columnas de timbrado si existen)
                for _, r in df.fillna("").iterrows():
                    try:
                        id_as = int(r.get("id_asiento"))
                    except Exception:
                        continue
                    if id_as not in libro.asientos:
                        libro.asientos[id_as] = {"id": id_as, "fecha": r.get("fecha"), "descripcion": r.get("descripcion") or "", "lineas": [], "total_cargo": float(r.get("total_cargo") or 0.0), "total_abono": float(r.get("total_abono") or 0.0)}
                    else:
                        libro.asientos[id_as].update({
                            "fecha": r.get("fecha"),
                            "descripcion": r.get("descripcion") or libro.asientos[id_as].get("descripcion", ""),
                            "total_cargo": float(r.get("total_cargo") or libro.asientos[id_as].get("total_cargo", 0.0)),
                            "total_abono": float(r.get("total_abono") or libro.asientos[id_as].get("total_abono", 0.0))
                        })
                    # leer posibles columnas de timbrado
                    uuid = r.get("timbrado_uuid") or r.get("uuid") or ""
                    sello = r.get("timbrado_sello") or ""
                    xmlp = r.get("timbrado_xml") or ""
                    imported = r.get("timbrado_importado_en") or ""
                    if any([uuid, sello, xmlp, imported]):
                        libro.asientos[id_as].setdefault("timbrado", {})
                        libro.asientos[id_as]["timbrado"].update({
                            "uuid": uuid,
                            "sello": sello,
                            "xml_path": xmlp,
                            "importado_en": imported
                        })
                    libro.next_asiento_id = max(libro.next_asiento_id, id_as + 1)
            else:
                hoja = Hoja.from_dataframe(sheet_name, df)
                libro.add_hoja(hoja)
        libro.mapeo_fiscal_warnings = libro.validate_mapeo_fiscal()
        return libro

    def _load_mapeo_fiscal_from_df(self, df: "pd.DataFrame") -> None:
        col_map = {}
        for col in df.columns:
            norm = _normalize_col_name(col)
            col_map[norm] = col
        filas = []
        for _, row in df.fillna("").iterrows():
            rowd = dict(row)
            normalized_row = {}
            for orig_col, val in rowd.items():
                norm_col = _normalize_col_name(orig_col)
                normalized_row[norm_col] = val
            mapped = {}
            for std_key, possibles in _MAPEO_KEYS.items():
                for p in possibles:
                    p_norm = _normalize_col_name(p)
                    if p_norm in normalized_row and normalized_row[p_norm] not in (None, ""):
                        mapped[std_key] = normalized_row[p_norm]
                        break
            mapped["_raw_normalized"] = normalized_row
            filas.append(mapped)
        self.mapeo_fiscal = {}
        for idx, m in enumerate(filas):
            codigo = m.get("codigo") or str(idx)
            codigo = str(codigo).strip()
            self.mapeo_fiscal[codigo] = m
        self.mapeo_fiscal_warnings = self.validate_mapeo_fiscal()
        for w in self.mapeo_fiscal_warnings:
            self.logger.warning(w)

    def validate_mapeo_fiscal(self) -> List[str]:
        msgs: List[str] = []
        if not self.mapeo_fiscal:
            msgs.append("La hoja 'Mapeo_Fiscal' está vacía o no se detectó durante la carga.")
            return msgs
        for codigo, fila in self.mapeo_fiscal.items():
            if not fila.get("codigo") and not fila.get("tipo_operacion"):
                msgs.append(f"Fila del Mapeo_Fiscal con clave '{codigo}': faltan 'Codigo' o 'Tipo_operacion'.")
            aplica_iva = str(fila.get("aplica_iva") or "").strip().lower() in ("si", "sí", "s", "true", "1", "yes")
            iva_tasa = fila.get("iva_tasa", "")
            if aplica_iva or (iva_tasa not in ("", None)):
                if not fila.get("codigo_destino_iva"):
                    msgs.append(f"Fila '{codigo}': indica IVA (aplica/tasa) pero falta 'Codigo_destino_IVA' para las contrapartidas.")
            if fila.get("retencion_isr") not in (None, "", 0) and not fila.get("codigo_destino_isr"):
                msgs.append(f"Fila '{codigo}': especifica retención de ISR pero falta 'Codigo_destino_ISR'.")
            if fila.get("retencion_iva") not in (None, "", 0) and not fila.get("codigo_destino_iva_retencion"):
                msgs.append(f"Fila '{codigo}': especifica retención de IVA pero falta 'Codigo_destino_IVA_Retencion'.")
        return msgs

    def get_mapeo_por_codigo(self, codigo: str):
        if not codigo:
            return None
        return self.mapeo_fiscal.get(str(codigo).strip())

    def aplicar_impuestos_a_registro(self, registro: Registro) -> Dict[str, Decimal]:
        mf = self.get_mapeo_por_codigo(registro.cuenta)
        if not mf and registro.tipo_operacion:
            for r in self.mapeo_fiscal.values():
                tp = str(r.get("tipo_operacion") or r.get("tipo_operacion_nombre") or "").strip().lower()
                if tp and tp == str(registro.tipo_operacion).strip().lower():
                    mf = r
                    break
        res = registro.aplicar_impuestos(self.parametros, mf)
        return res

    def add_registro_to_hoja(self, hoja_nombre: str, registro: Registro, aplicar_impuestos: bool = True) -> Tuple[bool, List[str]]:
        if self.locked:
            return False, ["El ejercicio está finalizado. No se pueden agregar nuevos registros."]
        hoja = self.hojas.get(hoja_nombre)
        if not hoja:
            hoja = self.new_hoja(hoja_nombre)

        if not self.catalogo._catalogo:
            if aplicar_impuestos:
                # CORREGIDO -> llamado correcto a la función de aplicar impuestos
                self.aplicar_impuestos_a_registro(registro)
            hoja.registros.append(registro)
            return True, [f"Registro agregado en hoja '{hoja.nombre}'. Aviso: catálogo de cuentas vacío, se recomienda cargar el catálogo para validaciones posteriores."]

        ok, msg = self.catalogo.validate_account(registro.cuenta)
        if not ok:
            return False, [msg]
        if aplicar_impuestos:
            self.aplicar_impuestos_a_registro(registro)
        return hoja.add_registro(registro)

    def _es_cuenta_naturaleza_acreedora(self, codigo: str) -> Optional[bool]:
        if not codigo:
            return None
        info = self.catalogo.get(str(codigo).strip())
        if not info:
            return None
        nat = str(info.get("Naturaleza") or info.get("naturaleza") or "").strip().lower()
        if "acre" in nat:
            return True
        if "deud" in nat:
            return False
        return None

    def _movimientos_fiscales_para_registro(self, registro: Registro, mapeo_fila: Optional[Dict]) -> List[Dict]:
        movimientos: List[Dict] = []
        m = mapeo_fila or {}
        tipo = (registro.tipo_operacion or "").strip().lower()
        try:
            iva = Decimal(registro.iva)
        except Exception:
            iva = Decimal("0.00")
        if iva > 0:
            codigo_destino_iva = m.get("codigo_destino_iva")
            if codigo_destino_iva:
                es_acreedora = self._es_cuenta_naturaleza_acreedora(str(codigo_destino_iva))
                if es_acreedora is True:
                    movimientos.append({
                        "cuenta": str(codigo_destino_iva),
                        "cargo": None,
                        "abono": float(iva),
                        "descripcion": f"IVA trasladado (autogenerado) - {registro.descripcion or ''}"
                    })
                elif es_acreedora is False:
                    movimientos.append({
                        "cuenta": str(codigo_destino_iva),
                        "cargo": float(iva),
                        "abono": None,
                        "descripcion": f"IVA acreditable (autogenerado) - {registro.descripcion or ''}"
                    })
                else:
                    if tipo == "ingreso":
                        movimientos.append({
                            "cuenta": str(codigo_destino_iva),
                            "cargo": None,
                            "abono": float(iva),
                            "descripcion": f"IVA trasladado (autogenerado) - {registro.descripcion or ''}"
                        })
                    else:
                        movimientos.append({
                            "cuenta": str(codigo_destino_iva),
                            "cargo": float(iva),
                            "abono": None,
                            "descripcion": f"IVA acreditable (autogenerado) - {registro.descripcion or ''}"
                        })
        try:
            iva_ret = Decimal(registro.iva_retencion)
        except Exception:
            iva_ret = Decimal("0.00")
        if iva_ret > 0:
            codigo_iva_ret = m.get("codigo_destino_iva_retencion")
            if codigo_iva_ret:
                es_acreedora = self._es_cuenta_naturaleza_acreedora(str(codigo_iva_ret))
                if es_acreedora is True:
                    movimientos.append({
                        "cuenta": str(codigo_iva_ret),
                        "cargo": None,
                        "abono": float(iva_ret),
                        "descripcion": f"IVA retenido (autogenerado) - {registro.descripcion or ''}"
                    })
                else:
                    movimientos.append({
                        "cuenta": str(codigo_iva_ret),
                        "cargo": float(iva_ret),
                        "abono": None,
                        "descripcion": f"IVA retenido (autogenerado) - {registro.descripcion or ''}"
                    })
        try:
            isr = Decimal(registro.isr)
        except Exception:
            isr = Decimal("0.00")
        if isr > 0:
            codigo_isr = m.get("codigo_destino_isr")
            if codigo_isr:
                es_acreedora = self._es_cuenta_naturaleza_acreedora(str(codigo_isr))
                if es_acreedora is True:
                    movimientos.append({
                        "cuenta": str(codigo_isr),
                        "cargo": None,
                        "abono": float(isr),
                        "descripcion": f"ISR retenido (autogenerado) - {registro.descripcion or ''}"
                    })
                else:
                    movimientos.append({
                        "cuenta": str(codigo_isr),
                        "cargo": float(isr),
                        "abono": None,
                        "descripcion": f"ISR retenido (autogenerado) - {registro.descripcion or ''}"
                    })
        return movimientos

    def _crear_asiento_y_almacenar(self, fecha, descripcion, lineas: List[Dict]) -> int:
        id_as = self.next_asiento_id
        self.next_asiento_id += 1
        total_cargo = sum([float(l.get("cargo") or 0.0) for l in lineas])
        total_abono = sum([float(l.get("abono") or 0.0) for l in lineas])
        self.asientos[id_as] = {
            "id": id_as,
            "fecha": fecha,
            "descripcion": descripcion,
            "lineas": lineas,
            "total_cargo": total_cargo,
            "total_abono": total_abono
        }
        self.logger.info(f"Se creó asiento {id_as} fecha {fecha} - Cargo:{total_cargo} Abono:{total_abono} lineas:{len(lineas)}")
        return id_as

    def generar_movimientos_desde_poliza(self, hoja_nombre: str) -> Dict[str, Any]:
        hoja = self.hojas.get(hoja_nombre)
        if not hoja:
            return {"status": "no_hoja", "message": f"No existe la hoja {hoja_nombre}"}
        salida_nombre = f"{hoja_nombre}_Movimientos"
        hoja_salida = Hoja(salida_nombre)
        total_generados = 0
        for reg in hoja.registros:
            tipo_poliza = reg.extra.get("tipo_poliza") or reg.tipo_operacion or "Diario"
            movimientos = self.polizas.generar_movimientos(tipo_poliza, reg.to_dict())
            lineas_asiento: List[Dict] = []
            for mv in movimientos:
                cuenta = mv.get("cuenta") or ""
                cargo = float(mv.get("cargo") or 0.0) if mv.get("cargo") not in (None, "") else None
                abono = float(mv.get("abono") or 0.0) if mv.get("abono") not in (None, "") else None
                linea = {
                    "cuenta": str(cuenta),
                    "cargo": cargo,
                    "abono": abono,
                    "descripcion": mv.get("descripcion") or reg.descripcion,
                    "es_abono": True if abono not in (None, 0) and (cargo in (None, 0)) else False
                }
                lineas_asiento.append(linea)
            mapeo = self.get_mapeo_por_codigo(reg.cuenta)
            if not mapeo and reg.tipo_operacion:
                for r in self.mapeo_fiscal.values():
                    tp = str(r.get("tipo_operacion") or "").strip().lower()
                    if tp and tp == str(reg.tipo_operacion).strip().lower():
                        mapeo = r
                        break
            movimientos_fiscales = self._movimientos_fiscales_para_registro(reg, mapeo)
            for mv in movimientos_fiscales:
                cuenta = mv.get("cuenta") or ""
                cargo = float(mv.get("cargo") or 0.0) if mv.get("cargo") not in (None, "") else None
                abono = float(mv.get("abono") or 0.0) if mv.get("abono") not in (None, "") else None
                linea = {
                    "cuenta": str(cuenta),
                    "cargo": cargo,
                    "abono": abono,
                    "descripcion": mv.get("descripcion") or reg.descripcion,
                    "es_abono": True if abono not in (None, 0) and (cargo in (None, 0)) else False
                }
                lineas_asiento.append(linea)
            id_as = self._crear_asiento_y_almacenar(reg.fecha, reg.descripcion or "", lineas_asiento)
            total_generados += len(lineas_asiento)
            for linea in lineas_asiento:
                reg_mv = Registro.create(
                    fecha=reg.fecha.isoformat(),
                    cuenta=linea.get("cuenta") or "",
                    cantidad=linea.get("cargo") or linea.get("abono") or 0,
                    descripcion=linea.get("descripcion") or reg.descripcion,
                    tipo_operacion=reg.tipo_operacion
                )
                reg_mv.extra["es_abono"] = bool(linea.get("es_abono", False))
                reg_mv.extra["id_asiento"] = id_as
                hoja_salida.registros.append(reg_mv)
        self.hojas[salida_nombre] = hoja_salida
        if self.mapeo_fiscal_warnings:
            for w in self.mapeo_fiscal_warnings:
                self.logger.warning(w)
        return {"status": "ok", "hoja": salida_nombre, "movimientos_generados": total_generados, "asientos_creados": len(self.asientos)}

    def compute_libro_mayor(self) -> "pd.DataFrame":
        rows = []
        for hoja in self.hojas.values():
            for reg in hoja.registros:
                codigo = str(reg.cuenta).strip()
                es_abono = bool(reg.extra.get("es_abono", False))
                importe = Decimal(str(reg.cantidad)).quantize(Decimal("0.01"))
                rows.append({"cuenta": codigo, "es_abono": es_abono, "importe": importe})
        from collections import defaultdict
        suma_cargo = defaultdict(Decimal)
        suma_abono = defaultdict(Decimal)
        for r in rows:
            c = r["cuenta"]
            if r["es_abono"]:
                suma_abono[c] = suma_abono[c] + r["importe"]
            else:
                suma_cargo[c] = suma_cargo[c] + r["importe"]
        data = []
        cuentas = set(list(suma_cargo.keys()) + list(suma_abono.keys()))
        for c in sorted(cuentas):
            cargo = suma_cargo.get(c, Decimal("0.00")).quantize(Decimal("0.01"))
            abono = suma_abono.get(c, Decimal("0.00")).quantize(Decimal("0.01"))
            saldo = (cargo - abono).quantize(Decimal("0.01"))
            info = self.catalogo.get(c) or {}
            nombre = info.get("Nombre", info.get("Nombre_OSC", info.get("Nombre_Comercial", "")))
            tipo_cuenta = info.get("Tipo_cuenta") or info.get("Tipo_cuenta".lower(), "")
            data.append({
                "Codigo": c,
                "Nombre": nombre,
                "Tipo_cuenta": tipo_cuenta,
                "Cargo": float(cargo),
                "Abono": float(abono),
                "Saldo": float(saldo)
            })
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(columns=["Codigo", "Nombre", "Tipo_cuenta", "Cargo", "Abono", "Saldo"])
        return df

    def compute_balance(self) -> "pd.DataFrame":
        mayor = self.compute_libro_mayor()
        def categoria_tipo(tipo_str):
            if not tipo_str:
                return "Otros"
            t = str(tipo_str).lower()
            if "activo" in t:
                return "Activo"
            if "pasivo" in t:
                return "Pasivo"
            if "patrimonio" in t or "capital" in t:
                return "Patrimonio"
            return "Otros"
        if mayor.empty:
            return pd.DataFrame(columns=["Categoria", "Total"])
        mayor["Categoria"] = mayor["Tipo_cuenta"].fillna("").apply(categoria_tipo)
        mayor["Saldo_num"] = mayor["Saldo"].astype(float)
        resumen = mayor.groupby("Categoria", as_index=False)["Saldo_num"].sum()
        resumen = resumen.rename(columns={"Saldo_num": "Total"})
        for cat in ("Activo", "Pasivo", "Patrimonio", "Otros"):
            if cat not in list(resumen["Categoria"]):
                resumen = pd.concat([resumen, pd.DataFrame([{"Categoria": cat, "Total": 0.0}])], ignore_index=True)
        resumen = resumen.set_index("Categoria").loc[["Activo", "Pasivo", "Patrimonio", "Otros"]].reset_index()
        return resumen

    def compute_estado_resultados(self) -> "pd.DataFrame":
        """
        Genera un Estado de Resultados básico de manera segura:
        - evita indexaciones encadenadas problemáticas
        - usa contains() sobre Tipo_cuenta para detectar 'Ingreso' y 'Gasto'
        """
        mayor = self.compute_libro_mayor()
        if mayor.empty:
            return pd.DataFrame(columns=["Tipo", "Total"])

        # Crear columnas auxiliares de forma explícita y robusta
        mayor = mayor.copy()
        mayor["Tipo_cuenta_filled"] = mayor["Tipo_cuenta"].fillna("").astype(str)
        # Asegurar que 'Saldo' sea numérico
        mayor["Saldo_num"] = pd.to_numeric(mayor["Saldo"], errors="coerce").fillna(0.0)

        # identificar ingresos y gastos por texto en Tipo_cuenta
        ingresos_mask = mayor["Tipo_cuenta_filled"].str.contains("ingreso", case=False, na=False)
        gastos_mask = mayor["Tipo_cuenta_filled"].str.contains("gasto", case=False, na=False) | mayor["Tipo_cuenta_filled"].str.contains("gastos", case=False, na=False)

        ingresos = mayor.loc[ingresos_mask, "Saldo_num"].sum()
        gastos = mayor.loc[gastos_mask, "Saldo_num"].sum()
        resultado = ingresos - gastos

        df = pd.DataFrame([
            {"Tipo": "Ingresos", "Total": float(ingresos)},
            {"Tipo": "Gastos", "Total": float(gastos)},
            {"Tipo": "Resultado del ejercicio", "Total": float(resultado)}
        ])
        return df

    def export_asiento(self, id_asiento: int, path: str, fmt: str = "csv") -> Dict[str, Any]:
        """
        Exporta un asiento por id (lineas) a path.
        fmt: 'csv' (por defecto), 'xlsx', 'json'
        Devuelve dict con status y path.
        """
        if id_asiento not in self.asientos:
            return {"status": "error", "message": f"Asiento {id_asiento} no encontrado."}
        asi = self.asientos[id_asiento]
        filas = []
        for linea in asi.get("lineas", []):
            filas.append({
                "id_asiento": id_asiento,
                "fecha": asi.get("fecha").isoformat() if isinstance(asi.get("fecha"), date) else str(asi.get("fecha")),
                "cuenta": linea.get("cuenta"),
                "cargo": linea.get("cargo") or 0.0,
                "abono": linea.get("abono") or 0.0,
                "descripcion": linea.get("descripcion"),
                "es_abono": bool(linea.get("es_abono", False))
            })
        df = pd.DataFrame(filas)

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fmt = fmt.lower()
        try:
            if fmt == "csv":
                df.to_csv(str(p), index=False, float_format="%.2f")
            elif fmt == "xlsx":
                df.to_excel(str(p), sheet_name=f"Asiento_{id_asiento}", index=False)
            elif fmt == "json":
                p.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                return {"status": "error", "message": f"Formato no soportado: {fmt}"}
            self.logger.info(f"Asiento {id_asiento} exportado a {p} ({fmt})")
            return {"status": "ok", "path": str(p)}
        except Exception as e:
            self.logger.error(f"Error exportando asiento {id_asiento}: {e}")
            return {"status": "error", "message": str(e)}

    def listar_asientos(self) -> List[Dict[str, Any]]:
        """
        Devuelve lista de asientos (resumen) para UI/CLI.
        """
        salida: List[Dict[str, Any]] = []
        for id_as, asi in sorted(self.asientos.items()):
            salida.append({
                "id_asiento": id_as,
                "fecha": asi.get("fecha").isoformat() if isinstance(asi.get("fecha"), date) else str(asi.get("fecha")),
                "descripcion": asi.get("descripcion"),
                "lineas": len(asi.get("lineas", [])),
                "total_cargo": asi.get("total_cargo"),
                "total_abono": asi.get("total_abono")
            })
        return salida

    def finalizar_ejercicio(self, destino_base: str, iniciar_nuevo: bool = False) -> Dict[str, str]:
        if self.locked:
            return {"status": "already_locked", "message": "El ejercicio ya fue finalizado y está bloqueado."}
        sufijo = "AC" if self.contabilidad_tipo.upper().startswith("OSC") else "Comercial"
        carpeta = os.path.join(destino_base, f"{self.ejercicio}_{sufijo}")
        os.makedirs(carpeta, exist_ok=True)
        archivo_libro = os.path.join(carpeta, f"Libro_{self.ejercicio}.xlsx")
        self.save_xlsx(archivo_libro)
        self.locked = True
        resultado = {"status": "ok", "carpeta": carpeta, "archivo": archivo_libro}
        if iniciar_nuevo:
            nuevo = self._iniciar_nuevo_ejercicio()
            archivo_nuevo = os.path.join(carpeta, f"Libro_{nuevo.ejercicio}.xlsx")
            nuevo.save_xlsx(archivo_nuevo)
            resultado["nuevo_ejercicio"] = str(nuevo.ejercicio)
            resultado["archivo_nuevo"] = archivo_nuevo
        return resultado

    def _iniciar_nuevo_ejercicio(self):
        nuevo_ejercicio = int(self.ejercicio) + 1
        nuevo = Libro(contabilidad_tipo=self.contabilidad_tipo, ejercicio=nuevo_ejercicio)
        nuevo.catalogo = self.catalogo
        nuevo.parametros = self.parametros
        nuevo.polizas = self.polizas
        nuevo.add_hoja(Hoja("Movimientos"))
        return nuevo