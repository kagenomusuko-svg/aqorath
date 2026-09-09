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

### Runtime vigente — AQR-002

PR #33 incorporó el calendario aprobado, períodos y cierre anual atómico en `bc41cffcbc192bbf179e7eb28ea137521f079526`. Head revisado `f0f55d9bcd6d40112dea395e896d4f3cc5554326`, CI verde (run 34385801594), **1936 passed, 8 warnings** local. El árbol de main resultante coincide con ese head. Esquema actual 5; la migración no infiere estados ni calendarios históricos. Contrato: `docs/AQR_002_PERIOD_DECISION.md`.

Los commits exclusivamente documentales posteriores pueden avanzar main sin cambiar este corte de runtime.

### Fundamentos que NO deben reconstruirse sin evidencia de defecto

Ya existe base funcional y pruebas para, entre otros:

- dinero exacto y semántica de saldos;
- catálogo canónico gobernado + extensiones particulares;
- SQLite como autoridad contable local;
- validación de cuentas y partida doble en la frontera de persistencia;
- migraciones versionadas, integridad, backup y restore;
- hechos económicos, resolución semántica, bindings, confirmación y posting;
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
- cierre de ejercicio mediante la autoridad canónica de posting.

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

**`AQR-003 — Inmutabilidad de pólizas consolidadas y correcciones por reversión`**

AQR-001 fue incorporada mediante PR #31 (`bff58de7cad11de6c2ab37c0d3e0b7b6c20ae003`). Su matriz única es `docs/PRODUCT_ACCEPTANCE_V1.md`. Consultar siempre el único `NEXT` del backlog antes de comenzar trabajo.

## 12. Autorización operativa vigente — 2026-09-09

El usuario autorizó expresamente fusionar PR #31 tras verificarlo y continuar autónomamente sobre las tareas AQR del backlog, incluida la fusión de PR preparados por el propio agente. No solicitar autorización individual nuevamente cuando se cumplan todas estas condiciones:

- corresponde a la única tarea NEXT y cumple sus criterios de aceptación;
- diff completo revisado, sin regresión conocida, suite relevante verde y suite completa ejecutada o verificada si el cambio afecta transversalmente al runtime;
- PR fusionable contra main vigente, sin violar la Constitución;
- no requiere decisiones de producto, contables, fiscales o arquitectónicas que el repositorio no haya resuelto.

Después de cada fusión, verificar main, actualizar el backlog conforme al §10, dejar exactamente un NEXT, actualizar REPO_AUDIT_V2 sólo si cambiaron materialmente arquitectura o capacidades, releer el estado vigente y continuar. Los commits internos no son nuevas fases ni motivo para detenerse.

Detenerse únicamente ante una decisión humana real, cambio constitucional necesario, decisión contable/fiscal material no resuelta, elección entre arquitecturas legítimas incompatibles, regresión de alcance indeterminable, operación irreversible fuera de esta autorización o agotamiento de tareas elegibles. Antes de detenerse, preparar lo resoluble y presentar decisión exacta, evidencia de por qué no se deriva del repositorio, alternativas, consecuencias y recomendación identificada como tal.
