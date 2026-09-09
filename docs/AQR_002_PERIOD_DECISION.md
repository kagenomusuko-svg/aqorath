# AQR-002 — Contrato aprobado de calendario y períodos

**Decisión de producto:** alternativa A, aprobada expresamente por el usuario el 2026-09-09 e incorporada al PR #33. Sustituye las preguntas temporales abiertas del baseline. No modifica la Constitución.

## 1. Contrato V1

- Ejercicio ordinario enero–diciembre.
- Períodos autoritativos de posting mensuales, correspondientes a meses calendario, sin solapamiento. Cada fecha contabilizable tiene una única pertenencia determinística.
- El primer ejercicio puede ser corto: comienza en la fecha efectiva de inicio de actividades y termina el 31 de diciembre del mismo año. Su primer mes sólo cubre desde esa fecha; no se crean períodos utilizables, operaciones ni cobertura anterior.
- Un período cerrado rechaza nuevos postings. Los ejercicios deben abrirse expresamente; una operación no los crea implícitamente.
- Consultas, comparativas y reportes admiten rangos arbitrarios que cruzan o combinan períodos. Los rangos no crean períodos de posting.
- V1 no admite calendarios configurables, ejercicios julio–junio ni otros calendarios personalizados. La flexibilidad futura requiere una tarea explícita y no puede reinterpretar silenciosamente ejercicios históricos.
- Existe una sola autoridad de dominio para resolver fechas; todas las rutas de posting la consumen.
- Este contrato no declara cobertura automática de obligaciones fiscales mexicanas ajenas al alcance V1.

## 2. Autoridades inspeccionadas antes de implementar

Se inspeccionaron las autoridades siguientes; ninguna debe reconstruirse:

| Punto existente | Evidencia concreta | Integración identificada en el baseline anterior |
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

## 3. Implementación y operación

`accounting_period.py` contiene `FiscalYear`, `AccountingPeriod` y el único resolvedor temporal puro. La fecha civil declarada se conserva sin trasladarla a otra zona horaria. `accounting_period_repository.py` persiste el calendario de la entidad activa, los ejercicios y los meses, y valida que sus límites correspondan al dominio. Application sólo delega.

La migración versionada 4→5 crea las tres tablas temporales con respaldo previo, sin inventar inicio de actividades, estados históricos ni correspondencias de IDs. Las bases anteriores siguen siendo legibles. Para habilitar posting, `configure_accounting_calendar` requiere inicio efectivo explícito y, si hay historia, estados de cada ejercicio y de todos sus meses utilizables. Un `period_id` legado incompatible requiere una correspondencia explícita por asiento; la declaración conserva el ID anterior. No se cambian importes ni fechas. El inicio declarado y los ejercicios existentes no se reabren ni redefinen implícitamente.

`open_accounting_year` crea la partición mensual completa; `close_accounting_period` bloquea el mes. `_stage_entry_in_session` y la validación de persistencia usan el mismo resolvedor. Los wrappers ordinarios, fiscalizados, de adquisición y depreciación conservan sus transacciones; un rechazo temporal no deja asiento ni metadatos parciales.

`close_accounting_year(year)` exige ejercicio explícito y diciembre abierto. Se debe ejecutar el cierre anual antes del cierre mensual de diciembre: nunca se reabre un período cerrado para introducir ajustes. El cierre reutiliza respaldo, motor SQLite de saldos, clasificación canónica (incluidas extensiones), cálculo de resultado y staging canónico. Cancela ingresos/costos/gastos del ejercicio y lleva su resultado a 3104; registra asiento y cierre de todos los meses/ejercicio en una transacción. Repetirlo no duplica el efecto. Un ejercicio sin movimientos puede cerrarse sin inventar un asiento.

`get_accounting_period_balances` y `get_accounting_range_balances` componen saldos iniciales, movimientos y finales mediante el motor existente. Son lecturas reproducibles por fecha y no generan estructura temporal.

## 4. Evidencia de aceptación

`tests/test_aqr002_accounting_periods.py` cubre 24 casos: primer ejercicio corto y febrero bisiesto; fronteras y pertenencia única; fechas anteriores al inicio y ejercicios no abiertos; período ausente, duplicado, cerrado o contradictorio; cierre posterior a preparación; todas las rutas atómicas; consultas históricas y rangos arbitrarios; fecha civil con offset; cierre 200−150=50, pérdida, año vacío y cuentas particulares; repetición sin duplicado; rechazo de diciembre cerrado; rollback del cierre; migración sin inferencias, correspondencias históricas explícitas y esquema incompleto rechazado; protección ORM ante traslado fuera de mes cerrado.

Los tests de integración anteriores declaran sus calendarios mediante APIs reales; no se desactiva ni simula la validación temporal. Las pruebas históricas de migración conservan sus datos y ahora verifican el destino v5 y el respaldo cuando corresponde. La prueba de delegación del cierre usa staging real, necesario para que asiento y cierre se confirmen juntos.

La aceptación técnica exige suite completa verde por el impacto transversal. La revisión profesional reproducible es el cierre V1-10: ingreso 200, gasto 150, cancelación de ambas cuentas y resultado acumulado 50, conservando historia. La experiencia gráfica y su prueba humana continúan en AQR-005; esta tarea entrega dominio y Application, sin declarar una interfaz productiva inexistente.
