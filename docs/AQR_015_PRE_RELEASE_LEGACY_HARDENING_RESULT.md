# AQR-015 — Resultado del hardening pre-release #56

## Corte

Este documento conserva el resultado de ejecutar el blocker identificado por `AQR_015_PRE_RELEASE_LEGACY_AUDIT.md` sobre el candidato técnico AQR-015.

- baseline AQR-015: `62ada81ec98fe02e174e8b98c932232c7bf6c27c`;
- rama: `aqr-015-pre-release-legacy-hardening`;
- PR apilado: #58, base `aqr-015-packaging-install-acceptance`;
- head de código endurecido validado: `08b35a693a4031d2b8343d2c26e0bb4cd1b231a4`;
- CI de hardening: run #726 (`34707219460`), **SUCCESS**;
- source suite: **2182 passed, 8 warnings**;
- package version: `0+aqr015`;
- schema: `13`;
- `22/22 TECHNICAL_INSTALLED: PASS` preservado.

La suite fuente disminuye respecto del corte anterior porque se retiraron tests cuyo único contrato era mantener ejecutables las APIs legacy eliminadas. Esos tests fueron sustituidos por una regresión arquitectónica específica y una comprobación del wheel construido; ningún caso V1 instalado se retiró ni se debilitó.

## Resultado por blocker

| Pieza auditada | Acción | Resultado |
|---|---|---|
| `aqorath/assets.py` | **Eliminada** | El wheel ya no contiene el segundo camino de depreciación/posting con `float`, cuentas `6000/1700` y commits separados. V1-08/V1-09 continúan verdes sobre las autoridades modernas. |
| `scripts/generate_depr.py` | **Eliminado** | Ya no existe activador desde checkout de la autoridad retirada. |
| `aqorath/templates.py` | **Neutralizada como tombstone fail-closed** | Ya no existe `OperationTemplate`, `_TEMPLATES`, `LineSpec`, fórmulas, selección de cuentas ni posting. `list_templates()` devuelve vacío; resolución/registro fallan explícitamente como `retired`. |
| fachada template de `core.py`/`application.py` | **Neutralizada por ausencia de autoridad resoluble** | Los nombres de compatibilidad que aún exigen pruebas históricas no pueden producir contabilidad desde una `template_key`; `core.post_entry(entry_dict)` y `_stage_entry_in_session` se conservan como infraestructura moderna. |
| `aqorath/config.py` | **Neutralizada como tombstone fail-closed** | Ya no contiene `DB_KEY`, `FALLBACK_PATH`, `_read_db` ni `_write_db`; no interpreta ni persiste `accounting_model`. Se conservan dos patch points privados inertes para pruebas de independencia. |
| `scripts/init_catalog_db.py` | **Eliminado** | El bootstrap instalado y el catálogo gobernado son la única ruta vigente. |
| `aqorath/template_utils.py` | **Eliminado** | No tenía consumidores modernos localizados. |
| raíz `templates/` / `static/` | **Eliminados** | AQR-005 ya los clasificaba como arqueología de la antigua identidad binaria; no eran package data ni runtime. |
| `patches/import_catalog_fix.patch` / `nomina_patch.diff` | **Eliminados** | Arqueología sin consumidor productivo; nómina continúa fuera de V1. |
| `assets/catalogo.csv/.xlsx` | **Conservados** | Inputs de mantenimiento, no autoridad runtime. El producto instalado sigue consumiendo `aqorath/data/catalogo_base.json`. |

La tabla completa de semántica rescatada/rechazada está en `AQR_015_LEGACY_EQUIVALENCE.md`.

## Compatibilidad fail-closed

`templates.py` y `config.py` permanecen importables únicamente porque varias pruebas de pureza usan esos módulos como puntos de monkeypatch para demostrar que fiscalidad, bindings y otras autoridades modernas **no los llaman**. Mantener un nombre importable no mantiene una autoridad de negocio si:

1. no contiene regla, registry ni persistencia;
2. cualquier invocación operativa falla explícitamente;
3. el wheel prueba esa conducta fuera del checkout;
4. los flujos V1 reales continúan usando las autoridades canónicas.

Durante run #725 un test de independencia (`test_account_bindings_use_only_supplied_session_without_json_or_direct_sqlite`) reveló precisamente esta necesidad: parchea `_read_fallback_file`/`_write_fallback_file` con una bomba para demostrar que bindings nunca los usa. Se conservaron esos nombres como stubs que sólo lanzan `retired`; no se restauró ningún fallback ni I/O.

## Regresiones nuevas

`tests/test_aqr015_pre_release_hardening.py` demuestra en source tree:

- `aqorath.assets` ya no existe;
- el registry de templates está neutralizado;
- `core` y `application` no pueden ejecutar una `template_key`;
- `accounting_model` no puede leerse/escribirse;
- no existen `DB_KEY` ni `FALLBACK_PATH` productivos.

`scripts/verify_pre_release_hardening.py` se ejecuta dentro del mismo gate de distribution smoke y abre el wheel real. Demuestra:

- ausencia estructural de `aqorath/assets.py` y `aqorath/template_utils.py`;
- ausencia del antiguo registry/cálculos de templates;
- ausencia de persistencia/fallback de `accounting_model`;
- ejecución fail-closed de las superficies de compatibilidad desde el wheel, fuera del checkout.

Artifact de run #726:

```text
AQR-015 distribution smoke: OK
AQR-015 #56 built-wheel hardening: OK
```

## No regresión V1

El mismo wheel de run #726 volvió a ejecutar la aceptación instalada completa. Permanecen verdes V1-01…V1-22 según su adjudicación combinada entre installed harness y distribution contract; entre la evidencia material reaparecen:

- V1-08/V1-09: adquisición/depreciación moderna, posted + audit + book state + reopen;
- V1-10: cierre anual y reapertura;
- V1-13/V1-14: CFDI/fiscalidad delimitada;
- V1-16/V1-17: restore y portable export;
- V1-19: monoentidad/perfil/ThirdParty reutilizable;
- V1-20: instalación/migración/offline;
- V1-21: inventario 16 unidades / 240 / promedio 15 tras reinicio.

Por tanto el resultado material de #56 es:

```text
menos autoridades ejecutables
+
mismas capacidades V1 acreditadas
```

## Estado de integración

Este documento registra el hardening en su PR separado. #56 sólo se considera completamente resuelto después de:

1. CI final del PR #58 verde;
2. integración de PR #58 a `aqr-015-packaging-install-acceptance`;
3. CI posterior de PR #55 verde con 22/22 preservado.

No se fusiona #58 directamente a `main`.

Después de esa integración:

- PR #55 debe permanecer draft y sin merge;
- AQR-015 continúa `NEXT`, no `DONE`;
- `PROFESSIONAL_REVIEW: PENDING`;
- `HUMAN_ACCEPTANCE: PENDING`;
- `END_TO_END: NOT YET`;
- #57 continúa sin iniciar.
