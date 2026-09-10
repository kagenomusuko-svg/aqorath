# REPO AUDIT V2 — ESTADO ACTUAL DE AQORATH

**Fecha de corte:** 2026-09-09  
**Rama de continuidad:** `main`  
**Baseline histórico de runtime:** `7623e4eb0636064cdab0582ce3c98e7b9c844e93` (PR #30)  
**Runtime material vigente:** AQR-002 + AQR-003 + AQR-004 + AQR-005  
**Esquema vigente:** 6

> Este documento sustituye a `REPO_AUDIT_V1.md` como descripción del estado actual. V1 queda únicamente como referencia histórica. Los apartados del baseline PR #30 conservan valor de evidencia; las actualizaciones AQR posteriores prevalecen cuando amplían el estado material.

---

## 1. Conclusión ejecutiva

Aqorath dispone de un núcleo contable local ampliamente endurecido y probado: SQLite como autoridad, dinero exacto, partida doble, catálogo gobernado, resolución de hechos económicos, reporting, fiscalidad versionada, trazabilidad, fundamentos OSC y activos fijos.

AQR-002 añadió la autoridad explícita de período y ejercicio. AQR-003 consolidó inmutabilidad append-only y corrección por reversión con auditoría. AQR-004 compuso las autoridades existentes en un caso de uso Application ordinario completo: **hecho → decisión → consentimiento → posting → auditoría**, sin crear un segundo motor ni una persistencia paralela. AQR-005 añadió una superficie local común + profesional sobre esas mismas autoridades, estrictamente loopback y sin trasladar reglas contables a presentación.

### Resultado del corte

- **P0 de integridad contable conocidos:** ninguno abierto después de PR #36/#37/#39.
- **Estado de producción:** **NO declarado listo para producción**; una suite verde no sustituye aceptación profesional/humana ni cobertura fiscal declarada.
- **Gap de producto principal inmediato:** los flujos de crédito/cobro/pago contabilizan, pero todavía no constituyen submayores operativos CxC/CxP por tercero y partida abierta.
- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-006.

---

## 2. Evidencia de corte

### Baseline histórico — PR #30

- merge `7623e4eb0636064cdab0582ce3c98e7b9c844e93`;
- head probado `7dbef85bcdd4157106c3779356303c9271dc56bb`;
- suite registrada: **1912 passed, 0 failed**.

### AQR-002 — autoridad temporal

- contrato: `AQR_002_PERIOD_DECISION.md`;
- PR #33 incorporado; autoridad única de ejercicio/período, posting bloqueado en período cerrado y cierre anual por staging canónico;
- consultas de rango componen el motor de saldos; no existen calendarios paralelos ni inferencia histórica silenciosa.

### AQR-003 — inmutabilidad/reversión

- PR #35 incorporó la base de estados y reversión;
- PR #36, merge `63e321fececb301eaa1337baff7ebe4acb07682a`;
- head revisado `84cbc947259da62c03c5c5546d6699d542e2a479`;
- CI verde run 34393029104;
- suite completa local registrada por la rama: **1944 passed, 8 warnings**;
- comparación head→merge: cero diferencias de archivos.

PR #36 cerró dos defectos reproducidos tras PR #35: edición balanceada de líneas `posted` y reversión sin `AuditEvent`. Protege cabecera/líneas/identidad/estado `reversed`, hace reversión + auditoría atómica y prueba rollback ante fallo aun si el llamador captura la excepción.

La decisión `AQR_003_CLOSED_YEAR_DECISION.md` aprobó bloquear preventivamente correcciones automáticas de ejercicios ya cerrados mediante reversión/sustitución sobre cuentas originales en un ejercicio posterior. En ejercicios abiertos se conserva la autoridad canónica. La política futura de errores de ejercicios anteriores permanece separada y no es el `NEXT`.

### AQR-004 — caso de uso unificado

- contrato: `AQR_004_UNIFIED_USE_CASE.md`;
- PR #37, merge `fe99ce06f334f8a12d37146f4504e78f497b18ca`;
- head revisado `f6a268b43dd7b600201a7dfe5501ee804a8d8926`;
- CI verde run 34394126158;
- comparación head→merge: cero diferencias de archivos;
- ocho pruebas AQR-004 nuevas, además de la regresión completa ejecutada por CI.

AQR-004 añade únicamente composición: `AccountingDecision` inmutable, preparación mediante provenance + bindings + resolución + explicación + snapshot, consentimiento por la autoridad existente, posting por `PostingInstruction` y staging canónico, y `AuditEvent entry_posted` en la misma transacción. La fiscalidad ya confirmada delega a `fiscalized_posting_persistence.py`.

### AQR-005 — superficie local común + profesional

- decisión: `AQR_005_SURFACE_DECISION.md`;
- operación: `AQR_005_LOCAL_SURFACE.md`;
- PR #39, merge `97604e1e887129cd4ded484f1e170c10396ea980`;
- head revisado `d0c10b4003c23c63be223752f3db4dea8da5cba2`;
- CI verde run 34397980985;
- tree de head y merge idéntico: `d9d41cd0989f588256b46d1b1f40d1b9a0a3545e`.

AQR-005 deriva del repositorio una superficie web local estrictamente `127.0.0.1`. `web_surface.py` es un adaptador FastAPI delgado; `presentation_controller.py` conserva únicamente decisiones preparadas efímeras; `surface_application.py` delega en AQR-004/Application; `accounting_operation_read.py` consulta las autoridades persistidas existentes. La vista común no solicita Debe/Haber ni códigos; la profesional inspecciona la misma `JournalEntry`, período, líneas, documentos, reversión y auditorías. La lista de pólizas recientes consulta directamente `JournalEntry`: no existe índice profesional paralelo.

---

## 3. Ledger y persistencia

Estado: **IMPLEMENTADO / PROBADO**

- partida doble y rechazo de pólizas vacías/descuadradas;
- validación `account_id` / `account_code` contra `Account`;
- dinero exacto;
- SQLite como única autoridad primaria;
- `JournalEntry.state` explícito `draft / posted / reversed`;
- pólizas `posted`/`reversed` y sus líneas son inmutables;
- corrección mediante reversión vinculada, nunca edición destructiva;
- toda reversión produce `AuditEvent` en la misma transacción;
- posting AQR-004 termina explícitamente `posted` y queda bajo estas invariantes.

No reintroducir escritura directa/fallback alternativo para “salvar” errores del staging canónico.

---

## 4. Período y ejercicio

Estado: **IMPLEMENTADO AQR-002**

- ejercicio enero–diciembre;
- primer ejercicio corto desde inicio efectivo;
- meses calendario exclusivos;
- años abiertos explícitamente;
- fecha de posting resuelta por una sola autoridad;
- período cerrado rechaza nuevos postings;
- cierre anual utiliza staging canónico y acumula el resultado en 3104;
- rangos arbitrarios son consultas, no períodos alternativos.

AQR-004 revalida el período dentro de la transacción de posting: una preparación previa no concede autorización si el período se cierra después.

---

## 5. Catálogo y resolución de cuentas

Estado: **IMPLEMENTADO / PROBADO**

- catálogo canónico gobernado;
- extensiones particulares bajo padre canónico;
- naturaleza heredada;
- bindings persistidos de rol semántico → cuenta concreta;
- resolución por catálogo existente.

El caso de uso AQR-004 obtiene bindings desde SQLite. La superficie común no necesita suministrar códigos contables.

---

## 6. Flujo de hechos económicos y autoridad Application

Estado: **ORQUESTACIÓN ORDINARIA UNIFICADA IMPLEMENTADA**

Fundamentos existentes:

- `EconomicFact` y `EconomicEvent`;
- resolución semántica;
- provenance entre hecho y propuesta;
- account bindings y resolución concreta;
- explicación estructurada;
- confirmación;
- posting;
- auditoría.

AQR-004 compone esos fundamentos en `accounting_operation.py`:

1. `prepare_accounting_operation(session, fact, posting_date)`;
2. `confirm_accounting_operation(decision)`;
3. `execute_accounting_operation(confirmed_decision)`;
4. `load_accounting_operation_audit(...)`.

La decisión no constituye un segundo ledger. La evidencia durable se divide por autoridad:

- JournalEntry/JournalLine: cuentas, importes, fecha y estado efectivamente consolidados;
- AuditEvent `entry_posted`: hecho, fecha solicitada, rule_id/version, consentimiento y explicación estructurada;
- auditoría fiscal: provenance fiscal cuando aplica.

AQR-005 consume estas fronteras; no añade una segunda ruta de posting.

---

## 7. Fiscalidad

Estado: **ARQUITECTURA Y FLUJOS IMPLEMENTADOS; COBERTURA V1 NO CERRADA**

Existen:

- FiscalRuleSet y registry;
- reglas/datos versionados;
- aplicabilidad por fecha/contexto;
- cálculo exacto;
- redondeo;
- confirmación fiscal y monetaria;
- efectos contables fiscales;
- composición hecho + efecto fiscal;
- resolución de cuentas;
- posting fiscalizado;
- persistencia/lectura de auditoría fiscal;
- múltiples efectos fiscales.

AQR-004 no infiere silenciosamente una regla fiscal desde un hecho ordinario. `execute_fiscalized_accounting_operation(...)` delega la instrucción y persistencia de una verdad fiscalizada **ya confirmada** a las autoridades existentes.

### Pendiente real

AQR-010/AQR-011 deben cerrar documento fuente, aplicabilidad y cobertura fiscal V1. Lo no soportado debe fallar explícitamente.

---

## 8. Reporting financiero y documentos

Estado: **IMPLEMENTACIÓN MATERIAL EXISTENTE**

Existe cobertura para:

- trial balance por fecha;
- estado de resultados;
- balance general;
- bundle de estados;
- CSV/XLSX/PDF;
- fuente SQLite única.

También existen fundamentos de ReportDefinition, ReportRequest, ReportPackage y CustomReportPackage.

Pendiente: convertirlos en motor completo de documentos/reportes de producto (AQR-013) y añadir reportes especializados conforme se completen OSC/fiscalidad.

---

## 9. Entidad, terceros y evidencia

Estado: **FUNDACIONES IMPLEMENTADAS**

Existen:

- Entity;
- EntityProfile;
- FiscalProfile con vigencia;
- ThirdParty;
- DocumentReference;
- CfdiImportMetadata;
- AuditEvent.

La identidad de entidad no se reduce a un selector “Comercial / OSC”.

Pendientes: submayores operativos AQR-006 y CFDI XML real AQR-010.

---

## 10. OSC

Estado: **FUNDACIONES PARCIALES**

Existen Program, Donation y AnalyticalDimension/valores/asignaciones.

Fund y FundingSource quedaron implementados en AQR-008 como trazabilidad OSC sobre `JournalLine`; InKindDonation sigue pendiente.

Pendiente: AQR-009 (donativos completos/en especie).

---

## 11. Activos fijos

Estado: **CAPACIDAD TÉCNICA AVANZADA**

Existen registro/persistencia, adquisición, confirmación, posting idempotente, depreciación, asignación exacta, reconocimiento por período, resolución contable y reconstrucción de valor en libros.

No corresponde reconstruir este subsistema; debe integrarse en la experiencia de producto.

---

## 12. Explicabilidad y aprendizaje

Estado: **FUNDACIÓN IMPLEMENTADA / INTEGRACIÓN DE PRODUCTO PARCIAL**

Existen ExplanationData, formatting/presentation/delivery, explicación bajo demanda, progresividad, topic learning y UserKnowledgeState.

AQR-004 incorpora `ExplanationData` a la misma decisión y conserva evidencia estructurada en auditoría. AQR-005 presenta esa explicación desde la misma decisión; no crea una fuente narrativa independiente.

---

## 13. Conceptos del baseline: mapa de cobertura

| Concepto | Estado actual |
|---|---|
| Entity | Fundación implementada |
| EntityProfile | Fundación implementada |
| FiscalProfile | Fundación implementada |
| AccountingPeriod | Implementado AQR-002 |
| FiscalYear | Implementado AQR-002 |
| Account | Implementado |
| AccountExtension | Implementado |
| EconomicEvent | Implementado |
| EconomicFact | Implementado |
| AccountingDecision | **Valor unificado AQR-004 + evidencia durable distribuida ledger/AuditEvent** |
| JournalEntry | Implementado; posted/reversed inmutable AQR-003 |
| JournalLine | Implementado; líneas consolidadas inmutables AQR-003 |
| ThirdParty | Implementado |
| DocumentReference | Implementado |
| Program | Fundación implementada |
| Fund | **Implementado AQR-008** |
| FundingSource | **Implementado AQR-008** |
| AnalyticalDimension | Implementado |
| Donation | Fundación implementada |
| InKindDonation | **Pendiente** |
| BankAccount | **Implementado AQR-007** |
| FiscalRuleSet | Implementado |
| ExplanationData | Implementado e integrado en AQR-004/AQR-005 |
| UserKnowledgeState | Implementado |
| ReportDefinition | Fundación implementada |
| ReportRequest | Fundación implementada |
| ReportPackage | Fundación implementada |
| CustomReportPackage | Fundación implementada |
| AuditEvent | Implementado; reversal/posting ordinario integrados |
| FixedAsset | Implementado |

---

## 14. Superficie de presentación

Estado: **IMPLEMENTADA AQR-005 / EMPAQUETADO FINAL PENDIENTE**

Existe una superficie V1 nueva, local y estrictamente loopback:

- `aqorath/web_surface.py`: adaptador HTTP FastAPI delgado, sin autoridad contable/persistente;
- `aqorath/local_server.py`: Uvicorn fijado a `127.0.0.1`;
- `aqorath/presentation_controller.py`: estado efímero de preview/consentimiento;
- `aqorath/surface_application.py`: puente a Application/AQR-004 y read-models;
- `aqorath/accounting_operation_read.py`: proyección profesional desde autoridades existentes;
- `aqorath/web_assets.py`: vista común + profesional sin framework frontend.

La vista común solicita hechos, importe y fecha; nunca exige Debe/Haber ni códigos contables. La vista profesional presenta pólizas, cuentas, cargos/abonos, períodos, documentos y trazabilidad a partir del mismo ledger. Los PR históricos PySide #18/#19 y los recursos raíz `templates/`/`static/` permanecen supersedidos y no se usan.

AQR-015 conserva la responsabilidad del empaquetado/instalación final y de la aceptación humana completa del producto.

---

## 15. Otras capacidades de producto faltantes

- submayores CxC/CxP operativos;
- conciliación bancaria sobre evidencia externa, matching one-to-one, pendientes y diferencias;
- donativos completos/en especie OSC;
- donativo en especie;
- CFDI XML productivo;
- cobertura fiscal V1 declarada;
- inventario/costos según alcance V1;
- motor completo de documentos/reportes;
- experiencia de backup/restore;
- empaquetado/release;
- prueba humana reproducible.

Todas están registradas y ordenadas en `PRODUCT_BACKLOG_V1.md`.

---

## 16. Gobernanza y documentación

- `REPO_AUDIT_V1.md` es histórico y supersedido.
- PR antiguos #2, #11, #13, #14, #15, #16, #18 y #19 no son autoridad de continuidad y no deben fusionarse sobre `main`.
- `CFDI.md` y documentos especializados pueden conservar contexto, pero no prueban implementación.
- Las etiquetas de fases históricas en commits/tests son arqueología, no roadmap.
- La continuidad deriva exclusivamente del único `NEXT` del backlog.

---

## 17. Riesgos actuales

### P0 — integridad contable

**Ninguno conocido en el corte actual.** Los defectos reproducidos durante la revisión de AQR-003 quedaron corregidos e integrados por PR #36.

“Ninguno conocido” no significa garantía absoluta de ausencia de defectos.

### P1 — completitud/seguridad de producto

- submayores CxC/CxP operativos pendientes;
- donativos completos/en especie OSC pendientes;
- OSC incompleto en donativos y tratamiento en especie;
- CFDI/cobertura fiscal V1 incompletos;
- producto no empaquetado.

### P2 — higiene/mantenibilidad

- documentación y nombres históricos que deben permanecer marcados;
- scripts/assets/templates antiguos que deberán evaluarse antes de release;
- prueba humana final pendiente de AQR-015.

---

## 18. Qué sigue

La continuidad **NO** se deriva de numeración histórica ni de PR antiguos.

Leer `INSTRUCCIONES.md` y ejecutar la única tarea `NEXT` de `PRODUCT_BACKLOG_V1.md`:

> **AQR-006 — Cuentas por cobrar y pagar como submayores operativos**

Antes de modelar partidas abiertas, inspeccionar las identidades y relaciones ya persistidas por los flujos de crédito/cobro/pago. El submayor debe ser una proyección operacional explicable del ledger: distinguir origen, aplicaciones y saldo abierto; reutilizar ThirdParty, documentos, posting, períodos, reversión y auditoría; y detectar cualquier diferencia en vez de mantener un balance paralelo mutable.

---

## 19. Límite de esta auditoría

Esta auditoría combina estructura del repositorio, código vigente, pruebas y CI. No constituye:

- dictamen de auditoría financiera;
- certificación fiscal ante SAT;
- revisión externa por contador independiente;
- pentest de seguridad;
- garantía de ausencia absoluta de defectos.

Es el **corte técnico y arquitectónico de autoridad para continuar el desarrollo** a partir del 2026-09-09.
