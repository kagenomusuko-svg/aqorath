# ARCHITECTURE BASELINE V1

## Propósito

Este documento describe la **arquitectura objetivo** de Aqorath sin implementarla. Propone una estructura conceptual que:

1. Satisface los 28 principios de AQORATH_CONSTITUTION_V1.md
2. Permite crecimiento futuro sin reescrituras disruptivas
3. Mantiene separación clara de responsabilidades
4. Facilita testabilidad en capas

---

## ARQUITECTURA DE CAPAS PROPUESTA

```
┌─────────────────────────────────────────────────────┐
│  PRESENTATION                                       │
│  (UI/API/CLI) - No contiene lógica de negocio     │
│                                                     │
│  - desktop.py (PySide)                              │
│  - api/app.py (FastAPI/REST)                        │
│  - cli.py (CLI) [futuro]                            │
└───────────────┬─────────────────────────────────────┘
                │
┌───────────────v─────────────────────────────────────┐
│  APPLICATION (Casos de Uso / Servicios)             │
│  (Orquestación, validaciones de flujo)              │
│                                                     │
│  - OperationService (crear asientos)                │
│  - ReportingService (generar reportes)              │
│  - FiscalService (calcular impuestos)               │
│  - EntityService (gestionar entidad)                │
│  - ExerciseService (cierres contables)              │
└───────────────┬─────────────────────────────────────┘
                │
┌───────────────v─────────────────────────────────────┐
│  DOMAIN (Motor de Negocio - Lógica Contable)        │
│  (Entidades, reglas, cálculos)                      │
│                                                     │
│  - EconomicEvent (hechos económicos)                │
│  - JournalEntry / JournalLine (asientos)            │
│  - Account / AccountCatalog (catálogo)              │
│  - FiscalRuleSet (reglas versionadas)               │
│  - EntityProfile (naturaleza de entidad)            │
│  - Explanation (justificación de decisión)          │
│  - AnalyticalDimension (dimensiones analíticas)     │
│  - ReportDefinition (documentos)                    │
└───────────────┬─────────────────────────────────────┘
                │
┌───────────────v─────────────────────────────────────┐
│  INFRASTRUCTURE (Persistencia, Integraciones)       │
│  (Implementa abstracciones del dominio)             │
│                                                     │
│  - SQLiteRepository                                 │
│  - FileBackupService                                │
│  - ConfigurationManager                             │
│  - ReportRenderer (PDF, Excel, etc.)                │
│  - CFDIService (integración)                        │
└─────────────────────────────────────────────────────┘
```

---

## DEPENDENCIAS PERMITIDAS

```
Presentation → Application (consume servicios)
Presentation → (NO puede acceder directamente a Domain/Infrastructure)

Application → Domain (consume entidades/reglas)
Application → Infrastructure (para persistencia)
Application → (NO Presentation)

Domain → (NADA más - autónomo)
Domain solo importa: dataclasses, typing, decimal, datetime, logging

Infrastructure → Domain (implementa interfaces del dominio)
Infrastructure → (NO Presentation)
Infrastructure → (NO Application - solo lo contrario)
```

---

## DIRECTORIOS PROPUESTOS

```
aqorath/
├── domain/
│   ├── __init__.py
│   ├── entities.py              # EconomicEvent, JournalEntry, Account, etc.
│   ├── value_objects.py         # Money (Decimal), Period, etc.
│   ├── specifications.py        # Catálogo, reglas fiscales
│   └── services.py              # Servicios de dominio (e.g., calcular saldos)
│
├── application/
│   ├── __init__.py
│   ├── services/
│   │   ├── operation.py         # Crear/registrar asientos
│   │   ├── reporting.py         # Generar reportes
│   │   ├── fiscal.py            # Calcular impuestos
│   │   ├── entity.py            # Gestionar entidad/company
│   │   └── exercise.py          # Cierres contables
│   │
│   ├── dto.py                   # Data Transfer Objects (input/output)
│   ├── exceptions.py            # Excepciones de aplicación
│   └── validators.py            # Validadores de flujo
│
├── infrastructure/
│   ├── __init__.py
│   ├── persistence/
│   │   ├── repositories.py      # Implementaciones SQLAlchemy/SQLModel
│   │   ├── migrations.py        # Versiones de schema
│   │   └── session.py           # Gestión de sesión
│   │
│   ├── files/
│   │   ├── backup.py            # Backups automáticos
│   │   └── export.py            # Exportación CSV/Excel/JSON
│   │
│   ├── rendering/
│   │   ├── pdf.py               # Reportes PDF
│   │   ├── excel.py             # Reportes Excel
│   │   └── json.py              # Exportación JSON
│   │
│   └── integrations/
│       └── cfdi.py              # CFDI (futuro)
│
├── presentation/
│   ├── desktop.py               # PySide UI
│   ├── api.py                   # FastAPI endpoints
│   ├── cli.py                   # CLI (futuro)
│   └── templates/               # HTML/Jinja si aplica
│
├── models.py                    # SQLModel ORM (persistencia)
├── storage.py                   # Session management
├── config.py                    # Configuración
├── __init__.py
└── main.py                      # Entry point
```

---

## CONCEPTO DE ENTIDADES CLAVE

### 1. EconomicEvent (Dominio)
```python
@dataclass
class EconomicEvent:
    """Hecho económico capturado por usuario"""
    id: Optional[int]
    event_type: str  # "sale", "purchase", "donation", "expense"
    date: datetime
    amount: Decimal
    description: str
    third_party: Optional[str]
    context: Dict[str, Any]  # Datos semánticos (bank, program, etc.)
    
    def interpret(self) -> JournalEntry:
        """Interpreta el hecho en asiento contable"""
        ...
```

### 2. JournalEntry (Dominio)
```python
@dataclass
class JournalEntry:
    """Asiento contable - Invariante: Σ(débitos) = Σ(créditos)"""
    id: Optional[int]
    date: datetime
    concept: str
    lines: List[JournalLine]
    period_id: Optional[int]
    fiscal_rule_set_id: Optional[int]  # Qué reglas fiscales aplicaban
    state: str  # "draft", "posted"
    
    @property
    def is_balanced(self) -> bool:
        return sum(l.debit for l in self.lines) == sum(l.credit for l in self.lines)
    
    def post(self) -> None:
        if not self.is_balanced:
            raise BalanceError("Asiento descuadrado")
        self.state = "posted"
```

### 3. Account (Dominio)
```python
@dataclass
class Account:
    """Cuenta contable"""
    id: Optional[int]
    code: str                    # Único en catálogo
    name: str                    # Nombre canónico
    account_type: str            # "asset", "liability", "equity", "income", "expense"
    subtype: str                 # "current", "noncurrent", etc.
    nature: str                  # "debit", "credit"
    is_canonical: bool = True    # True = en catálogo base; False = creación usuario
    
    name_osc: Optional[str]      # Nombre para OSC
    name_comercial: Optional[str] # Nombre para comercial
```

### 4. FiscalRuleSet (Dominio)
```python
@dataclass
class FiscalRuleSet:
    """Reglas fiscales versionadas (México)"""
    id: Optional[int]
    version: str                 # "2024-01-01", "2025-06-01"
    entity_profile_id: int       # Para qué tipo de entidad
    rules: Dict[str, Any]        # JSON con reglas (IVA, ISR, retenciones)
    effective_from: date
    effective_to: Optional[date]
    
    def calculate_tax(self, account_code: str, amount: Decimal) -> Dict[str, Decimal]:
        """Calcula impuestos automáticos para una cuenta/monto"""
        ...
```

### 5. EntityProfile (Dominio)
```python
@dataclass
class EntityProfile:
    """Perfil de entidad (multicomponente)"""
    id: Optional[int]
    entity_id: int               # Referencia a Company
    
    # Características
    juridical_nature: str        # "persona_fisica", "persona_moral", "osc"
    fiscal_regime: str           # "RIF", "RIF+", "RGSO", "RGSO+"
    
    is_nonprofit: bool           # Aplican reglas OSC
    is_donor_authorized: bool    # Donataria autorizada
    
    modules_enabled: List[str]   # ["banking", "inventory", "payroll", "osc"]
```

### 6. Explanation (Dominio)
```python
@dataclass
class Explanation:
    """Explicación determinística de una decisión contable"""
    id: Optional[int]
    entry_id: int
    rule_id: str                 # Qué regla/template aplicó
    context: Dict[str, Any]      # Variables de decisión
    interpretation: str          # Texto explicativo
    affected_accounts: List[str] # Qué cuentas afectó
    timestamp: datetime
    
    def to_user_text(self) -> str:
        """Retorna explicación en lenguaje usuario"""
        ...
```

### 7. ReportDefinition (Dominio)
```python
@dataclass
class ReportDefinition:
    """Define qué datos mostrar en un documento"""
    id: Optional[int]
    name: str                    # "Balanza", "Diario", "Mayor"
    template: str                # Qué template usar
    
    # Parámetros
    period_id: Optional[int]
    from_date: date
    to_date: date
    filters: Dict[str, Any]      # {"account_codes": ["1101", "1102"], ...}
    
    applicable_entities: List[str] # ["comercial", "osc"]
    
    def generate(self, repo) -> ReportResult:
        """Genera el reporte"""
        ...
```

### 8. AnalyticalDimension (Dominio)
```python
@dataclass
class AnalyticalDimension:
    """Dimensión adicional de análisis (no duplica contabilidad)"""
    id: Optional[int]
    name: str                    # "Programa", "Fuente", "Centro de Costo"
    entity_id: int
    
    values: List[str]            # ["Regularización", "Becas", ...] para Programas


@dataclass
class JournalLineAnalytics:
    """Liga JournalLine con dimensiones"""
    line_id: int
    dimension_id: int
    value: str                   # Qué valor de la dimensión
```

---

## CASOS DE USO PRINCIPALES

### UC1: Registrar Venta (OperationService)

**Actor:** Usuario (interfaz común)
**Input:** 
```python
{
    "event_type": "sale",
    "amount": 1000.00,
    "vat_rate": 0.16,
    "description": "Venta de servicios",
    "bank_account": "1101",  # Rol → código de cuenta
}
```

**Flujo:**
1. Crear EconomicEvent desde input
2. Interpretar a JournalEntry (qué cuentas, qué montos)
3. Validar partida doble
4. Guardar con Explanation
5. Retornar: {"ok": true, "entry_id": 123, "lines": [...], "explanation": "..."}

**Output:** JournalEntry validado + Explanation

---

### UC2: Generar Balanza (ReportingService)

**Input:** 
```python
ReportDefinition(
    name="Balanza",
    from_date="2025-01-01",
    to_date="2025-12-31",
    filters={"account_type": ["asset", "liability"]}
)
```

**Flujo:**
1. Cargar ReportDefinition
2. Resolver cuentas del filtro
3. Cargar todos los JournalLine del período
4. Agrupar por cuenta, sumar débitos/créditos
5. Calcular saldos (debit - credit)
6. Retornar con formato (PDF/Excel/JSON)

**Output:** ReportResult con tabla de balanza

---

### UC3: Cierre de Ejercicio (ExerciseService)

**Precondiciones:**
- Cuentas 3103 (Resultado del Ejercicio) y 3104 (Pérdida del Ejercicio) existen

**Flujo:**
1. Crear backup automático
2. Calcular resultado neto (Ingresos - Gastos)
3. Crear asiento de traslado (si hay resultado)
4. Crear nuevo período/ejercicio
5. Registrar cierre en auditlog

**Output:** Backup creado + Asiento de traslado insertado + Nuevo período

---

## RESPONSABILIDADES POR CAPA

### PRESENTATION
- Recolectar input del usuario
- Llamar Application services
- Formatear output para display
- NO validación de negocio
- NO lógica contable

### APPLICATION
- Orquestar flujos de usuario
- Validar reglas de negocio (pre-condiciones)
- Llamar Domain services / Repositories
- Mapear DTO ← → Domain entities
- Manejar excepciones y convertir a respuestas

### DOMAIN
- Definir entidades contables
- Implementar reglas (partida doble, etc.)
- Especificar interfaces (repositories)
- NO depender de frameworks

### INFRASTRUCTURE
- Implementar Repositories (persist entities)
- Manejar transacciones
- Renderers (PDF/Excel)
- Integración con sistemas externos
- File I/O (backup, export)

---

## TRANSICIONES ARQUITECTÓNICAS

### FASE 1: Separación Básica
- Mover lógica de `app.py` a `application/`
- Mover modelos a `domain/entities.py`
- Crear base `OperationService` en `application/services/operation.py`
- Mantener modelos/libro.py como LEGACY, documentado como deprecated

### FASE 2: Explicabilidad
- Implementar tabla Explanation
- Templates retornan "explanation reason"
- ReportingService documenta cálculos

### FASE 3: Dimensiones Analíticas
- Crear tabla AnalyticalDimension
- JournalLine → many-to-many con dimensiones
- Reportes filtran/agrupan por dimensión

### FASE 4: Gobierno de Catálogo
- Cambiar listener a validador (no bloqueador)
- Permitir cuentas is_canonical=False (extensiones usuario)
- UI para "crear cuenta con guía"

### FASE 5: Fiscal Versionado
- FiscalRuleSet versionado por fecha
- Cambio de régimen = nuevo FiscalRuleSet
- Cálculos referencian FiscalRuleSet histórico

---

## PRINCIPIOS DE ESTA ARQUITECTURA

1. **Inversión de Dependencias:** Las capas superiores dependen de abstracciones (interfaces) de inferiores
2. **Single Responsibility:** Cada clase/módulo tiene una razón para cambiar
3. **No Circular Dependencies:** La estructura es acíclica
4. **Testabilidad:** Domain es 100% testeable sin frameworks; Application testeable con mocks
5. **Escalabilidad:** Nuevas características se agregan sin modificar existentes

---

## REFERENCIAS

- Seguimiento a AQORATH_CONSTITUTION_V1.md (todas las 28 reglas)
- Clean Architecture (Robert C. Martin)
- Domain-Driven Design (Eric Evans)
- REPO_AUDIT_V1.md para estado actual

