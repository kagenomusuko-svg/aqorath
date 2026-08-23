# ARCHITECTURE BASELINE V1

## Propósito

Este documento describe la **arquitectura objetivo** de Aqorath sin implementarla en la actualidad.

Propone una estructura conceptual que:
1. Satisface los 28 principios de AQORATH_CONSTITUTION_V1.md
2. Permite crecimiento futuro sin reescrituras disruptivas
3. Mantiene separación clara de responsabilidades
4. Facilita testabilidad en capas

**Advertencia importante:** Esta no es descripción del código actual. El estado actual se documentaa en REPO_AUDIT_V1.md.

---

## ARQUITECTURA DE CAPAS PROPUESTA

```
┌─────────────────────────────────────────────────────┐
│  PRESENTATION                                       │
│  (UI/API/CLI) - Thin wrappers                      │
│                                                     │
│  No contiene lógica de negocio.                     │
│  Recolecta input → Llama Application → Formatea    │
└───────────────┬─────────────────────────────────────┘
                │
                ↓ depende de

┌─────────────────────────────────────────────────────┐
│  APPLICATION (Casos de Uso / Servicios)             │
│  (Orquestación, validaciones de flujo)              │
│                                                     │
│  OperationService (crear asientos)                  │
│  ReportingService (generar reportes)                │
│  FiscalService (calcular impuestos)                 │
│  EntityService (gestionar entidad)                  │
│  ExerciseService (cierres contables)                │
│                                                     │
│  Mapea entre DTO e inversiones Domain.              │
│  NO conoce implementaciones de persistencia.        │
└───────────────┬─────────────────────────────────────┘
                │
        ├───────┴───────┐
        ↓               ↓ depende de

┌─────────────────────┐  ┌────────────────────────┐
│  DOMAIN             │  │  INFRASTRUCTURE         │
│  (Motor de Negocio) │  │  (Implementaciones)    │
│                     │  │                        │
│  Entidades puras    │  │  SQLiteRepository      │
│  Reglas de negocio  │  │  FileBackupService     │
│  Sin dependencias   │  │  ReportRenderer        │
│  externas           │  │  (PDF, Excel, JSON)    │
└─────────────────────┘  │  ConfigurationManager  │
                         │  CFDIService           │
                         └────────────────────────┘

REGLA: Domain no importa nada externo (dataclasses, typing, decimal, datetime solo).
REGLA: Infrastructure implementa interfaces/puertos definidos por Domain/Application.
REGLA: Application importa Domain + abstracciones, no implementaciones concretas.
```

---

## DOMAIN MODEL (Puro, sin ORM)

El dominio define entidades y lógica contable. NO tiene SQLModel, SQLAlchemy, ni SQLite directo.

### Entidades Conceptuales

#### 1. **Entity** - Titular de la contabilidad
```python
@dataclass
class Entity:
    """Una entidad económica (persona, empresa, asociación)"""
    id: Optional[int]
    name: str
    rfc: Optional[str]
    juridical_nature: str      # "persona_fisica", "persona_moral", "osc"
    
    # Composición, no herencia
    profile: EntityProfile
```

#### 2. **EntityProfile** - Características multicomponente
```python
@dataclass
class EntityProfile:
    """Describe qué es esta entidad y cómo contabilizar"""
    entity_id: int
    
    # Naturaleza
    juridical_nature: str       # persona_fisica, persona_moral, osc
    fiscal_regime_code: str     # RIF, RGSO, RGSO+, etc. (códigos neutrales)
    is_nonprofit: bool
    is_donor_authorized: bool   # Donataria autorizada SAT
    
    # Módulos habilitados
    modules_enabled: List[str]  # ["banking", "inventory", "osc", "payroll"]
    
    # Referencia a reglas que aplican
    fiscal_rule_set_version: str  # "2024-01-01"
```

#### 3. **EconomicEvent** - Hecho económico capturado por usuario
```python
@dataclass
class EconomicEvent:
    """Lo que ocurrió en la realidad económica"""
    id: Optional[int]
    event_type: str             # "sale", "purchase", "donation", "expense"
    date: datetime
    amount: Decimal
    description: str
    third_party: Optional[str]
    
    # Contexto semántico (no técnico)
    context: Dict[str, Any]  # {"bank": "1101", "program": "education", ...}
```

#### 4. **AccountingDecision** - Decisión contable derivada
```python
@dataclass
class AccountingDecision:
    """Cómo se contabiliza el hecho económico"""
    id: Optional[int]
    event_id: int
    journal_entry: JournalEntry
    
    # Explicación estructurada
    rule_id: str                # Qué regla/template aplicó
    rule_version: str
    facts_used: Dict[str, Any]
    assumptions: List[str]
    calculations: Dict[str, Decimal]
    
    # Efectos
    fiscal_effects: FiscalEffects
    explanations: List[ExplanationNode]
    
    # Warnings
    warnings: List[str]         # Cosas inusuales pero permitidas
```

#### 5. **JournalEntry** - Asiento contable
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
    
    state: str                  # "draft", "posted", "reversed"
    
    # Invariante
    def is_balanced(self) -> bool:
        return sum(l.debit for l in self.lines) == sum(l.credit for l in self.lines)
    
    def post(self) -> None:
        if not self.is_balanced:
            raise BalanceError(...)
        self.state = "posted"
```

#### 6. **JournalLine** - Línea del asiento
```python
@dataclass
class JournalLine:
    """Línea de asiento con dimensiones analíticas"""
    id: Optional[int]
    entry_id: int
    
    # Cuenta (semántica, no código quemado)
    account: Account
    
    # Dinero (Decimal siempre)
    debit: Decimal              # 0.00 o importe
    credit: Decimal             # 0.00 o importe
    
    description: Optional[str]
    
    # Dimensiones analíticas
    analytics: List[AnalyticalDimensionValue]
```

#### 7. **Account** - Cuenta del catálogo
```python
@dataclass
class Account:
    """Cuenta contable gobernada"""
    id: Optional[int]
    code: str                   # Único
    name: str
    
    # Estructura canónica
    account_type: str           # "asset", "liability", "equity", "income", "expense"
    subtype: str                # "current", "noncurrent", "operating", ...
    nature: str                 # "debit", "credit"
    
    # Extensibilidad
    is_canonical: bool = True   # True = catálogo base; False = extensión usuario
    
    # Multiidioma
    name_osc: Optional[str]
    name_comercial: Optional[str]
```

#### 8. **FiscalRuleSet** - Reglas fiscales versionadas
```python
@dataclass
class FiscalRuleSet:
    """Reglas fiscales por fecha (México)"""
    id: Optional[int]
    version: str                # "2024-01-01"
    entity_profile_id: int      # Para qué tipo de entidad
    
    rules: Dict[str, Any]       # JSON con lógica
    
    effective_from: date
    effective_to: Optional[date]
    
    def calculate_tax(self, decision: AccountingDecision) -> FiscalEffects:
        """Calcula impuestos basado en decisión contable completa"""
        ...
```

#### 9. **AnalyticalDimension** - Dimensiones sin duplicar contabilidad
```python
@dataclass
class AnalyticalDimension:
    """Dimensión de análisis (programa, fuente, centro de costo)"""
    id: Optional[int]
    name: str                   # "Programa", "Fuente", "CentroCosto"
    entity_id: int
    
    values: List[str]           # ["Educación", "Salud", "Admin"]
    
@dataclass
class AnalyticalDimensionValue:
    """Valor de dimensión en una línea"""
    dimension: AnalyticalDimension
    value: str
```

#### 10. **Explanation** - Explicabilidad estructurada
```python
@dataclass
class ExplanationNode:
    """Nodo de explicación (no string libre)"""
    type: str                   # "rule_applied", "calculation", "assumption", "warning"
    label: str
    content: str
    
    # Datos estructurados
    data: Dict[str, Any]

@dataclass
class ExplanationData:
    """Paquete de explicación completa"""
    decision_id: int
    nodes: List[ExplanationNode]
    
    def render_common(self) -> str:
        """Versión para usuario común"""
        ...
    
    def render_professional(self) -> str:
        """Versión para contador"""
        ...
```

#### 11. **ReportDefinition** - Qué documento existe
```python
@dataclass
class ReportDefinition:
    """Define QUÉ documento puede generarse"""
    id: Optional[int]
    name: str                   # "Balanza", "Diario", "Estado Financiero"
    description: str
    
    # Qué necesita
    required_data: List[str]    # ["accounts", "journal_entries"]
    supported_formats: List[str] # ["pdf", "excel", "json"]
    
    # Cuándo aplica
    applicable_entities: List[str] # ["comercial", "osc", "both"]
    
    # Identificador de lógica
    renderer_id: str
    query_template_id: str
```

#### 12. **ReportRequest** - Qué generar esta vez
```python
@dataclass
class ReportRequest:
    """Solicitud de generación concreta"""
    id: Optional[int]
    report_definition_id: int
    entity_id: int
    
    # Parámetros
    from_date: date
    to_date: date
    as_of_date: Optional[date]  # Corte contable
    
    filters: Dict[str, Any]
    dimensions_to_group: List[str]
    
    format: str                 # "pdf", "excel", "json"
```

#### 13. **ReportPackage** - Preset oficial
```python
@dataclass
class ReportPackage:
    """Selección inicial de Aqorath"""
    id: Optional[int]
    name: str                   # "Bancos", "Asamblea", etc.
    
    # Qué incluye
    included_reports: List[ReportDefinition]
    suggested_parameters: Dict[str, Any]
    
    is_official: bool = True    # Preset de Aqorath, no usuario
```

#### 14. **CustomReportPackage** - Preset del usuario
```python
@dataclass
class CustomReportPackage:
    """Selección personalizada por usuario"""
    id: Optional[int]
    owner_entity_id: int
    
    name: str
    included_reports: List[ReportDefinition]
    
    created_at: datetime
```

#### 15. **Donation** - Donativo (OSC)
```python
@dataclass
class Donation:
    """Donativo recibido"""
    id: Optional[int]
    date: datetime
    amount: Decimal
    donor: Optional[str]
    
    purpose: Optional[str]      # Destino del donativo
    is_restricted: bool         # ¿Tiene restricción de uso?
```

#### 16. **Program** - Programa (OSC)
```python
@dataclass
class Program:
    """Programa de la organización"""
    id: Optional[int]
    entity_id: int
    
    name: str
    description: Optional[str]
    budget: Optional[Decimal]
```

#### 17. **AuditEvent** - Trazabilidad
```python
@dataclass
class AuditEvent:
    """Evento para auditoría"""
    id: Optional[int]
    entity_id: int
    
    event_type: str             # "entry_posted", "entry_reversed", "export", ...
    timestamp: datetime
    details: Dict[str, Any]
```

---

## INVARIANTES DE DOMINIO

1. **PARTIDA DOBLE:** `JournalEntry.is_balanced()` siempre true antes de post()
2. **DINERO EXACTO:** Todos los montos son Decimal, nunca float
3. **MONOENTIDAD:** Máximo una Entity activa por instalación (persistence enforces)
4. **INTEGRIDAD DE CUENTA:** JournalLine.account referencia solo Account que existe
5. **SEMÁNTICA DE SIGNOS:** Saldos normalizados según naturaleza (deudor → positivo, acreedor → negativo)
6. **FISCAL VERSIONADO:** FiscalRuleSet histórico recuperable por fecha
7. **EXPLICABILIDAD:** Cada AccountingDecision contiene datos para explicar por qué

---

## APPLICATION LAYER (Casos de Uso)

Los servicios de Application orquestan Domain + Infrastructure.

### Patrón: User Story → Service → Domain

```
CreateJournalEntryRequest (DTO)
    ↓
OperationService.create_entry(request)
    ├─ Interpreta EconomicEvent
    ├─ Aplica TemplateRule
    ├─ Genera AccountingDecision
    ├─ Valida partida doble
    ├─ Llama JournalRepository.save()
    └─ Retorna CreatedEntryResponse (DTO)
```

### Servicios Principales

- **OperationService:** Crear/modificar/revertir asientos
- **ReportingService:** Generar documentos/reportes
- **FiscalService:** Calcular impuestos, generar CFDI
- **ExerciseService:** Cierres, transferencias de resultado
- **CatalogService:** Gestionar cuentas (canónicas + extensiones)
- **EntityService:** Cambiar perfil de entidad, configuración

---

## INFRASTRUCTURE LAYER

Implementa interfaces/puertos para persistencia, rendering, integraciones.

### Repositories (Persistencia)

```python
class JournalRepository:
    def save(entry: JournalEntry) -> int: ...
    def find_by_id(id: int) -> Optional[JournalEntry]: ...
    def list_by_period(period_id: int) -> List[JournalEntry]: ...

class AccountRepository:
    def save(account: Account) -> int: ...
    def find_by_code(code: str) -> Optional[Account]: ...
    def list_canonical() -> List[Account]: ...
```

### Rendering

```python
class ReportRenderer:
    def render_pdf(report: GeneratedReport) -> bytes: ...
    def render_excel(report: GeneratedReport) -> bytes: ...
    def render_json(report: GeneratedReport) -> str: ...
```

---

## MODELO CONCEPTUAL COMPLETO

| Entidad | Capa | Naturaleza | Persistencia | Notas |
|---------|------|-----------|--------------|-------|
| Entity | Domain | Aggregate Root | Requerida | Singleton lógico |
| EntityProfile | Domain | Value Object | Requerida | Multicomponente |
| EconomicEvent | Domain | Entity | Requerida | Captura del hecho |
| AccountingDecision | Domain | Entity | Requerida | Auditoría |
| JournalEntry | Domain | Aggregate Root | Requerida | Invariante partida doble |
| JournalLine | Domain | Entity | Requerida | Parte de JournalEntry |
| Account | Domain | Entity | Requerida | Gobernada/Extensible |
| FiscalRuleSet | Domain | Value Object | Requerida | Histórico |
| AnalyticalDimension | Domain | Entity | Requerida | Flexibilidad |
| ExplanationData | Domain | Value Object | Opcional | Snapshot de decisión |
| ReportDefinition | Domain | Entity | Requerida | Catálogo de reportes |
| ReportRequest | Application | DTO | Opcional | Solo para solicitud |
| ReportPackage | Domain | Entity | Requerida | Presets |
| CustomReportPackage | Domain | Entity | Requerida | Personalizaciones |
| Donation | Domain | Entity | Requerida | OSC |
| Program | Domain | Entity | Requerida | OSC |
| AuditEvent | Domain | Entity | Requerida | Trazabilidad |

---

## TRANSICIÓN DESDE ACTUAL

No implementar en Phase 0. Solo documentar:

- Mover lógica de `app.py` → `application/`
- Separar models.py (persistencia) de domain/ (conceptual)
- Crear mappers Infrastructure ↔ Domain
- Consolidar modelos/libro.py → única autoridad
- Deprecate test/ → migrate a tests/

