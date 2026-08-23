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

#### 2. **EntityProfile** - Características económicas y jurídicas
```python
@dataclass
class EntityProfile:
    """Describe características ECONÓMICAS y JURÍDICAS, NO fiscales"""
    entity_id: int
    
    # Identidad económico-jurídica
    juridical_nature: str       # persona_fisica, persona_moral
    legal_form: str             # forma jurídica específica
    economic_purpose: str       # lucro / no_lucro
    
    # Capacidades especiales (ej. A.C. puede tener donataria)
    is_nonprofit: bool          # ¿es no lucrativa?
    is_donor_authorized: bool   # ¿Donataria autorizada SAT?
    special_capabilities: List[str]  # ["osc", "payroll_reporting", "inventory_control"]
    
    # Módulos habilitados (funcionales)
    modules_enabled: List[str]  # ["banking", "inventory", "osc", "payroll"]
    
    # Referencia a perfil fiscal (separado)
    fiscal_profile_id: int      # Referencia a FiscalProfile versionado
```

#### 2a. **UserKnowledgeState** - Preferencias pedagógicas del usuario (Monousuario)
```python
@dataclass
class UserKnowledgeState:
    """Estado de conocimiento LOCAL del propietario (monousuario)"""
    id: Optional[int]
    
    # Preferencias pedagógicas
    explanation_level: str      # "none", "brief", "detailed"
    concepts_seen: List[str]    # Conceptos ya presentados al usuario
    
    # Configuración de UI
    ui_language: str            # "es", "en"
    decimal_separator: str      # "." o ","
    currency_symbol: str        # "$", "MX$", "USD"
    
    # Preferencias de reporteo
    preferred_report_format: str  # "pdf", "excel"
    always_show_professional_view: bool
    
    # Historial de aprendizaje
    learned_topics: Dict[str, datetime]  # Cuándo aprendió cada tema
```

**NOTA:** Monousuario significa:
- ✓ Una identidad/perfil del propietario
- ✓ Preferencias locales guardadas
- ✓ UserKnowledgeState persistido
- ✗ RBAC empresarial
- ✗ Múltiples operadores concurrentes
- ✗ Auditoría por usuario

#### 2b. **FiscalProfile** - Régimen fiscal y obligaciones
```python
@dataclass
class FiscalProfile:
    """Describe RÉGIMEN FISCAL y obligaciones tributarias"""
    id: Optional[int]
    entity_id: int
    
    # Régimen (códigos SAT neutrales)
    fiscal_regime_code: str     # RIF, RGSO, RGSO+, RFSC, etc.
    tax_obligation_level: str   # ordinary, simplified, micro, exempt
    
    # Efectivas desde
    effective_from: date
    effective_to: Optional[date]
    
    # Referencia a reglas que aplican
    fiscal_rule_set_id: int     # FiscalRuleSet versionado para este período
    
    # Requisitos de reporte
    requires_cfdi: bool
    requires_monthly_vat: bool
    requires_annual_isr: bool
    
    # Cambios de régimen deben conservar histórico
    # Un Entity puede cambiar FiscalProfile a lo largo del tiempo
```

**IMPORTANTE:** Una A.C. (EntityProfile.is_nonprofit=true) PUEDE tener FiscalProfile.fiscal_regime_code="RFSC" (Régimen Fiscal de Contribuyentes Morales). Los dos conceptos son independientes y complementarios.

#### 3. **ThirdParty** - Contrapartes (Clientes, Proveedores, Donantes, etc.)
```python
@dataclass
class ThirdParty:
    """Tercero con quien la entidad se relaciona"""
    id: Optional[int]
    entity_id: int              # La entidad contable propietaria
    
    # Identidad
    name: str
    rfc: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    
    # Clasificación
    party_type: str             # "customer", "supplier", "donor", "creditor", "debtor", "other"
    
    # Datos adicionales
    address: Optional[str]
    contact_person: Optional[str]
    notes: Optional[str]
    
    # Control
    is_active: bool
    created_at: datetime
```

**IMPORTANTE:** Monoentidad (una instalación = una Entity) NO significa "sin clientes". Significa:
- ✓ Tabla ThirdParty (clientes, proveedores, donantes, acreedores, deudores)
- ✗ Tabla CompanySelector o ManagedEntity[]
- ✗ Múltiples filas Company activas
- ✗ "Seleccionar empresa" en UI

Una instalación administra **una** entidad contable pero se relaciona con **miles** de terceros.

#### 3b. **DocumentReference** - Referencias a documentos fuente
```python
@dataclass
class DocumentReference:
    """Vinculación a documento físico/digital fuente"""
    id: Optional[int]
    entry_id: int               # Asiento referenciado
    
    # Tipo de documento
    document_type: str          # "cfdi", "recibo", "factura", "contrato", "otro"
    
    # Identificación
    document_number: str        # Folio, número, referencia
    issuer_name: Optional[str]
    date: datetime
    
    # Almacenamiento
    file_hash: Optional[str]    # SHA-256 para integridad
    file_path: Optional[str]    # Si se almacena localmente
    external_url: Optional[str] # Si es referencia remota
    
    # Validación
    is_validated: bool
    validation_notes: Optional[str]
```

#### 4. **EconomicEvent** - Hecho económico capturado por usuario
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
    
    # Cuándo aplica (capacidades y requisitos estructurados)
    requires_capabilities: List[str]      # ["osc", "inventory", "payroll"] - debe tener
    forbidden_capabilities: List[str]     # ["payroll"] - no debe tener
    required_fiscal_features: List[str]   # ["requires_cfdi", "requires_monthly_vat"]
    
    # NO usar ["comercial", "osc", "both"] — eso reintroduce el viejo switch
    
    # Identificador de lógica
    renderer_id: str
    query_template_id: str
```

**NOTA CRÍTICA:** `applicable_entities` debe ser reemplazado con `requires_capabilities` + `forbidden_capabilities` + `required_fiscal_features`. Esto permite expresar lógica compleja como:
- "Este reporte requiere ser OSC Y tener módulo de donativos" → `requires_capabilities=["osc", "donations"]`
- "Este reporte NO aplica a payroll" → `forbidden_capabilities=["payroll"]`
- "Requiere declaración mensual VAT" → `required_fiscal_features=["requires_monthly_vat"]`

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
5. **SEMÁNTICA DE SIGNOS FORMAL:** Dos conceptos distintos SIEMPRE SEPARADOS:

   **A) LedgerSignedBalance** — saldo algebraico literal
   ```
   LedgerSignedBalance = sum(débitos) - sum(créditos)
   
   Ejemplo:
   Ingreso: debit=0, credit=100 → LedgerSignedBalance = 0 - 100 = -100
   Gasto:   debit=40, credit=0  → LedgerSignedBalance = 40 - 0 = +40
   ```
   
   **B) NormalBalanceAmount** — magnitud conforme a naturaleza contable
   ```
   Ingreso (naturaleza=credit): 
     LedgerSignedBalance = -100 → NormalBalanceAmount = +100
   Gasto (naturaleza=debit):
     LedgerSignedBalance = +40 → NormalBalanceAmount = +40
   
   Fórmula general:
   NormalBalanceAmount = LedgerSignedBalance * (-1 si nature=credit, +1 si nature=debit)
   ```
   
   **PROHIBIDO:** Usar ambos indistintamente. PROHIBIDO asumir que "saldo normalizado" es lo mismo que "saldo algebraico".

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

## EXACTITUD MONETARIA (Política de Escala y Redondeo)

**PROHIBIDO:** Asumir que "2 decimales" es universal para TODO tipo de valor.

**Distinción de tipos:**

| Tipo | Rango de Escala | Política de Redondeo | Ejemplos |
|------|-----------------|---------------------|----------|
| Money (dinero) | 2 decimales | Redondeo bancario (half-even) | Ingresos, gastos, bancos |
| TaxRate | Variable (2-6) | Truncar, nunca redondear | ISR al 17.15%, IVA 16% |
| ExchangeRate | Variable (4-8) | Usar precisión del mercado | USD/MXN: 20.5234 |
| Percentage | 2 decimales | Truncar/redondear según contexto | 15.25% de margen |
| Intermediate Calculation | Decimal exacto | SIN redondeo intermedio | Cálculos internos mantienen precisión |

**DECISIONES EN PHASE 1:**
- Especificar representación persistente exacta (SQLite NUMERIC vs DECIMAL)
- Definir redondeo en frontera contable (qué operaciones pueden perder precisión)
- Definir redondeo en frontera fiscal (cálculos de impuestos)
- Realizar round-trip tests (guardar → leer → verificar exactitud)

**ACTUAL (NO DECISIVO):**
- NO imponer cuantización a 2 decimales en TODOS los cálculos
- Float PROHIBIDO en persistencia (core.py línea 690 bug conocido)
- Decimal permitido siempre en memoria
- Serialización JSON puede usar string decimal

---

## MODELO CONCEPTUAL COMPLETO (30+ Elementos Evaluados)

### Tabla Resumida

| Entidad | Capa | Naturaleza | Persistencia | Decisiones Abiertas |
|---------|------|-----------|--------------|-----|
| Entity | Domain | Aggregate Root | Requerida | Singleton enforced en qué capa |
| EntityProfile | Domain | Value Object | Requerida | Cambiar perfil = historial versionado |
| FiscalProfile | Domain | Value Object | Requerida | ¿Versionado separado de entidad? |
| AccountingPeriod | Domain | Entity | Requerida | ¿Períodos solapables o exclusivos? |
| FiscalYear | Domain | Value Object | Requerida | ¿Coincide con año calendario o fiscal? |
| Account | Domain | Entity | Requerida | is_canonical marca, no bloquea extensión |
| AccountExtension | Domain | Entity | Requerida | Usuario define, validación no bloqueo |
| EconomicEvent | Domain | Entity | Requerida | ¿Versionable o inmutable? |
| AccountingDecision | Domain | Entity | Requerida | Justificación completa persistida |
| JournalEntry | Domain | Aggregate Root | Requerida | Invariante: partida doble siempre |
| JournalLine | Domain | Entity | Requerida | Parte de JournalEntry, sin independencia |
| ThirdParty | Domain | Entity | Requerida | Agrega clientes, proveedores, donantes |
| DocumentReference | Domain | Entity | Requerida | CFDI, recibo, factura, documento fuente |
| Program | Domain | Entity | Requerida | OSC: programa/proyecto/fondo |
| Fund | Domain | Entity | Requerida | OSC: recurso financiero gestionar |
| FundingSource | Domain | Entity | Requerida | OSC: tipo fuente (donativa, propia, etc) |
| AnalyticalDimension | Domain | Entity | Requerida | Usuario define dimensiones de análisis |
| Donation | Domain | Entity | Requerida | OSC: donativo individual |
| InKindDonation | Domain | Entity | Requerida | OSC: donativo en especie, valuación |
| BankAccount | Domain | Entity | Requerida | Cuenta bancaria, conexión a cuentas contables |
| FiscalRuleSet | Domain | Value Object | Requerida | Versionado por fecha, histórico recuperable |
| ExplanationData | Domain | Value Object | Opcional | Paquete no persistido si lógica es recuperable |
| UserKnowledgeState | Domain | Value Object | Opcional | Preferencias pedagogía, nivel de detalle |
| ReportDefinition | Domain | Entity | Requerida | Qué documento PUEDE generarse |
| ReportRequest | Application | DTO | Opcional | Parámetros concretos, no persistible |
| ReportPackage | Domain | Entity | Requerida | Presets oficiales de Aqorath |
| CustomReportPackage | Domain | Entity | Requerida | Presets personalizados por usuario |
| ReportGenerationRequest | Application | DTO | Opcional | Solicitud en vuelo (async/batch) |
| AuditEvent | Domain | Entity | Requerida | Trazabilidad de cambios, auditoría |

### Explicación de Decisiones Abiertas

**FiscalProfile versionado:** ¿Cada cambio en perfil fiscal crea histórico? ¿O es reemplazable? Depende de requisitos normativos mexicanos.

**AccountingPeriod:** ¿Períodos mensuales fijos o definibles? ¿Solapables para comparativas?

**FiscalYear:** ¿Sistema sigue año civil (Ene-Dic) o fiscal personalizado?

**AccountExtension:** Permite crear cuentas que extienden estructura canónica. Validación asegura coherencia pero NO bloquea creación.

**EconomicEvent:** ¿Registra todos los intentos (fallidos + exitosos) o solo hechos persistidos?

**DocumentReference:** Vínculo a documento fuente (CFDI, recibo, contrato). ¿Almacena contenido o solo referencia?

**ReportGenerationRequest:** Para reportes grandes/async. ¿Qué persistencia temporal? ¿Cuánto tiempo guardar generaciones anteriores?

**UserKnowledgeState:** Pedagogía adaptativa local. ¿Almacena qué conceptos vio el usuario? ¿Ajusta explicaciones?

---

## TRANSICIÓN DESDE ACTUAL

**ACLARACIÓN CRÍTICA:** La autoridad objetivo es la **nueva arquitectura** (DOMAIN + APPLICATION + INFRASTRUCTURE), **NO** modelos/libro.py.

Proceso de transición (no implementar en Phase 0):

1. **Identificar comportamiento útil** en modelos/libro.py
2. **Migrar ese comportamiento** a aqorath/core.py con tests
3. **Eliminar dependencia** de modelos/libro.py en app.py
4. **Deprecate modelos/libro.py** formalmente
5. **Retirar** después de Phase 1

**CAMBIOS NO NEGOCIABLES:**
- SQLite (aqorath/) = autoridad única
- modelos/libro.py = solo para lectura/auditoria histórica (si es necesario)
- Trial balance, asientos, saldos: SIEMPRE desde SQLite
- Ningún fallback a Pandas/Excel

**CAMBIOS ESPECÍFICOS:**

- Mover lógica de `app.py` → `application/`
- Separar models.py (persistencia) de domain/ (conceptual)
- Crear mappers Infrastructure ↔ Domain
- Consolidar test/ → tests/

