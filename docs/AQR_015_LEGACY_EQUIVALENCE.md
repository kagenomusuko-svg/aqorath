# AQR-015 — Equivalencia y retiro de autoridades legacy (#56)

## Propósito

Este documento registra qué semántica existía en las rutas legacy auditadas y dónde vive, si corresponde, la autoridad V1 vigente. El hardening retira **rutas**, no capacidades. No convierte código histórico en una nueva etapa funcional ni reabre AQR-002…AQR-014.

Baseline del hardening: `62ada81ec98fe02e174e8b98c932232c7bf6c27c`, con `22/22 TECHNICAL_INSTALLED: PASS`.

## Depreciación legacy

| Ruta legacy | Semántica | Autoridad vigente | Decisión |
|---|---|---|---|
| `aqorath/assets.py::generate_depreciation_entries_for_period` | depreciación mensual/anual, selección directa de cuentas, posting | `fixed_asset_depreciation*`, `fixed_asset_depreciation_allocation`, `fixed_asset_depreciation_recognition`, `fixed_asset_depreciation_accounting`, confirmación/persistencia especializada y book state | **Eliminar**. V1-09 ya acredita cálculo exacto, confirmación, póliza posted, audit, idempotencia y reapertura; la ruta antigua era una segunda autoridad con `float`, cuentas `6000/1700` y commits separados. |
| `scripts/generate_depr.py` | activador CLI desde checkout de la ruta anterior | superficie moderna de activos/períodos | **Eliminar**. No es entry point instalado ni contiene una capacidad distinta. |

La tabla/modelo histórico que pudiera permanecer en SQLite no se convierte por ello en autoridad ejecutable. #56 no hace una migración destructiva sólo para borrar historia inerte.

## Templates de operación retirados

El registro `OperationTemplate` no es autoridad V1. Las ocho claves que existían en el baseline se adjudican así:

| Template legacy | Intención económica histórica | Autoridad/caso V1 vigente | Clasificación | Decisión |
|---|---|---|---|---|
| `ingreso_venta` | venta inmediata con eventual IVA | V1-01 por AQR-004; fiscalidad exclusivamente por AQR-011/V1-14 | capacidad V1 ya cubierta | Retirar cálculo/template. |
| `ingreso_venta_bruto` | venta inmediata partiendo de importe bruto con IVA | AQR-004 + cobertura fiscal explícita AQR-011 cuando exista | capacidad cubierta sólo dentro del alcance fiscal declarado | Retirar; no inferir IVA desde template. |
| `egreso_compra` | compra/gasto inmediato con eventual IVA | V1-03 por AQR-004; mercancía V1-21/AQR-012; fiscalidad AQR-011 | capacidad V1 ya cubierta | Retirar. |
| `pago_proveedor` | pago de pasivo a proveedor | V1-04/AQR-006 | capacidad V1 ya cubierta | Retirar. |
| `pago_proveedor_con_retencion_iva` | reconocimiento + pago + retención IVA en un template único | AQR-006 para partida; AQR-011/V1-14 para tratamiento fiscal soportado | semántica válida sólo bajo autoridades modernas separadas | Retirar motor; no migrar fórmula histórica. |
| `nota_credito` | nota de crédito comercial | `PRODUCT_ACCEPTANCE_V1` la excluye de V1; corrección contable sólo V1-18 | fuera de V1 | Retirar. |
| `honorarios` | gasto de honorarios con retención ISR | V1-14/AQR-011, con reglas/versiones/vigencias/fuentes explícitas | capacidad V1 ya cubierta de forma más estricta | Retirar fórmula/template. |
| `nomina` | nómina simplificada, ISR/IMSS | nómina y obligaciones laborales están fuera de V1 | fuera de V1 | Retirar. |

`aqorath/templates.py` queda temporalmente como **tombstone fail-closed**: es importable para que pruebas de independencia puedan demostrar que las autoridades modernas no dependen de él, pero no conserva registro, cálculos, selección de cuentas ni posting. `list_templates()` devuelve vacío y cualquier resolución/registro falla explícitamente como `retired`.

La fachada `core/application` puede conservar nombres de compatibilidad mientras existan consumidores de importación, pero ya no puede convertir una `template_key` en contabilidad. El camino `core.post_entry(entry_dict)` permanece porque pertenece a la infraestructura full-entry validada y no obtiene reglas de templates. Esta distinción evita retirar por accidente `_stage_entry_in_session` y demás composición moderna.

## `accounting_model` binario

| Ruta legacy | Semántica | Autoridad vigente | Decisión |
|---|---|---|---|
| `aqorath/config.py` | `accounting_model=comercial|sin_fines` | `Entity + EntityProfile + FiscalProfile + capabilities/modules` | **Neutralizar** como tombstone fail-closed. No lee ni escribe `AppConfig`, no tiene JSON fallback y no enumera valores de identidad. |
| `scripts/init_catalog_db.py` | inicialización histórica de catálogo condicionada por ese selector | bootstrap instalado + catálogo gobernado `aqorath/data/catalogo_base.json` | **Eliminar**. |

Una fila histórica `AppConfig(accounting_model=...)` puede permanecer en una base antigua como historia inerte. No se interpreta, no decide identidad y no justifica una migración destructiva.

## Arqueología raíz

`templates/`, `static/`, `patches/` y `nomina_patch.diff` no eran package data ni tenían consumidor productivo vigente. AQR-005 ya clasificaba `templates/main.html`, `static/main.css` y `report_template.html` como arqueología de la antigua identidad binaria. Se retiran del árbol; Git conserva su historia.

`assets/catalogo.csv` y `assets/catalogo.xlsx` se conservan porque son **inputs de mantenimiento**, no autoridad runtime. El producto instalado continúa consumiendo únicamente el JSON gobernado empaquetado.

## Gate de no regresión

El hardening sólo queda aceptado si demuestra simultáneamente:

- ningún módulo ejecutable `aqorath.assets` en la distribución;
- templates y `accounting_model` fail-closed, sin reglas ni persistencia;
- full-entry/posting canónico preservado;
- ninguna capacidad V1 perdida;
- source suite verde;
- build sdist/wheel verde;
- distribution smoke fuera del checkout verde;
- installed V1 acceptance offline conserva `22/22 TECHNICAL_INSTALLED: PASS`.

`PROFESSIONAL_REVIEW`, `HUMAN_ACCEPTANCE` y `END_TO_END` permanecen pendientes hasta ejecutar sus gates reales sobre el candidato endurecido.
