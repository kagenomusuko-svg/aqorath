# main.py
"""
main.py - script con CLI mínimo para usar funcionalidades del App.
Comandos relevantes añadidos:
  - export-report --type {balance,mayor,estado_resultados} --out PATH
  - generate-cfdi --id ID --emisor-rfc RFC --emisor-nombre NAME --receptor-rfc RFC --receptor-nombre NAME --out DIR
"""

import argparse
from app import App
from modelos.registro import Registro
import sys
from pathlib import Path

def cmd_export_report(args):
    app = App()
    res = app.load_or_create()
    if res["status"] not in ("loaded", "created"):
        print("No se pudo cargar/crear el libro:", res)
        return 1
    libro = app.libro
    # default output path
    out = args.out or f"datos/report_{args.type}.pdf"
    # llamar al generador de reportes
    from modelos.reportes import export_report
    r = export_report(libro, args.type, out)
    if r.get("status") == "ok":
        print("Reporte generado en:", r.get("path"))
        return 0
    else:
        print("Error generando reporte:", r)
        return 2

def cmd_generate_cfdi(args):
    app = App()
    res = app.load_or_create()
    if res["status"] not in ("loaded", "created"):
        print("No se pudo cargar/crear el libro:", res)
        return 1
    libro = app.libro
    try:
        id_as = int(args.id)
    except Exception:
        print("ID de asiento inválido.")
        return 2
    emisor = {"rfc": args.emisor_rfc, "nombre": args.emisor_nombre}
    receptor = {"rfc": args.receptor_rfc, "nombre": args.receptor_nombre}
    outdir = args.out or "datos/cfdi"
    from modelos.cfdi import generate_cfdi_from_asiento
    r = generate_cfdi_from_asiento(libro, id_as, outdir, emisor, receptor)
    if r.get("status") == "ok":
        print("CFDI generado:", r)
        return 0
    else:
        print("Error generando CFDI:", r)
        return 2

def main():
    parser = argparse.ArgumentParser(prog="SistemaContable")
    sub = parser.add_subparsers(dest="command")

    p_report = sub.add_parser("export-report", help="Exportar reportes a PDF")
    p_report.add_argument("--type", required=True, choices=["balance", "mayor", "estado_resultados"], help="Tipo de reporte")
    p_report.add_argument("--out", required=False, help="Ruta de salida (PDF)")

    p_cfdi = sub.add_parser("generate-cfdi", help="Generar CFDI skeleton (XML+CSV+PDF) desde un asiento")
    p_cfdi.add_argument("--id", required=True, help="ID del asiento")
    p_cfdi.add_argument("--emisor-rfc", required=True, help="RFC del emisor")
    p_cfdi.add_argument("--emisor-nombre", required=True, help="Nombre del emisor")
    p_cfdi.add_argument("--receptor-rfc", required=True, help="RFC del receptor")
    p_cfdi.add_argument("--receptor-nombre", required=True, help="Nombre del receptor")
    p_cfdi.add_argument("--out", required=False, help="Directorio de salida (default: datos/cfdi)")

    args = parser.parse_args()
    if args.command == "export-report":
        return cmd_export_report(args)
    elif args.command == "generate-cfdi":
        return cmd_generate_cfdi(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())