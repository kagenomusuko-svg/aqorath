#!/usr/bin/env python3
"""
Comentar (neutralizar) inserciones de Accounts no presentes en el catálogo.

- Dry-run (por defecto): muestra los archivos y líneas que serían comentados.
- Con --apply: modifica los archivos in-place creando backups <file>.bak.

Uso:
  # dry-run
  .venv/bin/python scripts/comment_non_catalog_inserts.py

  # aplicar cambios
  .venv/bin/python scripts/comment_non_catalog_inserts.py --apply

Notas:
- Crea backups .bak antes de modificar cada archivo.
- Revisa los backups si algo no te convence.
"""
import re
import argparse
from pathlib import Path
import json
from aqorath.catalog import load_catalog_codes

TEST_DIR = Path("tests")
CATALOG_CODES = load_catalog_codes()

# Patrón simple para detectar s.add(Account(code="...") y s.add(Account(code='...')
# Captura también si hay espacios y otros kwargs.
PATTERN_ADD_SINGLE = re.compile(r'(?P<prefix>\s*)(s\.add\(\s*Account\(\s*code\s*=\s*[\'"](?P<code>[^\'"]+)[\'"][^\)]*\)\s*\))')
# Patrón para s.add_all([... Account(code="...") ...])
PATTERN_ADD_ALL = re.compile(r'(?P<prefix>\s*)(s\.add_all\(\s*\[.*?Account\(\s*code\s*=\s*[\'"](?P<code>[^\'"]+)[\'"].*?\).*?\]\s*\))', re.DOTALL)

def find_matches_in_file(path: Path):
    text = path.read_text(encoding="utf-8")
    matches = []
    for m in PATTERN_ADD_SINGLE.finditer(text):
        code = m.group("code").strip()
        matches.append(("single", m.start(2), m.end(2), code, m.group(0)))
    for m in PATTERN_ADD_ALL.finditer(text):
        code = m.group("code").strip()
        matches.append(("add_all", m.start(2), m.end(2), code, m.group(0)))
    return matches

def process_file(path: Path, apply: bool):
    matches = find_matches_in_file(path)
    if not matches:
        return []
    text = path.read_text(encoding="utf-8")
    changes = []
    new_text = text
    # process in reverse order to not break offsets
    for typ, start, end, code, snippet in sorted(matches, key=lambda x: x[1], reverse=True):
        if code in CATALOG_CODES:
            # skip catalog codes (we allow these)
            continue
        # Comment the exact snippet (preserve indentation)
        # We'll prefix with a clear marker so it's easy to find later.
        comment = f"# BLOCKED_NON_CATALOG_INSERT: removed insert of Account(code='{code}')\n# {snippet.replace(chr(10),'\\n# ')}"
        new_text = new_text[:start] + comment + new_text[end:]
        changes.append((code, snippet))
    if changes and apply:
        backup = path.with_suffix(path.suffix + ".bak")
        path.rename(backup)
        path.write_text(new_text, encoding="utf-8")
        return [(path, backup, changes)]
    elif changes:
        return [(path, None, changes)]
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Aplicar cambios (modificar archivos).")
    args = ap.parse_args()

    py_files = list(TEST_DIR.rglob("*.py"))
    total = 0
    effected = []
    for p in py_files:
        res = process_file(p, apply=args.apply)
        if res:
            total += 1
            effected.extend(res)

    if not effected:
        print("No se encontraron inserciones de Accounts no-catalogadas en tests (o ya están usando códigos del catálogo).")
        return

    print(f"Se detectaron {len(effected)} archivos con inserciones no-catalogadas.")
    for item in effected:
        path, backup, changes = item
        print(f"\nArchivo: {path}")
        if backup:
            print(f"  Backup creado: {backup}")
        for code, snippet in changes:
            print(f"  - code: {code}  snippet: {snippet.splitlines()[0][:180]}")
    if not args.apply:
        print("\nDRY-RUN: no se modificaron archivos. Ejecuta con --apply para comentar las líneas detectadas.")
    else:
        print("\nCambios aplicados. Revisa los archivos .bak si necesitas revertir.")

if __name__ == "__main__":
    main()