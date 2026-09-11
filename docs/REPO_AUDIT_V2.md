# REPO AUDIT V2 — ESTADO ACTUAL DE AQORATH

**Fecha de corte:** 2026-09-10
**Rama de continuidad:** `main`  
**Baseline histórico de runtime:** `7623e4eb0636064cdab0582ce3c98e7b9c844e93` (PR #30)  
**Runtime material vigente:** AQR-002 a AQR-012
**Esquema vigente:** 12

> Este documento sustituye a `REPO_AUDIT_V1.md` como descripción del estado actual. V1 queda únicamente como referencia histórica. Los apartados del baseline PR #30 conservan valor de evidencia; las actualizaciones AQR posteriores prevalecen cuando amplían el estado material.

---

## 1. Conclusión ejecutiva

Aqorath dispone de un núcleo contable local ampliamente endurecido y probado: SQLite como autoridad, dinero exacto, partida doble, catálogo gobernado, resolución de hechos económicos, reporting, fiscalidad versionada, trazabilidad, fundamentos OSC y activos fijos.

AQR-002 añadió la autoridad explícita de período y ejercicio. AQR-003 consolidó inmutabilidad append-only y corrección por reversión con auditoría. AQR-004 compuso las autoridades existentes en un caso de uso Application ordinario completo: **hecho → decisión → consentimiento → posting → auditoría**, sin crear un segundo motor ni una persistencia paralela. AQR-005 añadió una superficie local común + profesional sobre esas mismas autoridades. AQR-006 a AQR-009 completaron submayores, conciliación bancaria, trazabilidad OSC y donativos monetarios/en especie manteniendo `JournalLine` como única autoridad contable. AQR-010 incorporó CFDI XML como evidencia externa verificable y lo vinculó a esas autoridades sin convertirlo en ledger ni regla fiscal. AQR-011 cerró la cobertura fiscal mexicana V1 mediante matriz normativa versionada, aplicabilidad factual fail-closed, cálculo exacto y superficies común/profesional sobre la misma autoridad contable. AQR-012 incorporó inventario perpetuo y costo por promedio ponderado móvil manteniendo `JournalEntry`/`JournalLine` como única autoridad monetaria y reconciliando existencia, valuación y COGS con el ledger.

### Resultado del corte

- **P0 de integridad contable conocidos:** ninguno abierto después de PR #36/#37/#39.
- **Estado de producción:** **NO declarado listo para producción**; una suite verde no sustituye la aceptación profesional/humana restante.
- **Cobertura fiscal V1:** cerrada por AQR-011 con vigencias/fuentes versionadas, aplicabilidad factual y rechazo explícito fuera de soporte.
- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-013.

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

### AQR-006 a AQR-009 — submayores, bancos y OSC

- AQR-006, PR #41, incorporó `OpenItem`/`OpenItemApplication` line-granulares sin backfill ni saldo paralelo.
- AQR-007, PR #42, separó evidencia bancaria y ledger, con conciliación, pendientes y diferencias reproducibles.
- AQR-008, PR #43, incorporó fondos, fuentes y aplicaciones derivados de líneas efectivas, con schema 9 aditivo.
- AQR-009, PR #44, merge `e3c8cd1f76ec2157c752a245efa74f3711526ffa`, head revisado `1f209cd6b1f56e74f57a325942078491c0a4de31`, tree idéntico `40c1f81749d7ad6689e53564f851acb2c76ef152`, CI verde y suite completa **2022 passed, 8 warnings**. Integra donativos monetarios y en especie con posting, documentos, fondos, activos, auditoría, reversión, idempotencia y superficies común/profesional; no crea efectivo ficticio ni autoridad monetaria o fiscal paralela.

### AQR-010 — CFDI como evidencia documental verificable

- PR #45, merge `6517b303c48d7d38eef01003dad487f676c5c2e7`;
- head revisado `83c0a058337b2345a7134a9a72a8472e980abb52`, tree idéntico `54afbbe94bf577749ac5dfadbc956e448c0463de`;
- CI verde run 458 y suite completa Python 3.12: **2060 passed, 8 warnings**;
- schema 11 aditivo desde snapshot histórico real 10, sin backfill;
- ingestión offline y exacta de CFDI 4.0 ingreso/MXN, XML/hash/UUID/RFC/fechas/importes/impuestos y deduplicación;
- posición documental `issuer/receiver` separada de venta/compra/donativo, que permanece clasificación factual explícita;
- importación independiente del posting y vínculo atómico a un único `DocumentReference`, `CfdiImportMetadata` y ledger canónico;
- donativo CFDI compuesto sobre AQR-009 con una sola póliza, Donation, FundReceipt, documento y auditoría, incluido rollback e idempotencia transversal;
- impuestos del XML presentados sólo como evidencia; no se declara aplicabilidad fiscal ni consulta SAT.

### AQR-011 — cobertura fiscal V1 declarada y versionada

- PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`;
- head definitivo revisado `527934106b6b852b67f51d4a708435c3e4897aec`;
- CI del head run 498 verde; CI post-merge de `main` run 499 verde;
- suite completa Python 3.12: **2092 passed, 8 warnings**;
- cobertura fiscal V1 declarada/versionada con fuentes y vigencias explícitas;
- aplicabilidad factual fail-closed y rechazo explícito de contextos fuera de soporte;
- fórmula exacta de retención de dos terceras partes cuando corresponde y `vat_pending_credit` como efecto explícito;
- `ThirdParty` persistido como autoridad factual para condiciones que dependen de contraparte;
- CFDI permanece evidencia documental y no selector jurídico;
- posting fiscal, documento/CFDI y auditoría se componen atómicamente sobre las autoridades existentes;
- superficies común/profesional reconstruyen la misma verdad fiscal persistida.

### AQR-012 — inventario perpetuo y costos

- PR #48, merge `79d4ec06a6b5fe9e20b511284cfe105d21dddd40`;
- head definitivo revisado `bf74211975ce4ef19b0cf0243d6f315f8dbe5fd4`;
- CI del head run 546 verde; CI post-merge de `main` run 547 verde;
- suite completa Python 3.12: **2125 passed, 8 warnings**;
- schema 12 aditivo con `inventoryproduct` / `inventorymovement` vacíos al migrar historia, sin backfill inventado;
- promedio ponderado móvil exacto con Decimal y V1-21 reproducible de superficie común a movimiento/ledger/readback/auditoría;
- stock, valor y COGS se reconcilian contra `JournalLine`; no existe shadow ledger de inventario;
- compras/ventas atómicas, oversell fail-closed e idempotencia por operación;
- crédito compone AQR-006 `OpenItem`, CFDI compone AQR-010 en el mismo commit y fiscalidad soportada compone AQR-011 antes de un único posting;
- reversión AQR-003 invierte el costo consolidado original sin revalorar el pasado y conserva historia `as_of`;
- ownership de producto/tercero/banco/CFDI/documento/OpenItem y cambio de Entity activa fallan antes de verdad parcial;
- superficies común/profesional y HTTP/UI consultan la misma persistencia canónica.

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

Estado: **ARQUITECTURA, FLUJOS Y COBERTURA FISCAL V1 IMPLEMENTADOS**

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

### Cobertura V1 cerrada

AQR-011 declara los tratamientos soportados por fuente/vigencia y resuelve aplicabilidad con hechos persistidos; lo no soportado falla explícitamente. CFDI no selecciona por sí mismo la norma aplicable y la autoridad monetaria continúa en `JournalEntry` / `JournalLine`.

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

AQR-013 materializa el motor gobernado de documentos/reportes de producto sobre las autoridades existentes: schema 13 aditivo, presets owner-scoped persistidos como configuración, packages como composición y ejecución fresca sin resultados monetarios persistidos ni shadow ledger. Las superficies común/profesional, controlador y HTTP consumen las mismas autoridades; inventario proviene de AQR-012, fiscalidad de AQR-011, CFDI de AQR-010 y dimensiones de AQR-008. JSON/XLSX son formatos de producto; la exportación relacional portable permanece separada y corresponde a AQR-014.

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
- CfdiSource/CfdiTaxEvidence/CfdiSourceLink con XML exacto y deduplicación;
- AuditEvent.

La identidad de entidad no se reduce a un selector “Comercial / OSC”.

Pendiente: aplicabilidad y cobertura fiscal declarada AQR-011; la evidencia CFDI no determina por sí sola tratamiento fiscal.

---

## 10. OSC

Estado: **FLUJOS OSC DE RECURSOS Y DONATIVOS IMPLEMENTADOS**

Existen Program, Donation, InKindDonation, Fund, FundingSource y AnalyticalDimension/valores/asignaciones. AQR-008 trazó recepción/aplicación sobre `JournalLine`; AQR-009 completó los flujos monetario y en especie, incluida evidencia, activo durable, reversión y superficie humana/profesional.

La fiscalidad específica de donativos permanece deliberadamente limitada a reglas versionadas existentes; AQR-011 es la autoridad siguiente para cobertura fiscal.

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

> **AQR-011 — Cobertura fiscal V1 declarada y versionada**

Inspeccionar y reutilizar `FiscalRuleSet`, registry, fuentes/versiones, aplicabilidad, cálculo, redondeo, confirmación, efectos, posting y auditoría fiscal existentes, además de la evidencia CFDI AQR-010. La tarea debe declarar sólo los tratamientos V1 autorizados, probarlos por fecha/contexto y rechazar explícitamente lo desconocido sin convertir impuestos documentales en aplicabilidad automática.

---

## 19. Límite de esta auditoría

Esta auditoría combina estructura del repositorio, código vigente, pruebas y CI. No constituye:

- dictamen de auditoría financiera;
- certificación fiscal ante SAT;
- revisión externa por contador independiente;
- pentest de seguridad;
- garantía de ausencia absoluta de defectos.

Es el **corte técnico y arquitectónico de autoridad para continuar el desarrollo** a partir del 2026-09-09.
