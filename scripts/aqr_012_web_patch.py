from pathlib import Path

p = Path("aqorath/web_surface.py")
s = p.read_text(encoding="utf-8")
anchor = '''@app.post("/api/fiscal-v1/prepare")
def prepare_fiscal_v1(payload: dict):
'''
block = '''@app.get("/api/inventory/products")
def inventory_products():
    try:
        return controller.inventory_products()
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/products")
def create_inventory_product(payload: dict):
    try:
        return controller.create_inventory_product(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/prepare")
def prepare_inventory(payload: dict):
    try:
        return controller.prepare_inventory(payload)
    except Exception as exc:
        raise _error(exc) from exc


@app.get("/api/inventory/movements/{movement_id}/professional")
def professional_inventory(movement_id: int):
    try:
        return controller.professional_inventory(movement_id)
    except Exception as exc:
        raise _error(exc) from exc


@app.post("/api/inventory/movements/{movement_id}/reverse")
def reverse_inventory(movement_id: int, payload: dict):
    try:
        return controller.reverse_inventory(movement_id, payload)
    except Exception as exc:
        raise _error(exc) from exc


'''
if s.count(anchor) != 1:
    raise SystemExit(f"HTTP anchor count={s.count(anchor)}")
s = s.replace(anchor, block + anchor, 1)
p.write_text(s, encoding="utf-8")
