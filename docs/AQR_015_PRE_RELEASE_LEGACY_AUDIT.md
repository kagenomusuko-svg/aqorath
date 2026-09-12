# AQR-015 — Auditoría pre-release de rutas legacy (#56)

## Alcance y decisión

Esta auditoría se ejecuta **después** del corte `22/22 TECHNICAL_INSTALLED: PASS` de AQR-015 y **antes** de iniciar hardening. No implementa #56, no retira rutas, no modifica autoridades productivas y no altera los gates pendientes de revisión profesional o aceptación humana.

Corte auditado:

- repositorio: `kagenomusuko-svg/aqorath`;
- rama: `aqr-015-packaging-install-acceptance`;
- head documental previo: `d8ba16416b650da083f3ec259f35857ddbfc4ce6`;
- candidato técnico: `f6f63969dc5574fe86333a275e6c8ce77cde6e4e`;
- CI técnico 22/22: run #710 (`34683648450`), verde;
- CI del expediente: run #711 (`34683889936`), verde;
- package version: `0+aqr015`;
- schema: `13`.

**Conclusión:** `#56 = PRE-RELEASE BLOCKER`.

La condición del issue se cumple porque existen rutas legacy dentro del paquete Python instalado que siguen siendo importables/ejecutables y conservan semántica paralela a autoridades modernas. En particular, `aqorath/assets.py` contiene un segundo camino de depreciación/posting y `aqorath/templates.py` continúa conectado a una fachada legacy distribuida en `core.py`/`application.py`. Además, `aqorath/config.py` mantiene una autoridad ejecutable `comercial`/`sin_fines` incompatible con la identidad componible exigida por R15.

Por tanto, el siguiente hardening debe realizarse **en rama separada y PR separado**, después de AQR-015 y antes de congelar/publicar el candidato V1. Este documento no inicia ese trabajo.

## Autoridades aplicables

La adjudicación usa, entre otras, estas reglas constitucionales:

- **R15**: Entity no se reduce a “modo comercial / OSC”; identidad, fiscalidad, características y capacidades son componentes.
- **R23**: presentación, aplicación, dominio e infraestructura deben permanecer separadas.
- **R24**: debe existir una sola autoridad de negocio; la misma regla no puede variar según la ruta de entrada.
- **R25**: no se permiten fallbacks que oculten errores estructurales o continúen por adivinación.

El packaging vigente declara `packages = find:`; por ello los módulos Python bajo `aqorath/` forman parte de la distribución. El único `package_data` declarado es `aqorath/data/*.json`, y el único recurso extra declarado por `MANIFEST.in` es `aqorath/data/catalogo_base.json`. El único console entry point es `aqorath = aqorath.entrypoint:main`.

## Inventario de piezas auditadas

| Pieza | ¿Distribuida? | ¿Importable/ejecutable? | Consumidores/localización | Capacidad V1 legítima | Autoridad moderna | Hallazgo |
|---|---|---|---|---|---|---|
| `aqorath/assets.py` | **Sí**, módulo de `aqorath` | **Sí** | `scripts/generate_depr.py`; tests/arqueología | Depreciación de activo fijo sí es V1-09 | `fixed_asset_*`, confirmación/posting/persistencia canónicas | **BLOCKER**: calcula con `float`, busca cuentas hard-coded `6000/1700`, crea `JournalEntry(state="posted")` y hace commits directos separados. Es una autoridad paralela material. |
| `scripts/generate_depr.py` | No es entry point ni `package_data`; no forma parte de la superficie instalada canónica | Ejecutable desde checkout | importa `aqorath.assets.generate_depreciation_entries_for_period` | ninguna capacidad distinta | fixed-asset moderno | Debe retirarse o neutralizarse junto con `assets.py`; activa expresamente la ruta legacy cuando se usa desde checkout. |
| `aqorath/templates.py` | **Sí** | **Sí** | `core.generate_preview/list_templates`; fachada de `application.py`; tests de compatibilidad | varias operaciones V1 tienen equivalentes modernos | EconomicFact/AQR-004, account bindings, fiscal AQR-011 y verticales canónicos | **BLOCKER**: registro de `OperationTemplate` distribuido y todavía consumido. También contiene semánticas fuera de V1. Debe construirse tabla de equivalencia antes de retirar la ruta legacy. |
| `aqorath/core.py` — modo `template_key` y fallback de templates | **Sí** | **Sí** | `application.py` y tests; `generate_preview()` usa `get_template()` | el posting de full-entry aún es infraestructura usada por autoridades modernas | posting/confirmation modernos | **BLOCKER sólo en la fachada legacy**. `core.post_entry` no puede borrarse en bloque: el camino full-entry sigue siendo usado por posting moderno. Debe separarse/retirarse únicamente la entrada por template y fallbacks históricos. |
| `aqorath/application.py` — `preview_template` / `post_template` / compatibilidad legacy | **Sí** | **Sí** | tests de compatibilidad y API importable | ninguna semántica V1 exclusiva localizada | casos de uso modernos del mismo `application.py` | **BLOCKER** como superficie importable que mantiene viva la ruta de templates. La API moderna del módulo debe preservarse. |
| `aqorath/config.py` — `accounting_model` | **Sí** | **Sí** | `scripts/init_catalog_db.py` y tests; no se localizó consumidor productivo moderno | ninguna: V1 usa Entity/EntityProfile/FiscalProfile | onboarding + Entity/Profile + catálogo gobernado | **BLOCKER**: `set_accounting_model()` todavía acepta/persiste únicamente `comercial` o `sin_fines`. Es una autoridad binaria ejecutable contraria a R15. El propio archivo conserva helpers de fallback JSON históricos aunque la API pública actual declara SQLite como autoridad. |
| `scripts/init_catalog_db.py` | No es entry point ni package data | Ejecutable desde checkout | usa `get_accounting_model()` y escribe Account/AppConfig | mantenimiento histórico de catálogo | bootstrap/catálogo gobernado instalado | Debe auditarse/retirarse como consumidor de la identidad binaria. No es necesario para el runtime instalado probado de AQR-015. |
| raíz `templates/` + `static/` | No declarados como package data/runtime | Sólo desde checkout; `core.list_templates()` conserva fallback al directorio `templates` si falla el módulo | AQR-005 ya los clasifica como arqueología de “OSC / Comercial”; `report_template.html` sin consumidor productivo | ninguna capacidad V1 exclusiva | web assets/surfaces modernas | No bloquean por distribución de datos, pero el fallback de `core.py` es una razón adicional para limpiar #56. Deben quedar retirados o explícitamente archivados sin ruta ejecutable. |
| `patches/` + `nomina_patch.diff` | No declarados como package data/runtime | No ruta de producto localizada | no consumidor runtime/build localizado | ninguna; nómina está fuera de V1 | N/A | Arqueología. No constituye autoridad instalada, pero debe eliminarse o archivarse explícitamente en #56 para que no parezca superficie soportada. |
| `assets/catalogo.xlsx` / `assets/catalogo.csv` | No package data de runtime | herramientas de mantenimiento desde checkout | `convert_catalog_xlsx_to_json.py`, política de catálogo | fuente de mantenimiento, no autoridad runtime | `aqorath/data/catalogo_base.json` + catálogo/bootstrap | No es blocker por sí mismo. Conservar sólo si queda documentado como input de mantenimiento; el runtime debe continuar consumiendo exclusivamente el JSON gobernado. |

## Detalle de los blockers materiales

### 1. `aqorath/assets.py`

La ruta legacy no es un simple helper matemático. `generate_depreciation_entries_for_period()`:

1. abre persistencia directamente;
2. recorre el modelo histórico `Asset`;
3. calcula depreciación con `float`/`round`;
4. resuelve directamente las cuentas `6000` y `1700`;
5. crea `JournalEntry` ya `posted`;
6. hace commit de cabecera;
7. crea líneas y vuelve a hacer commit.

Esto compite materialmente con la cadena moderna de activo fijo que separa cálculo, asignación, reconocimiento, resolución contable, confirmación y posting/persistencia idempotente. Viola el objetivo de una única autoridad de R24 y atraviesa capas según R23. El script `generate_depr.py` demuestra además que la función fue concebida como ruta ejecutable, aunque ese script raíz no sea el console entry point instalado.

### 2. Templates y fachada legacy

`aqorath/templates.py` forma parte del paquete y mantiene un registro de operaciones por template. `core.py` importa `get_template`/`list_templates`, `generate_preview()` construye líneas desde esa autoridad y `application.py` conserva la fachada `post_template(...) -> _core.post_entry(...)`. Pruebas de compatibilidad todavía exigen que esa API exista.

El hardening no debe eliminar indiscriminadamente `core.py`: la ejecución moderna usa todavía el camino de `post_entry` sobre instrucciones/full entries. #56 debe distinguir:

- semántica reusable que deba migrarse;
- camino moderno de posting que debe preservarse;
- template-key/fallbacks/fachadas que deben retirarse o quedar inequívocamente no ejecutables.

La tabla de equivalencia legacy → autoridad moderna exigida por #56 es necesaria antes de borrar.

### 3. `aqorath/config.py`

Aunque la API pública actual lee/escribe SQLite, `set_accounting_model()` persiste sólo `comercial` o `sin_fines`. `scripts/init_catalog_db.py` todavía usa esa selección para elegir `name_comercial`/`name_osc`. La arquitectura V1 aceptada, en cambio, usa Entity + EntityProfile + FiscalProfile + capacidades y módulos. Mantener una segunda autoridad binaria importable dentro del wheel contradice directamente R15 y puede volver a introducir identidad paralela aun cuando hoy no exista consumidor productivo principal.

## Piezas no distribuidas y arqueología

`setup.cfg` y `MANIFEST.in` no declaran `scripts/`, `templates/`, `static/`, `patches/`, `nomina_patch.diff` ni `assets/*.xlsx|csv` como runtime/package data. La distribución canónica declara únicamente el package Python `aqorath`, `aqorath/data/*.json` y el console script `aqorath`.

Esto **no** permite cerrar #56 por ausencia aparente de imports: los blockers están dentro del propio package `aqorath`. Para las piezas raíz, la conclusión es más limitada: no forman parte de la superficie instalada canónica según la configuración de packaging inspeccionada y no se localizó consumidor productivo actual, pero #56 debe decidir entre eliminación, archivo explícito o mantenimiento documentado según cada caso.

AQR-005 ya había documentado que `templates/main.html`, `static/main.css` y `report_template.html` son arqueología que la superficie vigente no revive. La auditoría actual es coherente con esa decisión.

## Capacidad V1 que debe preservarse durante #56

El retiro no puede degradar las capacidades acreditadas por AQR-015. En particular:

- V1-08/V1-09 deben seguir usando la autoridad moderna de activos y conservar posted + audit + idempotencia + book state;
- V1-01…V1-07/V1-10…V1-18/V1-21/V1-22 deben seguir pasando por sus autoridades modernas sin template authority paralela;
- onboarding debe seguir usando Entity/EntityProfile/FiscalProfile y bindings gobernados, nunca `accounting_model`;
- catálogo runtime debe seguir resolviéndose desde `aqorath/data/catalogo_base.json` mediante su autoridad moderna;
- `core.post_entry` sólo puede modificarse después de identificar qué camino moderno aún lo consume; retirar la fachada legacy no autoriza romper posting canónico.

## Gate exigido al futuro PR de #56

#56 debe ejecutarse en **rama y PR separados**. Antes de considerarlo resuelto deberá demostrar, como mínimo:

1. inventario final de rutas eliminadas/neutralizadas y consumidores migrados;
2. ninguna segunda autoridad contable/persistencia ejecutable en la distribución V1;
3. ninguna pérdida de semántica V1 acreditada;
4. pruebas arquitectónicas que impidan reintroducir las rutas retiradas cuando corresponda;
5. source suite completa verde;
6. build sdist/wheel verde;
7. distribution smoke fuera del checkout verde;
8. installed V1 acceptance offline verde.

## Estado después de esta auditoría

- `22/22 TECHNICAL_INSTALLED: PASS` permanece válido para el candidato AQR-015 ya adjudicado.
- `PROFESSIONAL_REVIEW: PENDING`.
- `HUMAN_ACCEPTANCE: PENDING`.
- `END_TO_END: NOT YET`.
- AQR-015 continúa `NEXT`, **no DONE**.
- PR #55 debe permanecer draft y sin merge.
- **#56 = PRE-RELEASE BLOCKER**.
- #56 no se implementa dentro de PR #55.
- #57 no se inicia.
