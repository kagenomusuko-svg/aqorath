# AQR-015 — Expediente reproducible de aceptación técnica instalada V1

## Estado del expediente

Este documento registra **evidencia técnica instalada** de AQR-015. No sustituye `docs/PRODUCT_ACCEPTANCE_V1.md`, no modifica sus fichas y no convierte ninguna fila en «Soportada de extremo a extremo».

- AQR-015: `NEXT`, **no DONE**.
- PR de trabajo: `#55`, debe permanecer `open`, `draft`, `not merged`.
- candidato técnico de código/harness: `f6f63969dc5574fe86333a275e6c8ce77cde6e4e`.
- CI de adjudicación técnica: run `#710` (`34683648450`), cuatro gates en orden.
- source suite del candidato: `2192 passed, 8 warnings`.
- versión de paquete: `0+aqr015` (identificador de desarrollo, no versión semántica final).
- schema SQLite: `13`.
- plataforma técnicamente acreditada: GitHub Actions `ubuntu-latest`, Python `3.12`.
- moneda/frontera local: MXN, una entidad activa, un usuario, loopback/local, sin requerimiento de Internet.
- `TECHNICAL_INSTALLED: 22/22 PASS`.
- `PROFESSIONAL_REVIEW: PENDING`.
- `HUMAN_ACCEPTANCE: PENDING`.
- `END_TO_END: NOT YET` para V1-01…V1-22.

El commit documental que contiene este expediente es posterior al candidato técnico anterior por necesidad lógica: un documento no puede contener su propio SHA sin recursión. El body de PR #55 registra el head documental final y el CI de reproducibilidad posterior.

## Autoridades de aceptación

La adjudicación se hizo subordinada a:

1. `docs/AQORATH_CONSTITUTION_V1.md`;
2. `INSTRUCCIONES.md`;
3. `docs/PRODUCT_BACKLOG_V1.md`;
4. `docs/PRODUCT_ACCEPTANCE_V1.md`;
5. `docs/REPO_AUDIT_V2.md`.

La prueba fuente no sustituye la prueba instalada. La autoridad material de este expediente son los recorridos del wheel real fuera del checkout, los readbacks profesionales, la persistencia SQLite y los gates de distribución.

## Procedimiento reproducible

El workflow `.github/workflows/ci.yml` ejecuta, sobre `ubuntu-latest` y Python 3.12:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
python -m pytest -x -vv --tb=short
python -m build --sdist --wheel
python scripts/verify_distribution.py --wheel "$WHEEL" --sdist "$SDIST"
python scripts/verify_installed_v1.py --wheel "$WHEEL"
```

`verify_distribution.py` instala el wheel en un `venv` limpio y trabaja desde un CWD fuera del checkout. `verify_installed_v1.py` instala una sola vez el mismo wheel en otro entorno aislado y conduce los casos por la superficie HTTP loopback; sus lecturas SQLite externas sólo adjudican persistencia/integridad, no sustituyen la surface de producto.

## V1-19 — adjudicación

**Decisión:** `V1-19 TECHNICAL_INSTALLED: PASS`.

La instalación crea y recupera una Entity estable (`id=1`) con EntityProfile, un FiscalProfile persistido (`id=1`, `MX`, régimen `603`, `effective_from=2026-01-01`, `effective_to=null`), calendario/FY y bindings gobernados. `/api/onboarding` declara `monoentity=true`, `currency=MXN`, `internet_required=false` y que los códigos de binding son valores de selección, no campos ordinarios de Debe/Haber.

El harness instalado intenta un segundo `POST /api/onboarding` con otra entidad. La surface lo rechaza con la semántica vigente y explicación `active Entity already configured`; el GET posterior es idéntico al anterior y una lectura SQLite tras apagar el servidor confirma una sola Entity y un solo FiscalProfile. No hay verdad parcial.

La cadena fiscal reutiliza la autoridad existente: FiscalProfile de onboarding → `resolve_fiscal_profile(session, entity_id, operation_date)` → operación V1-14 del `2026-09-10` → readback profesional con `fiscal_profile_id=1`. El perfil `2026-01-01..∞` cubre esa fecha y su identidad coincide exactamente con la fila persistida.

V1-21 aporta la reutilización de ThirdParty: proveedor `id=1` en compra #1 y #2, cliente `id=2`; documentos y reconstrucciones profesionales conservan esos ids, y un reinicio real recupera las mismas identidades. V1-13/V1-14 añaden evidencia complementaria de terceros persistidos.

No se creó una segunda persistencia, un CRUD paralelo de perfiles ni una autoridad alterna de catálogo.

## V1-20 — adjudicación

**Decisión:** `V1-20 TECHNICAL_INSTALLED: PASS`.

`verify_distribution.py` ya demuestra el contrato sin un smoke redundante:

- construye sdist y wheel;
- crea `venv` limpio e instala el wheel con `pip`;
- verifica imports, metadata/version y `aqorath/data/catalogo_base.json`;
- exige console entry point;
- ejecuta fuera del checkout y rechaza fuga de imports al source tree;
- inicializa una DB local limpia con schema explícito actual;
- migra una fixture histórica de schema `6` a `13`;
- antes de migrar conserva backup schema 6;
- el sentinel histórico (`JournalLine` ligada a cuenta `1103`, débito exacto `123.45`) conserva exactamente ids, referencia de cuenta, importes, descripción y timestamp después de migrar;
- `PRAGMA integrity_check` queda `ok`;
- para schema futuro `14`, bootstrap falla cerrado, el SHA-256 de la DB queda byte-identical, sentinel y versión quedan intactos y no se crea un backup ficticio;
- la guardia offline intercepta DNS/conexiones externas y sólo permite loopback;
- el producto instalado arranca, sirve `/`, responde `/api/system/integrity`, backup y portable export, y termina limpiamente.

Esto prueba instalación limpia, actualización conservativa, misma verdad antes/después, incompatibilidad `EXPLAIN/STOP` sin reparación inventada y operación local sin Internet. No se infiere soporte multiplataforma: la evidencia de AQR-015 se limita al runner `ubuntu-latest`/Python 3.12 usado por CI.

## Matriz V1-01…V1-22

Leyenda: `TC` = `f6f63969dc5574fe86333a275e6c8ce77cde6e4e`; `CI` = `#710` / `34683648450`. En todas las filas: `PROFESSIONAL_REVIEW=PENDING`, `HUMAN_ACCEPTANCE=PENDING`, `END_TO_END=NOT YET`.

| ID | Hecho/fixture | Surface(s) | Autoridad de dominio | Autoridad contable | Source evidence | Installed evidence | Commit/CI | Identidades durables | Restart/readback | Límites | TECHNICAL_INSTALLED | PROFESSIONAL_REVIEW | HUMAN_ACCEPTANCE | END_TO_END |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V1-01 | Venta de servicio 200 al contado | `/api/operations/prepare` → professional-preview → confirm → professional readback | `economic_facts` / common operation preparation | canonical posting; `JournalEntry`/`JournalLine` | `economic_facts.py`; `test_p2_application_confirmation_posting.py`; `test_p2_posting_execution.py` | `_installed_v1_core_cases._assert_v1_01_http_flow`; posted entry + common/professional readback | TC / CI | `JournalEntry` id | durable professional readback in installed DB; human reopen remains separate | servicios o mercancía V1-21; sin anticipos/devoluciones/multimoneda | PASS | PENDING | PENDING | NOT YET |
| V1-02 | Venta 200 a crédito; cobros parcial/final | common/subledger HTTP; `/api/subledger/*` | AQR-006 `OpenItem`/ThirdParty application lifecycle | `JournalEntry`/`JournalLine` + control line | AQR-006 subledger contracts; `test_p3_accounts_receivable_lifecycle_e2e.py` | installed credit journey; `open_item_id=1`, source/partial/final entry identities; saldo parcial→0 | TC / CI | ThirdParty/OpenItem/source+application entry ids | persistent SQLite identities/readback; human reopen remains pending | sin intereses, factoring ni deterioro automático | PASS | PENDING | PENDING | NOT YET |
| V1-03 | Electricidad 150 pagada por banco | common operation HTTP + professional readback | economic fact utility expense | canonical posting | `test_p3_utility_expense_persistence_e2e.py` | installed correction DB baseline V1-03: gasto 150, banco `1101`, gasto `5102`, posted entry | TC / CI | `JournalEntry` id | durable DB/readback; correction fixture later preserves original history | mercancía→V1-21; activo durable→V1-08; sin prepagos/importación | PASS | PENDING | PENDING | NOT YET |
| V1-04 | Compra/servicio 1500 a crédito; pagos parcial/final | common/subledger HTTP; `/api/subledger/*` | AQR-006 payable/OpenItem lifecycle | `JournalEntry`/`JournalLine` + control line | `test_p3_accounts_payable_lifecycle_e2e.py`; AQR-006 | installed payable journey; `open_item_id=2`, source/partial/final entry identities; saldo→0 | TC / CI | ThirdParty/OpenItem/source+application entry ids | persistent SQLite identities/readback | sin intereses/anticipos; mercancía usa V1-21 | PASS | PENDING | PENDING | NOT YET |
| V1-05 | Transferencia 300 entre cuentas propias | banking HTTP surface | AQR-007 owned `BankAccount` transfer | single balanced `JournalEntry`/`JournalLine` | AQR-007 banking contracts | installed banking journey: source `bank_account_id=1` → destination `2`; one entry | TC / CI | 2 BankAccount ids + entry id | durable SQLite + integrity | sólo cuentas propias; no transferencia a tercero | PASS | PENDING | PENDING | NOT YET |
| V1-06 | Estado bancario y conciliación | banking/reconciliation HTTP surface | AQR-007 `BankStatement`/`Reconciliation` | ledger bank lines vs imported transactions | AQR-007 reconciliation contracts | installed reconciliation: bank 1200, ledger 1300, difference 100, unmatched line retained | TC / CI | BankAccount/Reconciliation/JournalLine ids | durable SQLite + integrity | no feed bancario remoto ni conciliación inventada | PASS | PENDING | PENDING | NOT YET |
| V1-07 | Donativo monetario OSC | OSC donation HTTP surface + professional readback | AQR-009 donation + AQR-008 source/fund composition | canonical ledger posting | `test_aqr009_donations.py`; AQR-008/009 | installed OSC journey: `donation_id=1`, `entry_id=1`, owned bank account identity | TC / CI | Donation/BankAccount/JournalEntry ids | durable SQLite + integrity | no certifica deducibilidad/timbrado; no subvenciones reembolsables | PASS | PENDING | PENDING | NOT YET |
| V1-08 | Adquisición de equipo de cómputo 12000 | fixed-asset local HTTP surface | fixed-asset acquisition authority | posted `JournalEntry`/`JournalLine` + `AuditEvent` | fixed-asset acquisition persistence contracts | installed assets: `asset_id=1`, `acquisition_entry_id=1`, posted + `entry_posted` audit | TC / CI | FixedAsset + JournalEntry ids | second real server process recovers same acquisition | fixture técnica `computer_equipment`; `land_buildings` no implica depreciar terreno | PASS | PENDING | PENDING | NOT YET |
| V1-09 | Depreciación 1000; valor en libros 11000 | fixed-asset depreciation/book-state HTTP | fixed-asset depreciation/book-state authority | posted depreciation entry + audit | fixed-asset depreciation/book-state contracts | installed assets: `depreciation_entry_id=2`; carrying value `11000.00` | TC / CI | FixedAsset + depreciation JournalEntry | real restart reproduces `11000.00` | sin depreciación fiscal integral; no extrapolar categorías no probadas | PASS | PENDING | PENDING | NOT YET |
| V1-10 | Períodos + cierre anual; resultado 50 | period/year-close local HTTP | AQR-002 period/FY/closing authority | canonical closing JournalEntry; closed-period guard | `test_aqr002_accounting_periods.py`; closing contracts | installed: sale+expense, pre-close backup, `closing_entry_id=3`, transfer 50, closed posting rejected | TC / CI | FiscalYear/Period/closing entry/backup path | real restart: FY sigue closed y transfer=50 | cierre contable no equivale a declaración fiscal | PASS | PENDING | PENDING | NOT YET |
| V1-11 | Póliza, diario, mayor, auxiliares, balanza | reporting/subledger professional surfaces | AQR-013 report authorities + AQR-006 subledger | canonical `JournalEntry`/`JournalLine` ledger | reporting integrations; ledger/subledger tests | installed reporting: policy entry, open item, cutoff trial debit=credit=650; extended=690 | TC / CI | JournalEntry/OpenItem/report request identities | persistent readback; reporting DB integrity | reportes V1 enumerados; no dictamen | PASS | PENDING | PENDING | NOT YET |
| V1-12 | Estados/paquetes/preset | `/api/reports/*` + report preset surface | AQR-013 `ReportDefinition`/`ReportPreset`/runtime | ledger-derived financial statement authorities | `test_p4_formal_financial_statements_e2e.py`; `test_p6_custom_report_package_foundation.py`; AQR-013 | installed package/preset `id=1`; result 450→490; XLSX generated | TC / CI | ReportPreset id | real restart reloads preset `id=1` and result 490 | paquete selecciona; no cambia cifras; no juego normativo exhaustivo | PASS | PENDING | PENDING | NOT YET |
| V1-13 | CFDI 4.0 fuente de operación incluida | CFDI import + common operation + professional readback | AQR-010 `CfdiSource`/`DocumentReference`/ThirdParty | single canonical JournalEntry | `test_aqr010_cfdi_source.py`; CFDI integration tests | installed: source/document/link `id=1`, UUID stable, total 1160, tax evidence 160 | TC / CI | CfdiSource/DocumentReference/link/ThirdParty/Entry ids | real restart preserves UUID/link/readback | sin timbrado, consulta SAT obligatoria, cancelación ni complementos | PASS | PENDING | PENDING | NOT YET |
| V1-14 | Honorarios base 1000 con fiscalidad delimitada | fiscal V1 common/professional HTTP | AQR-011 factual applicability + rule/version/effective profile | fiscalized canonical posting + `FiscalPostingAudit` | AQR-011 coverage/rule/source/rounding tests | installed V1-14: rule provenance, base, exact/rounded effects, balanced lines, audit; unknown fails closed | TC / CI | FiscalProfile `id=1`, ThirdParty `id=1`, Entry/Audit ids | real restart reproduces exact professional snapshot | tabla V1 únicamente; no cumplimiento/declaración integral | PASS | PENDING | PENDING | NOT YET |
| V1-15 | Fuente/fondo 1000; aplicación 300; disponible 700 | OSC funds/analytical/report surfaces | AQR-008 Fund/FundingSource/Program/AnalyticalDimension | same canonical JournalEntry/JournalLine | `test_aqr008_funds.py`; analytical dimension/program contracts | installed OSC journey: `fund_id=1`, `funding_source_id=1`, `program_id=1`; 1000/300/700 | TC / CI | Fund/FundingSource/Program ids | durable SQLite + integrity | sin contabilidades paralelas; subvenciones reembolsables fuera | PASS | PENDING | PENDING | NOT YET |
| V1-16 | Backup → mutación → restore | `/api/system/backup`, `/api/system/restore`, `/api/system/integrity` | AQR-014 recovery infrastructure | restored canonical SQLite truth | `test_aqr014_recovery_portability.py` | installed backup ZIP; unconfirmed restore rejected unchanged; explicit restore removes later mutation | TC / CI | backup package id + baseline/mutation entry ids | second server proves restored baseline and absent mutation | local; SQLite-only no prueba documentos externos salvo manifiesto soportado | PASS | PENDING | PENDING | NOT YET |
| V1-17 | Salida portable para contador/otro sistema | `/api/system/portable-export` | AQR-014 portable export authority | read-only export of canonical relational truth | `test_aqr014_recovery_portability.py`; reporting export contracts | installed ZIP independently parsed with stdlib; manifest/schema/data/reconciliation; PK/FK checked | TC / CI | stable table PK/FK and JournalEntry→JournalLine ids | export from reopened restored DB | no importación automática en ERP; Excel no es base primaria | PASS | PENDING | PENDING | NOT YET |
| V1-18 | Corregir 150→120 con motivo | common correction/reversal HTTP + professional readback | AQR-003 reversal/correction | original + reversing + replacement JournalEntries | `tests/test_aqr003_reversal.py`; AQR-006 integration | installed correction: original=1, reversal=2, replacement=3, net expense=120 | TC / CI | 3 linked JournalEntry ids + reason/audit | durable SQLite/readback | no edita/borrar posted; no cancela CFDI | PASS | PENDING | PENDING | NOT YET |
| V1-19 | Onboarding + datos reutilizables | GET/POST `/api/onboarding`; ThirdParty; V1-14; V1-21 | Entity/EntityProfile/FiscalProfile/ThirdParty + `resolve_fiscal_profile` | governed account bindings feed canonical posting | `onboarding_surface_application.py`; `entity_repository.py`; V1-14/V1-21 source tests | installed: Entity `id=1`; FiscalProfile `id=1` MX/603 `2026-01-01..∞`; second Entity rejected unchanged; supplier `id=1` reused twice and after restart | TC / CI | Entity/FiscalProfile/ThirdParty ids | V1-14 and V1-21 real restarts preserve profile/party-linked truth | monoentidad, monousuario, MXN; RFC histórico no es preferencia visual | PASS | PENDING | PENDING | NOT YET |
| V1-20 | Instalar/actualizar/abrir offline | wheel/sdist → fresh venv → console → loopback APIs | `product_bootstrap` + migrations + `local_server` | same migrated canonical SQLite ledger | `scripts/verify_distribution.py`; migration hardening tests | distribution smoke: clean bootstrap; schema6→13 exact sentinel; future14 fail-closed byte-identical; offline guard; root/integrity/backup/export/shutdown | TC / CI | historical account/entry/line identities + backup | post-upgrade same exact sentinel; external-CWD installed product | sólo GitHub Actions `ubuntu-latest`/Python3.12 acreditado; no promesa multiplataforma | PASS | PENDING | PENDING | NOT YET |
| V1-21 | Compra 10@10 + 10@20; venta 4@25 | `/api/inventory/*` + professional valuation report | AQR-012 `inventory_state`/moving weighted average | same JournalEntry/JournalLine; AQR-013 read-only valuation | `tests/test_aqr012_inventory*.py`; AQR-013 inventory integration | installed: 20/300/avg15; sale revenue100, COGS60, margin40; final 16/240; supplier reused | TC / CI | Product, ThirdParty, Movement[1..3], Entry[1..3] | real restart preserves 16/240/15 and valuation 240 | reventa simple; 1 inventario lógico; sin negativo/manufactura/lotes/series/otros métodos | PASS | PENDING | PENDING | NOT YET |
| V1-22 | Computadora donada en especie 12000 | OSC in-kind donation HTTP/professional surface | AQR-009 in-kind donation + destination/program authority | canonical non-cash JournalEntry | in-kind donation repository/tests; AQR-008/009/013 | installed OSC journey: `inkind_donation_id=1`, `entry_id=3`, `program_id=1`; no cash simulation | TC / CI | InKindDonation/Program/JournalEntry ids | durable SQLite + integrity | requiere evidencia de valuación; sin valuación no inventar importe; reglas fiscales separadas | PASS | PENDING | PENDING | NOT YET |

## Evidencia de CI y artifacts

El corte técnico conserva tanto verdes como rojos. Un run rojo no se borra del expediente: se clasifica por causa y se usa para demostrar cómo se cerró el contrato.

- #700 — **HISTORICAL TEST FIXTURE INCOMPATIBILITY**: fixtures 6N intentaban fabricar corrupción histórica mutando/eliminando ORM posted. Se reemplazó sólo esa fabricación adversarial por `sqlite3` directo; no se relajaron listeners/loaders/inmutabilidad productiva.
- #701 — **HARNESS DEFECT**: V1-10 esperaba `400`; `PeriodError` usa correctamente `409 Conflict`. Se alineó el harness, no el producto.
- #702 (`34678967045`) — verde; consolidó V1-08/V1-09/V1-10 instalados.
- #704 (`34681148274`) — **HARNESS DEFECT**: lectura case-sensitive de headers pese a normalización de `urllib`; source/build/distribution estaban verdes.
- #705 (`34681379855`) — verde; consolidó V1-16/V1-17.
- #707 (`34681651603`) — **HARNESS DEFECT**: confundía `definition.required_data` con `source_authorities`; las cifras V1-21 ya eran correctas.
- #708 (`34681929374`) — verde; consolidó V1-21.
- #709 (`34683342431`) — **HARNESS DEFECT**: el readback profesional usa `entity_id`, no `id`; antes del fallo ya acreditó rechazo monoentidad sin verdad parcial.
- #710 (`34683648450`) — corte técnico 22/22: source-tree, build, distribution smoke e installed acceptance verdes.

### Defectos de producto descubiertos durante aceptación

1. **PRODUCT DEFECT — composición de reference data fiscal en instalación limpia.** La instalación desde wheel no materializaba inicialmente toda la referencia fiscal requerida por V1-14. Se corrigió la composición de bootstrap/seed y el harness instalado ahora exige el conjunto gobernado exacto.
2. **PRODUCT DEFECT — adquisición/depreciación de activo fijo persistían `draft`.** El recorrido instalado detectó que las pólizas de V1-08/V1-09 no quedaban en estado posted. Se corrigieron esas rutas para persistir mediante la autoridad posted.
3. **PRODUCT DEFECT — faltaba `entry_posted` en esas rutas de activo fijo.** Se alineó la auditoría de adquisición/depreciación con la autoridad canónica de posting.

Estos defectos son distintos de los errores de harness anteriores y de la incompatibilidad de fixtures históricas. Los runs rojos forman parte de la evidencia de aceptación y no deben reinterpretarse como verdes retrospectivos.

## Límites V1 conservados

- moneda V1: MXN;
- un usuario local;
- una sola Entity activa;
- producto local/loopback; ninguna dependencia remota obligatoria para captura, consulta, explicación, backup o export;
- fiscalidad limitada a la tabla V1; no promesa de cumplimiento fiscal general, declaraciones, SAT filing, timbrado, certificación de deducibilidad ni consulta SAT obligatoria;
- `land_buildings` no significa depreciación automática de terreno;
- fixture técnica de activos: `computer_equipment`;
- inventario V1: mercancía comprada para reventa, un almacén/inventario lógico, promedio ponderado móvil único, sin stock negativo;
- fuera de V1 de inventario: manufactura, costos industriales, lotes, series, caducidad, consignación y métodos alternativos;
- no multimoneda;
- corrección contable no cancela CFDI;
- portable export no promete importación automática en cualquier ERP;
- plataforma probada para este candidato: GitHub Actions `ubuntu-latest`, Python 3.12; no se infiere soporte completo de Windows/macOS/Linux por ser Python.

Los límites específicos de cada ficha permanecen en `docs/PRODUCT_ACCEPTANCE_V1.md` y la matriz anterior los resume sin ampliarlos.

## Protocolo pendiente de PROFESSIONAL_REVIEW

Estado: `PENDING`.

Debe existir un revisor profesional real y quedar registrada, por cada caso aplicable, la revisión de hecho, póliza, saldos, documentos y explicación. En fiscalidad debe revisar además contexto, regla, versión, vigencia, base, redondeo y efecto. El expediente deberá añadir: identidad del revisor, fecha, head/versión, dictamen y discrepancias. Ningún pytest ni este dossier sustituye esa intervención.

## Protocolo pendiente de HUMAN_ACCEPTANCE

Estado: `PENDING`.

Una persona no contadora real debe ejecutar sobre instalación limpia y datos ficticios: vista común sin Debe/Haber ni captura ordinaria de códigos; confirmar/cancelar; pedir explicación; reabrir; contrastar contra vista profesional. El observador no puede operar ni traducir conceptos por la persona. Deben conservarse pasos, resultado, bloqueos y evidencia. Automatización no sustituye esta gate.

## Consecuencia de este corte

`22/22 TECHNICAL_INSTALLED: PASS` no implica AQR-015 `DONE`, no autoriza merge y no cambia `NEXT`. AQR-015 seguirá abierta hasta, como mínimo, revisión profesional real, aceptación humana real, adjudicación/hardening pre-release si corresponde, decisión de release, integración a `main` y actualización final de backlog/auditoría.
