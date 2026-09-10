from pathlib import Path

p = Path("aqorath/migrations.py")
s = p.read_text(encoding="utf-8")

def once(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match, got {n}")
    s = s.replace(old, new, 1)

once('CURRENT_SCHEMA_VERSION = 11\n"""Schema 11 adds independent, exact CFDI source evidence."""',
     'CURRENT_SCHEMA_VERSION = 12\n"""Schema 12 adds AQR-012 product identity and inventory movement provenance."""',
     'schema version')
once('    from aqorath import cfdi_models as _cfdi_models  # noqa: F401\n',
     '    from aqorath import cfdi_models as _cfdi_models  # noqa: F401\n    from aqorath import inventory_models as _inventory_models  # noqa: F401\n',
     'current schema imports')
anchor = '''def _validate_cfdi_schema(db_path):\n'''
insert = '''def _migrate_11_to_12(db_path):
    """Add physical inventory provenance without inventing historical stock or value."""
    from aqorath.inventory_models import ProductRecord, InventoryMovementRecord
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            ProductRecord.__table__.create(conn, checkfirst=True)
            InventoryMovementRecord.__table__.create(conn, checkfirst=True)
    finally:
        engine.dispose()


def _validate_inventory_schema(db_path):
    required = {
        "inventoryproduct": {
            "id", "entity_id", "sku", "name", "unit", "is_active", "created_at",
        },
        "inventorymovement": {
            "id", "operation_id", "entity_id", "product_id", "entry_id", "movement_kind",
            "occurred_on", "quantity_delta", "value_delta", "unit_price", "unit_cost_basis",
            "quantity_after", "value_after", "moving_average_after", "third_party_id",
            "document_reference_id", "inventory_line_id", "cogs_line_id", "source_movement_id",
            "created_at",
        },
    }
    with sqlite3.connect(str(db_path)) as conn:
        for table, expected in required.items():
            found = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if found != expected:
                raise RuntimeError(f"Invalid schema 12 inventory table: {table}")
        def unique_sets(table):
            return {
                tuple(item[2] for item in conn.execute(f"PRAGMA index_info('{row[1]}')"))
                for row in conn.execute(f"PRAGMA index_list({table})") if row[2] == 1
            }
        if ("entity_id", "sku") not in unique_sets("inventoryproduct"):
            raise RuntimeError("Invalid schema 12 product ownership uniqueness")
        movement_unique = unique_sets("inventorymovement")
        for key in (("operation_id",), ("inventory_line_id",), ("cogs_line_id",), ("source_movement_id",)):
            if key not in movement_unique:
                raise RuntimeError(f"Invalid schema 12 movement uniqueness: {key}")


'''
once(anchor, insert + anchor, 'inventory migration insertion')
once('    11: _migrate_10_to_11,\n}', '    11: _migrate_10_to_11,\n    12: _migrate_11_to_12,\n}', 'migration registry')
p.write_text(s, encoding="utf-8")
