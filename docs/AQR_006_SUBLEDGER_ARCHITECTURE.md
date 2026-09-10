# AQR-006 — Arquitectura de submayores CxC/CxP

## Autoridad y evidencia inspeccionada

AQR-006 parte de las autoridades vigentes de `main`, no de los lifecycle tests históricos como diseño normativo.

La inspección verificó:

- `EconomicFact` ya resuelve `sale/credit`, `utility_expense_incurred/credit`, `receivable_collection/bank` y `supplier_payment/bank`, pero no contiene tercero, documento, vencimiento ni identidad de obligación;
- `EconomicEvent.third_party` es texto, no una FK persistida que pueda identificar una cuenta individual;
- `AccountingDecision` preserva la decisión contable AQR-004 y tampoco contiene identidad de tercero/open item;
- `ThirdParty` sí es una identidad persistida y Entity-scoped;
- `DocumentReference` ya vincula estructuralmente `JournalEntry` y `ThirdParty` y es la autoridad documental que debe reutilizarse;
- `JournalEntry`/`JournalLine` son la única verdad monetaria consolidada;
- `JournalEntryReversalRecord` y `JournalEntry.state` ya representan la reversión/cancelación contable sin destruir historia;
- `core._stage_entry_in_session` existe precisamente para componer metadata dentro de la misma transacción antes de un único commit;
- `AuditEvent.stage_audit_event` ya sigue esa disciplina;
- no existe actualmente `OpenItem`, aplicación de partida, vencimiento ni saldo individual persistido;
- los E2E históricos sólo prueban venta/compra a crédito seguida de liquidación total agregada; AQR-001 exige parcialidades, tercero, documento, vencimiento, antigüedad y rechazo de sobreaplicación.

## Decisión derivada

No se persiste `outstanding_balance`, `status`, antigüedad ni un saldo monetario de submayor.

AQR-006 añade únicamente metadata relacional que señala **qué líneas del ledger representan**:

1. el origen de una obligación;
2. cada movimiento aplicado a esa obligación.

La cantidad original y cada aplicación se leen de `JournalLine`. El saldo abierto se deriva de esas líneas y del estado/reversión de sus pólizas. De este modo el submayor no puede convertirse en una segunda contabilidad monetaria.

### OpenItem

Una partida abierta identifica:

- Entity;
- ThirdParty;
- tipo `receivable` o `payable`;
- `source_entry_id`;
- `source_line_id` — la línea real de CxC/CxP;
- `source_document_reference_id` — documento real ligado a la misma póliza y tercero;
- fecha de vencimiento.

No almacena importe ni saldo.

### OpenItemApplication

Una aplicación identifica:

- open item;
- `application_entry_id`;
- `application_line_id` — la reducción real de la cuenta de control;
- `application_document_reference_id` — comprobante de cobro/pago.

No almacena importe ni saldo. El importe aplicado es el importe exacto de la línea vinculada.

## Semántica monetaria

Para CxC:

- origen: débito en la cuenta resuelta para `accounts_receivable`;
- aplicación: crédito en esa misma identidad contable.

Para CxP:

- origen: crédito en `accounts_payable`;
- aplicación: débito.

Las cuentas concretas nunca se codifican en AQR-006: se verifican contra las identidades resueltas por AQR-004/bindings y las líneas persistidas.

## Reversión y corte histórico

Una póliza original revertida no se borra. Para una fecha de corte, una póliza produce efecto hasta la fecha de su póliza de reversión. Por tanto:

- una aplicación revertida vuelve a abrir saldo automáticamente;
- un origen revertido sin aplicaciones activas queda cancelado y con saldo cero;
- un origen con aplicaciones activas debe revertir primero esas aplicaciones; la reversión del origen se bloquea para evitar una estructura imposible;
- la corrección genérica `reverse + replacement` se bloquea para entradas que participan en un submayor, porque el replacement necesitaría metadata de open item/aplicación dentro de la misma transacción. La corrección se hace revirtiendo y registrando el nuevo hecho por el caso de uso AQR-006.

Esta regla compone AQR-003; no introduce edición ni borrado.

## Reconciliación

Toda lectura del submayor puede demostrar:

`saldo submayor derivado == saldo ledger de las cuentas de control`

La reconciliación incluye:

- líneas origen;
- líneas de aplicación;
- sus líneas de reversión cuando existan;
- cuenta de control vigente y las identidades contables observadas en la metadata/auditoría canónica.

Una línea de CxC/CxP en el ledger sin representación en origen/aplicación/reversión se reporta como movimiento no asignado. Una diferencia o movimiento no asignado provoca `SubledgerDivergenceError` en las fronteras estrictas; nunca se corrige ni oculta automáticamente.

Esto permite detectar bases históricas con saldo de control previo a AQR-006 sin inventar qué tercero/documento les corresponde.

## Parcialidades, liquidación y sobreaplicación

El saldo de una partida es:

`efecto vigente del origen - suma de efectos vigentes de sus aplicaciones`

Una aplicación se rechaza si:

- la partida no existe;
- está cancelada/revertida;
- ya está liquidada;
- el importe excede el saldo vigente;
- la línea resultante no corresponde exactamente a la cuenta/side esperados.

La liquidación total no necesita una mutación de `status`: `open_balance == 0` implica `settled`.

## Antigüedad

La antigüedad se calcula a la fecha de corte desde `due_date` y el saldo abierto derivado. Los buckets V1 son:

- `current`;
- `1-30`;
- `31-60`;
- `61-90`;
- `91+`.

No se persisten buckets.

## Atomicidad

AQR-006 no ejecuta AQR-004 y después “anota” el submayor. Se extrae una frontera de staging sin commit de AQR-004 y otra de `DocumentReference`.

En una única sesión/transacción se realiza:

`decision confirmada -> staging canónico JournalEntry/JournalLine -> AuditEvent -> DocumentReference -> OpenItem/Application -> auditoría de submayor -> reconciliación -> commit`

Cualquier fallo hace rollback de todo.

## Esquema

Las dos relaciones nuevas son persistencia material y se incorporan mediante migración explícita **schema 7**. No se esconden como tablas aditivas dentro del schema 6.

## Superficie

La superficie AQR-005 se amplía sin trasladar reglas contables al navegador:

- origen CxC/CxP: tercero, importe, fecha, vencimiento y documento;
- cobro/pago: selección de una partida abierta, importe, fecha y comprobante;
- profesional: partidas por tercero, origen, aplicaciones, saldo, vencimiento, antigüedad y estado de reconciliación.

La vista común nunca pide Debe/Haber ni códigos contables.

## Límite V1

AQR-006 cubre los verticales ordinarios ya soportados (`sale/credit` y servicio/gasto a crédito) y sus cobros/pagos. Compra de mercancía/inventario, crédito de activo fijo y tratamiento fiscal adicional se conectarán cuando sus respectivos casos de uso AQR posteriores existan; no se simulan mediante una segunda ruta.
## Cierre técnico y verificación de continuidad — 2026-09-10

El log efectivo de CI run `34425778465` sobre `029a899ac8ea3139a5ceb2edcb0c02e9feab5bd1` muestra que `test_schema_6_to_7_does_not_invent_historical_provenance` ya pasaba. Los 12 fallos restantes eran siete fixtures sin EntityProfile y cinco expectativas residuales de schema 6. No hubo evidencia de defecto en `_migrate_6_to_7`, que se conserva.

La fixture histórica ahora materializa `tests/fixtures/schema6.sql`, DDL congelado de `models.py` de main `9c4a9882d47c327c02a096be1e38f96fa1b90f7e` (ese archivo no fue modificado por AQR-006). No importa metadata del runtime. La prueba verifica `user_version=6`, exclusión física de ambas relaciones AQR-006, columnas históricas y capacidad de insertar JournalLine; después exige únicamente las dos tablas nuevas, preservación del DDL histórico y de todos los campos de la línea, FK, NOT NULL, PK, CHECK de tipo, unicidades, tablas sin datos inventados e integridad SQLite.

La fixture operacional crea Entity + EntityProfile por la autoridad existente. Se conserva la cobertura previa de CFDI, incluidos los tests que habían desaparecido al reformatear el archivo. Las adaptaciones de pruebas históricas sólo cambian expectativas de versión vigente.

Las aplicaciones se validan en **todas las fechas de cambio** de la obligación, incluidas reversiones futuras: comprobar sólo el saldo final ocultaba sobreaplicaciones intermedias de cobros/pagos retroactivos. La reversión del origen no puede preceder a la reversión de sus aplicaciones ni a su propia operación. Estas comprobaciones componen las relaciones AQR-003; no persisten saldos.

La superficie incluye alta/selección de terceros, origen, parcialidad/liquidación, distribución de un cobro/pago entre documentos del mismo tercero, detalle y reversión. La vista profesional muestra el origen, líneas reales, aplicaciones, documentos, auditoría, reversión, aging a fecha y reconciliación. El navegador conserva únicamente tokens y valores de captura; los importes mostrados llegan como texto exacto del servidor y no se suman con Number/float. `Number` se limita a identificadores.

La reconciliación permite una nueva operación sobre gaps históricos sólo si mantiene exactamente la diferencia y las líneas no asignadas previas; la respuesta conserva esas discrepancias y la interfaz las presenta explícitamente. La frontera estricta `assert_subledger_reconciled` sigue rechazándolas. No se hace backfill.

Verificación local Python 3.12.14, instalación equivalente a CI: **81 pruebas específicas/regresiones AQR-002–006** y **1993 pruebas en suite completa**, con 8 advertencias heredadas. Incluye rollback inyectado en documento, segunda aplicación de batch, auditoría y reconciliación, consentimiento obsoleto, límites de aging y cortes históricos. JavaScript de la superficie validado sintácticamente. La comprobación visual no se acredita: el navegador del entorno perdió conexión; el recorrido humano reproducible siguiente permite verificar la interacción sin afirmar una inspección que no ocurrió.

## Recorrido humano reproducible

Con entidad, calendario abierto y bindings legítimos ya configurados por las autoridades existentes:

1. En vista común, guardar un cliente o proveedor y seleccionarlo para una venta a crédito o compra de servicios a crédito.
2. Capturar importe, fecha, vencimiento, folio y fecha documental; revisar y confirmar.
3. Consultar obligaciones al corte elegido. Capturar una parcialidad junto a su documento; revisar el cobro/pago y confirmar. El pendiente disminuye por el importe derivado de la nueva línea del ledger.
4. Intentar exceder el pendiente: se rechaza sin nuevas pólizas/documentos/aplicaciones. «Saldo completo» copia el saldo mostrado sin calcularlo.
5. Crear otra obligación del mismo tercero; escribir importes en ambos documentos y confirmar un único cobro/pago. Deben existir líneas de control distintas para cada aplicación.
6. Abrir Detalle y revertir el cobro/pago completo con motivo y fecha. Actualizar el corte a esa fecha: ambas obligaciones reaparecen abiertas.
7. En vista profesional, inspeccionar el ID de obligación y el corte; contrastar documento, tercero, fechas, póliza/línea origen, pólizas/líneas aplicadas, auditoría, reversión, importes, saldo, estado y aging. Consultar reconciliación; una diferencia o línea sin asignar permanece explícita.

La aceptación no amplía compras a inventario/activos ni inventa cobertura fiscal: siguen gobernados por sus tareas específicas.
