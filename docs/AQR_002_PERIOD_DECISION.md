# AQR-002 — Decisión pendiente sobre calendario y períodos

**Estado:** preparación documental; no es una política aprobada ni una capacidad implementada.  
**Base inspeccionada:** `fb2ef1bcf31020ee21d9753dc470703b2ad73211`.  
**Continuidad:** AQR-001 incorporada por PR #31, cierre por PR #32; AQR-002 es el único NEXT.

## 1. Decisión exacta que falta

Definir para V1 la partición temporal autoritativa de la contabilidad: **ejercicio calendario con meses fijos, ejercicio calendario con períodos configurables, o ejercicio y períodos configurables**. Además, determinar si las comparativas que se solapan son sólo parámetros de reportes o pueden constituir períodos contables de posting.

No se pide autorización para fusionar: ya existe. Falta resolver una elección de producto que condiciona qué fecha pertenece a qué período, qué se bloquea al cerrar y qué datos debe aceptar una migración. La autorización operativa vigente exige detenerse antes de tomar una decisión de esta clase no resuelta por el repositorio.

## 2. Evidencia y orden de autoridad

| Fuente vigente | Lo que resuelve | Lo que no resuelve |
|---|---|---|
| [Constitución](AQORATH_CONSTITUTION_V1.md), R3/R22/R24 | Períodos, cierres, migración explícita y autoridad única | No fija calendario, duración de períodos ni política de solapamiento |
| [Backlog](PRODUCT_BACKLOG_V1.md), AQR-002 | Posting en período válido y abierto, bloqueo, cierre canónico y consultas reproducibles | No elige meses fijos ni ejercicio personalizado |
| [Matriz aceptada](PRODUCT_ACCEPTANCE_V1.md), V1-10 | Guion de apertura/cierre de mes y cierre anual; resultado esperado | Un ejemplo mensual no prohíbe períodos diferentes ni elige límites del ejercicio |
| [Auditoría V2](REPO_AUDIT_V2.md), §§9/11/13 | Existe cierre y depreciación; no AccountingPeriod ni FiscalYear explícitos | No hay autoridad de calendario implementada que reutilizar |
| [Baseline](ARCHITECTURE_BASELINE_V1.md), «Explicación de Decisiones Abiertas» | Pregunta expresamente «¿Períodos mensuales fijos o definibles? ¿Solapables para comparativas?» y «¿Sistema sigue año civil (Ene-Dic) o fiscal personalizado?» | Las preguntas permanecen abiertas; no se localizó una resolución posterior en las fuentes de mayor autoridad |

Verificación reproducible sobre el main inspeccionado:

```bash
git grep -n -i -E 'año civil|año calendario|fiscal personalizado|períodos mensuales|periodos mensuales|solapab|AccountingPeriod|FiscalYear' fb2ef1bcf31020ee21d9753dc470703b2ad73211 -- INSTRUCCIONES.md docs aqorath
```

No se usaron PR históricos ni conversaciones como autoridad de diseño. Esta decisión no requiere modificar la Constitución.

## 3. Alternativas reales y consecuencias

| Alternativa | Contrato de producto | Consecuencia de implementación y aceptación |
|---|---|---|
| A — Calendario y meses fijos | Ejercicio enero-diciembre; períodos mensuales sin solapamiento; primer ejercicio admite inicio efectivo documentado dentro del año | Menos configuración; límites reproducibles y menores combinaciones de prueba. No permite un ejercicio julio-junio ni períodos operativos arbitrarios como autoridad de posting |
| B — Calendario con períodos configurables | Ejercicio enero-diciembre; partición interna elegida explícitamente, sin huecos ni solapamiento para las fechas habilitadas | Permite períodos distintos del mes; requiere configurar/validar cobertura, fronteras e inmutabilidad de rangos usados. El ejercicio sigue sin poder cruzar año calendario |
| C — Ejercicio y períodos configurables | Inicio/fin del ejercicio y su partición declarados explícitamente, sin solapamiento entre períodos de posting | Mayor flexibilidad, más configuración, validación de duración/cobertura y pruebas de cierres no calendarios. Un rango configurable no prueba por sí solo aplicabilidad fiscal |

**Comparativas:** en A/B/C pueden existir consultas de fechas que se solapen sin crear períodos contables solapados. Permitir también solapamiento en la autoridad de posting sería una variante adicional: exigiría decidir prioridad/selección del período y qué cierre prevalece cuando otro período abierto comparte la fecha. La interfaz común no debe tener que resolver esa ambigüedad contable. No se implementó tal variante.

**Recomendación técnica, no decisión tomada:** alternativa A para V1 y comparativas mediante filtros de reportes. Es la frontera más pequeña compatible con los recorridos mensuales/anuales de la matriz; B/C sólo aportan valor si se necesita esa configuración como capacidad V1. Es una recomendación de alcance del software, no un dictamen sobre obligaciones o calendarios fiscales de una entidad real.

## 4. Preparación técnica ya resuelta documentalmente

Se inspeccionaron las autoridades siguientes; ninguna debe reconstruirse:

| Punto existente | Evidencia concreta | Integración necesaria después de resolver la decisión |
|---|---|---|
| `aqorath/journal_entry.py` y `aqorath/models.py` | `period_id` opcional ya existe; en ORM no referencia todavía una tabla de períodos | Reutilizar la identidad; establecer resolución por fecha y relación válida, sin un segundo JournalEntry |
| `aqorath/core.py::_stage_entry_in_session` | Normaliza la fecha, construye JournalEntry/JournalLine en la sesión del llamador, sin commit propio | Comprobar período dentro de la misma transacción; un período ausente/cerrado no se corrige silenciosamente |
| `aqorath/core.py::_persist_entry` y `post_entry` | Wrappers canónicos de escritura | Conservar la ruta; no añadir persistencia alternativa para sortear un rechazo temporal |
| `aqorath/fiscalized_posting_persistence.py` | Usa `_stage_entry_in_session` junto con auditoría en una transacción | Rechazo temporal debe impedir tanto asiento como auditoría parcial |
| `aqorath/fixed_asset_acquisition_persistence.py` y `aqorath/fixed_asset_depreciation_persistence.py` | Componen el mismo staging con registros idempotentes | Rechazo temporal no consume identidad de adquisición/depreciación ni crea metadatos sin asiento |
| `aqorath/exercise.py::close_exercise` | Backup y traslado 3103/3104 por `post_entry`; actualmente usa fecha actual y `trial_balance()` sin delimitación de ejercicio | Añadir alcance temporal explícito y coordinar traslado/cierre en la autoridad existente. La prueba actual acredita delegación, no todo el cierre de resultados de V1-10 |
| `aqorath/core.py::trial_balance(as_of=...)` y `aqorath/reporting_source.py` | Fuente SQLite y corte por fecha existentes | Componer consultas inicial/movimientos/final del período sin otro motor de saldos |
| `aqorath/migrations.py` | Versión actual 4, migraciones explícitas, integridad, backup/restore | Definir evolución del esquema y validación de relaciones; no asignar estado abierto/cerrado ni inventar calendarios históricos |

El `period_number` del registro de depreciación identifica el reconocimiento mensual del activo; **no sustituye AccountingPeriod** ni debe reinterpretarse como tal.

La comprobación al preparar una propuesta no basta: entre preparación y persistencia puede cerrarse el período. La integración debe validar en la frontera transaccional que ya protege el ledger. Se debe probar también acceso por wrappers y composición fiscal/activos, preservando los contratos existentes.

## 5. Casos de aceptación preparados, pendientes de implementación

Estos escenarios son requisitos verificables para AQR-002; **no se presentan como tests ejecutados ni como criterios ya cumplidos**.

| Caso | Resultado exigido |
|---|---|
| Operación de 200 en fecha perteneciente a período abierto | Una póliza balanceada con identidad del período correcto |
| Misma operación con período cerrado | Rechazo sin póliza, líneas ni metadatos parciales |
| Fecha fuera de los períodos configurados | Rechazo explícito; no crear período implícito para continuar |
| `period_id` suministrado no coincide con la fecha | Rechazo; no privilegiar silenciosamente ID sobre fecha |
| Cerrar período después de preparar la operación y antes de confirmar posting | Rechazo transaccional; saldo sin cambio |
| Fecha en frontera consecutiva | Una única pertenencia; para A, 31-enero y 1-febrero resuelven a meses distintos |
| Período inexistente, rango invertido o fuera de su ejercicio | Rechazo antes de persistir estructura temporal inválida |
| Cierre anual con ingreso 200/gasto 150 | Cumplir V1-10, resultado 50, historia conservada, respaldo, alcance del ejercicio correcto y misma autoridad de posting |
| Repetición de cierre | Sin segundo efecto contable; conservar referencia del cierre o informar estado ya cerrado |
| Consulta al corte después de registrar movimientos de otro período | El saldo histórico no incorpora fechas posteriores |
| Posting fiscalizado/adquisición/depreciación rechazado por período | Sin auditoría ni registro idempotente parcial; reintento válido no queda consumido |
| Migración de base con `period_id` histórico sin definición | Diagnóstico y resolución explícita; no adivinar calendario/estado, no perder legibilidad ni cambiar importes |
| Fallo de migración o versión futura | Protección de la base anterior y rechazo conforme autoridad de migraciones existente |

Suite de regresión a conservar: `tests/test_p6bp_persistence_hardening.py`, `tests/test_p0_trial_balance_as_of.py`, `tests/test_p1_schema_migration_foundation.py`, `tests/test_p1_migration_hardening.py`, `tests/test_p5_fiscalized_posting_audit_persistence.py`, `tests/test_p6_fixed_asset_acquisition_persistence.py`, `tests/test_p6_fixed_asset_depreciation_persistence.py`, además de la suite completa por el impacto transversal en posting.

## 6. Límite de este avance y siguiente acción

No se añadió una tabla, migración ni guard de posting parcialmente activo: hacerlo antes de resolver el calendario convertiría una propuesta en política o dejaría las rutas de persistencia con contratos divergentes. Los criterios AQR-002 siguen pendientes. No se inicia AQR-003.

Una vez resuelta la decisión, incorporarla aquí y en la definición AQR-002, continuar en esta misma tarea con dominio/persistencia/migración, integración de posting/cierre y tests indicados, revisar el diff completo y ejecutar la suite completa antes de proponer fusión. No renumerar backlog ni convertir estos pasos en fases nuevas.
