# AQR-005 — Decisión derivada de superficie V1

**Estado:** decisión técnica derivada del repositorio.  
**Fecha:** 2026-09-09.  
**Base:** `main` después de PR #38 (`207529b21a34d642311b6ec22e94a3652e61d6a7`).

## 1. Pregunta

¿Existe evidencia vigente suficiente para escoger una arquitectura de presentación V1 sin una nueva decisión humana?

**Sí.** La tecnología histórica no es autoridad, pero el conjunto de restricciones vigentes y del runtime permite derivar una opción dominante sin alterar la Constitución.

## 2. Evidencia agotada

### FastAPI / Uvicorn

`fastapi` y `uvicorn` no nacieron como dependencias neutras. El commit `f31a4c6b347296c5f3dbe7dd8258205ec1ff6067` añadió ambos junto con una API que llamaba directamente a `aqorath.core` y recibía `template_key`, importe y `ctx`. El commit `cdfc7d6f0a393accfdd47e59c03030ed1ea8c3c4` amplió esa superficie con Jinja, Company y reportes.

Esa composition root fue **retirada expresamente** por `ac45543aff0dec826662abe8c53cfcf04ce3f768` durante la consolidación del runtime del 2026-08-25. En `main` ya no existe `aqorath/api.py`; tampoco existen imports productivos de `fastapi`, y `uvicorn` sólo sobrevive en `requirements.txt`. Por tanto, su mera instalación no ratifica la arquitectura antigua.

La misma consolidación introdujo contratos para que el runtime contable no importe frameworks de interfaz y para que `import aqorath` no los cargue ávidamente. Esa separación sí sigue siendo compatible con la Constitución.

### `templates/` y `static/`

Los archivos raíz `templates/main.html` y `static/main.css` se incorporaron en `f4a87daf9d2b27b6acecc9b54c31c2eb31f0b325`, dentro de la antigua arquitectura de “modo OSC / Comercial”. Esa identidad binaria fue posteriormente prohibida por R15. El HTML actual sólo muestra sello/Company y no implementa captura contable ni vista profesional. `report_template.html` no tiene consumidores productivos actuales. Estos recursos son arqueología; AQR-005 no los revive ni los usa como contrato.

### Documentación vigente

La Constitución no prescribe framework. Sí prescribe:

- R1: la interfaz común recibe hechos, nunca Debe/Haber ni códigos contables;
- R2: una sola contabilidad y dos interfaces sobre la misma verdad;
- R6: funcionamiento sin Internet y fuente primaria local;
- R8: monousuario y ausencia de APIs expuestas en red; localhost/IPC sí están permitidos;
- R11/R12: explicación determinística y consentimiento informado;
- R15: no reintroducir identidad binaria Comercial/OSC.

`REPO_AUDIT_V2.md` y `PRODUCT_BACKLOG_V1.md` declaran que la UI productiva histórica está supersedida y que AQR-005 debe consumir los casos de uso canónicos. AQR-004 ya compone hecho → decisión → consentimiento → posting → auditoría.

## 3. Alternativas legítimas evaluadas

### A. GUI nativa nueva

Es constitucionalmente posible, pero el runtime actual no contiene un toolkit vigente ni contratos de UI nativa. Revivir PySide heredaría una arquitectura expresamente supersedida y añadiría otra dependencia pesada antes de AQR-015. Una GUI nativa nueva también elevaría el coste de pruebas de interacción y empaquetado sin aportar una autoridad que el producto necesite.

### B. Superficie web local nueva

Es constitucionalmente posible **sólo en loopback**. No requiere red externa, puede funcionar totalmente offline, mantiene SQLite local y permite separar HTML/HTTP del dominio. FastAPI/Uvicorn ya forman parte del entorno instalado, aunque su presencia no sea la razón normativa para escogerlos. La capa puede probarse como adaptador y reemplazarse sin tocar Application ni el ledger.

### C. CLI como superficie V1

Es útil para diagnóstico, pero no satisface adecuadamente el criterio humano de AQR-005 ni las dos vistas de producto. Puede seguir existiendo como adaptador auxiliar, no como superficie V1 principal.

## 4. Decisión

AQR-005 implementará una **superficie web local nueva**, servida exclusivamente en `127.0.0.1`, con estas fronteras:

1. **Application / caso de uso** sigue siendo la autoridad. La UI no importa `models`, `storage`, `core`, repositorios, reglas contables, fiscalidad, período ni reversión.
2. Se añade un **servicio de aplicación para superficie local** que orquesta sesiones y read-models, pero no crea reglas contables. Su función es ocultar SQLModel/SQLite al adaptador.
3. Se añade un **controlador de presentación independiente del framework**, responsable únicamente de estado efímero de una decisión preparada. Un token de preview no es verdad contable; reiniciar la aplicación puede descartarlo sin efecto en el ledger.
4. FastAPI es sólo el adaptador HTTP local. Uvicorn siempre enlaza a `127.0.0.1`; no habrá `0.0.0.0`, autenticación multiusuario ni API remota.
5. La UI usa HTML/CSS/JavaScript sin framework frontend ni Jinja. Los recursos históricos raíz no se reutilizan.
6. La **vista común** ofrece operaciones semánticas soportadas, importe y fecha, explica la decisión y exige confirmación/cancelación. No contiene campos de cuenta, Debe/Haber, período interno ni SQL.
7. La **vista profesional** proyecta la misma decisión/entrada persistida: póliza, fecha/período, estado, cuentas, cargos/abonos, documentos, reversión, auditoría general y, cuando exista, auditoría fiscal.
8. Las capacidades futuras AQR-006…AQR-014 se incorporarán a esta superficie mediante nuevos casos de uso Application. AQR-005 no simulará capacidades de dominio todavía `TODO`.

## 5. Testabilidad

La aceptación se divide en contratos independientes del framework y pruebas del adaptador:

- el controlador común no expone códigos, `debit`, `credit` ni objetos ORM como entrada;
- preparar/cancelar no escribe;
- confirmar ejecuta exactamente la decisión preparada;
- common/professional preview derivan del mismo `AccountingDecision`;
- la vista profesional persistida lee la misma `JournalEntry` y AuditEvent producidos por AQR-004;
- un período cerrado sigue fallando por AQR-002, no por código de UI;
- una póliza posted sigue siendo inmutable por AQR-003;
- análisis estático impide imports de autoridades internas desde el módulo FastAPI;
- el launcher sólo acepta loopback.

## 6. Empaquetado

AQR-005 no redefine AQR-015. La superficie es local y offline desde código fuente; el empaquetado reproducible, inicialización de instalación limpia y experiencia de actualización quedan en AQR-015. La elección actual minimiza esa deuda: no añade toolkit nativo ni servidor externo y puede incorporarse después al ejecutable local existente/planeado.