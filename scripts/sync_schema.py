#!/usr/bin/env python3
"""
scripts/sync_schema.py

Detecta diferencias entre JournalLine.__table__.columns (aqorath/models.py)
y la tabla 'journalline' en la DB sqlite. Intenta añadir columnas faltantes
usando ALTER TABLE (solo columnas simples). Reporta columnas que no se pudieron
añadir automáticamente y sugiere pasos manuales.

Uso:
  python scripts/sync_schema.py [--db path/to/db]
"""
from __future__ import annotations
import sqlite3
import argparse
import logging
from pathlib import Path
from typing import List

LOG = logging.getLogger("sync_schema")
logging.basicConfig(level=logging.INFO)

DEFAULT_DB_CANDIDATES = [
    "tests/test.db",
    "datos/aqorath.db",
    "aqorath.db",
    "test.db",
]

def find_db(provided: str | None) -> Path | None:
    if provided:
        p = Path(provided)
        if p.exists():
            return p
        return None
    for p in DEFAULT_DB_CANDIDATES:
        if Path(p).exists():
            return Path(p)
    return None

def get_model_columns() -> List[str]:
    # Import de forma defensiva
    try:
        from aqorath.models import JournalLine
    except Exception as e:
        LOG.error("No se pudo importar JournalLine desde aqorath.models: %s", e)
        return []
    try:
        return [c.name for c in JournalLine.__table__.columns]
    except Exception as e:
        LOG.error("No se pudo leer columnas de JournalLine.__table__: %s", e)
        return []

def get_db_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    rows = cur.fetchall()
    return [r[1] for r in rows]

def add_column(conn: sqlite3.Connection, table: str, column: str):
    # SQLite only supports ADD COLUMN with a default/nullable simple type.
    # We'll add as TEXT NULL and log assumption.
    sql = f"ALTER TABLE {table} ADD COLUMN {column} TEXT"
    LOG.info("Ejecutando SQL: %s", sql)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", help="Path to sqlite DB")
    parser.add_argument("--table", default="journalline")
    args = parser.parse_args()

    db = find_db(args.db)
    if not db:
        LOG.error("No se encontró la base de datos. Pasa --db o crea tests/test.db")
        return 2

    LOG.info("Usando DB: %s", db)
    conn = sqlite3.connect(str(db))
    try:
        model_cols = get_model_columns()
        if not model_cols:
            LOG.error("No se detectaron columnas del modelo. Revisa aqorath/models.py")
            return 3
        db_cols = get_db_columns(conn, args.table)
        LOG.info("Columnas modelo (%d): %s", len(model_cols), model_cols)
        LOG.info("Columnas DB (%d): %s", len(db_cols), db_cols)

        missing = [c for c in model_cols if c not in db_cols]
        if not missing:
            LOG.info("No faltan columnas. Schema ok.")
            return 0

        LOG.info("Columnas faltantes detectadas: %s", missing)
        auto_added = []
        could_not_add = []
        for col in missing:
            try:
                add_column(conn, args.table, col)
                auto_added.append(col)
            except Exception as e:
                LOG.exception("No se pudo añadir columna %s: %s", col, e)
                could_not_add.append((col, str(e)))

        LOG.info("Columnas añadidas automáticamente: %s", auto_added)
        if could_not_add:
            LOG.warning("Algunas columnas no pudieron añadirse automáticamente:")
            for col, err in could_not_add:
                LOG.warning(" - %s : %s", col, err)
            LOG.warning("Revisa manualmente la estructura o realiza migración más avanzada.")
    finally:
        conn.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())