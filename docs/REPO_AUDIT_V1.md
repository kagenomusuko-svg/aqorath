# REPO AUDIT V1 - ARQUEOLOGÍA Y MAPEO DE BRECHAS

**Fecha de auditoría:** 2025-11-02 (contra commit actual)
**Rama:** main
**Estado de tests:** 26/26 PASSED

---

## RESUMEN EJECUTIVO

Aqorath es un **ERP contable en construcción** con dos arquitecturas coexistentes:

1. **NUEVA:** `aqorath/` package → SQLModel/SQLAlchemy + SQLite local (CANÓNICA)
2. **LEGACY:** `modelos/` package → Pandas/DataFrames (FALLBACK)

**Estado arquitectónico:** Transición en progreso. Sistema funcional pero con riesgos de inconsistencia.

**Hallazgos críticos (P0):** 3
**Hallazgos graves (P1):** 4
**Hallazgos técnicos (P2):** 8

---

## I. ENTRY POINTS (SUPERFICIES DE ENTRADA)

| Archivo | Tipo | Estado | Notas |
|---------|------|--------|-------|
| main.py | Desktop | PROTOTIPO | Entry point PySide (aqorath/desktop.py) |
| app.py  | Web/Hybrid | LEGACY | Flask?/Pandas, parece mezclar modelos.* |
| api.py  | REST API | PROTOTIPO | Minimal wrapper |
| api/app.py | REST API | CANÓNICA | FastAPI, consume aqorath.core |
| aqorath/desktop.py | Desktop UI | PROTOTIPO | PySide, esquelético |

**Riesgo:** 5 entry points diferentes → posibles inconsistencias si consumen lógica diferentes.

---

## II. CAPAS Y COMPONENTES

### A. PERSISTENCIA Y CONFIGURACIÓN

| Módulo | Líneas | Clasificación | Descripción |
|--------|--------|---|---|
| aqorath/storage.py | 124 | CANÓNICA | SQLite sesión, listener anti-non-catalog |
| aqorath/models.py | 52 | CANÓNICA | SQLModel (Account, JournalEntry, JournalLine, Asset, AppConfig) |
| aqorath/config.py | 131 | CANÓNICA | AppConfig + fallback ~/.local/.../config.json |

**Problemas detectados:**
- **P0:** JournalLine.debit/credit son float (líneas 43-44), violando Regla 5 (DINERO EXACTO)
- **P0:** Asset.value es float (línea 52)
- **P1:** storage.py listener (líneas 50-64) PREVIENE cuentas no-en-catálogo, violando Regla 10 (extensible)

---

### B. MOTOR CONTABLE NUEVO

| Módulo | Líneas | Clasificación | Descripción |
|--------|--------|---|---|
| aqorath/core.py | 905 | CANÓNICA | **motor central**: generate_preview(), post_entry(), trial_balance() |
| aqorath/templates.py | 329 | CANÓNICA | Plantillas de operaciones (ingreso, egreso, etc.) |
| aqorath/catalog.py | 78 | CANÓNICA | Carga catálogo JSON + resolve_account |
| aqorath/accounting_rules.py | 52 | CANÓNICA | Mapeos de cuenta+reglas fiscales |

**Patrones observados:**
1. **Fallbacks adaptativos:** ORM first, sqlite second
2. **Defensive imports:** Circular dependencies prevented
3. **Decimal para cálculos intermedios** (generate_preview)
4. **Float para persistencia** (incorrecto, P0)

**Hallazgo core.py:**
- Línea 107-112: Exception genérica en _row_to_obj()
- Línea 131: "fallback to sqlite" (LOG.debug)
- Línea 164: generate_preview usa float() para retorno
- Línea 265-266: quantize() to 0.01, después convierte a float
- Línea 320+: _balances_from_sqlite() con detección dinámica de columnas
- Línea 436-504: _balances_from_libro() fallback a DataFrame (LEGACY!)
- Línea 690-691: Inserción con float() (P0)
- Línea 707: except Exception silencioso→ sqlite fallback

**Estado:** FUNCIONABLE pero con anti-patterns

---

### C. MOTOR CONTABLE LEGACY

| Módulo | Líneas | Clasificación | Descripción |
|--------|--------|---|---|
| modelos/libro.py | 779 | LEGACY | DataFrame-based trial balance, genera movimientos |
| modelos/registro.py | 271 | LEGACY | Validación de registros contables |
| modelos/poliza.py | 74 | LEGACY | Definición de pólizas |
| modelos/cfdi.py | 359 | PROTOTIPO | CFDI (XML, firma) |
| modelos/hoja.py | 59 | LEGACY | ???  |
| modelos/catalogo.py | 64 | LEGACY | Catálogo (duplica aqorath/catalog.py) |
| modelos/reportes.py | 118 | LEGACY | Generación de reportes |

**Riesgos:**
- **DUPLICACIÓN:** modelos/catalog.py + aqorath/catalog.py (misma responsabilidad)
- **FUENTE MÚLTIPLE:** modelos/libro.py crea DataFrames que podrían ser "verdad"
- **29 except Exception:** Tratamiento de errores demasiado genérico

---

### D. EJERCICIOS Y CIERRES

| Módulo | Líneas | Clasificación | Descripción |
|---------|--------|---|---|
| aqorath/exercise.py | 330 | CANÓNICA | Cierres contables, backups automáticos |

**Implementación:**
- Backup a ~/.local/share/aqorath/ejercicios/YYYYMMDD_HHMMSS/
- Requiere cuentas 3103 + 3104 (no las crea)
- Usa trial_balance() → cálculo resultado → inserta traslado
- ORM primero, sqlite fallback

**Estado:** CUMPLE requisitos de integridad

---

### E. ENTIDAD/COMPANY

| Módulo | Líneas | Clasificación | Descripción |
|---------|--------|---|---|
| aqorath/company.py | 16 | CANÓNICA | Modelo Company (monoentidad) |
| company.py (root) | ? | LEGACY | Duplica aqorath/company.py |

**Falta:** EntityProfile (para naturaleza/régimen de entidad)

---

### F. INTERFACES DE USUARIO

| Módulo | Líneas | Clasificación | Descripción |
|---------|--------|---|---|
| aqorath/desktop.py | 251 | PROTOTIPO | PySide main window, muy esquelético |
| aqorath/ui/ | - | PROTOTIPO | Templates/componentes UI |
| aqorath/api.py | 163 | PROTOTIPO | Endpoints REST mínimos |
| api/app.py | 4 | PROTOTIPO | FastAPI app stub |

**Observación:** Interfaces altamente esqueletizadas. No hay UI funcional completa.

---

## III. DATOS Y DEPENDENCIAS

### Catálogo

**Ubicación:** aqorath/data/catalogo_base.json
**Formato:** JSON con estructura:
```json
{
  "version": "2025-11-01T03:11:26Z",
  "accounts": {
    "1101": {
      "name_osc": "Bancos",
      "name_comercial": "Bancos",
      "tipo": "Activo",
      "subtipo": "Circulante",
      "naturaleza": "Deudora",
      "descripcion": "..."
    }
  }
}
```

**Cuentas:** 61 cuentas base (activo, pasivo, patrimonio, ingresos, gastos)

**Política actual (CONFLICTIVA):**
- docs/CATALOG_POLICY.md: "Catálogo inmutable"
- storage.py listener: previene INSERT de cuentas no en JSON
- Constitución Regla 10: Requiere "gobernado pero extensible"

**P1 HALLAZGO:** Conflicto arquitectónico explícito

---

### Dependencias (requirements.txt)

```
pandas>=2.0                 ← LEGACY
openpyxl>=3.0              ← Para Excel (export/import)
pytest>=7.0                ← Tests (DUPLICADO línea 3 y 12)
pyinstaller>=5.10          ← Compilación ejecutable
reportlab>=4.0             ← PDF
lxml>=4.9                  ← XML (CFDI)
requests                   ← HTTP
REQ                        ← ✗ INVÁLIDO (línea 8)
sqlmodel                   ← ORM
sqlalchemy                 ← SQL
python-dateutil            ← Manejo fechas
fastapi                    ← API
uvicorn                    ← ASGI server
```

**P2 HALLAZGO:** 
- Línea 8: "REQ" no es paquete válido (rompe instalación)
- Duplicados: pytest (línea 3, 12), pandas (importado pero legacy)

---

### SQLite Schema

**DB default:** ~/.local/share/aqorath/aqorath.db (AQORATH_DB env var)

**Tablas esperadas (inferidas de código):**
- account (id, code, name, nature, vat_flag, created_at)
- journalentry (id, date, concept, doc_ref, period_id, posted_by, state, created_at)
- journalline (id, entry_id, account_code, account_id, debit, credit, description, created_at)
- appconfig (id, key, value, created_at)
- asset (id, name, value, created_at)
- company (id, name, rfc, denominacion, phrase, logo_path, primary_color, secondary_color, created_at)

**Falta:** period, exercise, fisc al_rule_set, entity_profile, analytical_dimension, explanation, report_definition

---

## IV. RESIDUALES Y ARTEFACTOS

### .bak files (RESIDUO)

```
aqorath/templates.py.bak               (27KB)
aqorath/core.py.bak                    (24KB)
aqorath/models.py.bak                  (2KB)
tests/test_templates_fiscal.py.bak     (3KB)
tests/test_templates_extended.py.bak   (4KB)
tests/test_core.py.bak                 (5KB)
tests/test_more_templates.py.bak       (3KB)
```

**Estado:** No afectan funcionamiento pero generan "ruido" en repo.

---

### .patch files (RESIDUO)

```
aqorath/catalog_immutable.patch        (12KB)
patches/import_catalog_fix.patch       (16KB)
```

**Propósito aparente:** Patches de cambios en política de catálogo o imports. Documentan decisiones iterativas.

---

### __pycache__ y .pyc (RESIDUO)

Múltiples directorios __pycache__. Debe agregarse a .gitignore si no está.

---

### Test DBs (RESIDUO)

```
tests/test.db.bak.2025-11-01_023239    (32KB, vacío)
tests/test.db.bak.2025-11-01_...       (13 backups históricos)
tests/test.db                          (40KB, activo)
```

**Hallazgo:** Se crean backups durante tests pero no se limpian.

---

## V. TESTS

### Ejecución

```
Command: python -m pytest -v
Result: 26/26 PASSED (0.61s)

test/ (legacy): 16 tests
  - test_asientos.py (2)
  - test_cfdi.py (1)
  - test_cfdi_timbrado.py (1)
  - test_fiscal.py (3)
  - test_libro.py (2)
  - test_registro.py (4)
  - test_reportes.py (3)

tests/ (new): 10 tests
  - test_accounting_rules.py (1)
  - test_assets.py (1)
  - test_catalog_accounts.py (1)
  - test_core.py (1)
  - test_more_templates.py (3)
  - test_templates_extended.py (1)
  - test_templates_fiscal.py (2)
```

**Observación:** Ambas carpetas existen, ambas pasan. Transición en progreso.

---

### Cobertura

**No existe reporte de cobertura.** Tests validan comportamiento pero cobertura desconocida.

**Hallazgo P2:** Necesario agregar pytest-cov para medir cobertura.

---

## VI. MATRIZ DE BRECHAS ENTRE ESTADO ACTUAL Y ARQUITECTURA OBJETIVO

| COMPONENTE | ESTADO ACTUAL | ARQUITECTURA OBJETIVO | RIESGO | PRINCIPIO AFECTADO | PRIORIDAD |
|-----------|---|---|---|---|---|
| JournalLine.debit/credit | float | Decimal | Datos incorrectos futuro | R5 (Dinero Exacto) | P0 |
| Asset.value | float | Decimal | Datos incorrectos futuro | R5 (Dinero Exacto) | P0 |
| post_entry() persistencia | float insert | Decimal insert | Pérdida precisión | R5 (Dinero Exacto) | P0 |
| Catálogo | Inmutable | Extensible/Gobernado | Bloquea usuarios | R10 (Catálogo) | P1 |
| Dos carpetas test/ + tests/ | Duplicadas | Una sola (tests/) | Confusión mantenimiento | R24 (Autoridad) | P1 |
| modelos/libro.py fallback | Es fuente alternativa | Solo legacy fallback | Inconsistencia posible | R7 (SQLite primario) | P1 |
| AppConfig en JSON fallback | Fallback silencioso | Persistencia clara | Inconsistencia config | R6 (Local-first) | P1 |
| Explicabilidad | Nula | Explanation entity | Violación R11 | R11 (Explicabilidad) | P2 |
| Modo acompañado/operativo | No existe | Toggle en AppConfig | Violación R12 | R12 (Consentimiento) | P2 |
| Progresividad pedagógica | No existe | UserKnowledgeState | Violación R13 | R13 (Pedagogía) | P2 |
| FiscalRuleSet | No versionado | Versionado explícito | Cambios fiscales rompen | R14 (Fiscal) | P2 |
| EntityProfile | No existe | Multicomponente | Violación R15 | R15 (Entidad) | P2 |
| Módulo OSC | Catálogo ready, módulo no | Módulo integrado | OSC no soportado | R16 (OSC) | P2 |
| Dimensiones analíticas | No existen | many-to-many | Violación R17 | R17 (Dimensiones) | P2 |
| ReportDefinition | Reportes hardcoded | Templates generalizadas | Violación R18 | R18 (Documentos) | P2 |
| ReportPackage | No existe | Paquetes reutilizables | Violación R19 | R19 (Paquetes) | P2 |
| Caché de datos | No existe | Resolver automático | Reingreso de datos | R20 (Reutilización) | P3 |
| Export format doc | Falta | Especificación abierta | Violación R21 | R21 (Interoperabilidad) | P3 |
| Migraciones versionadas | Falta | Schema versioning | Riesgo upgrades | R22 (Integridad) | P2 |
| Separación de capas | Parcial | domain/appl/infra/pres | Mezcla de responsabilidades | R23 (Capas) | P1 |
| Multiple implementations | Riesgo | Una autoridad (core.py) | Inconsistencia | R24 (Autoridad) | P1 |
| Exception generic | 29 detectados | Try-except específicas | Ocultamiento errores | R25 (Fallbacks) | P2 |
| Límites de nicho | No documentados | Capabilities + docs | Usuario confundido | R26 (Nicho) | P3 |
| Prueba C (humana) | No realizada | UI funcional | Falta validación UX | R27 (Triple test) | P3 |
| Licencia | Sin definir | Decisión pendiente | Incertidumbre legal | R28 (Licencia) | P3 |

---

## VII. ANÁLISIS DETALLADO DE COMPONENTES

### core.py (905 líneas)

**Responsabilidades:**
1. generate_preview(template_key, amount, ctx) → Dict con líneas
2. post_entry(entry_dict) → {"ok": bool, "entry_id": int}
3. trial_balance(as_of) → Dict[account_code: Decimal]
4. list_templates() → [str]

**Fortalezas:**
- Motor único de lógica contable
- ORM + fallback sqlite adaptativo
- Usa Decimal para cálculos intermedios
- Valida partida doble antes de persistir

**Debilidades:**
- Retorna float para display (cosmético pero incorrecto internamente)
- Exception genéricas en fallbacks (líneas 85, 106, 131, etc.)
- _persist_entry() inserta float a BD (P0)
- Detecta dinámicamente columnas de tabla (flexible pero frágil)

**Flujo de datos:**
```
User input (amount) 
  → generate_preview() 
  → EvaluateTemplate (Decimal intermediate)
  → Retorna float lines
  → UI displays
  → Usuario confirma
  → post_entry() 
  → _persist_entry()
  → Inserta float (P0)
```

---

### templates.py (329 líneas)

**Responsabilidades:**
- Registrar plantillas de operaciones
- Resolver roles (bank, sales, expense) → account_codes via ctx
- Calcular montos (percentajes, IVA, etc.)

**Plantillas disponibles (detectadas):**
- ingreso_venta (neto)
- ingreso_venta_bruto
- egreso_compra (neto)
- [y más - revisar líneas 150+]

**Fortaleza:** Roles semánticos desacoplan usuario de códigos contables

**Debilidad:** Expresiones de cálculo retornan float, no Decimal

---

### storage.py (124 líneas)

**Listener (líneas 50-64):**
```python
@event.listens_for(Account, "before_insert")
def _prevent_non_catalog_account(mapper, connection, target):
    if code not in load_catalog_codes():
        raise ValueError("Inserción denegada: cuenta no en catálogo")
```

**Problema:** PREVIENE extensiones (violación Regla 10)

**Debería:** Validar estructura pero permitir is_canonical=False

---

### catalog.py (78 líneas)

**Dual API:**
- resolve_account_by_code(session, code) → Account ORM
- resolve_account_by_code(code) → Dict JSON

**Parámetro 'prefer':** Mencionado para futuro (osc vs comercial)

**Estado:** Base para Regla 15 (multicomponente)

---

## VIII. FLUJOS CRÍTICOS IDENTIFICADOS

### Flujo 1: Crear Asiento (Happy Path)

```
UI común (desktop/api)
  ↓ { "event_type": "sale", "amount": 1000 }
generate_preview()
  ↓ resuelve roles via ctx
templates.<operation>.create_lines()
  ↓ retorna LineSpec[]
_load_accounts_map() + role resolution
  ↓ 
Retorna preview con líneas + totales (float)
  ↓ usuario acepta
post_entry(entry_dict)
  ↓
_persist_entry()
  ├─ _verify_accounts() [sqlite o ORM]
  ├─ si ORM disponible: crea JournalEntry + JournalLine[] (float ← P0)
  └─ si fallback sqlite: inserción dinámica por PRAGMA
  ↓
Retorna {"ok": true, "entry_id": 123}
```

---

### Flujo 2: Calcular Balanza

```
trial_balance(as_of)
  ├─ _balances_from_sqlite()
  │  ├─ detecta columnas dinámicamente
  │  ├─ agrupa por account_code
  │  ├─ suma (debit - credit)
  │  └─ retorna Dict[code: Decimal]
  ├─ si vacío, fallback a _balances_from_libro()
  │  ├─ crea Libro() [DataFrames]
  │  ├─ compute_balance()
  │  ├─ adivina qué columna es "saldo"
  │  └─ retorna Dict
  └─ Merge con catálogo (cuentas con saldo cero)
  ↓
Retorna Dict[code: Decimal]
```

**Observación:** Fallback a Libro (legacy) si sqlite falla. Esto es el "segundo motor".

---

## IX. ARQUITECTURA ACTUAL VS OBJETIVO

### Actual (Coexistencia)

```
┌─ new aqorath/               ← Core actual
│  ├─ core.py (motor)
│  ├─ templates.py
│  ├─ models.py (ORM)
│  ├─ storage.py (sesión)
│  └─ ...
│
└─ legacy modelos/            ← Fallback alternativo
   ├─ libro.py (DataFrames)
   ├─ registro.py
   ├─ catalogo.py (duplica)
   └─ ...

+ root app.py / api.py / main.py  ← Entry points múltiples
```

**Problema:** Dos "motores" contables, múltiples entry points, potencial inconsistencia.

---

### Objetivo (Separación clara)

```
presentation/
  ├─ desktop.py
  ├─ api.py
  └─ cli.py

application/
  ├─ operation_service.py
  ├─ reporting_service.py
  └─ ...

domain/
  ├─ entities.py (JournalEntry, Account, etc.)
  ├─ services.py (lógica contable pura)
  └─ ...

infrastructure/
  ├─ repositories/
  │  ├─ journal_repository.py
  │  └─ account_repository.py
  ├─ persistence/
  └─ rendering/
```

**Ventaja:** Claridad, testabilidad, mantenibilidad.

---

## X. ANÁLISIS DE RIESGOS

### P0 (CRÍTICO - Puede comprometer integridad contable)

1. **Float para dinero en persistencia**
   - Impacto: Pérdida de precisión decimal en cálculos futuros
   - Mitigación: Migrar JournalLine.debit/credit a Decimal
   - Esfuerzo: Alto (cambio schema + migración datos)

2. **Fallback a Libro (DataFrames) como fuente de balanza**
   - Impacto: Dos motores podem divergir
   - Mitigación: Eliminar fallback, usar solo sqlite
   - Esfuerzo: Medio (refactorización core.py)

3. **requirements.txt "REQ" inválido**
   - Impacto: Instalación falla
   - Mitigación: Remover línea 8
   - Esfuerzo: Trivial (1 línea)

---

### P1 (GRAVE - Contradicción arquitectónica)

1. **Catálogo inmutable vs Regla 10 (extensible)**
   - Impacto: Bloquea capacidad de adaptación
   - Mitigación: Cambiar listener a validador
   - Esfuerzo: Medio

2. **Dos carpetas test/ + tests/**
   - Impacto: Confusión, mantenimiento duplicado
   - Mitigación: Consolidar a tests/, deprecate test/
   - Esfuerzo: Bajo (refactor imports en CI)

3. **Duplicación modelos/catalogo.py + aqorath/catalog.py**
   - Impacto: Posible divergencia
   - Mitigación: Usar único aqorath/catalog.py, deprecate modelos/
   - Esfuerzo: Bajo

4. **Separación de capas incompleta**
   - Impacto: Lógica contable posiblemente duplicada
   - Mitigación: Refactorización a domain/appl/infra/pres
   - Esfuerzo: Alto (reestructura significativa)

---

### P2 (TÉCNICO - Deuda que debe resolverse antes de crecer)

1. **29 except Exception genéricas** → Log específico requerido
2. **Esquema dinámico en persistencia** → Fragilidad
3. **Sin versionamiento de migraciones** → Riesgo upgrades
4. **Interfaces esqueletizadas** → Prueba C incompleta

---

### P3 (MEJORA - Limpieza/documentación/optimización)

1. **Archivos .bak residuales**
2. **Backups test.db no limpios**
3. **Sin reporte de cobertura**
4. **Documentación de límites ausente**

---

## XI. CLASIFICACIÓN DE COMPONENTES

### CANÓNICA (Mantener - Nueva arquitectura)

```
✓ aqorath/core.py
✓ aqorath/templates.py
✓ aqorath/catalog.py
✓ aqorath/models.py
✓ aqorath/storage.py
✓ aqorath/company.py
✓ aqorath/config.py
✓ aqorath/exercise.py
✓ tests/ (carpeta)
```

**Revisiones necesarias:** P0 float, P1 listener (storage)

---

### RECUPERABLE (Adaptar)

```
~ aqorath/api.py (expand endpoints)
~ aqorath/desktop.py (implementar UI)
~ aqorath/accounting_rules.py (versionamiento fiscal)
~ api/app.py (integración)
```

**Acciones:** Refactorización + documentación

---

### LEGACY (Deprecate)

```
✗ modelos/libro.py (fallback DataFrames)
✗ modelos/registro.py (validación legacy)
✗ modelos/catalogo.py (duplica aqorath/)
✗ modelos/poliza.py (pendiente reemplazo)
✗ app.py (root - reemplazar con api/app.py + main.py)
✗ test/ (carpeta - migrar a tests/)
```

**Línea de muerte:** Documentar deprecación, mantener fallbacks temporales, planificar eliminación en Phase 2

---

### PROTOTIPO (Completar)

```
◐ aqorath/desktop.py (UI muy esquelética)
◐ aqorath/api.py (stub minimal)
◐ modelos/cfdi.py (timbrado no productivo)
◐ templates/report_template.html (falta contenido)
```

---

### RESIDUO (Limpiar)

```
🗑️ aqorath/*.py.bak (7 archivos)
🗑️ aqorath/*.patch (2 archivos)
🗑️ tests/test.db.bak.* (13 backups)
🗑️ __pycache__/ (múltiples)
🗑️ *.pyc
```

---

## XII. DECISIONES PENDIENTES DE CONFIRMACIÓN HUMANA

1. ¿CFDI será funcionalidad productiva o educativa?
2. ¿Módulo OSC integrado o separable?
3. ¿Cuándo deprecate modelos/?
4. ¿Licencia social qué modelo específico?
5. ¿UI primaria: desktop (PySide) o web (FastAPI)?
6. ¿Multimoneda nunca o Phase 3?
7. ¿Depreciaciones integradas o módulo?

---

## XIII. RECOMENDACIONES INMEDIATAS (PHASE 1)

**P0 - Corregir float para dinero**
1. Cambiar JournalLine.debit/credit a Decimal
2. Cambiar Asset.value a Decimal
3. Migración de datos existentes (SQL)
4. Actualizar post_entry() para usar Decimal
5. Agregar validaciones de cuantización

**P0 - Fijar requirements.txt**
1. Remover línea "REQ"
2. Unificar duplicados

**P1 - Política de catálogo**
1. Cambiar listener a validador
2. Agregar Account.is_canonical bool
3. Permitir creación de cuentas con guía en UI

**P1 - Consolidar tests**
1. Migrar test/ → tests/
2. Actualizar imports en CI
3. Deprecate test/ carpeta

**P1 - Separación de capas**
1. Crear domain/, application/, infrastructure/
2. Mover entidades a domain/
3. Mover core.py → application/services/operation.py
4. Documentar transición

---

## XIV. ESTADO DE CFDI

**Archivo:** modelos/cfdi.py (359 líneas)
**Documentación:** docs/CFDI.md

**Clasificación:** PROTOTIPO (no productivo)

**Funcionalidad:**
- Generación de XML CFDI (estructura)
- Firma digital (esqueleto)
- Importación de timbrado (test)

**Limitaciones:**
- Timbrado real: NO (test mock)
- Validación SAT: NO
- Integración con flujo contable: Parcial

**En Phase 0:** Solo documentar estado actual

---

## XV. ESTADÍSTICAS FINALES

| Métrica | Valor |
|---------|-------|
| Total archivos Python | ~90 |
| Total líneas de código | ~4800 |
| Líneas core/lógica | ~2000 |
| Líneas tests | ~800 |
| Tests ejecutables | 26 |
| Tests pasando | 26 (100%) |
| Archivos .bak residuales | 7 |
| Except Exception genéricas | 29 |
| Entry points distintos | 5 |
| Carpetas test | 2 |
| Fallbacks arquitectónicos | 4+ |
| Componentes CANÓNICA | 9 |
| Componentes LEGACY | 6 |
| Componentes PROTOTIPO | 7 |
| Componentes RESIDUO | 20+ |

---

## XVI. CONCLUSIONES

### Estado Actual
Aqorath es un **ERP funcional pero en transición.** La arquitectura nueva (aqorath/) es sólida pero incompleta. La legacy (modelos/) existe como fallback pero genera riesgos de inconsistencia.

### Fortalezas
- Motor contable unificado (core.py)
- Fallbacks defensivos (ORM + sqlite)
- Pruebas automatizadas (26 tests)
- Catálogo bien estructurado
- Local-first + SQLite

### Debilidades Críticas
- Float para dinero (P0)
- Catálogo inmutable bloquea (P1)
- Dos arquitecturas coexisten (P1)
- Interfaces esqueletizadas (falta Prueba C)
- Documentación de arquitectura ausente hasta hoy

### Camino Adelante
1. Corregir P0 (float → Decimal)
2. Resolver P1 (catálogo, capas, tests consolidados)
3. Completar arquitectura objetivo
4. Implementar explicabilidad + pedagogía
5. Deprecate legacy gradualmente

---

## XVII. REFERENCIAS

- AQORATH_CONSTITUTION_V1.md (28 principios)
- ARCHITECTURE_BASELINE_V1.md (diseño objetivo)
- pytest output: 26/26 PASSED
- Git log: Cambios frecuentes en catalogo.py, core.py
- Código: aqorath/ como fuente canónica

