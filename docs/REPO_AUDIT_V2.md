# REPO AUDIT V2 — ESTADO ACTUAL DE AQORATH

**Fecha de corte:** 2026-09-09  
**Rama auditada:** `main`  
**Baseline de runtime:** `7623e4eb0636064cdab0582ce3c98e7b9c844e93`  
**PR de runtime más reciente incluido:** #30 — Phase 6BP persistence hardening  
**Head probado previo al merge:** `7dbef85bcdd4157106c3779356303c9271dc56bb`  
**Suite completa verificada:** **1912 passed, 0 failed**

> Este documento sustituye a `REPO_AUDIT_V1.md` como descripción del estado actual. V1 queda conservado únicamente como referencia histórica en el historial de Git.

---

## 1. Conclusión ejecutiva

Aqorath ya no se encuentra en el estado descrito por la auditoría del 23 de agosto.

El proyecto dispone hoy de un **núcleo contable ampliamente endurecido y probado**, con una autoridad local SQLite, dinero exacto, catálogo gobernado/extensible, flujos de hechos económicos, reporting, fiscalidad versionada, explicabilidad, varios fundamentos OSC y activos fijos.

### Resultado de esta auditoría

- **P0 conocidos que obliguen a detener el desarrollo:** ninguno identificado en el corte auditado.
- **Regresión conocida en el baseline incorporado mediante PR #30:** ninguna después de la corrección y suite completa verde.
- **Estado de producción:** **NO declarado listo para producción**. La ausencia de P0 conocidos no equivale a completitud de producto ni a certificación contable/fiscal.
- **Riesgo principal actual:** pérdida de dirección por documentación/PR históricos y por confundir “fundamentos de dominio implementados” con “flujos de producto terminados”.

La prioridad pasa, por tanto, de rehacer fundamentos a **cerrar capacidades de producto contra un alcance V1 explícito**.

---

## 2. Evidencia de corte

El merge de PR #30 incorporó el endurecimiento transversal de persistencia sobre el estado posterior a 6BO.2.

Se verificó la suite completa del head final de la rama antes de fusionar:

```text
1912 passed
0 failed
```

PR #29, que reutilizaba incorrectamente la etiqueta histórica “Phase 6U” y retiraba funcionalidad de cierre de ejercicio, fue cerrado sin fusionar y supersedido por #30.

Los commits posteriores a `7623e4...` que sólo modifican documentación de gobierno no alteran este baseline de runtime.

---

## 3. Invariantes y fundamentos actualmente protegidos

### 3.1 Ledger y persistencia

Estado: **IMPLEMENTADO / PROBADO**

- partida doble como invariante de persistencia;
- rechazo de JournalEntry vacío o descuadrado en la frontera canónica;
- validación local de JournalLine;
- validación agregada de líneas completas antes de commit;
- integridad `account_id` / `account_code` contra Account;
- dinero exacto mediante Decimal/representación exacta;
- una sola autoridad contable local SQLite;
- cierre de ejercicio reencauzado por la autoridad canónica de posting.

No reintroducir escritura directa o fallback alternativo para “salvar” errores de la autoridad canónica.

### 3.2 Catálogo

Estado: **IMPLEMENTADO / PROBADO**

- catálogo canónico gobernado;
- extensiones particulares de entidad bajo padre canónico;
- código generado;
- naturaleza heredada;
- protección de estructura;
- resolución/bindings de roles contables.

### 3.3 Migraciones, integridad y seguridad local

Estado: **FUNDACIÓN IMPLEMENTADA**

`aqorath/migrations.py` es la autoridad central de evolución del esquema y contiene:

- `PRAGMA user_version`;
- migraciones secuenciales;
- validación de integridad;
- backup previo;
- restore seguro;
- rechazo de versiones futuras desconocidas.

`CURRENT_SCHEMA_VERSION = 4` en el corte auditado. Existen tablas aditivas posteriores que preservan la verdad v4 sin reinterpretarla.

Falta convertir estas capacidades de infraestructura en un flujo de producto operable por el usuario; eso está registrado como AQR-014.

---

## 4. Flujo de hechos económicos y autoridad de aplicación

Estado: **FUNDACIÓN AMPLIA / ORQUESTACIÓN DE PRODUCTO PENDIENTE**

`aqorath/application.py` funciona como fachada canónica independiente de interfaz y ya delega a autoridades especializadas para:

- hechos económicos;
- resolución de cuentas;
- bindings;
- confirmación;
- posting;
- reporting;
- tratamiento fiscal;
- posting fiscalizado y auditoría;
- Entity / FiscalProfile;
- ThirdParty;
- DocumentReference;
- metadatos CFDI;
- dimensiones analíticas;
- activos fijos.

Existe `EconomicEvent` como valor de dominio puro con fecha, importe Decimal, descripción, tercero y contexto.

### Pendiente real

Componer las autoridades existentes en un contrato de caso de uso completo y estable que una superficie de presentación pueda consumir sin conocer detalles contables internos. Registrado como AQR-004.

---

## 5. Reporting financiero

Estado: **IMPLEMENTACIÓN MATERIAL EXISTENTE**

Existe cobertura para:

- trial balance por fecha;
- semántica de estados financieros;
- estado de resultados;
- balance general;
- bundle de estados;
- CSV;
- XLSX;
- PDF;
- fuente SQLite única.

También existen fundamentos para ReportDefinition, ReportRequest, ReportPackage, CustomReportPackage y aplicabilidad.

### Pendiente real

Convertir las fundaciones de definición/paquetes en un motor completo de documentos del producto y añadir reportes especializados OSC/fiscales conforme se completen sus capacidades. AQR-013.

---

## 6. Fiscalidad

Estado: **ARQUITECTURA Y FLUJOS IMPLEMENTADOS; COBERTURA DE PRODUCTO NO CERRADA**

Existen:

- FiscalRuleSet;
- registry e instalación de reglas;
- datos fiscales mexicanos curados;
- aplicabilidad por fecha/contexto;
- cálculo exacto;
- políticas de redondeo;
- confirmación fiscal y monetaria;
- efectos contables fiscales;
- composición hecho económico + efecto fiscal;
- resolución de cuentas;
- posting fiscalizado;
- persistencia y lectura de auditoría fiscal;
- múltiples efectos fiscales.

### Pendiente real

No se declara que Aqorath cubra genéricamente “la fiscalidad mexicana”. Debe congelarse qué regímenes, obligaciones y casos son V1, completar sólo esos casos y declarar explícitamente los no soportados. AQR-011.

---

## 7. Entidad, terceros y evidencia

Estado: **FUNDACIONES IMPLEMENTADAS**

Existen conceptos y persistencia para:

- Entity;
- EntityProfile;
- FiscalProfile con vigencia;
- ThirdParty;
- DocumentReference;
- CfdiImportMetadata;
- AuditEvent.

La arquitectura ya evita reducir la entidad al antiguo switch binario “Comercial / OSC”.

### Pendientes de producto

- submayores operativos de cuentas por cobrar/pagar: AQR-006;
- CFDI XML real como fuente verificable: AQR-010.

---

## 8. OSC

Estado: **FUNDACIONES PARCIALES; CAPACIDAD INSTITUCIONAL INCOMPLETA**

Existen:

- Program;
- Donation;
- AnalyticalDimension y valores;
- asignación de dimensiones a líneas contables.

No se localizaron como implementaciones actuales separadas:

- Fund;
- FundingSource;
- InKindDonation.

El baseline conceptual sí los exige para la dirección OSC.

### Pendientes

- recursos, fondos, fuentes y restricciones: AQR-008;
- donativos completos y donativos en especie: AQR-009.

---

## 9. Activos fijos

Estado: **CAPACIDAD TÉCNICA AVANZADA**

Existen fundamentos y flujos para:

- FixedAsset;
- registro/persistencia;
- adquisición;
- confirmación;
- posting idempotente de adquisición;
- depreciación;
- asignación monetaria exacta;
- reconocimiento por período;
- resolución contable;
- confirmación;
- posting idempotente;
- reconstrucción de estado en libros.

Debe evaluarse como flujo de usuario dentro de la matriz V1 AQR-001, pero no corresponde reconstruir el subsistema.

---

## 10. Explicabilidad y aprendizaje

Estado: **FUNDACIÓN IMPLEMENTADA**

Existen:

- Explanation estructurada;
- formatting;
- presentation;
- delivery;
- explicación bajo demanda;
- progresividad de explicación;
- topic learning;
- UserKnowledgeState y persistencia.

### Pendiente real

Integrarlo en los flujos de producto y en la vista común/profesional, no crear una segunda fuente narrativa. AQR-004 y AQR-005.

---

## 11. Conceptos del baseline: mapa de cobertura

| Concepto | Estado en el corte |
|---|---|
| Entity | Fundación implementada |
| EntityProfile | Fundación implementada |
| FiscalProfile | Fundación implementada |
| AccountingPeriod | **No localizado como implementación actual** |
| FiscalYear | **No localizado como aggregate/VO explícito**; existe cierre en `exercise.py` |
| Account | Implementado |
| AccountExtension | Implementado |
| EconomicEvent | Implementado |
| AccountingDecision | **Representado parcialmente por proposal/resolution/provenance; aggregate durable unificado pendiente** |
| JournalEntry | Implementado |
| JournalLine | Implementado |
| ThirdParty | Implementado |
| DocumentReference | Implementado |
| Program | Fundación implementada |
| Fund | **Pendiente** |
| FundingSource | **Pendiente** |
| AnalyticalDimension | Implementado |
| Donation | Fundación implementada |
| InKindDonation | **Pendiente** |
| BankAccount | **Pendiente** |
| FiscalRuleSet | Implementado |
| ExplanationData / explicación estructurada | Implementado por módulos equivalentes |
| UserKnowledgeState | Implementado |
| ReportDefinition | Fundación implementada |
| ReportRequest | Fundación implementada |
| ReportPackage | Fundación implementada |
| CustomReportPackage | Fundación implementada |
| AuditEvent | Implementado |
| FixedAsset | Implementado aunque no figuraba como núcleo del listado original de 29 |

---

## 12. Superficie de presentación

Estado: **GAP DE PRODUCTO CRÍTICO, NO P0 DE INTEGRIDAD**

No se localizó en el `main` auditado una UI productiva vigente (`aqorath/ui`, `desktop.py` o equivalente actual).

Los PR antiguos #18/#19 sobre PySide corresponden a una etapa anterior y no deben fusionarse sobre el estado actual: pedían códigos contables al usuario y dependían de supuestos que ya no representan la arquitectura vigente.

AQR-005 define la nueva superficie, una vez establecida la orquestación de AQR-004.

---

## 13. Otras capacidades de producto faltantes

No se localizaron como capacidades completas actuales:

- períodos contables bloqueables y FiscalYear explícito;
- reversión/corrección formal de pólizas posted como contrato integral;
- BankAccount y conciliación bancaria;
- Fund/FundingSource/restricciones OSC;
- InKindDonation;
- CFDI XML productivo de extremo a extremo;
- cobertura fiscal V1 declarada y cerrada;
- inventario/costos como capacidad opcional;
- experiencia de backup/restore para usuario;
- empaquetado/release de producto;
- prueba humana reproducible de la interfaz común.

Todas están registradas, ordenadas y acotadas en `PRODUCT_BACKLOG_V1.md`.

---

## 14. Deuda de gobernanza y documentación encontrada

### 14.1 REPO_AUDIT_V1 obsoleto

V1 describía 26 tests y defectos P0/P1 que posteriormente fueron corregidos. Usarlo como “estado actual” podía hacer que una nueva conversación reabriera trabajo terminado.

**Resolución:** V2 pasa a ser la auditoría actual; V1 se convierte en tombstone histórico.

### 14.2 PR antiguos abiertos

Se localizaron abiertos #2, #11, #13, #14, #15, #16, #18 y #19. Contienen decisiones antiguas como:

- fallback JSON;
- SQLite directo como fallback de posting;
- account_code sin Account;
- selector inmutable Comercial/OSC;
- UI histórica;
- tolerancia de esquema incompatible con el fail-closed actual.

**Resolución:** deben quedar cerrados como supersedidos. Ninguno es fuente de continuidad.

### 14.3 Documentación especializada histórica

`docs/CFDI.md` y otros documentos pueden conservar contenido útil pero no deben utilizarse como prueba de que una función está implementada. El código actual, los tests, esta auditoría y el backlog prevalecen para estado/continuidad.

---

## 15. Riesgos actuales

### P0 — integridad contable bloqueante

**Ninguno conocido en este corte.**

Esto significa “no identificado por la suite y revisión actual”, no “imposible que exista”.

### P1 — completitud/seguridad de producto

- ausencia de períodos contables como autoridad;
- ausencia de workflow de reversión plenamente cerrado;
- ausencia de superficie de usuario actual;
- ausencia de bancos/conciliación;
- OSC incompleto en fondos/fuentes/restricciones;
- CFDI y cobertura fiscal V1 incompletos;
- producto no empaquetado para instalación/actualización.

### P2 — higiene y mantenibilidad

- documentación histórica que debe permanecer claramente marcada;
- scripts/assets/templates antiguos en raíz que deben evaluarse antes de release, no borrar por intuición;
- nombres históricos de fases en tests/commits que pueden confundir si se usan como roadmap;
- cobertura profesional/humana todavía no expresada como matriz de aceptación única.

---

## 16. Qué sigue

La continuidad **NO** se deriva de la numeración histórica de fases.

Leer `INSTRUCCIONES.md` y ejecutar la única tarea `NEXT` de `PRODUCT_BACKLOG_V1.md`:

> **AQR-001 — Matriz de aceptación del producto V1**

Su objetivo es congelar qué operaciones concretas forman Aqorath V1 y qué evidencia técnica, profesional y humana demuestra que cada una está terminada.

A partir de ahí, el resto del backlog convierte las capacidades faltantes en trabajo finito y secuencial.

---

## 17. Límite de esta auditoría

Esta auditoría combina estructura del repositorio, código vigente, pruebas y CI. No constituye:

- dictamen de auditoría financiera;
- certificación fiscal ante SAT;
- revisión externa por contador independiente;
- pentest de seguridad;
- garantía de ausencia absoluta de defectos.

Es el **corte técnico y arquitectónico de autoridad para continuar el desarrollo** a partir del 2026-09-09.
