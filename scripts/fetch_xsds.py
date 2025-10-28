#!/usr/bin/env python3
"""
scripts/fetch_xsds.py

Descarga recursiva del XSD principal (ej. cfdv40.xsd) y de los XSDs referenciados
(vía schemaLocation en <xs:import> / <xs:include>), guardando la estructura en
un directorio local (por defecto datos/xsds).

Uso:
  python scripts/fetch_xsds.py --url https://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd --out datos/xsds

Opciones:
  --url   URL pública del XSD principal (por defecto la URL del SAT si la conoces)
  --out   directorio destino (por defecto datos/xsds)
  --force forzar descarga y sobreescritura de archivos existentes
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import requests
from urllib.parse import urljoin, urlparse
import re
import time

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "SistemaContable/1.0 (+https://example.org)"})

SCHEMA_LOCATION_RE = re.compile(r'schemaLocation=["\']([^"\']+)["\']', re.IGNORECASE)
IMPORT_INCLUDE_RE = re.compile(r'<xs:(?:import|include)[^>]*schemaLocation=["\']([^"\']+)["\']', re.IGNORECASE)

def download(url: str, dest: Path, timeout: int = 15, retries: int = 3) -> None:
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=timeout)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            print(f"Guardado: {dest}  ({len(r.content)} bytes)")
            return
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
    for pth in sorted(out.rglob("*.xsd")):
        print(" -", pth.relative_to(out))

if __name__ == "__main__":
    main()