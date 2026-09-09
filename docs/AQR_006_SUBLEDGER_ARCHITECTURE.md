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