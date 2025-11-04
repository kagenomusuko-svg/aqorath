#!/usr/bin/env python3
"""
Schema sync helper that compares JournalLine.__table__.columns with the actual
SQLite DB schema and adds missing columns via ALTER TABLE when possible.
Logs columns that cannot be auto-added and prints manual migration steps.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any

try:
    from sqlalchemy import inspect, text
    from sqlmodel import SQLModel
    from aqorath.models import JournalLine, Account, JournalEntry, AppConfig, Asset
    from aqorath.storage import get_engine, get_db_path
except ImportError as e:
    print(f"Error importing required modules: {e}", file=sys.stderr)
    print("Make sure you have installed all dependencies: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


def get_model_columns(model_class) -> Dict[str, Any]:
    """Extract column definitions from SQLModel class."""
    columns = {}
    if hasattr(model_class, "__table__"):
        for col in model_class.__table__.columns:
            columns[col.name] = {
                "type": str(col.type),
                "nullable": col.nullable,
                "primary_key": col.primary_key,
                "unique": col.unique,
            }
    return columns


def get_db_columns(engine, table_name: str) -> Dict[str, Any]:
    """Get actual columns from SQLite DB using PRAGMA table_info."""
    db_columns = {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"PRAGMA table_info('{table_name}')"))
            for row in result:
                # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
                col_name = row[1]
                col_type = row[2]
                not_null = bool(row[3])
                pk = bool(row[5])
                db_columns[col_name] = {
                    "type": col_type,
                    "nullable": not not_null,
                    "primary_key": pk,
                }
    except Exception as e:
        print(f"Warning: Could not read table '{table_name}': {e}", file=sys.stderr)
    return db_columns


def sqlalchemy_type_to_sqlite(sa_type: str) -> str:
    """Convert SQLAlchemy type string to SQLite type."""
    sa_type_upper = sa_type.upper()
    if "VARCHAR" in sa_type_upper or "TEXT" in sa_type_upper or "STRING" in sa_type_upper:
        return "TEXT"
    elif "INTEGER" in sa_type_upper or "BIGINT" in sa_type_upper:
        return "INTEGER"
    elif "FLOAT" in sa_type_upper or "REAL" in sa_type_upper or "NUMERIC" in sa_type_upper:
        return "REAL"
    elif "BOOLEAN" in sa_type_upper or "BOOL" in sa_type_upper:
        return "INTEGER"  # SQLite stores boolean as INTEGER
    elif "DATETIME" in sa_type_upper or "TIMESTAMP" in sa_type_upper:
        return "DATETIME"
    elif "DATE" in sa_type_upper:
        return "DATE"
    else:
        return "TEXT"  # Default fallback


def sync_table_schema(engine, model_class, table_name: str, dry_run: bool = False) -> List[str]:
    """
    Compare model columns with DB columns and add missing columns.
    Returns list of messages about actions taken or needed.
    """
    messages = []
    model_cols = get_model_columns(model_class)
    db_cols = get_db_columns(engine, table_name)
    
    if not db_cols:
        messages.append(f"⚠️  Table '{table_name}' does not exist in the database.")
        messages.append(f"   Run 'init_db(create_tables=True)' or create tables manually.")
        return messages
    
    missing_cols = set(model_cols.keys()) - set(db_cols.keys())
    
    if not missing_cols:
        messages.append(f"✓ Table '{table_name}' schema is up to date.")
        return messages
    
    messages.append(f"\n📋 Table '{table_name}' - Found {len(missing_cols)} missing column(s):")
    
    for col_name in sorted(missing_cols):
        col_info = model_cols[col_name]
        sqlite_type = sqlalchemy_type_to_sqlite(col_info["type"])
        
        # Check if we can auto-add this column
        can_auto_add = True
        alter_statement = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sqlite_type}"
        
        # Columns with NOT NULL constraint and no default cannot be added to existing tables
        if not col_info["nullable"] and not col_info["primary_key"]:
            can_auto_add = False
            messages.append(f"  ⚠️  Column '{col_name}' (type: {sqlite_type}, NOT NULL) - Cannot auto-add")
            messages.append(f"      Manual migration required: This column has NOT NULL constraint without default.")
            messages.append(f"      Steps:")
            messages.append(f"        1. Add default value to model or make column nullable")
            messages.append(f"        2. Or migrate data manually with SQL commands")
        else:
            # Add default value if nullable
            if col_info["nullable"]:
                alter_statement += " DEFAULT NULL"
            
            messages.append(f"  ✓ Column '{col_name}' (type: {sqlite_type}, nullable={col_info['nullable']})")
            
            if not dry_run:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(alter_statement))
                        conn.commit()
                    messages.append(f"      ✓ Successfully added column")
                except Exception as e:
                    messages.append(f"      ✗ Failed to add column: {e}")
                    can_auto_add = False
            else:
                messages.append(f"      → Would execute: {alter_statement}")
    
    return messages


def sync_all_models(dry_run: bool = False) -> int:
    """
    Sync all model tables. Returns number of tables with issues.
    """
    engine = get_engine()
    db_path = get_db_path()
    
    print(f"🔍 Schema Sync Helper")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")
    
    models_to_check = [
        (Account, "account"),
        (AppConfig, "appconfig"),
        (JournalEntry, "journalentry"),
        (JournalLine, "journalline"),
        (Asset, "asset"),
    ]
    
    issues_count = 0
    all_messages = []
    
    for model_class, table_name in models_to_check:
        messages = sync_table_schema(engine, model_class, table_name, dry_run=dry_run)
        all_messages.extend(messages)
        
        # Check if there were issues
        if any("⚠️" in msg or "✗" in msg for msg in messages):
            issues_count += 1
    
    # Print all messages
    for msg in all_messages:
        print(msg)
    
    print("\n" + "="*80)
    if dry_run:
        print("DRY RUN completed. No changes were made.")
        print("Run without --dry-run to apply changes.")
    else:
        if issues_count > 0:
            print(f"⚠️  Schema sync completed with {issues_count} table(s) requiring manual attention.")
        else:
            print("✓ Schema sync completed successfully!")
    
    return issues_count


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Sync SQLModel schema with SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/sync_schema.py              # Apply changes
  python scripts/sync_schema.py --dry-run    # Preview changes without applying
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    
    args = parser.parse_args()
    
    try:
        issues = sync_all_models(dry_run=args.dry_run)
        sys.exit(0 if issues == 0 else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
