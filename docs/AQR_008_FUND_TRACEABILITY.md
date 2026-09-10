# AQR-008 — Fondos, fuentes, restricciones y aplicación

## Autoridad

`JournalEntry`/`JournalLine` siguen siendo la única autoridad monetaria. AQR-008
añade trazabilidad OSC, no un saldo de fondos paralelo: `FundReceipt` y
`FundApplication` sólo clasifican y cuantifican importes que deben coincidir con
líneas existentes del ledger.

## Modelo

- `Fund` identifica código, propósito, restricción, destino opcional y vigencia.
- `FundingSource` identifica la procedencia y puede referir un `ThirdParty`.
- `FundReceipt` relaciona un recurso recibido con fuente, fondo y una
  `JournalLine` exacta; opcionalmente conserva el `Donation` de origen.
- `FundApplication` relaciona fondo, `Program` y una `JournalLine` de aplicación.
  Las aplicaciones parciales se cuantifican explícitamente y su suma no puede
  exceder el importe de la línea canónica.

Las relaciones son entity-scoped, append-only en auditoría y se escriben en una
transacción. No se crean cuentas, pólizas, líneas ni saldos por registrar una
relación. Un importe divergente se rechaza; nunca se ajusta silenciosamente.

## Migración y pruebas

Schema 9 es aditivo y crea `fund`, `fundingsource`, `fundreceipt` y
`fundapplication`. No hace backfill de historia. Las pruebas cubren aislamiento
estructural, inmutabilidad del dominio y validación exacta contra `JournalLine`.
