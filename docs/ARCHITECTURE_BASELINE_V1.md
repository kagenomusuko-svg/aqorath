# ARQUITECTURA BASELINE V1.0 - LÍNEA DE BASE Y OBJETIVO

**Documento:** Descripción de arquitectura actual vs. arquitectura objetivo para Aqorath  
**Fecha:** 2025-11-01  
**Fase:** Fase 0 - Auditoría y Especificación Arquitectónica  

---

## EXECUTIVE SUMMARY

Aqorath actualmente exhibe una **arquitectura de coexistencia** donde:

1. Un **núcleo SQLite/SQLModel nuevo** (aqorath/) maneja operaciones contables básicas
2. Una **capa legacy de Pandas/Excel** (modelos/) aún realiza funciones críticas
3. **APIs duplicadas** en 3 ubicaciones distintas
4. **Fallbacks defensivos** que permiten múltiples fuentes de verdad
5. **Float para dinero**, violando el principio de exactitud
6. **Catálogo actualmente inmutable**, conflictuando con principio de extensibilidad

La arquitectura objetivo es una **separación nítida por capas** (Presentación → Aplicación → Dominio → Persistencia) con SQLite como única fuente de verdad, Decimal para dinero, y catálogo gobernado extensible.

---

## PARTE I: ESTADO ACTUAL DE LA ARQUITECTURA

### I.1 TOPLEVEL STRUCTURE

```
aqorath/
├── aqorath/                          [CANÓNICO - núcleo nuevo]
│   ├── __init__.py
│   ├── core.py                       [905 líneas - motor central]
│   ├── models.py                     [52 líneas - ORM/SQLModel]
│   ├── storage.py                    [124 líneas - sesiones SQLite]
│   ├── config.py                     [131 líneas - config global]
│   ├── templates.py                  [329 líneas - operaciones contables]
│   ├── accounting_rules.py           [52 líneas - reglas de negocio]
│   ├── exercise.py                   [330 líneas - cierre de ejercicio]
│   ├── catalog.py                    [78 líneas - catálogo]
│   ├── import_catalog.py             [210 líneas - importador de catálogo]
│   ├── company.py                    [17 líneas - modelo de empresa]
│   ├── assets.py                     [76 líneas - activos fijos]
│   ├── tax.py                        [70 líneas - impuestos]
│   ├── desktop.py                    [251 líneas - UI PySide]
│   ├── api.py                        [164 líneas - API FastAPI]
│   ├── templates/                    [HTML/Jinja2 para reportes]
│   ├── static/                       [CSS, imágenes]
│   ├── ui/                           [UI desktop PySide]
│   │   ├── main_window.py
│   │   ├── welcome.py
│   ├── data/
│   │   └── catalogo_base.json        [Catálogo embebido, JSON]
│   └── utils.py, template_utils.py, ...
│
├── modelos/                          [LEGACY - arquitectura anterior]
│   ├── libro.py                      [779 líneas - Libro en Pandas]
│   ├── hoja.py                       [59 líneas]
│   ├── catalogo.py                   [64 líneas]
│   ├── poliza.py                     [74 líneas]
│   ├── registro.py                   [271 líneas]
│   ├── cfdi.py                       [359 líneas - CFDI legacy]
│   ├── reportes.py                   [118 líneas]
│   ├── parametros.py                 [97 líneas]
│   └── xsdutils.py                   [63 líneas]
│
├── api/                              [DUPLICADO - API simplificada]
│   └── app.py                        [39 líneas - API minimalista]
│
├── api.py                            [164 líneas - DUPLICADO de aqorath/api.py]
├── main.py                           [Entry point]
├── app.py                            [App legacy]
├── desktop.py                        [UI legacy]
│
├── test/                             [Tests legacy - modelos/]
│   └── test_*.py
│
├── tests/                            [Tests nuevos - aqorath/]
│   ├── conftest.py
│   ├── test_core.py
│   ├── test_*.py
│   └── test.db                       [BD de prueba]
│
├── scripts/                          [Utilidades]
│   ├── init_db.py
│   ├── init_catalog_db.py
│   ├── fix_test_db.py
│   ├── generate_and_validate_demo.py
│   └── [10+ scripts más]
│
├── assets/                           [Datos de entrada]
│   └── catalogo.xlsx                 [Catálogo en Excel]
│
├── docs/                             [Documentación]
│   ├── CATALOG_POLICY.md             [Política actual: inmutable]
│   ├── CFDI.md                       [Documentación CFDI]
│   ├── AQORATH_CONSTITUTION_V1.md    [NUEVO]
│   ├── ARCHITECTURE_BASELINE_V1.md   [NUEVO]
│   └── REPO_AUDIT_V1.md              [NUEVO]
│
├── patches/                          [Patches experimentales]
│   └── *.patch
│
├── requirements.txt                  [Dependencias con errores]
├── setup.cfg                         [Configuración minimal]
├── pyproject.toml                    [Build config]
└── [backup files, .bak, etc.]
```

### I.2 FLUJO DE DATOS ACTUAL (ANÁLISIS)

```
ENTRADA DE USUARIO
       │
       ├─→ Desktop UI (PySide) / API REST
       │         │
       │         ├─→ aqorath/api.py o api/app.py
       │         │         │
       │         └─→ aqorath/core.py [NÚCLEO]
       │                    │
       │         ┌──────────┼──────────┐
       │         │          │          │
       │         ▼          ▼          ▼
       │    ORM PATH   SQLITE PATH   FALLBACK
       │    (SQLModel) (Directo)     (Detección)
       │         │          │          │
       │         └──────────┼──────────┘
       │                    ▼
       │           Persistencia SQLite
       │
       └─→ Legacy modelos/ [PARALELO]
               │
               ├─→ Libro (Pandas)
               ├─→ Excel
               └─→ JSON
```

### I.3 MULTIPLICIDAD DE FUENTES DE VERDAD

**PROBLEMA CRÍTICO:** Existen múltiples lugares donde la "verdad contable" puede residir:

1. **SQLite (aqorath/)**
   - Tabla: account, journal_entry, journal_line
   - Fuente primaria declarada
   - Validaciones deficitarias

2. **Pandas/Excel (modelos/)**
   - Clase Libro mantiene DataFrame interno
   - Puede divergir de SQLite
   - Usado en importación/exportación

3. **JSON (catalogo_base.json)**
   - Catálogo de cuentas embebido
   - Compite con tabla Account en SQLite
   - Política de Immutable vs. Extensible en conflicto

4. **Fallbacks en core.py**
   - Si ORM falla, intenta SQLite directo
   - Si no encuentra tabla, la busca por múltiples nombres
   - Si no encuentra columna, la adapta dinámicamente
   - Permite persistencia de estructuras incompletas

**IMPLICACIÓN:** Un usuario podría estar modificando diferentes "realidades contables" sin saber cuál es la verdadera.

### I.4 CAPAS ACTUALES (CONFUSAS)

```
┌─────────────────────────────────────┐
│ PRESENTACIÓN (Débilmente separada) │
│ - desktop.py (UI PySide)           │
│ - api.py, api/app.py (APIs)        │
│ - templates/ (Jinja2)              │
└────────┬────────────────────────────┘
         │ (Llamadas directas sin abstracción clara)
┌────────▼────────────────────────────┐
│ APLICACIÓN (No examinada)           │
│ - core.py (mezcla aplicación + dom)│
│ - templates.py (lógica de dominio) │
│ - exercise.py (lógica de dominio)  │
└────────┬────────────────────────────┘
         │ (Dependencias mixtas)
┌────────▼────────────────────────────┐
│ DOMINIO (Acoplado a persistencia)   │
│ - models.py (ORM, no dominio puro) │
│ - accounting_rules.py (reglas)      │
│ - catalog.py (mezcla JSON + BD)     │
└────────┬────────────────────────────┘
         │ (ORM vs. SQLite directo)
┌────────▼────────────────────────────┐
│ PERSISTENCIA (Dual)                 │
│ - storage.py (sesiones SQLModel)    │
│ - core.py (queries SQLite directas) │
│ - modelos/ (Pandas)                 │
└─────────────────────────────────────┘
```

**PROBLEMA:** Las capas no están separadas. core.py mezcla lógica de aplicación, dominio y persistencia.

### I.5 VIOLACIONES DE PRINCIPIOS DETECTADAS EN CÓDIGO

#### Violación: DINERO EXACTO (Principio 5)

**Ubicaciones donde se usa `float` para dinero:**

1. **models.py (líneas 43-44)**
   ```python
   debit: float = 0.0
   credit: float = 0.0
   ```

2. **templates.py (múltiples lugares)**
   - `percent_expr()` línea 43: `round(float(amount) * float(rate), 2)`
   - `gross_base_expr()` línea 59: `round(float(amount) / (1.0 + vat), 2)`
   - Todas las expresiones de cálculo usan float

3. **core.py (línea 836)**
   ```python
   insert_vals.append(float(ln.get("debit") or 0))
   ```

4. **exercise.py** - Cálculos de resultado usando Decimal pero conversiones a float

5. **modelos/libro.py** - Pandas usa float64 internamente

**IMPACTO:** Posibles pérdidas de centavos en operaciones, asientos descuadrados por redondeo.

#### Violación: CATÁLOGO (Principio 10)

**Conflicto Explícito:**

- **CATALOG_POLICY.md** (línea 7): "El catálogo contable es... inmutable"
- **AQORATH_CONSTITUTION_V1.md** (Principio 10): "Catálogo gobernado y extensible"

**Estado Actual:**
- Catálogo en `aqorath/data/catalogo_base.json` (immutable)
- Tabla `account` en SQLite (validada contra catálogo)
- Listener en storage.py (previene inserciones no-catálogo)
- Pero listener solo se registra en INSERT, no en UPDATE (BUG)

**Resolución Pendiente:** Definir si el catálogo es extensible o no.

#### Violación: PARTIDA DOBLE (Principio 4)

**Debilidades Detectadas:**

1. **core.py (línea 883)**
   ```python
   if not preview.get("balanced", False):
       # Validación en preview, pero...
   ```
   La validación es en preview, la persistencia es separada. Posible desincronización.

2. **exercise.py (línea 94-128)**
   - Asiento de transferencia de resultado es inserido directamente sin pasar por _persist_entry()
   - Bypassa validaciones de core.py

3. **JournalLine** (models.py)
   - `account_code` y `account_id` son ambos opcionales
   - Valido tener un asiento sin saber qué cuentas toca

#### Violación: FALLBACKS QUE OCULTAN ERRORES (Principio 25)

**core.py (líneas 715-856) - _persist_entry() con fallback SQLite:**

```python
if db is None:
    return {"ok": False, "error": "No se encontró base de datos..."}
# Fallback 1: intenta encontrar tabla por múltiples nombres
for candidate in ("entry", "journalentry", "journal_entry"):
    # Busca dinámicamente

# Fallback 2: inspecciona columnas con PRAGMA
cur.execute(f"PRAGMA table_info('{entry_table}')")
# Adapta a lo que encuentra

# Fallback 3: rellena campos con defaults si están NULL
if notnull:
    insert_cols.append(colname)
    insert_vals.append("posted")  # Adivinó un default
```

**PELIGRO:** Puede persistir estructuras semi-válidas.

#### Violación: LOCAL-FIRST (Principio 6) - Parcial

**Cumplimiento:**
- ✅ SQLite es local
- ✅ Sin dependencia de red para contabilidad base

**Incumplimiento:**
- ❌ APIs que podrían ser remotas (api.py, api/app.py)
- ❌ No está claro si Meriadock puede ser custodio en futuro
- ❌ No está explicitado cómo se sincroniza con central (si existe)

---

## PARTE II: ARQUITECTURA OBJETIVO

### II.1 TOPOLOGÍA OBJETIVO

```
aqorath/                            [Reorganizado]
├── domain/                         [CAPA: DOMINIO]
│   ├── __init__.py
│   ├── accounting.py               [Operaciones contables, sin ORM]
│   ├── entities.py                 [JournalEntry, JournalLine, Account - POJO]
│   ├── catalog.py                  [Catálogo gobernado, no mutable]
│   ├── rules.py                    [Reglas contables: partida doble, saldos]
│   ├── fiscal.py                   [Reglas fiscales versionadas]
│   ├── osc.py                      [Conceptos OSC: Donativos, Programas]
│   ├── validators.py               [Validadores de dominio]
│   └── exceptions.py               [Excepciones de negocio]
│
├── application/                    [CAPA: APLICACIÓN]
│   ├── __init__.py
│   ├── usecases.py                 [Casos de uso: register_entry, close_period]
│   ├── orquestador.py              [Orquestación de flujos]
│   ├── commands.py                 [Comandos del usuario]
│   └── queries.py                  [Consultas]
│
├── infrastructure/                 [CAPA: INFRAESTRUCTURA/PERSISTENCIA]
│   ├── __init__.py
│   ├── database.py                 [SQLite, sesiones]
│   ├── repositories.py             [Acceso a datos]
│   ├── migrations.py               [Versionado de schema]
│   ├── backups.py                  [Respaldos]
│   ├── export.py                   [Exportadores: CSV, Excel, XML]
│   └── import_.py                  [Importadores]
│
├── presentation/                   [CAPA: PRESENTACIÓN]
│   ├── __init__.py
│   ├── common/
│   │   ├── ui.py                   [Componentes reutilizables]
│   │   └── api.py                  [Dependencias FastAPI]
│   ├── desktop/                    [UI Desktop (PySide)]
│   │   ├── main_window.py
│   │   ├── dialogs/
│   │   └── widgets/
│   ├── rest/                       [API REST (FastAPI)]
│   │   ├── routes/
│   │   │   ├── entries.py
│   │   │   ├── accounts.py
│   │   │   ├── reports.py
│   │   │   └── ...
│   │   └── schemas.py              [Pydantic models para API]
│   ├── cli/                        [CLI (opcional)]
│   └── static/                     [CSS, JS]
│
├── shared/                         [CÓDIGO COMPARTIDO]
│   ├── logging.py
│   ├── config.py
│   ├── types.py                    [Decimal, Date tipos]
│   └── utils.py
│
├── tests/
│   ├── unit/                       [Tests sin BD]
│   │   ├── domain/
│   │   ├── application/
│   │   └── ...
│   ├── integration/                [Tests con BD real]
│   └── fixtures/                   [Datos de prueba]
│
├── data/
│   ├── catalogo_base.json          [Catálogo canónico]
│   ├── migrations/                 [Scripts de migración SQL]
│   └── seeds/                      [Datos iniciales]
│
└── docs/
    ├── CONSTITUTION.md
    ├── ARCHITECTURE.md
    ├── API.md
    └── DEVELOPER.md
```

### II.2 SEPARACIÓN DE CAPAS OBJETIVO

```
┌──────────────────────────────────────────────────┐
│ PRESENTACIÓN                                     │
│ - Desktop UI (PySide)                           │
│ - REST API (FastAPI)                            │
│ - CLI (Click)                                   │
│ Responsabilidad: Capturar y renderizar          │
│ NO: Lógica contable, validaciones de negocio    │
└───────────┬────────────────────────────────────┘
            │ Inyección de casos de uso
┌───────────▼────────────────────────────────────┐
│ APLICACIÓN                                      │
│ - Casos de uso (register_entry, close_period)  │
│ - Orquestación de flujos                        │
│ - Transacciones (begin/commit)                  │
│ - Manejo de errores                             │
│ Responsabilidad: Lógica de proceso              │
│ NO: Reglas contables del dominio, persistencia  │
└───────────┬────────────────────────────────────┘
            │ Llamadas a servicios del dominio
┌───────────▼────────────────────────────────────┐
│ DOMINIO                                         │
│ - Entidades (JournalEntry, Account, etc.)      │
│ - Reglas contables (partida doble, saldos)     │
│ - Validaciones de negocio                       │
│ - Cálculos (Decimal, no float)                  │
│ - Catálogo gobernado                            │
│ - Reglas fiscales versionadas                   │
│ Responsabilidad: Lógica de negocio              │
│ NO: Depender de UI, persistencia específica     │
│ Implementación: POJO + servicios sin ORM        │
└───────────┬────────────────────────────────────┘
            │ Abstracciones (Repository pattern)
┌───────────▼────────────────────────────────────┐
│ INFRAESTRUCTURA                                 │
│ - SQLite, sesiones, queries                     │
│ - Migraciones de schema                         │
│ - Backups, restauración                         │
│ - Exportadores/importadores                     │
│ Responsabilidad: Acceso a datos y persistencia  │
│ NO: Lógica contable                             │
└──────────────────────────────────────────────────┘
```

### II.3 FLUJOS DE DATOS OBJETIVO

**Ejemplo: Registrar una Venta**

```
UI (Usuario ingresa: "Vendí $1000 a Juan")
        │
        ▼
APLICACIÓN (RegisterSaleUseCase)
        │
        ├─→ Validación de flujo (Juan existe? Monto válido?)
        │
        ├─→ DOMINIO
        │   ├─→ Regla: "Venta genera Bancos +$1000 / Ventas -$1000"
        │   ├─→ Validación: Partida doble (OK)
        │   ├─→ Cálculo: IVA según contexto
        │   ├─→ Resultado: JournalEntry + Explicación
        │   └─→ Excepción si incumple invariantes
        │
        ├─→ INFRAESTRUCTURA (persist)
        │   ├─→ Validar FK (Juan debe existir en PartyRepository)
        │   ├─→ INSERT asiento y líneas
        │   ├─→ Logging de auditoría
        │   └─→ Excepciones si fallan constraints
        │
        ▼
UI (Muestra: "Venta #001 registrada. Bancos +$1000, Ventas -$1000")
```

### II.4 MODELO DE DATOS OBJETIVO

**Entidades Principales del Dominio:**

```python
# ENTITIES (sin ORM acoplamiento)
class Account:
    code: str                          # Único
    name: str
    nature: Nature                     # Deudora | Acreedora
    type: AccountType                  # Activo, Pasivo, etc.
    parent_code: Optional[str]         # Para extensiones
    is_canonical: bool                 # Parte del catálogo base?

class JournalEntry:
    id: int
    date: date                         # (no datetime!)
    concept: str
    state: EntryState                  # draft | posted | reversed
    lines: List[JournalLine]
    created_by: Optional[str]          # Para auditoría
    posted_by: Optional[str]
    period: FiscalPeriod              # Referencia a periodo fiscal
    doc_ref: Optional[DocumentRef]    # CFDI, comprobante, etc.

class JournalLine:
    id: int
    entry_id: int
    account: Account                   # Referencia fuerte
    debit: Decimal                     # Nunca float
    credit: Decimal                    # Nunca float
    description: Optional[str]
    analytical_dimensions: Dict[str, str]  # Programa, Centro, etc.

class FiscalYear:
    year: int
    entity: Entity
    status: YearStatus                 # open | closed | archived
    periods: List[FiscalPeriod]

class FiscalPeriod:
    id: int
    fiscal_year: FiscalYear
    month: int                         # 1-12
    status: PeriodStatus               # open | closed
    opening_balances: Dict[str, Decimal]
    closing_date: Optional[date]

class CatalogAccount:                  # Catálogo canónico
    code: str
    name_osc: str
    name_comercial: str
    tipo: str
    subtipo: str
    naturaleza: str
    descripcion: str

class FiscalRuleSet:                   # Versionado
    fiscal_year: int
    rule_type: str                     # "isr", "iva", "cfdi", etc.
    rules: Dict[str, Any]              # ISR rates, IVA rates, etc.
    effective_date: date
    version: int                       # Para historial

class Entity:                          # Entidad económica
    id: int
    name: str
    rfc: str
    naturaleza: EntityNatura          # "Comercial" | "OSC" | etc.
    régimen_fiscal: str
    características: Set[str]          # "donataria", "independiente", etc.
    created_at: datetime
```

### II.5 VALIDACIONES DE DOMINIO

Las validaciones de negocio residen en la capa de dominio:

```python
# domain/validators.py

class JournalEntryValidator:
    @staticmethod
    def validate_double_entry(entry: JournalEntry) -> None:
        debit_sum = sum(line.debit for line in entry.lines)
        credit_sum = sum(line.credit for line in entry.lines)
        if debit_sum != credit_sum:
            raise DoubleEntryViolation(
                f"Debit {debit_sum} != Credit {credit_sum}"
            )
    
    @staticmethod
    def validate_account_exists(account: Account, catalog: Catalog) -> None:
        if not catalog.can_contain(account):
            raise InvalidAccountError(
                f"Account {account.code} violates catalog structure"
            )
    
    @staticmethod
    def validate_required_accounts(entry: JournalEntry) -> None:
        if any(line.account is None for line in entry.lines):
            raise MissingAccountError(...)
```

### II.6 CASOS DE USO (Application Layer)

```python
# application/usecases.py

class RegisterEntryUseCase:
    """Registrar un nuevo asiento contable"""
    
    def __init__(self, 
                 repo: EntryRepository,
                 catalog: Catalog,
                 rules: AccountingRules):
        self.repo = repo
        self.catalog = catalog
        self.rules = rules
    
    def execute(self, command: RegisterEntryCommand) -> EntryDTO:
        # 1. Interpretar hecho económico
        hecho = parse_economic_fact(command)
        
        # 2. Aplicar regla contable
        entry = self.rules.apply(hecho)
        
        # 3. Validar
        JournalEntryValidator.validate_double_entry(entry)
        JournalEntryValidator.validate_account_exists(...)
        
        # 4. Persistir
        saved_entry = self.repo.save(entry)
        
        # 5. Generar explicación
        explanation = generate_explanation(hecho, entry)
        
        return EntryDTO(
            entry_id=saved_entry.id,
            explanation=explanation
        )
```

---

## PARTE III: RUTA DE MIGRACIÓN

### III.1 FASES PROPUESTAS (Post-Phase 0)

**FASE 1: Separación de Capas**
- Extraer dominio puro de core.py, templates.py
- Crear application/ con casos de uso
- Mantener API de compatibilidad

**FASE 2: Eliminación de Legacy**
- Deprecar modelos/
- Migrar tests de test/ → tests/
- Consolidar una única API

**FASE 3: Exactitud Numérica**
- Convertir JournalLine.debit/credit a Decimal
- Convertir templates a Decimal
- Re-validar todos los tests

**FASE 4: Catálogo Gobernado**
- Implementar extensiones controladas
- Deprecar immutabilidad
- UI para crear extensiones

**FASE 5: Arquitectura Fiscal Versionada**
- Separar tax/ del núcleo
- Implementar FiscalRuleSet
- Soportar múltiples periodos fiscales

**FASE 6: OSC como Primera Clase**
- Modelos de Program, Fund, Donation
- Dimensiones analíticas en JournalEntry
- Reportes OSC específicos

---

## PARTE IV: DECISIONES ARQUITECTÓNICAS PENDIENTES

### IV.1 Patrones de Acceso a Datos

**Opción A: Repository Pattern**
```python
class EntryRepository:
    def find_by_id(self, id: int) -> JournalEntry
    def find_by_period(self, period: FiscalPeriod) -> List[JournalEntry]
    def save(self, entry: JournalEntry) -> JournalEntry
```

**Opción B: Generic DAO**
```python
class GenericDAO[T]:
    def find(self, criteria: SearchCriteria) -> List[T]
    def save(self, entity: T) -> T
```

**Recomendación:** Repository Pattern es más explícito y testeable.

### IV.2 Transacciones

**Opción A: SQLAlchemy Session Management**
```python
with transaction():
    entry = create_entry(...)
    persist(entry)
```

**Opción B: Decorador @transactional**
```python
@transactional
def register_entry(cmd: Command):
    ...
```

**Recomendación:** Decorador es más limpio, pero necesita context handling.

### IV.3 Dependency Injection

**Opción A: Pasaje manual**
```python
use_case = RegisterEntryUseCase(repo, catalog, rules)
```

**Opción B: Container (injector)**
```python
container = DIContainer()
container.register(EntryRepository, SQLiteEntryRepository)
use_case = container.get(RegisterEntryUseCase)
```

**Recomendación:** Container para aplicaciones complejas, pasaje manual para tests.

---

## PARTE V: SUMMARY TABLE - ACTUAL vs. OBJETIVO

| Aspecto | Actual | Objetivo |
|---------|--------|----------|
| **Fuente de Verdad** | Múltiple (SQLite, Pandas, JSON) | Única: SQLite |
| **Separación de Capas** | Confusa, acopladas | Nítida: Presentation → Application → Domain → Infrastructure |
| **Tipo Numérico para Dinero** | float (INCORRECTO) | Decimal (CORRECTO) |
| **Catálogo** | Immutable, embebido | Gobernado, extensible |
| **APIs** | 3 ubicaciones, duplicadas | 1 única, clara |
| **Tests** | 2 carpetas (test/, tests/) | 1 carpeta: tests/unit, tests/integration |
| **Modelos** | SQLModel + Legacy Pandas | POJO + Repository |
| **Validaciones** | Mezcladas, defensivas | Dominio puro |
| **Fallbacks** | Múltiples, ocultadores | Ninguno (falla explícita) |
| **OSC Support** | No nativo | Primera clase |
| **Fiscal Versionado** | No existe | Implementado |

---

## CONCLUSIÓN

La arquitectura objetivo es una reorganización fundamental que:

1. **Clarifica responsabilidades** - Cada capa tiene un rol único
2. **Elimina duplicidad** - Una sola fuente de verdad
3. **Fortalece validaciones** - Dominio puro, sin fallbacks
4. **Mejora testabilidad** - Capas desacopladas
5. **Soporta extensión** - OSC, fiscal, catálogo gobernado

La transición requiere varias fases, pero el objetivo es claro: **un ERP contable profesional, no un prototipo rústico**.

---

**Documento Aprobado:** 2025-11-01  
**Próxima Revisión:** Fase 1 (Post-Auditoría)
