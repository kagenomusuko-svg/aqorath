#!/usr/bin/env python3
"""
Descarga XSDs desde una lista de URLs y opcionalmente verifica SHA256 y escribe un manifiesto.

Modo de uso:
  python scripts/fetch_xsds.py --manifest datos/xsds_urls.txt --verify --shafile datos/xsds/sha256.txt

Comportamiento:
  - Si el archivo destino ya existe y su SHA coincide con la versión remota (si --verify), se salta.
  - Si --manifest no se proporciona, buscará datos/xsds_urls.txt.
  - Es idempotente: no reescribe archivos sin cambios.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import pathlib
import requests
import tempfile
import shutil
from typing import List, Tuple

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_MANIFEST = ROOT / "datos" / "xsds_urls.txt"
DEFAULT_OUTDIR = ROOT / "datos" / "xsds"

def sha256_of_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def download_url(url: str, dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Descarga segura a archivo temporal y rename atómico
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent)) as tmp:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
            tmp.flush()
            tmp_name = tmp.name
    shutil.move(tmp_name, str(dest))

def parse_manifest(path: pathlib.Path) -> List[Tuple[str, str]]:
    """
    Lee un manifiesto con líneas:
      <url>
    o
      <url> <relative-path>
    Devuelve lista de (url, relative_path)
    """
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        url = parts[0]
        rel = parts[1] if len(parts) > 1 else os.path.basename(url)
        pairs.append((url, rel))
    return pairs

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=str, help="Archivo con URLs (una por línea).")
    p.add_argument("--verify", action="store_true", help="Verificar SHA y escribir manifiesto de sha.")
    p.add_argument("--shafile", type=str, help="Ruta para fichero de sha256 (por defecto datos/xsds/sha256.txt).")
    args = p.parse_args()

    manifest_path = pathlib.Path(args.manifest) if args.manifest else DEFAULT_MANIFEST
    pairs = parse_manifest(manifest_path)
    if not pairs:
        print("No se encontraron URLs a descargar. Crea", manifest_path, "con una URL por línea.")
        return

    outdir = DEFAULT_OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    shafile = pathlib.Path(args.shafile) if args.shafile else outdir / "sha256.txt"
    manifest_lines = []

    for url, rel in pairs:
        dest = outdir / rel
        try:
            if dest.exists() and args.verify:
                # Si se verifica, intentar descargar y comparar SHA de remoto por paso extra (no siempre posible).
                # Estrategia: descargar remoto a temp y comparar con local para idempotencia.
                print("Verificando", rel)
                with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent)) as tmp:
                    tmp_path = pathlib.Path(tmp.name)
                try:
                    download_url(url, tmp_path)
                    remote_sha = sha256_of_file(tmp_path)
                    local_sha = sha256_of_file(dest)
                    if remote_sha == local_sha:
                        print("Sin cambios:", rel)
                        tmp_path.unlink()
                    else:
                        print("Actualizando:", rel)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(tmp_path), str(dest))
                except Exception as e:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    print("Advertencia descargando", url, ":", e)
            else:
                # Si no existe o no se verifica, descargar si hace falta
                if dest.exists():
                    print("Ya existe (no -verify):", rel)
                else:
                    print("Descargando:", url, "->", dest)
                    download_url(url, dest)
        except Exception as e:
            print("Error procesando", url, ":", e)
            continue
        # Calcular sha del archivo final si existe
        if dest.exists():
            sha = sha256_of_file(dest)
            # Escribir ruta relativa respecto a datos/xsds
            relpath = os.path.relpath(dest, outdir)
            manifest_lines.append(f"{sha}  {relpath}")

    if args.verify:
        # Escribe manifiesto shafile
        shafile.parent.mkdir(parents=True, exist_ok=True)
        shafile.write_text("\n".join(manifest_lines) + ("\n" if manifest_lines else ""), encoding="utf-8")
        print("Manifiesto SHA escrito en", shafile)

if __name__ == "__main__":
    main()