from pathlib import Path

p = Path("aqorath/migrations.py")
s = p.read_text(encoding="utf-8")
old = "        _validate_subledger_schema(db_path)\n        _validate_cfdi_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))"
new = "        _validate_subledger_schema(db_path)\n        _validate_cfdi_schema(db_path)\n        _validate_inventory_schema(db_path)\n        _ensure_additive_current_schema(str(db_path))"
if s.count(old) != 1:
    raise SystemExit(f"current-version validation anchor count={s.count(old)}")
s = s.replace(old, new, 1)
old = "    _validate_subledger_schema(db_path)\n    _validate_cfdi_schema(db_path)\n    return {"
new = "    _validate_subledger_schema(db_path)\n    _validate_cfdi_schema(db_path)\n    _validate_inventory_schema(db_path)\n    return {"
if s.count(old) != 1:
    raise SystemExit(f"post-migration validation anchor count={s.count(old)}")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
