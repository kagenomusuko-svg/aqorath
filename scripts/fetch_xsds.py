#!/usr/bin/env python3
"""
scripts/fetch_xsds.py

Descarga recursiva del XSD principal (ej. cfdv40.xsd) y de los XSDs referenciados
(vía schemaLocation en <xs:import> / <xs:include>), guardando la estructura en
un directorio local (por defecto datos/xsds).

Uso:
  python scripts/fetch_xsds.py --url https://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd --out datos/xsds

Opciones:
  --url     URL pública del XSD principal (por defecto la URL del SAT si la conoces)
  --out     directorio destino (por defecto datos/xsds)
  --force   forzar descarga y sobreescritura de archivos existentes
  --verify  calcular SHA256 de cada archivo descargado y crear manifiesto
  --shafile ruta del archivo de manifiesto SHA256 (por defecto: <out>/sha256.txt)
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import requests
from urllib.parse import urljoin, urlparse
import re
import time
import hashlib

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "SistemaContable/1.0 (+https://example.org)"})

SCHEMA_LOCATION_RE = re.compile(r'schemaLocation=["\']([^"\']+)["\']', re.IGNORECASE)
IMPORT_INCLUDE_RE = re.compile(r'<xs:(?:import|include)[^>]*schemaLocation=["\']([^"\']+)["\']', re.IGNORECASE)

def download(url: str, dest: Path, timeout: int = 15, retries: int = 3) -> bytes:
    """Downloads a file and returns its content."""
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=timeout)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            print(f"Guardado: {dest}  ({len(r.content)} bytes)")
            return r.content
        except Exception as e:
            if attempt + 1 < retries:
                print(f"Error descargando {url}: {e}. Reintentando en 2s...")
                time.sleep(2)
            else:
                raise

def find_schema_locations(xsd_text: str) -> list[str]:
    # Buscar imports/includes con schemaLocation
    found = IMPORT_INCLUDE_RE.findall(xsd_text)
    # devolvemos lista de URL/paths tal como aparecen
    return found

def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def normalize_local_path_for_url(base_out: Path, url: str) -> Path:
    """
    Construye una ruta local para el URL. Ejemplo:
      https://www.sat.gob.mx/sitio_internet/cfd/catalogos/catCFDI.xsd
    se almacenará en base_out / 'catalogos' / 'catCFDI.xsd'
    Si URL es relativo (ej. 'catalogos/catCFDI.xsd') lo tratamos relativo.
    """
    up = urlparse(url)
    if up.scheme in ("http", "https"):
        # use path after the host
        parts = Path(up.path.lstrip("/"))
        return base_out.joinpath(parts)
    else:
        # relative path -> keep as relative under base_out
        return base_out.joinpath(Path(url))

def fetch_recursive(url: str, out_dir: Path, seen: set[str], base_url: str | None = None, force: bool = False):
    # Resolve absolute URL using base_url if provided and url is relative
    if base_url and not urlparse(url).scheme:
        abs_url = urljoin(base_url, url)
    else:
        abs_url = url
    if abs_url in seen:
        return
    seen.add(abs_url)
    local_path = normalize_local_path_for_url(out_dir, abs_url)
    if local_path.exists() and not force:
        print(f"Usando existente: {local_path}")
        try:
            text = local_path.read_text(encoding="utf-8")
        except Exception:
            text = ""
    else:
        print(f"Descargando {abs_url} -> {local_path}")
        download(abs_url, local_path)
        try:
            text = local_path.read_text(encoding="utf-8")
        except Exception:
            text = ""
    # buscar imports/includes
    for schema_loc in find_schema_locations(text):
        # resolver la URL relativa respecto a abs_url
        next_url = urljoin(abs_url, schema_loc)
        fetch_recursive(next_url, out_dir, seen, base_url=None, force=force)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="URL del XSD principal (ej. cfdv40.xsd)")
    p.add_argument("--out", default="datos/xsds", help="Directorio destino (por defecto datos/xsds)")
    p.add_argument("--force", action="store_true", help="Forzar re-descarga y sobreescritura")
    p.add_argument("--verify", action="store_true", help="Calcular SHA256 de archivos y crear manifiesto")
    p.add_argument("--shafile", help="Ruta del archivo de manifiesto SHA256 (por defecto: <out>/sha256.txt)")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Directorio destino: {out.resolve()}")

    seen = set()
    try:
        fetch_recursive(args.url, out, seen, base_url=None, force=args.force)
    except Exception as e:
        print(f"Error durante la descarga recursiva: {e}")
        raise SystemExit(2)

    print("Descarga completada. Archivos guardados:")
    xsd_files = sorted(out.rglob("*.xsd"))
    for pth in xsd_files:
        print(" -", pth.relative_to(out))

    # SHA256 verification and manifest creation
    if args.verify:
        shafile = Path(args.shafile) if args.shafile else out / "sha256.txt"
        print(f"\nCalculando SHA256 y creando manifiesto en: {shafile}")
        
        with open(shafile, "w", encoding="utf-8") as f:
            for pth in xsd_files:
                sha256 = calculate_sha256(pth)
                rel_path = pth.relative_to(out)
                f.write(f"{sha256}  {rel_path}\n")
                print(f"  {sha256}  {rel_path}")
        
        print(f"Manifiesto SHA256 guardado en: {shafile}")

if __name__ == "__main__":
    main()