from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


migrations = Path("aqorath/migrations.py")
s = migrations.read_text(encoding="utf-8")
s = replace_once(
    s,
    'CURRENT_SCHEMA_VERSION = 12\n"""Schema 12 adds AQR-012 product identity and inventory movement provenance."""',
    'CURRENT_SCHEMA_VERSION = 13\n"""Schema 13 adds AQR-013 custom report-package configuration only."""',
    "schema version",
)
s = replace_once(
    s,
    '    from aqorath import inventory_models as _inventory_models  # noqa: F401\n',
    '    from aqorath import inventory_models as _inventory_models  # noqa: F401\n'
    '    from aqorath import report_product_models as _report_product_models  # noqa: F401\n',
    "current metadata import",
)

migration_anchor = '''def _validate_inventory_schema(db_path):\n'''
migration = '''def _migrate_12_to_13(db_path):\n    """Add Entity-owned custom report presets without persisting report results."""\n    from aqorath.report_product_models import CustomReportPackageRecord\n    from sqlalchemy import create_engine\n\n    engine = create_engine(f"sqlite:///{db_path}")\n    try:\n        with engine.begin() as conn:\n            CustomReportPackageRecord.__table__.create(conn, checkfirst=True)\n    finally:\n        engine.dispose()\n\n\n'''
s = replace_once(s, migration_anchor, migration + migration_anchor, "migration insertion")

validator_anchor = '''def _validate_cfdi_schema(db_path):\n'''
validator = '''def _validate_report_product_schema(db_path):\n    required = {\n        "id",\n        "entity_id",\n        "name",\n        "report_definition_ids_json",\n        "created_at",\n    }\n    with sqlite3.connect(str(db_path)) as conn:\n        found = {\n            row[1]\n            for row in conn.execute("PRAGMA table_info(customreportpackage)")\n        }\n        if found != required:\n            raise RuntimeError("Invalid schema 13 custom report package table")\n\n        unique_sets = {\n            tuple(\n                item[2]\n                for item in conn.execute(\n                    f"PRAGMA index_info('{row[1]}')"\n                )\n            )\n            for row in conn.execute("PRAGMA index_list(customreportpackage)")\n            if row[2] == 1\n        }\n        if ("entity_id", "name") not in unique_sets:\n            raise RuntimeError("Invalid schema 13 custom report package ownership uniqueness")\n\n\n'''
s = replace_once(s, validator_anchor, validator + validator_anchor, "validator insertion")
s = replace_once(
    s,
    '    12: _migrate_11_to_12,\n}',
    '    12: _migrate_11_to_12,\n    13: _migrate_12_to_13,\n}',
    "migration registry",
)
s = replace_once(
    s,
    '        _validate_inventory_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))',
    '        _validate_inventory_schema(db_path)\n        _validate_report_product_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))',
    "current validation",
)
s = replace_once(
    s,
    '    _validate_inventory_schema(db_path)\n    return {',
    '    _validate_inventory_schema(db_path)\n    _validate_report_product_schema(db_path)\n    return {',
    "post-migration validation",
)
migrations.write_text(s, encoding="utf-8")

# Keep the AQR-012 historical contract scoped to the 11 -> 12 step rather than
# making it silently follow later CURRENT_SCHEMA_VERSION values.
test_path = Path("tests/test_aqr012_inventory_reversal_schema.py")
t = test_path.read_text(encoding="utf-8")
old = '''    result = migrations.migrate_database(path)\n    assert result["from_version"] == 11\n    assert result["to_version"] == 12\n    with sqlite3.connect(path) as conn:\n'''
new = '''    migrations._migrate_11_to_12(path)\n    migrations._set_schema_version(path, 12)\n    migrations._validate_inventory_schema(path)\n    with sqlite3.connect(path) as conn:\n'''
t = replace_once(t, old, new, "AQR-012 historical migration test")
test_path.write_text(t, encoding="utf-8")
