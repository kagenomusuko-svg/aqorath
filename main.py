#!/usr/bin/env python3
"""
CLI wrapper para funcionalidades principales:
 - fetch-xsds: descarga xsds usando scripts/fetch_xsds.py
 - generate-cfdi: genera ejemplos/esqueletos de CFDI
 - import-timbrado: importa resultados de timbrado
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import pathlib
import json

ROOT = pathlib.Path(__file__).parent

def run_fetch(args):
    cmd = [sys.executable, str(ROOT / "scripts" / "fetch_xsds.py")]
    if args.verify:
        cmd.append("--verify")
    if args.shafile:
        cmd.extend(["--shafile", args.shafile])
    if args.manifest:
        cmd.extend(["--manifest", args.manifest])
    print("Ejecutando:", " ".join(cmd))
    subprocess.run(cmd, check=True)

def run_generate(args):
    # Implementación mínima: genera tres esqueletos simples en datos/cfdi_examples/
    outdir = ROOT / "datos" / "cfdi_examples"
    outdir.mkdir(parents=True, exist_ok=True)
    templates = {
        "RESICO": "<CFDI version='4.0' tipo='RESICO'>\n  <!-- Ejemplo RESICO -->\n</CFDI>\n",
        "PM": "<CFDI version='4.0' tipo='PM'>\n  <!-- Ejemplo Persona Moral pequeña -->\n</CFDI>\n",
        "AC": "<CFDI version='4.0' tipo='AC'>\n  <!-- Ejemplo Asociación Civil -->\n</CFDI>\n",
    }
    names = args.kind.upper() if args.kind else None
    if names:
        if names not in templates:
            print("Tipo desconocido:", args.kind, "opciones: RESICO, PM, AC")
            return
        filepath = outdir / f"cfdi_{names}.xml"
        filepath.write_text(templates[names], encoding="utf-8")
        print("Generado:", filepath)
    else:
        for k, v in templates.items():
            fp = outdir / f"cfdi_{k}.xml"
            fp.write_text(v, encoding="utf-8")
            print("Generado:", fp)

def run_import(args):
    # Implementación mínima: copia XMLs timbrados a datos/timbrado_imported/
    import shutil
    src = pathlib.Path(args.source)
    if not src.exists():
        print("Archivo fuente no encontrado:", src)
        return
    dst_dir = ROOT / "datos" / "timbrado_imported"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    print("Importado a:", dst)

def main():
    p = argparse.ArgumentParser(prog="aqorath")
    sub = p.add_subparsers(dest="cmd")

    pf = sub.add_parser("fetch-xsds", help="Descargar XSDs (usa scripts/fetch_xsds.py)")
    pf.add_argument("--verify", action="store_true", help="Verificar SHA256 y actualizar manifest")
    pf.add_argument("--shafile", help="Ruta para escribir manifiesto SHA256 (por defecto datos/xsds/sha256.txt)")
    pf.add_argument("--manifest", help="Archivo de manifiesto con URLs a descargar (una por línea)")

    pg = sub.add_parser("generate-cfdi", help="Generar esqueletos de CFDI")
    pg.add_argument("--kind", choices=["RESICO","PM","AC"], help="Esqueleto específico (RESICO, PM, AC)")

    pi = sub.add_parser("import-timbrado", help="Importar XML de timbrado")
    pi.add_argument("source", help="Archivo XML timbrado a importar")

    args = p.parse_args()
    try:
        if args.cmd == "fetch-xsds":
            run_fetch(args)
        elif args.cmd == "generate-cfdi":
            run_generate(args)
        elif args.cmd == "import-timbrado":
            run_import(args)
        else:
            p.print_help()
    except subprocess.CalledProcessError as e:
        print("Error al ejecutar comando externo:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()