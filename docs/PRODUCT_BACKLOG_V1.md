# AQORATH — PRODUCT BACKLOG V1

## Propósito

Este documento responde una sola pregunta:

> **¿Qué falta para que Aqorath cumpla su misión de producto?**

No es una lista de fases técnicas. Es un backlog finito de **capacidades de producto**, ordenadas por dependencia y valor.

Los identificadores `AQR-###` son estables. Los detalles internos pueden resolverse en varios commits, pero no deben multiplicar artificialmente el roadmap.

Estados permitidos:

- `NEXT` — única tarea que debe continuarse ahora.
- `TODO` — pendiente, no iniciar antes de las dependencias previas.
- `DONE` — incorporada a `main` y aceptada.
- `DEFERRED` — decisión explícitamente pospuesta o fuera de V1.

Debe existir exactamente **un `NEXT`**.

---

# BASELINE YA CONSEGUIDO

El backlog parte del baseline de runtime incorporado mediante PR #30 y auditado en `docs/REPO_AUDIT_V2.md`.

No volver a tratar como tareas nuevas, salvo defecto probado:

- exactitud monetaria y semántica de saldos;
- partida doble y validación estructural en persistencia;
- autoridad SQLite local;
- catálogo gobernado y extensible;
- migraciones, integridad, backup y restore de infraestructura;
- EconomicFact/EconomicEvent, resolución, confirmación y posting existentes;
- flujos contables ya cubiertos de crédito, cobro, pago y gastos;
- estados financieros y exportaciones existentes;
- arquitectura fiscal versionada y posting fiscalizado con auditoría;
- entidad, perfiles, terceros, documentos, metadatos CFDI y dimensiones;
- Program y Donation como fundamentos;
- explicabilidad y estado pedagógico;
- activos fijos, adquisición y depreciación;
- cierre de ejercicio y endurecimiento de persistencia.

---

# TAREAS

## AQR-001 — Matriz de aceptación del producto V1

**Estado:** `DONE`

### Aceptación

Contrato único: [PRODUCT_ACCEPTANCE_V1.md](PRODUCT_ACCEPTANCE_V1.md), incorporado por [PR #31](https://github.com/kagenomusuko-svg/aqorath/pull/31) en `bff58de7cad11de6c2ab37c0d3e0b7b6c20ae003` el 2026-09-09, con autorización expresa del usuario.

Diff completo revisado: sólo matriz y enlace de continuidad; 22 fichas, campos de aceptación y límites explícitos. CI del head `049656de46d8a5cc4f479ce5c07c8960be3b7474`: **1912 passed, 8 warnings**, [run 34381734672](https://github.com/kagenomusuko-svg/aqorath/actions/runs/34381734672). El árbol del merge coincide con el head revisado. No cambia runtime ni declara completados los flujos futuros de la matriz.

### Resultado de producto

Definir de forma verificable qué significa “Aqorath V1 funciona” para cada nicho soportado, evitando que el proyecto siga creciendo por acumulación de módulos sin una frontera de terminación.

### Trabajo

Crear una matriz única de operaciones de usuario y clasificarlas como:

- soportada de extremo a extremo;
- fundamento implementado pero flujo incompleto;
- pendiente;
- fuera de V1.

La matriz debe incluir como mínimo:

- venta/cobro al contado;
- venta a crédito y cobranza parcial/total;
- compra/gasto al contado;
- compra a crédito y pago parcial/total;
- movimientos entre cuentas propias;
- donativo monetario;
- adquisición y depreciación de activo fijo;
- cierre de ejercicio;
- consulta de póliza/diario/mayor/balanza;
- estados financieros;
- CFDI como documento fuente;
- tratamiento fiscal declarado como soportado;
- programa/dimensión/fuente de recursos para OSC;
- backup/restore;
- exportación/migración de datos.

Para cada flujo se debe declarar:

- hecho económico que introduce el usuario común;
- resultado contable profesional esperado;
- evidencia/documentos vinculados;
- explicación que Aqorath debe poder proporcionar;
- pruebas técnicas existentes o faltantes;
- prueba humana mínima;
- límites explícitos.

### Criterio de aceptación

Existe en el repositorio una matriz V1 única y suficientemente concreta para que un desarrollador pueda responder “¿esta operación forma parte de V1?” sin consultar una conversación.

No se requiere implementar las capacidades faltantes dentro de AQR-001; se requiere **congelar el contrato de producto**.

### Dependencias

Ninguna. Es el próximo paso porque gobierna el alcance de todas las tareas posteriores.

---

## AQR-002 — Períodos contables y ejercicio fiscal como autoridades de dominio

**Estado:** `DONE`

### Decisión de producto aprobada

Alternativa A aprobada el 2026-09-09: ejercicio enero–diciembre, meses calendario exclusivos, primer ejercicio corto desde inicio efectivo, períodos cerrados bloqueantes y rangos arbitrarios sólo para reportes. Una sola autoridad temporal; sin calendarios personalizados V1 ni reinterpretación histórica. Contrato y evidencia: [AQR_002_PERIOD_DECISION.md](AQR_002_PERIOD_DECISION.md). Incorporada mediante [PR #33](https://github.com/kagenomusuko-svg/aqorath/pull/33), merge `bc41cffcbc192bbf179e7eb28ea137521f079526`. Árbol de main idéntico al head revisado `f0f55d9bcd6d40112dea395e896d4f3cc5554326`; suite completa local: **1936 passed, 8 warnings**. [CI del PR](https://github.com/kagenomusuko-svg/aqorath/actions/runs/34385801594) verde. Diff completo revisado, 24 casos nuevos, sin regresión conocida ni modificación constitucional. Auditoría V2 actualizada por el cambio material.

### Resultado de producto

Aqorath sabe a qué período pertenece cada operación y puede impedir contabilizar en períodos cerrados.

### Fundación existente

`trial_balance(as_of=...)`, reporting por fecha, migraciones y `exercise.py` ya proporcionan piezas del problema; no deben reescribirse sin necesidad.

### Trabajo

Incorporar `AccountingPeriod` y `FiscalYear` como conceptos explícitos con apertura, cierre y estado. Integrar la fecha de posting con la resolución de período. Formalizar la relación entre cierre de período y cierre anual.

### Criterio de aceptación

- una operación sólo puede consolidarse en un período válido y abierto;
- un período cerrado rechaza nuevos postings;
- el cierre anual usa las mismas autoridades contables existentes;
- consultas históricas son reproducibles por período;
- existen pruebas E2E de cambio de período y cierre.

### Dependencia

AQR-001.

---

## AQR-003 — Inmutabilidad de pólizas consolidadas y correcciones por reversión

**Estado:** `DONE`

### Aceptación

PR #35 incorporó la base de estados `draft / posted / reversed`, reversión balanceada y relación uno-a-uno. La revisión de cierre reprodujo dos omisiones: edición balanceada de líneas `posted` y reversión sin `AuditEvent`. PR #36 las corrigió sobre los listeners, staging y repositorio de auditoría existentes; protege cabecera, líneas, identidad y estado `reversed`, exige motivo, prueba rollback aun si el llamador captura el error y compone la corrección 150→120 como original + reversión + sustituto + dos eventos.

La decisión [AQR_003_CLOSED_YEAR_DECISION.md](AQR_003_CLOSED_YEAR_DECISION.md) aprobó la alternativa 2: una operación perteneciente a un ejercicio cerrado no se revierte y sustituye automáticamente usando las cuentas originales en un ejercicio posterior. Esas correcciones quedan bloqueadas preventivamente; en ejercicios abiertos siguen disponibles mediante la misma autoridad de período. La futura política de errores de ejercicios anteriores es una decisión contable separada, no se convirtió en `NEXT` y no bloquea AQR-004.

PR #36 fue incorporado en `63e321fececb301eaa1337baff7ebe4acb07682a`; su head revisado `84cbc947259da62c03c5c5546d6699d542e2a479` tuvo CI verde en run 34393029104. La suite completa local registrada por la rama fue **1944 passed, 8 warnings**. La comparación del head con el merge mostró cero diferencias de archivos.

### Resultado de producto

Una póliza consolidada no se “edita para que cuadre”. Los errores se corrigen mediante operaciones contables trazables.

### Trabajo

Formalizar estados `draft / posted / reversed` y las transiciones permitidas; prohibir modificación o borrado silencioso de pólizas posted; implementar reversión/corrección con referencia al asiento original y AuditEvent.

### Criterio de aceptación

- posted es inmutable;
- reversal genera una operación balanceada vinculada al original;
- historial permite reconstruir qué se corrigió y por qué;
- reportes reflejan reversión sin destruir historia.

### Dependencia

AQR-002.

---

## AQR-004 — Caso de uso unificado: hecho económico → decisión → consentimiento → posting → auditoría

**Estado:** `DONE`

### Aceptación

Contrato: [AQR_004_UNIFIED_USE_CASE.md](AQR_004_UNIFIED_USE_CASE.md). PR #37 incorporó un caso de uso Application que compone, sin reescribir, provenance del hecho, bindings persistidos, resolución de cuentas, explicación estructurada, confirmación, `PostingInstruction`, staging canónico, autoridad de período e `AuditEvent`.

La operación ordinaria recibe `EconomicFact` + fecha; la presentación no suministra Debe/Haber, códigos ni SQLModel. Preparar no escribe; confirmar conserva exactamente el snapshot presentado; ejecutar revalida período dentro del staging y confirma una póliza `posted` y un `entry_posted` en una sola transacción. El evento conserva hecho, fecha, `rule_id`, `rule_version`, consentimiento y explicación estructurada; las cuentas/importes efectivamente consolidados permanecen en el ledger, evitando un shadow ledger. La póliza resultante hereda las invariantes de AQR-003.

La fiscalidad no se infiere silenciosamente: una verdad fiscalizada ya confirmada delega en `fiscalized_posting_persistence.py` y su auditoría vigente. La selección de cobertura/aplicabilidad V1 continúa en AQR-010/AQR-011.

PR #37 fue incorporado en `fe99ce06f334f8a12d37146f4504e78f497b18ca`; head revisado `f6a268b43dd7b600201a7dfe5501ee804a8d8926`, CI verde run 34394126158. La comparación del head con el merge mostró cero diferencias de archivos. Ocho pruebas AQR-004 nuevas cubren preparación sin códigos, consentimiento exacto, posting+audit recuperable, revalidación de período, rollback ante fallo de auditoría, inmutabilidad AQR-003, ausencia de escritura durante preparación y delegación fiscalizada.

### Resultado de producto

Una superficie de presentación puede enviar un hecho económico a **un único caso de uso** y recibir todo lo necesario para operar sin conocer las autoridades internas.

### Fundación existente

Ya existen hechos económicos, resolución, account bindings, explicaciones, confirmaciones, tratamiento fiscal, posting y auditoría. Esta tarea es de **orquestación y contrato**, no de reconstrucción.

### Trabajo

Componer las autoridades actuales en un flujo Application estable que produzca:

1. interpretación del hecho;
2. propuesta contable/fiscal;
3. explicación estructurada;
4. confirmación cuando corresponda;
5. posting canónico;
6. evidencia/auditoría recuperable.

Formalizar qué información de la `AccountingDecision` debe persistirse y cuál puede reconstruirse determinísticamente.

### Criterio de aceptación

Una operación ordinaria completa puede ejecutarse desde una API de aplicación sin que el adaptador de presentación conozca Debe/Haber, códigos de cuentas, SQLModel o reglas fiscales internas.

### Dependencias

AQR-002 y AQR-003.

---

## AQR-005 — Superficie de presentación V1: vista común + vista profesional

**Estado:** `DONE`

### Aceptación

Decisión arquitectónica: [AQR_005_SURFACE_DECISION.md](AQR_005_SURFACE_DECISION.md). Operación local: [AQR_005_LOCAL_SURFACE.md](AQR_005_LOCAL_SURFACE.md). PR #39 fue incorporado en `97604e1e887129cd4ded484f1e170c10396ea980`; head definitivo revisado `d0c10b4003c23c63be223752f3db4dea8da5cba2`, CI verde [run 34397980985](https://github.com/kagenomusuko-svg/aqorath/actions/runs/34397980985). El merge y el head revisado comparten exactamente el tree `d9d41cd0989f588256b46d1b1f40d1b9a0a3545e`.

La superficie V1 es web local estrictamente loopback. FastAPI es sólo adaptador; el controlador conserva únicamente previews efímeros; `surface_application.py` delega preparación/confirmación/posting a AQR-004 y consultas a autoridades Application; el read-model profesional consume directamente ledger, período, documentos, reversión y auditoría sin una segunda persistencia ni índice paralelo. La vista común sólo solicita hecho económico, importe y fecha; la profesional inspecciona la misma póliza, sus cuentas, período, referencias, fiscalidad y trazabilidad. Las pruebas cubren ausencia de escritura en prepare/cancel, consentimiento exacto, equivalencia common/professional, ledger+AuditEvent real, período cerrado heredado de AQR-002, índice reciente respaldado por `JournalEntry`, aislamiento del framework y binding sólo a `127.0.0.1`.

### Resultado de producto

Aqorath deja de ser sólo un motor probado y se vuelve utilizable por su usuario objetivo.

### Estado actual

Existe una superficie productiva local nueva; los PR antiguos de PySide y los assets históricos `templates/`/`static/` permanecen supersedidos y no son autoridad.

### Trabajo

Elegir e implementar una superficie local compatible con R6/R8. Debe consumir exclusivamente `application.py`/casos de uso canónicos.

Dos vistas sobre la misma verdad:

- **Común:** captura hechos económicos en lenguaje cotidiano; no solicita Debe/Haber ni códigos contables.
- **Profesional:** pólizas, cuentas, cargos/abonos, auxiliares, referencias, períodos, fiscalidad y trazabilidad.

### Criterio de aceptación

La misma operación ingresada desde la vista común puede revisarse en la profesional sin diferencias sustantivas; una persona no contadora puede completar los flujos V1 definidos en AQR-001 conforme esos casos de uso están implementados.

### Dependencia

AQR-004.

---

## AQR-006 — Cuentas por cobrar y pagar como submayores operativos

**Estado:** `DONE`

### Aceptación

Incorporada mediante PR #41, merge `6617896f1bfe56093697be08f1a996db55930ab6`, tras CI verde sobre el head revisado `5291c63636e0eb3a97581f0048073c6f7e1a739c`.

La implementación conserva `JournalLine` como única autoridad monetaria y añade sólo relaciones line-granulares `OpenItem`/`OpenItemApplication`. Schema 7 crea ambas tablas sin backfill; la fixture histórica schema 6 está congelada en DDL independiente del metadata runtime. Las pruebas cubren origen, aplicaciones parciales/totales, batch multiobligación, vencimiento/aging derivado, reversión temporal, reconciliación fail-closed, divergencias históricas y atomicidad en todas las fronteras.

Verificación: suite específica AQR-002–006 con **80 passed**; suite completa Python 3.12 con **1993 passed, 8 warnings**.

### Resultado de producto

Aqorath no sólo contabiliza una venta/compra a crédito: sabe **qué saldo concreto sigue abierto con qué tercero**.

### Fundación existente

Los flujos contables de crédito, cobro y pago ya tienen cobertura E2E, y `ThirdParty` existe.

### Trabajo

Modelar documentos/open items, fecha de vencimiento, saldo pendiente, aplicaciones parciales, liquidación, cancelación/reversión y antigüedad de saldos. Vincular todo a ThirdParty y a las pólizas reales, sin contabilidad paralela.

### Criterio de aceptación

Aqorath puede responder de forma reproducible cuánto debe cada cliente, cuánto se debe a cada proveedor, qué partidas integran el saldo y cómo se liquidaron. Todo saldo CxC/CxP debe ser explicable y reconciliable con el ledger canónico; una divergencia no puede quedar silenciosa.

### Dependencia

AQR-004.

---

## AQR-007 — Bancos y conciliación

**Estado:** `DONE`

### Resultado de producto

Las cuentas bancarias reales pueden administrarse y conciliarse contra el ledger sin convertirse en una segunda fuente contable.

### Trabajo

Implementar `BankAccount`, relación con cuenta contable, importación de estados/movimientos, matching, conciliación, partidas pendientes y cierre de conciliación.

### Cierre de aceptación

Implementado y fusionado en `main` mediante PR #42 (`9117ac085e00e813bb2d5ae30267eb4184d181a6`), con head validado `5c6453a3840774b71a6bfd5892696c8d4cc064af`. La suite Python 3.12 quedó en **2002 passed, 8 warnings**. La evidencia bancaria permanece separada del ledger canónico; matching, diferencias, pendientes, reversión de relaciones y transferencias entre cuentas propias no crean una autoridad monetaria paralela.

### Criterio de aceptación

Para una fecha determinada Aqorath puede demostrar la reconciliación entre saldo bancario y saldo contable, identificando diferencias y partidas en tránsito.

### Dependencias

AQR-003 y AQR-006 cuando el movimiento involucre terceros.

---

## AQR-008 — Recursos OSC: fondos, fuentes, restricciones y aplicación

**Estado:** `DONE`

### Resultado de producto

Una OSC puede demostrar de dónde vino un recurso, bajo qué restricción se recibió y en qué programa/actividad se aplicó, sin duplicar la contabilidad.

### Fundación existente

`Program`, `Donation` y dimensiones analíticas ya existen como fundamentos.

### Trabajo

Implementar `Fund` y `FundingSource`; formalizar recursos restringidos/no restringidos, destino, vigencia y aplicación. Conectar Program, dimensiones y líneas del ledger.

### Cierre de aceptación

Implementado y fusionado mediante PR #43, merge `13133edfd9ed5015f6cb7bfdccbd8f1fc2515a27`, head validado `4ce5fc3e137426fa3923d007c8d5597a912ec574`. Schema 9 es aditivo; la suite Python 3.12 quedó en **2008 passed, 8 warnings**. La trazabilidad de fondos se deriva de `JournalLine`, con provenance canónica, disponibilidad efectiva, reversiones, migración histórica 8→9 y superficie común/profesional; no existe saldo ni ledger paralelo.

### Criterio de aceptación

Desde un recurso recibido se puede recorrer trazabilidad hasta su aplicación y generar un reporte por programa/fondo/fuente que reconcilie exactamente con el ledger general.

### Dependencias

AQR-004 y AQR-013 para la presentación documental final.

---

## AQR-009 — Donativos completos, incluido donativo en especie

**Estado:** `DONE`

### Resultado de producto

Donation deja de ser sólo un fundamento de dominio y se convierte en un flujo OSC completo.

### Trabajo

Vincular donante (`ThirdParty`), documento fuente, restricción/fondo/programa, tratamiento contable y fiscal. Incorporar `InKindDonation` con metodología de valuación, evidencia y reconocimiento contable.

### Criterio de aceptación

Un donativo monetario o en especie puede registrarse desde el hecho, producir su contabilidad, conservar evidencia y aparecer en reportes OSC sin captura redundante.

### Dependencia

AQR-008.

### Cierre de aceptación

Implementado y fusionado mediante PR #44, merge `e3c8cd1f76ec2157c752a245efa74f3711526ffa`, head validado `1f209cd6b1f56e74f57a325942078491c0a4de31`. El tree fusionado coincide con el revisado (`40c1f81749d7ad6689e53564f851acb2c76ef152`); CI remoto quedó verde sobre el head definitivo y la suite completa Python 3.12 registró **2022 passed, 8 warnings**. Los recorridos monetario y en especie son atómicos, idempotentes y reversibles; componen las autoridades de ledger, donante, documento, fondo/programa, activo y auditoría sin duplicar importes, inventar efectivo ni exceder la cobertura fiscal declarada. La superficie común prepara/cancela sin escribir y confirma el snapshot exacto; la profesional reconstruye la misma verdad persistida.

---

## AQR-010 — CFDI como documento fuente verificable

**Estado:** `DONE`

### Resultado de producto

Aqorath puede importar un CFDI real, extraer su verdad documental y utilizarla sin volver a pedir datos ya conocidos.

### Fundación existente

`DocumentReference`, `CfdiImportMetadata`, arquitectura fiscal y scripts/documentación histórica de XSD ya existen parcialmente.

### Trabajo

Implementar ingestión XML, extracción determinística de UUID/RFC/fechas/importes/impuestos, deduplicación, validaciones estructurales aplicables y vínculo con ThirdParty/EconomicEvent/AccountingDecision.

El timbrado/emisión NO forma parte de esta tarea.

### Criterio de aceptación

Importar dos veces el mismo UUID no duplica verdad; los datos extraídos son reproducibles; el XML queda trazablemente vinculado a la operación y los importes fiscales relevantes se contrastan contra el tratamiento de Aqorath.

### Dependencia

AQR-004.

### Cierre de aceptación

Implementado y fusionado mediante PR #45, merge `6517b303c48d7d38eef01003dad487f676c5c2e7`, head validado `83c0a058337b2345a7134a9a72a8472e980abb52`. El tree fusionado coincide exactamente con el revisado (`54afbbe94bf577749ac5dfadbc956e448c0463de`); CI remoto run 458 quedó verde y la suite completa Python 3.12 registró **2060 passed, 8 warnings**. Schema 11 incorpora evidencia CFDI aditiva sin backfill; XML, hash, UUID, RFC, fechas, importes e impuestos se preservan exactamente. La posición documental no se confunde con la clasificación económica, importar no contabiliza y el enlace confirmado reutiliza `JournalEntry`/`JournalLine`, `ThirdParty`, un único `DocumentReference` y auditoría. El donativo monetario respaldado por CFDI compone AQR-009 en un solo commit, con rollback e idempotencia cruzada, sin duplicar póliza/documento ni inferir tratamiento fiscal.

---

## AQR-011 — Cobertura fiscal V1 declarada y versionada

**Estado:** `NEXT`

### Resultado de producto

Aqorath declara exactamente qué casos fiscales mexicanos soporta y puede defender el cálculo por vigencia, en lugar de sugerir una cobertura fiscal genérica.

### Fundación existente

FiscalRuleSet, registry, datos versionados, aplicabilidad, cálculo, redondeo, confirmación, efectos y auditoría ya existen.

### Trabajo

A partir de AQR-001, completar únicamente los regímenes/obligaciones requeridos por el nicho V1; documentar fecha de vigencia, fuentes normativas y casos fuera de soporte. Incorporar reportes/cédulas necesarios.

### Criterio de aceptación

Cada tratamiento fiscal soportado tiene regla versionada, prueba con fecha, explicación y resultado profesionalmente revisable. Lo no soportado falla explícitamente.

### Dependencias

AQR-001 y AQR-010 para flujos CFDI.

---

## AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera

**Estado:** `TODO`

### Resultado de producto

Pequeños negocios del nicho que manejan mercancías pueden controlar existencias y costo sin romper la autoridad contable.

### Trabajo

Definir producto/ítem, entradas, salidas, existencia, método de costo explícitamente elegido, costo de venta y asientos resultantes. Activarlo por capacidades del EntityProfile, no como segundo motor.

### Criterio de aceptación

Existencia, valuación y costo de venta se reconcilian con el ledger y son reproducibles para los métodos declarados como soportados.

### Dependencia

AQR-001. Si la matriz V1 excluye inventario, esta tarea pasa a `DEFERRED` en vez de implementarse por inercia.

---

## AQR-013 — Motor de documentos, paquetes y reportes de producto

**Estado:** `TODO`

### Resultado de producto

Las fundaciones de ReportDefinition/ReportRequest/Package se convierten en un sistema de documentos reutilizable para contabilidad, fiscalidad y OSC.

### Fundación existente

ReportDefinition, ReportRequest, ReportPackage, CustomReportPackage, aplicabilidad y exportaciones financieras ya existen parcialmente.

### Trabajo

Completar catálogo de reportes V1, persistencia/selección cuando corresponda, paquetes como presets editables, filtros/dimensiones, formatos y metadatos de generación. Incluir reportes OSC derivados de AQR-008/009 y fiscales de AQR-011.

### Criterio de aceptación

Un mismo ReportDefinition puede generarse repetidamente con parámetros distintos; un paquete nunca bloquea personalización; los totales reconcilian con la fuente contable.

### Dependencias

AQR-008, AQR-009 y AQR-011 para sus reportes especializados.

---

## AQR-014 — Backup, restore, integridad y portabilidad como flujo de usuario

**Estado:** `TODO`

### Resultado de producto

La seguridad local ya existente a nivel de infraestructura se vuelve una capacidad operable por el usuario.

### Fundación existente

`migrations.py` ya centraliza migración, backup, restore e integridad; `exercise.py` realiza respaldo antes del cierre.

### Trabajo

Exponer backup manual, política de backup automático antes de operaciones destructivas, restore validado, comprobación de integridad, exportación portable y documentación de recuperación.

### Criterio de aceptación

En una instalación limpia se puede crear un backup, destruir/reemplazar la DB de prueba, restaurarlo y obtener exactamente los mismos saldos, entidades, documentos y relaciones soportadas.

### Dependencia

AQR-005 para la experiencia final; la autoridad de infraestructura no debe duplicarse.

---

## AQR-015 — Empaquetado, instalación y aceptación V1

**Estado:** `TODO`

### Resultado de producto

Aqorath puede instalarse y utilizarse como producto local, no sólo ejecutarse como repositorio de desarrollo.

### Trabajo

- empaquetado/release reproducible;
- inicialización y migración de DB en instalación limpia;
- actualización entre versiones soportadas;
- funcionamiento sin Internet;
- smoke tests de instalación;
- pruebas de los flujos de AQR-001 en superficie común y profesional;
- revisión profesional de resultados contables/fiscales declarados;
- documentación de límites y recuperación;
- exportación suficiente para migrar fuera de Aqorath.

### Criterio de aceptación

La matriz AQR-001 queda completamente en estado soportado o explícitamente fuera de V1; las pruebas técnicas están verdes; la prueba profesional y la prueba humana tienen evidencia reproducible; no existen bloqueadores críticos conocidos.

### Dependencias

Todas las tareas incluidas finalmente en el alcance V1.

---

# DECISIONES EXPLÍCITAMENTE POSPUESTAS

Estas materias no deben aparecer como “siguiente paso” sin decisión nueva:

- **CFDI emisión/timbrado propio:** `DEFERRED` hasta completar importación, tratamiento fiscal y necesidad de producto.
- **Multimoneda:** `DEFERRED` hasta que AQR-001 demuestre que el nicho V1 la necesita.
- **Nómina:** `DEFERRED` salvo incorporación explícita al alcance V1.
- **Licencia definitiva / modelo de licencia social:** `DEFERRED`, conforme a R28.
- **Multiusuario / RBAC empresarial:** no es backlog; está fuera de arquitectura mientras R8 permanezca vigente.
- **Multiempresa simultánea:** no es backlog; está prohibida por R9 mientras la Constitución no cambie.
- **Errores de ejercicios anteriores ya cerrados:** la corrección automática sobre cuentas originales está bloqueada por AQR-003. La política sustitutiva permanece pendiente de una decisión contable futura y no desplaza el `NEXT` mientras el backlog pueda continuar con casos válidos definidos.

---

# REGLA DE ACTUALIZACIÓN

Al completar una tarea:

1. cambiar su estado a `DONE`;
2. registrar en su sección el commit/PR de aceptación;
3. seleccionar exactamente una tarea elegible y cambiarla a `NEXT`;
4. no renumerar IDs;
5. no insertar una tarea nueva entre medias salvo que se haya demostrado una capacidad de producto indispensable que este backlog omitió;
6. si aparece deuda puramente interna, resolverla dentro de la tarea que la necesita o registrarla como issue técnico; no convertir automáticamente cada refactor en una nueva etapa del roadmap.

## SIGUIENTE ACTUAL

`AQR-011 — Cobertura fiscal V1 declarada y versionada`.
