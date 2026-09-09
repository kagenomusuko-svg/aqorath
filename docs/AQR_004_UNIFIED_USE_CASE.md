# AQR-004 — Contrato del caso de uso contable unificado

**Estado:** contrato de implementación de AQR-004. Subordinado a la Constitución, `INSTRUCCIONES.md`, AQR-002 y AQR-003.

## 1. Propósito

AQR-004 no crea una nueva autoridad contable. Su función es componer las autoridades ya existentes para que una superficie de presentación opere sobre un único caso de uso sin conocer Debe/Haber, códigos de cuenta, SQLModel ni reglas fiscales internas.

Cadena canónica:

> **hecho económico → decisión contable → consentimiento → posting → auditoría**

## 2. Autoridades reutilizadas

| Responsabilidad | Autoridad existente compuesta |
|---|---|
| Hecho económico y semántica | `economic_facts.py`, `economic_fact_accounting_provenance.py` |
| Cuenta concreta | `account_bindings.py`, `account_resolution.py`, catálogo vigente |
| Explicación estructurada | `explanation.py` |
| Consentimiento | `confirmation.py` |
| Instrucción de posting | `posting.py`, adaptación de `posting_execution.py` |
| Período | `accounting_period_repository.py` desde el staging canónico |
| Ledger y persistencia | `core._stage_entry_in_session`, listeners de `storage.py` |
| Auditoría general | `audit_event.py`, `audit_event_repository.py` |
| Fiscalidad confirmada | cadena `fiscal_*`/`fiscalized_*` ya existente y `fiscalized_posting_persistence.py` |
| Reversión/corrección | AQR-003; no se reconstruye dentro de AQR-004 |

`accounting_operation_persistence.py` es sólo un adaptador transaccional: convierte la instrucción ya confirmada con el adaptador existente, usa el staging canónico y añade `AuditEvent` en la misma transacción. No calcula contabilidad ni contiene una ruta alternativa de ledger.

## 3. Flujo ordinario

`prepare_accounting_operation(session, fact, posting_date)` recibe únicamente datos de hecho que una presentación puede conocer. La selección de cuentas proviene de bindings persistidos; la presentación no suministra códigos.

La preparación:

1. resuelve una vez el `EconomicFact` conservando su provenance;
2. obtiene los roles semánticos y consume los bindings persistidos;
3. resuelve las cuentas mediante el catálogo existente;
4. deriva `ExplanationData` de la misma resolución;
5. congela el snapshot de confirmación existente;
6. devuelve un `AccountingDecision` inmutable.

`confirm_accounting_operation(decision)` sólo llama a la autoridad de confirmación sobre exactamente ese snapshot. Preparar nunca confirma ni postea.

`execute_accounting_operation(confirmed_decision)` crea la `PostingInstruction` existente y delega el commit a la composición transaccional. En esa frontera se vuelve a comprobar el período mediante `_stage_entry_in_session`; que el período estuviera abierto al preparar no autoriza el posting si fue cerrado después.

La operación terminada queda explícitamente `posted`, por lo que hereda la inmutabilidad y reversión de AQR-003.

## 4. Persistencia de AccountingDecision

AQR-004 no añade una tabla paralela de decisión que replique el ledger. La evidencia durable se divide según su autoridad natural:

- **JournalEntry/JournalLine:** identidad de póliza, fecha, estado y cuentas/importes efectivamente consolidados;
- **AuditEvent `entry_posted`:** hecho de origen, fecha solicitada, `rule_id`, `rule_version`, consentimiento explícito y explicación estructurada que justificó la decisión;
- **bindings/catálogo:** configuración vigente; no se copia como segundo ledger dentro del evento;
- **fiscal audit records:** provenance fiscal versionada, tasas, bases, reglas, redondeos y efectos cuando la operación pasa por la cadena fiscalizada existente.

Así, los códigos e importes posted se recuperan del ledger, mientras que los hechos y la justificación que no pueden deducirse inequívocamente de una póliza permanecen append-only en auditoría. La vista textual puede reconstruirse desde la evidencia estructurada sin convertir una explicación generativa en fuente de verdad.

La versión inicial de la regla ordinaria se identifica como `economic-fact-v1`; un cambio futuro de semántica que altere resultados históricos deberá introducir una versión nueva, no reinterpretar eventos previos.

## 5. Atomicidad

Posting ordinario y su `AuditEvent` se confirman en una sola transacción. Si falla período, ledger, entidad o auditoría, no queda póliza parcial ni evento huérfano.

Esto reutiliza el mismo patrón ya probado por `fiscalized_posting_persistence.py` y por la reversión de AQR-003: staging canónico + evidencia en la sesión del llamador + un único commit.

## 6. Fiscalidad

AQR-004 **no inventa** tratamiento fiscal a partir de un hecho ordinario. La matriz V1 declara que los fixtures contables ordinarios no tienen efecto fiscal salvo V1-14 y que la aplicabilidad/cobertura real se cierra en AQR-010/AQR-011.

Por tanto:

- cálculo, aplicabilidad, confirmación monetaria, composición fiscal, resolución de cuentas, posting y auditoría fiscal conservan sus autoridades actuales;
- `execute_fiscalized_accounting_operation(...)` únicamente compone la creación de la instrucción fiscalizada ya confirmada y `execute_fiscalized_posting_with_audit(...)`;
- no se crea un segundo calculador fiscal ni se elige silenciosamente una regla;
- cuando AQR-011 declare qué tratamiento aplica a cada caso V1, esa selección se integrará antes de esta misma frontera de ejecución, sin reemplazarla.

## 7. Relación con AQR-003

AQR-004 crea operaciones nuevas válidas; no implementa otra corrección. Una póliza `posted` producida por este caso de uso sólo puede corregirse mediante las autoridades de AQR-003.

Las operaciones cuyo ejercicio de origen está cerrado permanecen bloqueadas para corrección automática conforme a `AQR_003_CLOSED_YEAR_DECISION.md`. La futura política de errores de ejercicios anteriores sigue siendo una decisión contable separada y no altera este flujo ordinario.

## 8. Aceptación técnica

AQR-004 se considera técnicamente aceptada cuando pruebas reproducibles demuestran que:

- la preparación recibe hecho + fecha y resuelve bindings sin códigos suministrados por presentación;
- la decisión contiene explicación estructurada y un snapshot único de consentimiento;
- preparar no escribe ledger ni auditoría;
- confirmar conserva exactamente el snapshot preparado;
- ejecutar produce una sola póliza `posted` y un solo `entry_posted` recuperable;
- el cierre del período entre preparación y ejecución bloquea todo sin escritura parcial;
- un fallo de auditoría revierte el posting;
- el asiento resultante queda protegido por AQR-003;
- la ejecución fiscalizada delega a las autoridades existentes sin recalcular ni persistir por una ruta alternativa.
