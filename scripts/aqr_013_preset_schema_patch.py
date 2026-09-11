from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1))


path = "aqorath/migrations.py"
replace_once(
    path,
    'CURRENT_SCHEMA_VERSION = 12\n"""Schema 12 adds AQR-012 product identity and inventory movement provenance."""',
    'CURRENT_SCHEMA_VERSION = 13\n"""Schema 13 adds AQR-013 owner-scoped report preset configuration."""',
)
replace_once(
    path,
    '    from aqorath import inventory_models as _inventory_models  # noqa: F401\n',
    '    from aqorath import inventory_models as _inventory_models  # noqa: F401\n    from aqorath import report_preset_models as _report_preset_models  # noqa: F401\n',
)
anchor = '''def _validate_inventory_schema(db_path):
'''
insert = '''def _migrate_12_to_13(db_path):
    """Add report preset configuration without inventing historical presets/results."""
    from aqorath.report_preset_models import ReportPresetRecord, ReportPresetItemRecord
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            ReportPresetRecord.__table__.create(conn, checkfirst=True)
            ReportPresetItemRecord.__table__.create(conn, checkfirst=True)
    finally:
        engine.dispose()


def _validate_report_preset_schema(db_path):
    required = {
        "reportpreset": {
            "id", "entity_id", "name", "format", "created_at", "updated_at",
        },
        "reportpresetitem": {
            "id", "preset_id", "position", "report_definition_id",
            "parameters_json", "created_at",
        },
    }
    with sqlite3.connect(str(db_path)) as conn:
        for table, expected in required.items():
            found = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if found != expected:
                raise RuntimeError(f"Invalid schema 13 report preset table: {table}")

        def unique_sets(table):
            return {
                tuple(item[2] for item in conn.execute(f"PRAGMA index_info('{row[1]}')"))
                for row in conn.execute(f"PRAGMA index_list({table})") if row[2] == 1
            }

        if ("entity_id", "name") not in unique_sets("reportpreset"):
            raise RuntimeError("Invalid schema 13 preset owner/name uniqueness")
        item_unique = unique_sets("reportpresetitem")
        for key in (("preset_id", "position"), ("preset_id", "report_definition_id")):
            if key not in item_unique:
                raise RuntimeError(f"Invalid schema 13 preset item uniqueness: {key}")


'''
replace_once(path, anchor, insert + anchor)
replace_once(
    path,
    '    12: _migrate_11_to_12,\n}',
    '    12: _migrate_11_to_12,\n    13: _migrate_12_to_13,\n}',
)
replace_once(
    path,
    '        _validate_inventory_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))',
    '        _validate_inventory_schema(db_path)\n        _validate_report_preset_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))',
)
replace_once(
    path,
    '    _validate_inventory_schema(db_path)\n    return {',
    '    _validate_inventory_schema(db_path)\n    _validate_report_preset_schema(db_path)\n    return {',
)
print("AQR-013 preset schema patch applied")
