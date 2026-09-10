from pathlib import Path

p = Path("aqorath/presentation_controller.py")
s = p.read_text(encoding="utf-8")

def once(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match, got {n}")
    s = s.replace(old, new, 1)

once(
    "from . import fiscal_v1_surface_application as _fiscal_v1\nfrom . import surface_application as _application\n",
    "from . import fiscal_v1_surface_application as _fiscal_v1\nfrom . import inventory_surface_application as _inventory_v1\nfrom . import surface_application as _application\n",
    "inventory import",
)
once(
    "    def capabilities(self):\n        fiscal_kinds = tuple(_fiscal_v1.list_fiscal_v1_surface_kinds())\n        return {",
    "    def capabilities(self):\n        fiscal_kinds = tuple(_fiscal_v1.list_fiscal_v1_surface_kinds())\n        try:\n            inventory_products = _inventory_v1.list_inventory_surface_products()\n            inventory_enabled = True\n        except (LookupError, ValueError):\n            inventory_products = []\n            inventory_enabled = False\n        return {",
    "capabilities setup",
)
once(
    '            "views": ("common", "professional"),\n        }',
    '            "views": ("common", "professional"),\n            "inventory": {"enabled": inventory_enabled, "products": inventory_products},\n        }',
    "capabilities inventory",
)
anchor = '''    def prepare_fiscal_v1(self, payload):
        prepared = _fiscal_v1.prepare_fiscal_v1_surface_operation(payload)
        return self._store(prepared, prepared.common_preview)

'''
insert = '''    def prepare_inventory(self, payload):
        prepared = _inventory_v1.prepare_inventory_surface_operation(payload)
        return self._store(prepared, prepared.preview)

    def inventory_products(self):
        return _inventory_v1.list_inventory_surface_products()

    def create_inventory_product(self, payload):
        return _inventory_v1.create_inventory_surface_product(payload)

    def professional_inventory(self, movement_id):
        return _inventory_v1.load_inventory_surface_professional(movement_id)

    def reverse_inventory(self, movement_id, payload):
        return _inventory_v1.reverse_inventory_surface_operation(
            movement_id, payload.get("reason"), payload.get("reversal_date")
        )

'''
once(anchor, anchor + insert, "inventory controller methods")
once(
    '        if isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):\n            return _fiscal_v1.professional_fiscal_v1_preview(prepared)\n        raise TypeError("unsupported prepared presentation value")',
    '        if isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):\n            return _fiscal_v1.professional_fiscal_v1_preview(prepared)\n        if isinstance(prepared, _inventory_v1.PreparedInventorySurfaceOperation):\n            return _inventory_v1.professional_inventory_preview(prepared)\n        raise TypeError("unsupported prepared presentation value")',
    "professional preview",
)
once(
    '        elif isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):\n            response = _fiscal_v1.confirm_and_execute_fiscal_v1_surface_operation(prepared)\n        else:',
    '        elif isinstance(prepared, _fiscal_v1.PreparedFiscalV1SurfaceOperation):\n            response = _fiscal_v1.confirm_and_execute_fiscal_v1_surface_operation(prepared)\n        elif isinstance(prepared, _inventory_v1.PreparedInventorySurfaceOperation):\n            response = _inventory_v1.confirm_inventory_surface_operation(prepared)\n        else:',
    "confirm inventory",
)
p.write_text(s, encoding="utf-8")
