# Legacy Test Disposition — Phase 1E.2

**Date:** 2026-08-25
**Phase:** 1E.2 - Runtime and Repository Consolidation
**Context:** Retirement of legacy motor (modelos.libro, modelos.registro, etc.) as accounting authority

This document maps all legacy test functions from `test/` directory to their disposition category.
These tests are intentionally retired from the active test suite because they validate a motor
that is no longer the source of truth for accounting data. SQLite/ORM is the canonical authority.

---

## Disposition Categories

### A. SUPERSEDED_BY_CANONICAL
Coverage for this intent **already exists** in tests/ using SQLite/ORM as authority.
Cite the canonical test file/function.

### B. FUTURE_FUNCTIONAL_CAPABILITY
The intent is **still desirable** but belongs to a future phase (2A onwards).
The behavior depends on features not yet implemented (e.g., fiscal engine, document factory).

### C. RETIRED_LEGACY_BEHAVIOR
The behavior was **structurally dependent** on legacy Libro/XLSX as authority.
This mode of operation will NOT be preserved; the intent (if any) must be redesigned.

---

## Legacy Test Inventory (16 functions)

### test/test_asientos.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_asientos_persisten_guardar_y_cargar` | Persistence of asientos (entries) to XLSX via Libro | RETIRED_LEGACY_BEHAVIOR | XLSX export as future document factory |
| `test_export_asiento_csv_and_xlsx` | Export single asiento to CSV/XLSX | FUTURE_FUNCTIONAL_CAPABILITY | Document factory CSV/XLSX output |

### test/test_libro.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_compute_libro_mayor_basic` | Compute libro mayor (ledger) from Libro | FUTURE_FUNCTIONAL_CAPABILITY | Trial balance / Ledger view on SQLite |
| `test_generar_movimientos_con_impuestos_autogenerados_y_signo_por_catalogo` | Auto-generated tax entries with catalog sign rules | FUTURE_FUNCTIONAL_CAPABILITY | Future fiscal integration |

### test/test_registro.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_validate_missing_fields` | Field validation in registro (transaction record) | FUTURE_FUNCTIONAL_CAPABILITY | Economic fact validation layer |
| `test_validate_zero_amount` | Reject zero amounts | FUTURE_FUNCTIONAL_CAPABILITY | Economic fact validation layer |
| `test_cfdi_requires_metodo_pago` | CFDI requires payment method field | FUTURE_FUNCTIONAL_CAPABILITY | Future CFDI/fiscal integration |
| `test_aplicar_impuestos_from_mapeo` | Tax application using mapping | FUTURE_FUNCTIONAL_CAPABILITY | Future fiscal integration |

### test/test_fiscal.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_retencion_isr_autogenerada` | Auto-generated ISR withholding | FUTURE_FUNCTIONAL_CAPABILITY | Future fiscal integration (Mexican tax rules) |
| `test_compra_egreso_iva_acreditable` | Purchase/expense with IVA credit | FUTURE_FUNCTIONAL_CAPABILITY | Future fiscal integration (Mexican tax rules) |
| `test_fallback_sin_mapeo_no_impuestos` | No tax fallback when mapping absent | FUTURE_FUNCTIONAL_CAPABILITY | Future fiscal integration fallback behavior |

### test/test_cfdi.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_generate_cfdi_basic` | Generate basic CFDI (Mexican invoice) | FUTURE_FUNCTIONAL_CAPABILITY | Future CFDI/fiscal integration |

### test/test_cfdi_timbrado.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_import_timbrado_roundtrip` | Import stamped CFDI and round-trip | FUTURE_FUNCTIONAL_CAPABILITY | Future CFDI/fiscal integration |

### test/test_reportes.py

| Test | Intent | Disposition | Future/Canonical Replacement |
|------|--------|-------------|------------------------------|
| `test_export_balance_pdf` | Export balance sheet to PDF | FUTURE_FUNCTIONAL_CAPABILITY | Future document factory (PDF reports) |
| `test_export_mayor_pdf` | Export ledger to PDF | FUTURE_FUNCTIONAL_CAPABILITY | Future document factory (PDF reports) |
| `test_export_estado_resultados_pdf` | Export P&L statement to PDF | FUTURE_FUNCTIONAL_CAPABILITY | Future document factory (PDF reports) |

---

## Summary

- **Total legacy tests:** 16
- **SUPERSEDED_BY_CANONICAL:** 0
- **FUTURE_FUNCTIONAL_CAPABILITY:** 14
- **RETIRED_LEGACY_BEHAVIOR:** 2

---

## Rationale

All 16 legacy tests validate behavior of the `modelos` motor (Libro, Registro, Fiscal, CFDI, Reportes)
which is **no longer the accounting authority**. The intent of each test remains potentially valuable
but must be redesigned and reimplemented against the canonical runtime (SQLite/ORM/economic facts)
in future phases.

Key architectural change:
- **Legacy Aqorath** used Libro/XLSX as an accounting path.
- **By Phase 1C**, SQLite had already become the sole accounting authority.
- **Phase 1E** removes the remaining runtime and test dependencies on the retired Libro path.

Future phases will implement:
- Economic Fact Application Layer (core accounting domain model)
- Fiscal engine (tax rules, CFDI integration)
- Document Factory (reporting, exports)
- Additional integrations and compliance features

All legacy test intents are catalogued for future reference and redesign.
