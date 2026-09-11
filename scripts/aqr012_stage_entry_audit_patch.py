from pathlib import Path

path = Path("aqorath/inventory_operations.py")
text = path.read_text(encoding="utf-8")
marker = '"inventory_posting": {'
if marker in text:
    raise SystemExit(0)

old = '''            session.flush()\n\n            if prepared.kind == "purchase":\n'''
new = '''            session.flush()\n\n            # Non-fiscal inventory postings must expose the canonical ownership audit\n            # before AQR-010 stages a CFDI link. Fiscalized postings already stage\n            # their own single entry_posted event through AQR-011. Everything remains\n            # caller-owned and uncommitted until the inventory transaction succeeds.\n            if fiscal_result is None:\n                posting_audit = _audit.stage_audit_event(\n                    session,\n                    AuditEvent(\n                        None,\n                        entity.id,\n                        "entry_posted",\n                        datetime.now(timezone.utc),\n                        {\n                            "entry_id": entry.id,\n                            "inventory_posting": {\n                                "operation_id": prepared.operation_id,\n                                "kind": prepared.kind,\n                                "product_id": product.id,\n                                "consent": "explicit_confirmation",\n                            },\n                        },\n                    ),\n                )\n                if posting_audit.id is None:\n                    raise RuntimeError("canonical inventory posting audit did not receive identity")\n\n            if prepared.kind == "purchase":\n'''
if text.count(old) != 1:
    raise SystemExit(f"expected one inventory staging anchor, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
