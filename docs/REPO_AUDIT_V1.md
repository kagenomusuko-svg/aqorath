# AUDITORÍA DE REPOSITORIO AQORATH - V1.0

**Documento:** Inspección exhaustiva del estado actual del repositorio Aqorath  
**Fecha:** 2025-11-01  
**Fecha de Ejecución:** 2025-11-01  
**Versión:** 1.0  
**Fase:** Fase 0 - Auditoría Constitucional

---

## EXECUTIVE SUMMARY

### Estadísticas Generales

- **Líneas de código (Python):** ~5,413 líneas
- **Tests ejecutados:** 10 passed
- **Resultado de tests:** ✅ EXITOSO (10/10)
- **Archivos Python:** 50+
- **Archivos de backup/residuo:** 16 (bak, patch, diff)
- **Bases de datos de prueba:** 13 (backups de test.db)

### Hallazgos Críticos

| Severidad | Cantidad | Categoría |
|-----------|----------|-----------|
| **P0 (Integridad Contable)** | 4 | Float para dinero, Fallbacks ocultadores, Partida doble débil, Múltiples fuentes de verdad |
| **P1 (Contradicción Arquitectónica)** | 3 | Catálogo Immutable vs. Gobernado, APIs duplicadas, Capas confusas |
| **P2 (Deuda Técnica)** | 8 | Dependencias inválidas, Código legacy, Archivos residuales, Bug en config.py |
| **P3 (Mantenibilidad)** | 12 | Documentación desactualizada, Paths hardcodeados, Fallbacks defensivos |

### Clasificación de Componentes

| Estado | Cantidad | Ejemplos |
|--------|----------|----------|
| **CANÓNICO** | 8 | core.py, models.py, storage.py, templates.py, exercise.py |
| **RECUPERABLE** | 5 | desktop.py, api.py, catalog.py, import_catalog.py, assets.py |
| **LEGACY** | 8 | modelos/*, test/* |
| **DUPLICADO** | 3 | api.py (raíz) vs aqorath/api.py, api/app.py |
| **RESIDUO** | 16 | archivos .bak, .patch, test.db backups |
| **PROTOTIPO** | 2 | modelos/cfdi.py (CFDI legacy) |
| **INCIERTO** | 4 | desktop.py, config.py (BUG), algunos scripts |

---

## PARTE I: INVENTARIO EXHAUSTIVO

### I.1 ANÁLISIS POR CARPETA

#### **aqorath/** - Núcleo Nuevo

**Clasificación: CANÓNICO + RECUPERABLE**

| Archivo | Líneas | Rol | Estado | Notas |
|---------|--------|-----|--------|-------|
| core.py | 905 | Motor central de operaciones | CANÓNICO | Contiene lógica de aplicación + dominio + persistencia. Fallbacks a SQLite. Usa float para cálculos. |
| models.py | 52 | Modelos ORM (SQLModel) | CANÓNICO | JournalLine.debit/credit son float. account_code y account_id opcionales. |
| storage.py | 124 | Sesiones SQLite + listeners | CANÓNICO | Listener en INSERT valida contra catálogo, pero NO en UPDATE (BUG). |
| templates.py | 329 | Reglas de operaciones contables | CANÓNICO | Usa float en expresiones de cálculo. Implementa operaciones como venta, compra, etc. |
| accounting_rules.py | 52 | Reglas de resultado del ejercicio | CANÓNICO | Simple, funciona con Decimal (bien). |
| exercise.py | 330 | Cierre de ejercicio contable | CANÓNICO | Fallback a SQLite. Calcula resultado, transfiere a cuentas 3103/3104. |
| catalog.py | 78 | Acceso a catálogo (JSON + BD) | RECUPERABLE | Dual API: (session, code) o (code). Mezcla JSON y BD. |
| config.py | 131 | Configuración global | RECUPERABLE | **BUG CRÍTICO en línea 65**: `AppConfig.select()` no existe en SQLModel. Debería usar `select(AppConfig)`. |
| desktop.py | 251 | UI PySide | RECUPERABLE | Interfaz gráfica. Incompleta. Depende de core.py. |
| api.py | 164 | API REST (FastAPI) | RECUPERABLE | Endpoints para company, CFDI, reportes. **DUPLICADO de api.py en raíz**. |
| company.py | 17 | Modelo de empresa | CANÓNICO | Simple: nombre, RFC, logo, colores. |
| assets.py | 76 | Gestión de activos fijos | RECUPERABLE | Calcula depreciación. Usa float (incorrectamente). |
| tax.py | 70 | Funciones de impuestos | RECUPERABLE | Muy básico. No versionado. |
| import_catalog.py | 210 | Importador de catálogo | RECUPERABLE | Carga XLSX/CSV hacia JSON. Útil pero puede mejorarse. |
| utils.py | ? | Utilidades varias | CANÓNICO | Routines auxiliares. |
| template_utils.py | ? | Utilidades de templates | CANÓNICO | Funciones auxiliares para templates. |
| __init__.py | 4 | Inicialización del paquete | CANÓNICO | Básico. |

**UI/**
- main_window.py (3.5 KB) - Ventana principal PySide - RECUPERABLE
- welcome.py (4.3 KB) - Pantalla de bienvenida - RECUPERABLE

**data/**
- catalogo_base.json - Catálogo embebido - CANÓNICO (aunque su política es inmutable)

**templates/**
- Plantillas Jinja2 para reportes - CANÓNICO

---

#### **modelos/** - Arquitectura Legacy

**Clasificación: LEGACY + PROTOTIPO**

| Archivo | Líneas | Rol | Estado | Notas |
|---------|--------|-----|--------|-------|
| libro.py | 779 | Libro contable con Pandas | LEGACY | Motor alternativo basado en DataFrames. Puede divergir de SQLite. |
| registro.py | 271 | Registro de operaciones | LEGACY | Manejo de registros contables. Legacy. |
| cfdi.py | 359 | CFDI (Facturación) | PROTOTIPO | Generación de CFDI. Estado desconocido (¿timbrado real o documentación?). |
| poliza.py | 74 | Póliza contable | LEGACY | Representación de póliza. Legacy. |
| catalogo.py | 64 | Catálogo (legacy) | LEGACY | Anterior al JSON. |
| hoja.py | 59 | Hoja de cálculo interna | LEGACY | DataFrames. |
| parametros.py | 97 | Parámetros fiscales | LEGACY | Configuración fiscal old-style. |
| reportes.py | 118 | Reportes legacy | LEGACY | Generación de reportes con Pandas. |
| xsdutils.py | 63 | Utilidades XSD | LEGACY | Manejo de esquemas XSD. Poco usado. |

**Conclusión:** Módulo completo puede ser deprecado en Fase 2.

---

#### **api/** - API Simplificada

**Clasificación: DUPLICADO**

| Archivo | Líneas | Rol | Estado | Notas |
|---------|--------|-----|--------|-------|
| app.py | 39 | API FastAPI minimalista | DUPLICADO | Solo endpoints básicos (/templates, /preview, /post). **Duplica aqorath/api.py**. |

**Conclusión:** Debe consolidarse en una sola API.

---

#### **test/** - Tests Legacy

**Clasificación: LEGACY**

- test_asientos.py (64 líneas)
- test_libro.py (62 líneas)
- test_fiscal.py (98 líneas)
- test_cfdi.py (49 líneas)
- test_cfdi_timbrado.py (49 líneas)
- test_reportes.py (62 líneas)
- test_registro.py (64 líneas)
- conftest.py

**Conclusión:** Tests de módulos legacy. Pueden ser migrados a tests/ o descartados.

---

#### **tests/** - Tests Nuevos

**Clasificación: CANÓNICO**

```
tests/
├── conftest.py (75 líneas)             - Fixtures, inicialización
├── test_accounting_rules.py            - ✅ PASSA
├── test_assets.py                      - ✅ PASSA
├── test_catalog_accounts.py            - ✅ PASSA
├── test_core.py (150+ líneas)          - ✅ PASSA (main test de core)
├── test_more_templates.py (72 líneas)  - ✅ PASSA (3 tests)
├── test_templates_extended.py          - ✅ PASSA
├── test_templates_fiscal.py (49 líneas) - ✅ PASSA (2 tests)
├── test.db (BD de prueba)
└── test.db.bak.* (13 backups)          - RESIDUO
```

**Resumen de Tests Ejecutados:**
```
============================= test session starts ==============================
collected 10 items

tests/test_accounting_rules.py::test_resultado_simple PASSED             [ 10%]
tests/test_assets.py::test_monthly_depr PASSED                           [ 20%]
tests/test_catalog_accounts.py::test_catalog_codes_have_single_account PASSED [ 30%]
tests/test_core.py::test_generate_preview_and_post PASSED                [ 40%]
tests/test_more_templates.py::test_nota_credito PASSED                   [ 50%]
tests/test_more_templates.py::test_pago_con_retencion_iva PASSED         [ 60%]
tests/test_more_templates.py::test_nomina_basic PASSED                   [ 70%]
tests/test_templates_extended.py::test_ingreso_net_with_vat PASSED       [ 80%]
tests/test_templates_fiscal.py::test_ingreso_gross_with_vat PASSED       [ 90%]
tests/test_templates_fiscal.py::test_honorarios_with_isr_and_post PASSED [100%]

============================== 10 passed in 0.71s ===============================
```

**Conclusión:** Tests ejecutados exitosamente. Pero coverage desconocido, y qué lógica realmente prueban es incierto.

---

#### **scripts/** - Utilidades

**Clasificación: RECUPERABLE + LEGACY**

18 scripts presentes:
- init_db.py, init_catalog_db.py - Inicialización
- fix_test_db.py - Reparación de BD de prueba
- generate_and_validate_demo.py, generate_depr.py - Generación de datos
- Múltiples scripts de "ensure", "assign", "clean", "convert", "sync" - Mantenimiento

**Conclusión:** Muchos scripts = falta de automatización clara. Posible deuda técnica.

---

#### **patches/** - Patches Experimentales

**Clasificación: RESIDUO + INCIERTO**

- catalog_immutable.patch (12 KB) - Patch para hacer catálogo mutable (experimental)
- import_catalog_fix.patch - Fix para importador
- nomina_patch.diff - Patch para nómina

**Conclusión:** Patches no aplicados = cambios en limbo. Decidir si aplicar o descartar.

---

#### **docs/** - Documentación

**Archivos Existentes:**
- CATALOG_POLICY.md - Política actual (inmutable)
- CFDI.md - Documentación de CFDI

**Archivos Nuevos (esta auditoría):**
- AQORATH_CONSTITUTION_V1.md ✅
- ARCHITECTURE_BASELINE_V1.md ✅
- REPO_AUDIT_V1.md (este documento) ✅

---

#### **assets/** - Datos de Entrada

- catalogo.xlsx (8 KB) - Catálogo en Excel (fuente)
- catalogo.csv (8 KB) - Catálogo en CSV

**Conclusión:** Fuente del catálogo. Debe actualizarse regularmente.

---

#### **Root Level Files**

| Archivo | Rol | Estado | Notas |
|---------|-----|--------|-------|
| api.py (164 L) | API REST | DUPLICADO | Idéntico a aqorath/api.py. Debería eliminarse. |
| main.py (4 L) | Entry point | CANÓNICO | Inicializa y lanza app. |
| app.py (4 L) | Legacy entry | LEGACY | Probablemente no usado. |
| desktop.py (4 L) | UI entry | RECUPERABLE | Lanza interfaz desktop. |
| company.py (4 L) | Legacy | LEGACY | Probablemente duplica aqorath/company.py. |
| utils.py (4 L) | Utilidades | LEGACY | Legacy. |
| validate_run.py | Validador | INCIERTO | Desconocido. |
| reports_jinja.py | Reportes | RECUPERABLE | Generador de reportes PDF. |
| name-app.py | ? | INCIERTO | Desconocido. |
| requirements.txt | Dependencias | ERROR | Tiene "REQ" inválido en línea 8. pytest duplicado. |
| pyproject.toml | Build | CANÓNICO | Minimal pero funciona. |
| setup.cfg | Setup | CANÓNICO | Metadata básica. |

---

### I.2 ANÁLISIS DE DEPENDENCIAS

#### **requirements.txt - PROBLEMAS DETECTADOS**

```
1  pandas>=2.0
2  openpyxl>=3.0
3  pytest>=7.0
4  pyinstaller>=5.10
5  reportlab>=4.0
6  lxml>=4.9
7  requests
8  REQ                              ❌ INVÁLIDO (No es paquete)
9  sqlmodel
10 sqlalchemy
11 python-dateutil
12 pytest                           ❌ DUPLICADO (línea 3)
13 fastapi
14 uvicorn
```

**Problemas:**
- P2: Línea 8 ("REQ") causa fallos de instalación
- P2: pytest duplicado (línea 3 y 12)
- P2: Falta importar otros: PySide2/PySide6 para desktop.py, Jinja2 para templates

**Impacto:** Dependencia faltante de PySide causará error al ejecutar desktop.py.

#### **Dependencias Detectadas en Uso:**

```python
# Declaradas correctamente:
- sqlalchemy, sqlmodel
- fastapi, uvicorn
- pandas
- openpyxl (Excel)
- reportlab (PDF)
- lxml (XML)
- requests

# Usadas pero NO declaradas:
- PySide2 o PySide6 (desktop.py, aqorath/ui/*)      ❌ FALTA
- Jinja2 (templates.py, aqorath/api.py)            ❌ FALTA
- Click (si hay CLI)                               ? INCIERTO
- cryptography (si hay encriptación)               ? INCIERTO
```

---

### I.3 ANÁLISIS DE ENTRY POINTS

**Puntos de Entrada al Sistema:**

| Punto de Entrada | Ubicación | Estado | Responsabilidad |
|------------------|-----------|--------|-----------------|
| **Desktop UI** | main.py → desktop.py → aqorath/desktop.py | RECUPERABLE | Interfaz PySide |
| **API REST** | main.py → api.py (raíz) o aqorath/api.py | DUPLICADO | FastAPI server |
| **CLI (si existe)** | ? | NO ENCONTRADO | Línea de comandos |
| **Batch/Scripts** | scripts/*.py | RECUPERABLE | Automatización |

**Problema:** Múltiples entry points, algo confuso. main.py no está claro sobre qué lanza.

---

### I.4 FUENTES DE PERSISTENCIA

**MÚLTIPLES FUENTES DE VERDAD:**

| Fuente | Ubicación | Rol | Problema |
|--------|-----------|-----|---------|
| **SQLite (Primaria Declarada)** | ~/.local/share/aqorath/aqorath.db | BD contable | Validaciones débiles |
| **JSON (Catálogo)** | aqorath/data/catalogo_base.json | Catálogo embebido | Compite con tabla Account |
| **Pandas/Excel (Legacy)** | modelos/libro.py | Motor alternativo | Puede divergir |
| **Fallback en core.py** | core.py líneas 715-856 | Persistencia adaptativa | Peligroso, ocultador |

**P0 CRÍTICO:** Existen múltiples vías de persistencia sin sincronización garantizada.

---

### I.5 ESTADO DE CFDI

**Hallazgo:** Estado desconocido. Documentación vs. código pueden divergir.

**Indicios:**
- test_cfdi.py (✅ executes)
- test_cfdi_timbrado.py (✅ executes) - "timbrado" sugiere facturación real
- modelos/cfdi.py (359 líneas) - Generación de CFDI legacy
- docs/CFDI.md (documentación)
- CFDI generación en aqorath/api.py (endpoints)

**Incertidumbre:**
- ¿Es timbrado real o simulado?
- ¿Integración con SAT o mock?
- ¿Production-ready?

**Recomendación:** Auditar CFDI separadamente. No está claro si es prototipo o funcional.

---

### I.6 ARQUIVOS RESIDUALES

**Archivos de Backup/Cleanup Detectados:**

```
aqorath/
├── _init_.py.bak.2025-11-01_165452          - RESIDUO
├── catalog.py.bak.2025-11-01_163339         - RESIDUO (vacío)
├── catalog.py.bak.2025-11-01_164132         - RESIDUO
├── catalog.py.bak.2025-11-01_165441         - RESIDUO
├── core.py.bak                               - RESIDUO
├── models.py.bak                             - RESIDUO
├── templates.py.bak                          - RESIDUO

tests/
├── test.db.bak.2025-11-01_*                 - RESIDUO (13 archivos)
├── test.db.manualbak.2025-11-01_234458     - RESIDUO
├── test_core.py.bak                         - RESIDUO
├── test_more_templates.py.bak               - RESIDUO
├── test_templates_extended.py.bak           - RESIDUO
├── test_templates_fiscal.py.bak             - RESIDUO

Root:
├── nomina_patch.diff                        - RESIDUO/INCIERTO
├── catalog_immutable.patch                  - RESIDUO/INCIERTO
├── patches/import_catalog_fix.patch         - RESIDUO/INCIERTO
```

**Conclusión:** 16+ archivos residuales. Limpiar repositorio.

---

## PARTE II: HALLAZGOS CRÍTICOS (P0)

### H1: DINERO COMO FLOAT - VIOLACIÓN DE PRINCIPIO 5

**Severidad:** P0 (Integridad Contable)

**Ubicaciones:**

1. **models.py (líneas 43-44)**
   ```python
   class JournalLine:
       debit: float = 0.0      # ❌ INCORRECTO
       credit: float = 0.0     # ❌ INCORRECTO
   ```

2. **templates.py (múltiples)**
   - Línea 37: `return lambda amount, ctx: float(amount_fixed)`
   - Línea 43: `round(float(amount) * float(rate), 2)`
   - Línea 59: `round(float(amount) / (1.0 + vat), 2)`
   - Línea 68: `return round(float(amount) - base, 2)`

3. **core.py (línea 836)**
   ```python
   insert_vals.append(float(ln.get("debit") or 0))
   insert_vals.append(float(ln.get("credit") or 0))
   ```

**Impacto:**
- Pérdida de precisión en operaciones
- Asientos potencialmente descuadrados por centavos
- Incapacidad de justificar centavos ante SAT/auditoría
- Errores de redondeo acumulados

**Evidencia en Tests:**
- test_more_templates.py::test_pago_con_retencion_iva
- test_templates_extended.py::test_ingreso_net_with_vat
- Todos estos tests probablemente enmascaran errores de float

**Resolución:** Migrar a Decimal (decimal.Decimal). FASE 3.

---

### H2: MÚLTIPLES FUENTES DE VERDAD - VIOLACIÓN DE PRINCIPIO 6 y 7

**Severidad:** P0 (Integridad Contable)

**Fuentes Identificadas:**

1. **SQLite (primaria declarada)**
   - Tabla: account, journal_entry, journal_line
   - Ubicación: ~/.local/share/aqorath/aqorath.db

2. **JSON (catálogo)**
   - Ubicación: aqorath/data/catalogo_base.json
   - Compite con tabla Account

3. **Pandas/Excel (legacy)**
   - Clase Libro en modelos/libro.py
   - Puede mantener estado paralelo

4. **Fallbacks sin sincronización**
   - core.py _persist_entry() (líneas 715-856)
   - Si ORM falla, intenta SQLite directo
   - Adaptaciones dinámicas de schema

**Impacto:**
- Usuario podría estar trabajando en diferentes "realidades contables"
- Migraciones sin sincronización
- Sin garantía de que ambas fuentes muestren el mismo estado

**Evidencia:**
- exercise.py línea 94: "Inserta entry y journallines directamente en sqlite"
- core.py línea 708: "ORM persist failed, falling back to sqlite"
- modelos/libro.py: Motor completamente paralelo

**Resolución:** Consolidar en SQLite como única fuente. Deprecar legacy. FASE 2.

---

### H3: CATÁLOGO - CONFLICTO DE POLÍTICAS

**Severidad:** P0 / P1 (Contradicción Arquitectónica)

**Conflicto Explícito:**

- **CATALOG_POLICY.md** (línea 7): "El catálogo contable es... inmutable"
- **AQORATH_CONSTITUTION_V1.md** (Principio 10): "Catálogo gobernado y extensible"

**Estado Actual:**
```
Catálogo JSON (aqorath/data/catalogo_base.json)
    ↓
Importado a tabla Account en BD
    ↓
Validación en storage.py (listener before_insert)
    ↓
Previene inserción de cuentas no-catálogo
    ↓
PERO listener solo se registra en INSERT, no en UPDATE
    ↓
Vulnerabilidad: UPDATE puede cambiar code a no-catálogo
```

**Restricción Actual:**
```python
# storage.py línea 50-64
@event.listens_for(Account, "before_insert")
def _prevent_non_catalog_account(mapper, connection, target):
    # Valida contra catálogo
    if code_str not in catalog_codes:
        raise ValueError(...)
```

**BUG:** UPDATE no está validado.

**Conflicto de Decisión:**
- ¿Será el catálogo extensible (usuario puede crear cuentas)?
- ¿O será completamente inmutable?
- Decisión aún pendiente.

**Resolución:** Fase 0 documentó ambas opciones. Decisión humana en FASE 1.

---

### H4: FALLBACKS OCULTADORES DE ERRORES - VIOLACIÓN DE PRINCIPIO 25

**Severidad:** P0 (Riesgo de Integridad)

**core.py _persist_entry() (líneas 715-856):**

```python
# Fallback 1: Búsqueda dinámica de tabla
for candidate in ("entry", "journalentry", "journal_entry"):
    cur.execute("SELECT name FROM sqlite_master...")
    if cur.fetchone():
        entry_table = candidate
        break
# Si ninguno existe, error. Pero si existe alguno, continúa.

# Fallback 2: Inspección dinámica de columnas
cur.execute(f"PRAGMA table_info('{entry_table}')")
pragma_rows = cur.fetchall()
for cid, colname, coltype, notnull, dflt_value, pk in pragma_rows:
    # Adapta inserción a lo que encuentra

# Fallback 3: Rellena con defaults si NULL
if notnull and dflt_value is None:
    if "CHAR" in ctype:
        insert_vals.append("posted")  # ¿De dónde sabe que "posted" es válido?
    elif "INT" in ctype:
        insert_vals.append(0)         # Rellena con cero
```

**Peligros:**
- Puede persistir asiento sin saber qué cuentas toca
- Puede rellenar campos "status" con valores inventados
- Continúa cuando debería fallar

**Ejemplo Problemático:**
- Si tabla tiene columna "state" INT NOT NULL sin default
- El fallback rellena con 0
- Pero 0 podría no ser un estado válido
- Asiento se persiste en estado inválido

**P0 Crítico:** Para un ERP contable, captura genérica de Exception es especialmente peligrosa.

**Resolución:** Eliminar fallbacks, fallar explícitamente. FASE 1.

---

### H5: PARTIDA DOBLE DÉBIL - VIOLACIÓN DE PRINCIPIO 4

**Severidad:** P0 (Validación Insuficiente)

**Debilidades:**

1. **Validación en preview, persistencia separada**
   - core.py generate_preview() calcula si está balanceado (línea 883)
   - Pero persistencia (_persist_entry) es código separado
   - Posible desincronización

2. **Exercise.py bypassa validaciones**
   - Línea 94-128: inserta transferencia de resultado directamente en SQLite
   - No pasa por _persist_entry()
   - No valida partida doble antes de INSERT

3. **JournalLine sin cuenta**
   - account_code y account_id son ambos Optional
   - Válido tener línea sin saber qué cuenta toca
   - Debería ser un error

**Evidencia:**
```python
# exercise.py línea 115-128
cur.execute(f"INSERT INTO {jl_table} ({cols_sql}) VALUES ({placeholders})", ...)
# Inserta directamente, sin validación
```

**Resolución:** Centralizar validación en dominio, hacer que todas las rutas pasen por ella. FASE 1.

---

## PARTE III: HALLAZGOS SECUNDARIOS (P1)

### H6: APIs DUPLICADAS - VIOLACIÓN DE PRINCIPIO 24

**Severidad:** P1 (Contradicción Arquitectónica)

**Duplicidad Detectada:**

1. **aqorath/api.py** (164 líneas)
   - Endpoints: /company, /reports, /logo
   - Usa FastAPI
   - Importa core.generate_preview

2. **api.py** (164 líneas, en raíz)
   - Idéntico al anterior
   - Copy-paste

3. **api/app.py** (39 líneas)
   - Endpoints: /templates, /preview, /post
   - Más simple
   - Usa funciones de core.py

**Problema:** Tres APIs, posiblemente con lógica divergente.

**Restricción Violada:** Principio 24 - "Una Sola Autoridad de Negocio". Todas las superficies deben consumir los mismos casos de uso.

**Resolución:** Consolidar en una sola API. FASE 1.

---

### H7: CAPAS CONFUSAS - VIOLACIÓN DE PRINCIPIO 23

**Severidad:** P1 (Contradicción Arquitectónica)

**Problemas:**

1. **core.py mezcla capas**
   - 905 líneas de lógica heterogénea
   - Líneas 1-150: Helpers y fallbacks
   - Líneas 154-200: Preview (aplicación)
   - Líneas 630-700: Generación de asiento (dominio)
   - Líneas 710-856: Persistencia con fallbacks (infraestructura)

2. **templates.py mezcla capas**
   - Reglas de dominio (operaciones contables)
   - Expresiones de cálculo (templates de aplicación)

3. **Sin abstracción clara**
   - UI llama directamente a core.py
   - core.py accede a BD
   - No existe capa de aplicación explícita

**Impacto:**
- Difícil de testear (sin BD, fallan tests de dominio)
- Difícil de reutilizar (UI está acoplada a core.py)
- Difícil de evolucionar (cambios en core afectan todo)

**Resolución:** Refactorizar en capas (Presentation → Application → Domain → Infrastructure). FASE 1.

---

### H8: BUG EN config.py - LLAMADA A MÉTODO INEXISTENTE

**Severidad:** P1 / P2 (Código Quebrado)

**config.py línea 65:**
```python
row = s.exec(AppConfig.select().where(AppConfig.key == DB_KEY)).one_or_none()
```

**Problema:** SQLModel no tiene método `.select()` en el modelo. Debería usar:
```python
from sqlmodel import select
row = s.exec(select(AppConfig).where(AppConfig.key == DB_KEY)).one_or_none()
```

**Impacto:** config.py probablemente no funciona cuando se llama _read_db().

**Resolución:** Corregir llamadas a select(). FASE 1.

---

## PARTE IV: HALLAZGOS TERCIARIOS (P2)

### H9: DEPENDENCIAS INVÁLIDAS EN requirements.txt

**Severidad:** P2 (Fallos de Instalación)

- Línea 8: "REQ" no es un paquete válido → Causa error de instalación
- Línea 12: "pytest" duplicado (ya en línea 3)
- Faltan dependencias: PySide2/6, Jinja2

**Resolución:** Corregir requirements.txt. FASE 1.

---

### H10: CÓDIGO LEGACY SIN DEPRECACIÓN

**Severidad:** P2 (Deuda Técnica)

- modelos/ (8 archivos, 779+ líneas)
- test/ (7 archivos)
- app.py, desktop.py, company.py (raíz)

Sin marcas de deprecation. Usuarios no saben qué evitar.

**Resolución:** Deprecar explícitamente. FASE 2.

---

### H11: DOCUMENTACIÓN DESACTUALIZADA

**Severidad:** P2 (Mantenibilidad)

- CATALOG_POLICY.md dice "immutable" pero AQORATH_CONSTITUTION dice "extensible"
- CFDI.md no dice si es timbrado real o simulado
- No hay README claro sobre cómo instalar/ejecutar

**Resolución:** Centralizar documentación. FASE 1.

---

### H12: PATHS HARDCODEADOS

**Severidad:** P2 (Portabilidad)

- core.py línea 72: hardcoded paths
- exercise.py línea 60: `~/.local/share/aqorath/ejercicios`
- storage.py línea 10: `~/.local/share/aqorath/aqorath.db`

**Resolución:** Usar configuración centralizada. FASE 1.

---

## PARTE V: MATRIZ DE BRECHAS (GAP MATRIX)

| # | Componente | Estado Real | Riesgo | Principio Afectado | Destino Probable | Prioridad | Fase |
|---|-----------|-------------|--------|-------------------|-----------------|-----------|------|
| 1 | JournalLine.debit/credit (float) | float | ALTO | Principio 5 | Convertir a Decimal | P0 | 3 |
| 2 | Múltiples fuentes de verdad | SQLite + Pandas + JSON | ALTO | 6, 7 | Consolidar en SQLite | P0 | 2 |
| 3 | Catálogo Immutable vs. Extensible | Conflicto documentado | ALTO | 10 | Resolver decisión | P0/P1 | 1 |
| 4 | Fallbacks en core.py | Adaptativos, ocultan errores | ALTO | 25 | Eliminar, fallar explícitamente | P0 | 1 |
| 5 | Partida Doble débil | Validación en preview, persistencia separada | ALTO | 4 | Centralizar validación | P0 | 1 |
| 6 | APIs duplicadas | 3 APIs (aqorath/api, api, api/app) | MEDIO | 24 | Consolidar en 1 | P1 | 1 |
| 7 | Capas mezcladas | core.py, templates.py | MEDIO | 23 | Refactorizar en capas | P1 | 1 |
| 8 | BUG config.py línea 65 | AppConfig.select() no existe | MEDIO | - | Corregir select() | P1 | 1 |
| 9 | requirements.txt inválido | "REQ", pytest duplicado | BAJO | - | Corregir dependencias | P2 | 1 |
| 10 | Archivos residuales | .bak, .patch, test.db.* | BAJO | - | Limpiar repo | P2 | 1 |
| 11 | Código legacy sin deprecación | modelos/, test/ | BAJO | - | Deprecar explícitamente | P2 | 2 |
| 12 | Documentación desactualizada | CATALOG_POLICY vs. CONSTITUTION | BAJO | - | Unificar docs | P2 | 1 |
| 13 | Listener de catálogo débil | No valida UPDATE | BAJO | 10 | Mejorar listener | P2 | 1 |
| 14 | CFDI estado desconocido | Prototipo o funcional? | BAJO | - | Auditar separadamente | P3 | 2 |
| 15 | Paths hardcodeados | ~/.local/share/aqorath | BAJO | 6 | Configuración centralizada | P2 | 1 |

---

## PARTE VI: CLASIFICACIÓN DE COMPONENTES

### CANÓNICO (Mantener, Mejorar)
- ✅ core.py - Motor central (refactorizar capas)
- ✅ models.py - Modelos ORM (convertir debit/credit a Decimal)
- ✅ storage.py - Sesiones SQLite (mejorar listener)
- ✅ templates.py - Operaciones contables (convertir a Decimal)
- ✅ accounting_rules.py - Reglas de resultado
- ✅ exercise.py - Cierre de ejercicio (centralizar validaciones)
- ✅ company.py - Modelo de empresa
- ✅ tests/ - Tests nuevos

### RECUPERABLE (Adaptación Importante)
- ⚠️ desktop.py - UI PySide (incompleta, depende de refactorización)
- ⚠️ api.py (aqorath/) - API REST (consolidar APIs)
- ⚠️ catalog.py - Acceso a catálogo (mezcla JSON + BD)
- ⚠️ import_catalog.py - Importador (mejora necesaria)
- ⚠️ assets.py - Activos fijos (convertir a Decimal)
- ⚠️ config.py - Configuración (corregir BUG línea 65)
- ⚠️ tax.py - Impuestos (no versionado)
- ⚠️ reports_jinja.py - Generación de reportes

### LEGACY (Deprecar/Eliminar)
- ❌ modelos/ - Motor Pandas (8 archivos)
- ❌ test/ - Tests viejos (7 archivos)
- ❌ app.py, desktop.py, company.py (raíz)
- ❌ utils.py (raíz)

### DUPLICADO (Consolidar)
- 🔄 api.py (raíz) ← fusionar a aqorath/api.py
- 🔄 api/app.py ← fusionar a aqorath/api.py

### RESIDUO (Limpiar)
- 🗑️ Archivos .bak (16)
- 🗑️ Patches no aplicados (3)
- 🗑️ test.db.* backups (13)
- 🗑️ name-app.py
- 🗑️ validate_run.py (si no se usa)

### PROTOTIPO (Auditar)
- 🧪 modelos/cfdi.py (¿timbrado real?)
- 🧪 desktop.py (UI incompleta)

### INCIERTO (Investigar)
- ❓ config.py (¿se usa? Tiene BUG)
- ❓ CFDI endpoints (productivo?)
- ❓ CLI (¿existe?)

---

## PARTE VII: LISTA COMPLETA DE PROBLEMAS A RESOLVER

### ANTES de Fase 1 (Decisiones Humanas)

- [ ] **Decisión: Catálogo extensible o inmutable?**
  - Opción A: Implementar Principio 10 (extensible gobernado)
  - Opción B: Mantener inmutable (revisar CONSTITUTION)
  - Plazo: Antes de Fase 1

- [ ] **Decisión: CFDI estado?**
  - ¿Timbrado real o simulado?
  - ¿Production-ready?
  - Plazo: Antes de Fase 2

- [ ] **Decisión: Licencia social?**
  - ¿AGPL, Elastic, Custom?
  - Plazo: Después de Fase 1

### Fase 1 (Refactorización Arquitectónica)

- [ ] Separar capas (Presentation → Application → Domain → Infrastructure)
- [ ] Consolidar APIs (aqorath/api.py + api.py + api/app.py → 1)
- [ ] Corregir BUG config.py (select())
- [ ] Corregir requirements.txt
- [ ] Eliminar fallbacks en core.py
- [ ] Centralizar validación de partida doble
- [ ] Deprecar modelos/ explícitamente
- [ ] Crear abstracción Repository
- [ ] Unificar documentación

### Fase 2 (Eliminación de Legacy)

- [ ] Eliminar modelos/
- [ ] Eliminar test/
- [ ] Eliminar archivos residuales (bak, patch, etc.)
- [ ] Migrar importers a nuevos tests

### Fase 3 (Exactitud Numérica)

- [ ] Convertir JournalLine.debit/credit a Decimal
- [ ] Convertir templates a Decimal
- [ ] Convertir exercise.py a Decimal
- [ ] Re-validar todos los tests

### Fase 4 (Catálogo Gobernado)

- [ ] Implementar extensiones controladas
- [ ] UI para crear extensiones
- [ ] Mejorar listener de catálogo (UPDATE)

### Fase 5 (Fiscal Versionado)

- [ ] Separar tax/ del núcleo
- [ ] Implementar FiscalRuleSet
- [ ] Soportar múltiples periodos

### Fase 6 (OSC Primera Clase)

- [ ] Modelos Program, Fund, Donation
- [ ] Dimensiones analíticas
- [ ] Reportes OSC

---

## CONCLUSIÓN

**Estado General:** El repositorio tiene un **núcleo viable** (tests pasan) pero con **problemas arquitectónicos críticos** (múltiples fuentes de verdad, dinero como float, capas mezcladas).

**Próximos Pasos:**

1. ✅ **COMPLETADO:** Fase 0 - Auditoría y Constitución
2. → **SIGUIENTE:** Fase 1 - Refactorización Arquitectónica (Separación de capas, consolidación de APIs, correcciones de bugs)
3. → Fase 2 - Eliminación de Legacy
4. → Fase 3 - Exactitud Numérica
5. → ... (Fases 4-6)

**Estimación:** 10-15 sprints para completar Fases 1-3 (asumiendo 2 dev-weeks por fase).

---

**Documento Finalizado:** 2025-11-01  
**Auditoría Conducida Por:** Claude (Fase 0 Automated Review)  
**Próxima Revisión:** Tras Fase 1
