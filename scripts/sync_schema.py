#!/usr/bin/env python3
"""
Script to sync database schema with SQLModel definitions.
Detects missing columns by comparing JournalLine model with actual DB schema.
"""
import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from aqorath.models import JournalLine
from aqorath.storage import get_db_path


def get_db_columns(db_path: str, table_name: str) -> List[Tuple[str, str]]:
    """
    Get columns from the database table using PRAGMA table_info.
    Returns list of (column_name, column_type) tuples.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [(row[1], row[2]) for row in cursor.fetchall()]
    conn.close()
    return columns


def get_model_columns() -> Dict[str, str]:
    """
    Get expected columns from the JournalLine SQLModel.
    Returns dict of {column_name: column_type_hint}.
    """
    # Access SQLModel table metadata
    columns = {}
    table = JournalLine.__table__
    for col in table.columns:
        col_type = str(col.type)
        # Map SQLAlchemy types to SQLite types
        if "INTEGER" in col_type.upper():
            sqlite_type = "INTEGER"
        elif "FLOAT" in col_type.upper() or "NUMERIC" in col_type.upper():
            sqlite_type = "REAL"
        elif "DATETIME" in col_type.upper():
            sqlite_type = "DATETIME"
        else:
            sqlite_type = "VARCHAR"
        columns[col.name] = sqlite_type
    return columns


def detect_missing_columns(db_path: str) -> List[Tuple[str, str]]:
    """
    Compare model columns with DB columns and return missing ones.
    Returns list of (column_name, column_type) that need to be added.
    """
    db_cols = {name: type_ for name, type_ in get_db_columns(db_path, "journalline")}
    model_cols = get_model_columns()
    
    missing = []
    for col_name, col_type in model_cols.items():
        if col_name not in db_cols:
            missing.append((col_name, col_type))
    
    return missing


def add_columns(db_path: str, columns: List[Tuple[str, str]]) -> Tuple[bool, List[str]]:
    """
    Add missing columns to the journalline table.
    SQLite only supports ALTER TABLE ADD COLUMN (no DROP/MODIFY).
    Returns (success, list of messages).
    """
    if not columns:
        return True, ["No columns to add."]
    
    messages = []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for col_name, col_type in columns:
        try:
            # SQLite ALTER TABLE ADD COLUMN with default values
            default_clause = ""
            if col_type == "INTEGER":
                default_clause = " DEFAULT 0"
            elif col_type == "REAL":
                default_clause = " DEFAULT 0.0"
            elif col_type == "DATETIME":
                default_clause = " DEFAULT CURRENT_TIMESTAMP"
            else:
                default_clause = ""
            
            sql = f"ALTER TABLE journalline ADD COLUMN {col_name} {col_type}{default_clause}"
            cursor.execute(sql)
            messages.append(f"Added column: {col_name} ({col_type})")
        except sqlite3.Error as e:
            messages.append(f"ERROR adding column {col_name}: {e}")
            return False, messages
    
    conn.commit()
    conn.close()
    return True, messages


def sync_schema(db_path: str = None, dry_run: bool = False) -> Tuple[bool, List[str]]:
    """
    Main function to sync schema.
    If dry_run=True, only reports what would be done.
    Returns (success, messages).
    """
    if db_path is None:
        db_path = get_db_path()
    
    messages = [f"Checking schema for: {db_path}"]
    
    # Check if journalline table exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='journalline'")
    if not cursor.fetchone():
        conn.close()
        return False, messages + ["ERROR: journalline table does not exist. Run init_db first."]
    conn.close()
    
    # Detect missing columns
    missing = detect_missing_columns(db_path)
    
    if not missing:
        messages.append("✓ Schema is up to date. No missing columns.")
        return True, messages
    
    messages.append(f"Found {len(missing)} missing columns:")
    for col_name, col_type in missing:
        messages.append(f"  - {col_name} ({col_type})")
    
    if dry_run:
        messages.append("\n[DRY RUN] No changes made. Run without --dry-run to apply changes.")
        return True, messages
    
    # Add missing columns
    success, add_messages = add_columns(db_path, missing)
    messages.extend(add_messages)
    
    if success:
        messages.append("\n✓ Schema sync completed successfully.")
    else:
        messages.append("\n✗ Schema sync failed. See errors above.")
    
    return success, messages


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync database schema with SQLModel definitions")
    parser.add_argument("--db", help="Path to database file (default: uses AQORATH_DB env var)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    success, messages = sync_schema(db_path=args.db, dry_run=args.dry_run)
    
    for msg in messages:
        print(msg)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
