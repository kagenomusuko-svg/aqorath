from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


backlog = "docs/PRODUCT_BACKLOG_V1.md"
replace_once(
    backlog,
    "## AQR-013 — Motor de documentos, paquetes y reportes de producto\n\n**Estado:** `NEXT`\n",
    "## AQR-013 — Motor de documentos, paquetes y reportes de producto\n\n**Estado:** `DONE`\n\n### Aceptación\n\nPR #51 incorporó AQR-013 con head revisado `cf5f9386844083a60f8dc323b4e0b0b989256d78`, CI canónico verde run 630 y merge `46bf21f61dd2d3e1cbadfa681a02e40d9faef63c`; el CI post-merge de `main` run 632 terminó verde. Schema 13 es aditivo y `reportpreset` / `reportpresetitem` persisten únicamente configuración owner-scoped. El contrato V1-12 prueba creación, edición gobernada, guardado, cierre/reapertura de sesión y regeneración del mismo preset contra cifras actuales: persistencia del preset no equivale a persistencia del resultado. `ReportDefinition` y `ReportRequest` conservan responsabilidades distintas; `ReportPackage` / `CustomReportPackage` son composición/preset, no autoridad contable. No existe shadow ledger ni caché monetaria autoritativa. JSON/XLSX son formatos de producto y no mecanismo de portabilidad relacional. La superficie profesional declara provenance vigente mediante AQR-011 (`FiscalPostingAuditRecord`, `load_fiscal_posting_audit_snapshot`) y AQR-010 (`CfdiSourceRecord`, `CfdiSourceLinkRecord`, `DocumentReferenceRecord`) y rechaza presentar `CfdiImportMetadataRecord` como autoridad canónica.\n",
)
replace_once(
    backlog,
    "## AQR-014 — Backup, restore, integridad y portabilidad como flujo de usuario\n\n**Estado:** `TODO`\n",
    "## AQR-014 — Backup, restore, integridad y portabilidad como flujo de usuario\n\n**Estado:** `NEXT`\n",
)
text = Path(backlog).read_text(encoding="utf-8")
if text.count("**Estado:** `NEXT`") != 1:
    raise SystemExit(f"backlog: expected one NEXT, found {text.count('**Estado:** `NEXT`')}")

instructions = "INSTRUCCIONES.md"
replace_once(
    instructions,
    "**`AQR-013 — Motor de documentos, paquetes y reportes de producto`**",
    "**`AQR-014 — Backup, restore, integridad y portabilidad como flujo de usuario`**",
)
replace_once(
    instructions,
    "AQR-013 es el único siguiente trabajo: convertir las fundaciones `ReportDefinition` / `ReportRequest` / `ReportPackage` / `CustomReportPackage` y las exportaciones existentes en un motor de documentos y reportes de producto, reutilizando las fuentes contables, OSC y fiscales ya consolidadas.",
    "AQR-013 quedó incorporada mediante PR #51, merge `46bf21f61dd2d3e1cbadfa681a02e40d9faef63c`, head revisado `cf5f9386844083a60f8dc323b4e0b0b989256d78`, CI canónico verde run 630 y CI post-merge verde run 632. Schema 13 añade presets persistidos owner-scoped sin persistir resultados monetarios; packages permanecen composición y JSON/XLSX formatos de producto, no portabilidad relacional. AQR-014 es el único siguiente trabajo: elevar las autoridades existentes de integridad/backup/restore a un flujo de producto completo y añadir una salida relacional portable, sin confundirla con los reportes AQR-013 ni crear persistencia paralela.",
)

audit = "docs/REPO_AUDIT_V2.md"
replace_once(
    audit,
    "Pendiente: convertirlos en motor completo de documentos/reportes de producto (AQR-013) y añadir reportes especializados conforme se completen OSC/fiscalidad.",
    "AQR-013 materializa el motor gobernado de documentos/reportes de producto sobre las autoridades existentes: schema 13 aditivo, presets owner-scoped persistidos como configuración, packages como composición y ejecución fresca sin resultados monetarios persistidos ni shadow ledger. Las superficies común/profesional, controlador y HTTP consumen las mismas autoridades; inventario proviene de AQR-012, fiscalidad de AQR-011, CFDI de AQR-010 y dimensiones de AQR-008. JSON/XLSX son formatos de producto; la exportación relacional portable permanece separada y corresponde a AQR-014.",
)
