#!/usr/bin/env python3
"""
Convierte assets/catalogo.xlsx -> aqorath/data/catalogo_base.json

Uso:
    python scripts/convert_catalog_xlsx_to_json.py --input assets/catalogo.xlsx --out aqorath/data/catalogo_base.json

El script espera que la hoja tenga encabezado con columnas (al menos):
Codigo, Nombre_OSC, Nombre_Comercial, Tipo_cuenta, Subtipo, Naturaleza, Descripción/uso, Reporte_OSC

Si los encabezados tienen variantes (acentos / mayúsculas), el script intenta encontrarlos por nombres comunes.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from openpyxl import load_workbook

COMMON_CODE_HEADERS = ["Codigo", "Code", "codigo", "code", "CÓDIGO", "Código"]
COMMON_OSC_HEADERS = ["Nombre_OSC", "Nombre_Osc", "Nombre OSC", "Nombre Osc", "name_osc", "Nombre OSC"]
COMMON_COM_HEADERS = ["Nombre_Comercial", "Nombre Comercial", "name_comercial", "Nombre Comercial"]
COMMON_TIPO = ["Tipo_cuenta", "Tipo", "tipo"]
COMMON_SUBTIPO = ["Subtipo", "subtipo"]
COMMON_NAT = ["Naturaleza", "naturaleza"]
COMMON_DESC = ["Descripción/uso", "Descripcion", "descripcion", "Descripción", "Descripcion/uso"]

def find_index(headers, names):
    for n in names:
        for i,h in enumerate(headers):
            if not h:
                continue
            if h.strip().lower() == n.strip().lower():
                return i
    return None

def read_xlsx(path: Path):
    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    i_code = find_index(headers, COMMON_CODE_HEADERS)
    i_osc = find_index(headers, COMMON_OSC_HEADERS)
    i_com = find_index(headers, COMMON_COM_HEADERS)
    i_tipo = find_index(headers, COMMON_TIPO)
    i_sub = find_index(headers, COMMON_SUBTIPO)
    i_nat = find_index(headers, COMMON_NAT)
    i_desc = find_index(headers, COMMON_DESC)

    accounts = {}
    for r in rows[1:]:
        if i_code is None:
            continue
        if i_code >= len(r) or r[i_code] is None:
            continue
        code = str(r[i_code]).strip()
        if not code:
            continue
        def safe(i):
            return (str(r[i]).strip() if i is not None and i < len(r) and r[i] is not None else "")
        accounts[code] = {
            "name_osc": safe(i_osc),
            "name_comercial": safe(i_com),
            "tipo": safe(i_tipo),
            "subtipo": safe(i_sub),
            "naturaleza": safe(i_nat),
            "descripcion": safe(i_desc),
        }
    return accounts

def main(args):
    inp = Path(args.input)
    out = Path(args.out)
    if not inp.exists():
        print("Input file not found:", inp)
        return
    accounts = read_xlsx(inp)
    payload = {
        "version": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": "Generado desde assets/catalogo.xlsx",
        "accounts": accounts
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Escrito", out, "con", len(accounts), "cuentas.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="assets/catalogo.xlsx")
    p.add_argument("--out", default="aqorath/data/catalogo_base.json")
    args = p.parse_args()
    main(args)