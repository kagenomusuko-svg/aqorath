# AQR-007 — Bancos y conciliación

## Autoridad

El estado de cuenta y sus movimientos son evidencia externa. `JournalEntry` y
`JournalLine` siguen siendo la única autoridad contable. AQR-007 sólo relaciona
ambos dominios y nunca modifica importes por efecto del matching.

## Modelo mínimo

- `BankAccount` identifica una cuenta real, su entidad propietaria y la cuenta
  contable de control. No contiene saldo contable.
- `BankStatementRecord` conserva identidad del archivo, hash, nombre, rango y
  saldos únicamente cuando aparecen en la fuente externa.
- `BankTransactionRecord` conserva fecha, referencia, importe exacto, dirección,
  saldo externo opcional y fingerprint estable. La unicidad se aplica por cuenta
  bancaria y fingerprint.
- `ReconciliationRecord` fija cuenta, estado y fecha de corte.
- `ReconciliationMatchRecord` relaciona una transacción externa con una línea
  real del ledger. Las unicidades impiden doble consumo en ambos lados.
- `ReconciliationMatchRevocationRecord` revoca una relación sin borrar historia;
  la vista vuelve a derivar el pendiente.

No se persisten `ledger_balance`, `matched` ni `difference` como estados
mutables. Se derivan al consultar desde las líneas y relaciones vigentes.

## CSV V1

El adaptador acepta exclusivamente `date`, `reference`, `amount` y, de forma
opcional, `balance`. Las fechas son ISO, los importes usan `Decimal`, el signo
determina `credit`/`debit` y el fingerprint se calcula sobre la fila canónica.
Columnas ambiguas o sobrantes fallan explícitamente. El hash del archivo hace la
importación idempotente.

## Conciliación

Un match exige la misma cuenta contable vinculada, fecha no posterior al corte,
dirección compatible e importe exacto. Una sugerencia futura podrá usar fecha,
referencia e importe, pero nunca confirmará una relación ambigua.

La vista conserva separadamente saldo externo, saldo derivado del ledger,
movimientos externos sin vínculo, líneas contables no reflejadas y diferencia.
El caso `ledger=1000`, `banco=900` se presenta como diferencia de `100`; no se
crea una póliza ficticia. Una partida contable aún ausente del estado puede
explicarse como depósito en tránsito sólo como diferencia observable a ese corte.

La migración schema 8 es aditiva y no interpreta ni rellena historia previa.
Las acciones de matching y revocación generan `AuditEvent` dentro de la misma
transacción que la relación.
