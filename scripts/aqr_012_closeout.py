from pathlib import Path

BACKLOG = Path("docs/PRODUCT_BACKLOG_V1.md")
INSTR = Path("INSTRUCCIONES.md")
AUDIT = Path("docs/REPO_AUDIT_V2.md")


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"expected one occurrence, got {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


s = BACKLOG.read_text(encoding="utf-8")
s = once(s, "## AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera\n\n**Estado:** `NEXT`", "## AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera\n\n**Estado:** `DONE`")
anchor = "### Dependencia\n\nAQR-001. Si la matriz V1 excluye inventario, esta tarea pasa a `DEFERRED` en vez de implementarse por inercia.\n\n---"
closeout = """### Dependencia

AQR-001. Si la matriz V1 excluye inventario, esta tarea pasa a `DEFERRED` en vez de implementarse por inercia.

### Cierre de aceptación

Implementado y fusionado mediante PR #48, merge `79d4ec06a6b5fe9e20b511284cfe105d21dddd40`, head definitivo revisado `bf74211975ce4ef19b0cf0243d6f315f8dbe5fd4`. CI estándar del head run 546 verde; CI post-merge de `main` run 547 verde; suite completa Python 3.12 registrada: **2125 passed, 8 warnings**.

AQR-012 incorpora schema 12 aditivo sin inventar inventario histórico, `Product` e `InventoryMovement` como autoridad de identidad, cantidades físicas, movimientos y costo reproducible por promedio ponderado móvil. `JournalEntry` / `JournalLine` permanecen como única autoridad monetaria; valuación y COGS se reconcilian contra esas líneas. El escenario V1-21 queda probado extremo a extremo (10×10 + 10×20 → 20 unidades/300/15; venta 4×25 → ingreso 100, COGS 60, margen 40, existencia 16, inventario 240). Compras/ventas son atómicas, idempotentes y fail-closed ante sobreventa; crédito reutiliza AQR-006 `OpenItem`; CFDI AQR-010 permanece evidencia documental canónica; fiscalidad AQR-011 se compone explícitamente antes de un único posting y no se infiere desde inventario/CFDI. Reversión conserva el costo consolidado original y la historia `as_of`; ownership y cambio de contexto fallan antes de crear verdad parcial. Las superficies común/profesional y HTTP/UI proyectan la misma persistencia sin shadow ledger.

---"""
s = once(s, anchor, closeout)
s = once(s, "## AQR-013 — Motor de documentos, paquetes y reportes de producto\n\n**Estado:** `TODO`", "## AQR-013 — Motor de documentos, paquetes y reportes de producto\n\n**Estado:** `NEXT`")
s = once(s, "`AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera`.", "`AQR-013 — Motor de documentos, paquetes y reportes de producto`.")
BACKLOG.write_text(s, encoding="utf-8")

s = INSTR.read_text(encoding="utf-8")
s = once(s, "### Runtime vigente — AQR-002 a AQR-010", "### Runtime vigente — AQR-002 a AQR-012")
s = once(s, "**`AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera`**", "**`AQR-013 — Motor de documentos, paquetes y reportes de producto`**")
old = "AQR-011 quedó incorporada mediante PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`, head revisado `527934106b6b852b67f51d4a708435c3e4897aec`, CI verde runs 498/499 y suite completa **2092 passed, 8 warnings**. AQR-012 es el único siguiente trabajo: inventario perpetuo y costos por promedio ponderado móvil, activados cuando el perfil de entidad lo requiera, siempre reconciliados con el ledger canónico y sin crear autoridad monetaria paralela."
new = """AQR-011 quedó incorporada mediante PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`, head revisado `527934106b6b852b67f51d4a708435c3e4897aec`, CI verde runs 498/499 y suite completa **2092 passed, 8 warnings**.

AQR-012 quedó incorporada mediante PR #48, merge `79d4ec06a6b5fe9e20b511284cfe105d21dddd40`, head revisado `bf74211975ce4ef19b0cf0243d6f315f8dbe5fd4`, CI verde runs 546/547 y suite completa **2125 passed, 8 warnings**. Inventario perpetuo/costo por promedio ponderado móvil conserva `JournalEntry`/`JournalLine` como autoridad monetaria, reconcilia stock/valuación/COGS, compone crédito/CFDI/fiscalidad/reversión sin duplicar autoridades y expone superficies común/profesional sobre la misma verdad.

AQR-013 es el único siguiente trabajo: convertir las fundaciones `ReportDefinition` / `ReportRequest` / `ReportPackage` / `CustomReportPackage` y las exportaciones existentes en un motor de documentos y reportes de producto, reutilizando las fuentes contables, OSC y fiscales ya consolidadas."""
s = once(s, old, new)
INSTR.write_text(s, encoding="utf-8")

s = AUDIT.read_text(encoding="utf-8")
s = once(s, "**Runtime material vigente:** AQR-002 a AQR-011", "**Runtime material vigente:** AQR-002 a AQR-012")
s = once(s, "**Esquema vigente:** 11", "**Esquema vigente:** 12")
s = once(s, "AQR-011 cerró la cobertura fiscal mexicana V1 mediante matriz normativa versionada, aplicabilidad factual fail-closed, cálculo exacto y superficies común/profesional sobre la misma autoridad contable.", "AQR-011 cerró la cobertura fiscal mexicana V1 mediante matriz normativa versionada, aplicabilidad factual fail-closed, cálculo exacto y superficies común/profesional sobre la misma autoridad contable. AQR-012 incorporó inventario perpetuo y costo por promedio ponderado móvil manteniendo `JournalEntry`/`JournalLine` como única autoridad monetaria y reconciliando existencia, valuación y COGS con el ledger.")
s = once(s, "- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-012.", "- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-013.")
anchor = "- superficies común/profesional reconstruyen la misma verdad fiscal persistida.\n\n---"
addition = """- superficies común/profesional reconstruyen la misma verdad fiscal persistida.

### AQR-012 — inventario perpetuo y costos

- PR #48, merge `79d4ec06a6b5fe9e20b511284cfe105d21dddd40`;
- head definitivo revisado `bf74211975ce4ef19b0cf0243d6f315f8dbe5fd4`;
- CI del head run 546 verde; CI post-merge de `main` run 547 verde;
- suite completa Python 3.12: **2125 passed, 8 warnings**;
- schema 12 aditivo con `inventoryproduct` / `inventorymovement` vacíos al migrar historia, sin backfill inventado;
- promedio ponderado móvil exacto con Decimal y V1-21 reproducible de superficie común a movimiento/ledger/readback/auditoría;
- stock, valor y COGS se reconcilian contra `JournalLine`; no existe shadow ledger de inventario;
- compras/ventas atómicas, oversell fail-closed e idempotencia por operación;
- crédito compone AQR-006 `OpenItem`, CFDI compone AQR-010 en el mismo commit y fiscalidad soportada compone AQR-011 antes de un único posting;
- reversión AQR-003 invierte el costo consolidado original sin revalorar el pasado y conserva historia `as_of`;
- ownership de producto/tercero/banco/CFDI/documento/OpenItem y cambio de Entity activa fallan antes de verdad parcial;
- superficies común/profesional y HTTP/UI consultan la misma persistencia canónica.

---"""
s = once(s, anchor, addition)
AUDIT.write_text(s, encoding="utf-8")
