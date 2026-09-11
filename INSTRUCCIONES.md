# INSTRUCCIONES — CONTINUIDAD CANÓNICA DE AQORATH

## 1. Propósito

Este archivo es la **primera lectura obligatoria** para cualquier trabajo futuro sobre Aqorath.

Su función es impedir que una conversación nueva tenga que reconstruir el proyecto desde chats anteriores, reabrir fases ya resueltas o inferir el siguiente paso a partir de PR históricos.

El repositorio es la autoridad. La memoria de conversaciones no sustituye estos documentos.

---

## 2. Orden de autoridad

Cuando dos fuentes parezcan contradecirse, usar este orden:

1. `docs/AQORATH_CONSTITUTION_V1.md` — reglas normativas y atemporales: qué **debe ser** Aqorath.
2. `INSTRUCCIONES.md` — protocolo de ejecución y continuidad.
3. `docs/PRODUCT_BACKLOG_V1.md` — tareas de producto pendientes, ordenadas y con estado.
4. `docs/REPO_AUDIT_V2.md` — corte verificable del estado actual y de las capacidades ya existentes.
5. `docs/ARCHITECTURE_BASELINE_V1.md` — arquitectura objetivo y modelo conceptual de referencia.
6. Documentos especializados (`CATALOG_POLICY.md`, `CFDI.md`, etc.) — autoridad sólo dentro de su materia y siempre subordinados a las fuentes anteriores.
7. PR, issues, ramas antiguas y documentos históricos — **evidencia histórica, nunca autoridad de continuidad**.

`docs/REPO_AUDIT_V1.md` es histórico y está supersedido por V2.

---

## 3. Norte del producto

> **Aqorath pregunta hechos; Aqorath resuelve contabilidad.**

Aqorath debe convertirse en un ERP contable profesional, local-first, explicable, monousuario y monoentidad para autoempleados, microactividades, pequeños negocios, asociaciones civiles, OSC y donatarias dentro del nicho declarado.

La simplicidad pertenece a la interacción, no al rigor contable.

El usuario común describe hechos económicos. Aqorath determina de manera determinística la representación contable y fiscal, puede explicarla antes o después de consolidarla y conserva una única verdad contable auditable.

La vista común y la vista profesional son dos superficies sobre el **mismo motor, los mismos casos de uso y la misma persistencia**.

---

## 4. Corte técnico validado

### Baseline de runtime histórico — PR #30

- `main` incorporó PR #30 — **Phase 6BP persistence hardening**.
- Merge de runtime revisado: `7623e4eb0636064cdab0582ce3c98e7b9c844e93`.
- Head probado antes del merge: `7dbef85bcdd4157106c3779356303c9271dc56bb`.
- Última suite completa asociada a ese corte: **1912 passed, 0 failed**.
- No existe, al cierre de la auditoría del 2026-09-09, un P0 conocido que obligue a reabrir los fundamentos ya validados.

### Runtime vigente — AQR-002 a AQR-012

AQR-002 quedó incorporada por PR #33 y establece la única autoridad de período/calendario; contrato `docs/AQR_002_PERIOD_DECISION.md`.

AQR-003 quedó aceptada mediante PR #36, merge `63e321fececb301eaa1337baff7ebe4acb07682a`, head revisado `84cbc947259da62c03c5c5546d6699d542e2a479`, CI verde run 34393029104. La rama registró suite completa local **1944 passed, 8 warnings**. Corrige edición balanceada de líneas posted, hace atómica reversión + `AuditEvent`, protege `reversed`/identidades y aplica la decisión aprobada de `docs/AQR_003_CLOSED_YEAR_DECISION.md`: ejercicios cerrados bloquean corrección automática con cuentas originales; ejercicios abiertos conservan la ruta canónica. Esquema actual 6.

AQR-004 quedó incorporada mediante PR #37, merge `fe99ce06f334f8a12d37146f4504e78f497b18ca`, head revisado `f6a268b43dd7b600201a7dfe5501ee804a8d8926`, CI verde run 34394126158. `accounting_operation.py` compone hecho → decisión → consentimiento → posting → auditoría; `accounting_operation_persistence.py` reutiliza `core._stage_entry_in_session`, revalida período y confirma `JournalEntry.state='posted'` + `AuditEvent` en una sola transacción. La ejecución fiscalizada delega en las autoridades fiscalizadas existentes. Contrato: `docs/AQR_004_UNIFIED_USE_CASE.md`.

AQR-005 quedó incorporada mediante PR #39, merge `97604e1e887129cd4ded484f1e170c10396ea980`, head revisado `d0c10b4003c23c63be223752f3db4dea8da5cba2`, CI verde run 34397980985. El tree del merge y del head revisado coincide exactamente en `d9d41cd0989f588256b46d1b1f40d1b9a0a3545e`. La decisión `docs/AQR_005_SURFACE_DECISION.md` deriva una superficie web local estrictamente loopback: FastAPI permanece como adaptador delgado, `presentation_controller.py` conserva sólo previews efímeros, `surface_application.py` delega en AQR-004 y autoridades Application, y `accounting_operation_read.py` proyecta directamente ledger/período/documentos/reversión/auditoría sin una persistencia o índice paralelo. La vista común solicita únicamente hecho, importe y fecha; la profesional inspecciona la misma verdad persistida. Operación: `docs/AQR_005_LOCAL_SURFACE.md`.

Las comparaciones de los heads revisados de PR #36/#37 y el tree verificado de PR #39 contra sus merges no mostraron diferencias materiales del contenido aceptado.

Los commits exclusivamente documentales posteriores pueden avanzar main sin cambiar este corte de runtime.

### Fundamentos que NO deben reconstruirse sin evidencia de defecto

Ya existe base funcional y pruebas para, entre otros:

- dinero exacto y semántica de saldos;
- catálogo canónico gobernado + extensiones particulares;
- SQLite como autoridad contable local;
- validación de cuentas y partida doble en la frontera de persistencia;
- migraciones versionadas, integridad, backup y restore;
- hechos económicos, resolución semántica, bindings, confirmación y posting;
- caso de uso ordinario unificado con decisión, explicación, consentimiento, posting `posted` y auditoría atómica;
- superficie local común + profesional sobre los mismos casos de uso y persistencia;
- cuentas por cobrar/pagar en los flujos contables ya cubiertos;
- estados financieros y exportación CSV/XLSX/PDF;
- reglas fiscales versionadas, cálculo, confirmación, composición, posting fiscalizado y auditoría;
- Entity / EntityProfile / FiscalProfile;
- ThirdParty;
- DocumentReference y metadatos de importación CFDI;
- dimensiones analíticas;
- Program y Donation como fundamentos de dominio;
- explicabilidad estructurada y progresividad pedagógica;
- activos fijos, adquisición, depreciación y estado en libros;
- períodos, cierre de ejercicio y corrección por reversión sobre ejercicios abiertos;
- inmutabilidad append-only de pólizas consolidadas.

“Fundamento existente” no significa “capacidad de producto completa”. El backlog distingue ambas cosas.

---

## 5. Regla de continuidad

No se utilizarán nuevas “fases” como mecanismo principal de planificación.

Las etiquetas históricas `P0`, `P1`, `P2`, `Phase 6...`, etc. pueden permanecer en commits y tests como arqueología, pero **no determinan qué sigue**.

Desde este punto la continuidad se rige por identificadores estables `AQR-###` en `docs/PRODUCT_BACKLOG_V1.md`.

Siempre debe existir **exactamente una tarea marcada `NEXT`**.

El siguiente trabajo es la tarea `NEXT`, no la fase numéricamente posterior, no el PR abierto más antiguo y no una idea recuperada de un chat.

---

## 6. Protocolo para una conversación nueva

Antes de modificar código:

1. Leer íntegramente `docs/AQORATH_CONSTITUTION_V1.md`.
2. Leer íntegramente `INSTRUCCIONES.md`.
3. Leer `docs/PRODUCT_BACKLOG_V1.md` y localizar la única tarea `NEXT`.
4. Leer `docs/REPO_AUDIT_V2.md` para saber qué ya existe y qué no.
5. Verificar el HEAD vigente de `main` y el estado de CI.
6. Inspeccionar implementación y tests relacionados con la tarea `NEXT` antes de diseñar nada nuevo.
7. Ejecutar trabajo efectivo sobre esa tarea hasta cumplir sus criterios de aceptación o encontrar una decisión humana genuina que bloquee el avance.

No pedir al usuario que resuma trabajo ya documentado en el repositorio.

---

## 7. Disciplina de implementación

Para cada `AQR-###`:

- conservar el ID estable durante todo el trabajo;
- usar una rama descriptiva, por ejemplo `aqr-002-accounting-periods`;
- los pasos internos pueden dividirse en commits, pero **no se convierten automáticamente en nuevas tareas de roadmap**;
- antes de crear una autoridad nueva, demostrar que la capacidad no existe ya;
- preferir composición sobre reescritura de autoridades validadas;
- no introducir fallbacks que oculten errores estructurales;
- no crear una segunda ruta de persistencia contable;
- no permitir que UI/API/CLI contengan reglas contables independientes;
- toda nueva persistencia debe respetar dinero exacto, integridad referencial, partida doble y migraciones explícitas;
- mantener tests de regresión para contratos existentes;
- cuando aplique, evaluar la función contra la prueba triple de la Constitución: técnica, profesional y humana.

---

## 8. Qué está prohibido reintroducir

Salvo decisión explícita que modifique la Constitución:

- selector binario “Comercial / OSC” como identidad de la entidad;
- múltiples motores o persistencias contables;
- Excel/Pandas/JSON como segunda fuente primaria de verdad;
- persistencia directa como fallback cuando falle la autoridad canónica;
- aceptar `account_code` huérfanos;
- dinero autoritativo en `float`;
- corregir silenciosamente inconsistencias;
- multiusuario/RBAC empresarial;
- depender de Internet para leer la contabilidad local;
- IA generativa como fuente de verdad de una explicación contable;
- editar el catálogo canónico mediante operaciones ordinarias del usuario.

---

## 9. PR y ramas históricas

Los PR históricos supersedidos no definen el estado actual. En particular, los antiguos PR #2, #11, #13, #14, #15, #16, #18 y #19 contienen supuestos de etapas anteriores y **no deben fusionarse sobre `main`**.

Su historial puede consultarse como arqueología. La continuidad está en este archivo y en el backlog.

---

## 10. Cierre de una tarea

Una tarea sólo pasa de `NEXT` a `DONE` cuando:

1. se cumplen sus criterios de aceptación;
2. la suite relevante está verde;
3. no se degrada una invariante constitucional;
4. el cambio está incorporado a `main`;
5. `docs/PRODUCT_BACKLOG_V1.md` se actualiza: la tarea terminada queda `DONE` y exactamente una tarea posterior pasa a `NEXT`;
6. `docs/REPO_AUDIT_V2.md` se actualiza sólo si cambió materialmente el estado arquitectónico o las capacidades disponibles.

---

## 11. SIGUIENTE

**`AQR-015 — Empaquetado, instalación y aceptación V1`**

AQR-006 quedó incorporada mediante PR #41, merge `6617896f1bfe56093697be08f1a996db55930ab6`, con CI verde y suite completa Python 3.12 de **1993 passed, 8 warnings**. Sus submayores operativos conservan `JournalLine` como única autoridad monetaria, sin backfill histórico, y su fixture schema 6 es independiente del metadata runtime.

AQR-007 quedó incorporada mediante PR #42, merge `9117ac085e00e813bb2d5ae30267eb4184d181a6`, con CI verde y suite completa Python 3.12 de **2002 passed, 8 warnings**. Su evidencia bancaria permanece separada del ledger canónico y la conciliación conserva diferencias, pendientes, auditoría y reversión sin backfill ni autoridad monetaria paralela.

AQR-008 quedó incorporada mediante PR #43, merge `13133edfd9ed5015f6cb7bfdccbd8f1fc2515a27`, con CI verde sobre head `4ce5fc3e137426fa3923d007c8d5597a912ec574` y suite completa Python 3.12 de **2008 passed, 8 warnings**. Sus fondos/fuentes y aplicaciones conservan `JournalLine` como única autoridad, exigen provenance canónica, derivan disponibilidad efectiva y exponen la misma verdad en vista común y profesional, sin saldo paralelo ni backfill.

AQR-009 quedó incorporada mediante PR #44, merge `e3c8cd1f76ec2157c752a245efa74f3711526ffa`, con CI verde sobre el head revisado `1f209cd6b1f56e74f57a325942078491c0a4de31` y suite completa Python 3.12 de **2022 passed, 8 warnings**. Sus donativos monetarios y en especie componen posting, evidencia, fondos, activos y auditoría en una sola transacción; conservan `JournalLine` como autoridad contable, derivan reversión e idempotencia y exponen recorridos común/profesional sin efectivo ficticio ni tratamiento fiscal inventado. El tree fusionado coincide exactamente con el revisado en `40c1f81749d7ad6689e53564f851acb2c76ef152`.

AQR-010 quedó incorporada mediante PR #45, merge `6517b303c48d7d38eef01003dad487f676c5c2e7`, head revisado `83c0a058337b2345a7134a9a72a8472e980abb52`, CI verde run 458 y suite completa Python 3.12 de **2060 passed, 8 warnings**. El tree fusionado coincide exactamente con el revisado en `54afbbe94bf577749ac5dfadbc956e448c0463de`. El CFDI XML se conserva como evidencia externa exacta y deduplicada; posición documental y clasificación económica son dimensiones separadas. Los vínculos a ledger/documento y el recorrido de donativo AQR-009 son atómicos e idempotentes, con un solo `DocumentReference`, sin ledger ni fiscalidad paralelos.

AQR-011 quedó incorporada mediante PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`, head revisado `527934106b6b852b67f51d4a708435c3e4897aec`, CI verde runs 498/499 y suite completa **2092 passed, 8 warnings**.

AQR-012 quedó incorporada mediante PR #48, merge `79d4ec06a6b5fe9e20b511284cfe105d21dddd40`, head revisado `bf74211975ce4ef19b0cf0243d6f315f8dbe5fd4`, CI verde runs 546/547 y suite completa **2125 passed, 8 warnings**. Inventario perpetuo/costo por promedio ponderado móvil conserva `JournalEntry`/`JournalLine` como autoridad monetaria, reconcilia stock/valuación/COGS, compone crédito/CFDI/fiscalidad/reversión sin duplicar autoridades y expone superficies común/profesional sobre la misma verdad.

AQR-013 quedó incorporada mediante PR #51, merge `46bf21f61dd2d3e1cbadfa681a02e40d9faef63c`, head revisado `cf5f9386844083a60f8dc323b4e0b0b989256d78`, CI canónico verde run 630 y CI post-merge verde run 632. Schema 13 añade presets persistidos owner-scoped sin persistir resultados monetarios; packages permanecen composición y JSON/XLSX formatos de producto, no portabilidad relacional.

AQR-014 quedó incorporada mediante PR #53, merge `d7ccd44f53ce607c72cae44054af5236f63edc5f`, head definitivo `b551dae1accf17c1d30915993e3ea3af0ee26d91`, CI canónico verde run 643 y CI post-merge verde run 644. Backup/restore/integridad/portabilidad componen las autoridades de `migrations.py`; el restore valida y migra sólo en staging, conserva un commit point explícito y compensa fallos posteriores sin dejar DB/documentos deliberadamente inconsistentes. El export portable es relacional y autocontenido pero no constituye persistencia runtime. AQR-015 es el único siguiente trabajo.

AQR-001 fue incorporada mediante PR #31 (`bff58de7cad11de6c2ab37c0d3e0b7b6c20ae003`). Su matriz única es `docs/PRODUCT_ACCEPTANCE_V1.md`. Consultar siempre el único `NEXT` del backlog antes de comenzar trabajo.

## 12. Autorización operativa vigente — 2026-09-09

El usuario autorizó expresamente fusionar PR #31 tras verificarlo y continuar autónomamente sobre las tareas AQR del backlog, incluida la fusión de PR preparados por el propio agente. No solicitar autorización individual nuevamente cuando se cumplan todas estas condiciones:

- corresponde a la única tarea NEXT y cumple sus criterios de aceptación;
- diff completo revisado, sin regresión conocida, suite relevante verde y suite completa ejecutada o verificada si el cambio afecta transversalmente al runtime;
- PR fusionable contra main vigente, sin violar la Constitución;
- no requiere decisiones de producto, contables, fiscales o arquitectónicas que el repositorio no haya resuelto.

Después de cada fusión, verificar main, actualizar el backlog conforme al §10, dejar exactamente un NEXT, actualizar REPO_AUDIT_V2 sólo si cambiaron materialmente arquitectura o capacidades, releer el estado vigente y continuar. Los commits internos no son nuevas fases ni motivo para detenerse.

Detenerse únicamente ante una decisión humana real, cambio constitucional necesario, decisión contable/fiscal material no resuelta, elección entre arquitecturas legítimas incompatibles, regresión de alcance indeterminable, operación irreversible fuera de esta autorización o agotamiento de tareas elegibles. Antes de detenerse, preparar lo resoluble y presentar decisión exacta, evidencia de por qué no se deriva del repositorio, alternativas, consecuencias y recomendación identificada como tal.
