# REPO AUDIT V1 — ARQUEOLOGÍA Y ESTADO ACTUAL

**Fecha de auditoría:** 2026-08-23
**Rama:** main
**Commit:** HEAD
**Estado de tests:** 26/26 PASSED

---

## RESUMEN EJECUTIVO

Aqorath es un **ERP contable en transición arquitectónica** con hallazgos críticos que **afectan integridad contable**.

**Estado:** Funcional para casos básicos, pero con **4 riesgos P0** y **4 riesgos P1** que deben resolverse antes de producción.

**Nota de FASE 0.2:** Esta auditoría ha sido REVISADA para identificar:
- 4 hallazgos P0 (antes: 3) — incluye account_code no validado
- 4 hallazgos P1 (antes: 4) — downgrade de test/tests a P2, upgrade de fallback Excel a P1
- 5 hallazgos P2 (antes: 3+) — para deuda técnica acumulada

---

## HALLAZGOS CRÍTICOS P0 (Integridad Contable)

### P0-1: SEMÁNTICA DE SIGNOS INCORRECTA EN RESULTADO

**Ubicación:** `aqorath/core.py::_balances_from_sqlite()` + `aqorath/accounting_rules.py::compute_resultado_ejercicio()`

**Descripción:**
```python
# core.py calcula algebraicamente
saldo = debit - credit

# Para cuenta acreedora (ingreso):
# debit=0, credit=100
# saldo = 0 - 100 = -100

# compute_resultado hace:
resultado = ingresos - costos - gastos
# Si ingresos = -100, resultado = -100 - ... (INCORRECTO)
```

**Impacto:** 
- Resultado del ejercicio **incorrecto** (signo opuesto o magnitud incorrecta)
- Cierre contable produce asiento **con valores erróneos**
- Usuario no detecta el error porque el asiento está balanceado (pero mal)

**Causa Raíz:**
- `_balances_from_sqlite()` devuelve saldo algebraico (debit - credit)
- `compute_resultado_ejercicio()` asume saldos normalizados (ingresos positivos)
- Nunca se reconcilian los dos conceptos

**Verificación:**
```
Caso mínimo: 
- Venta 100 (acreedora): DB=0, CR=100 → saldo = -100
- Gasto 40 (deudor): DB=40, CR=0 → saldo = +40
- Resultado esperado: +60
- Resultado actual: -100 - 40 = -140 (INCORRECTO)
```

**Clasificación:** **P0 (CRÍTICO)** — Puede producir estados financieros materialmente incorrectos.

---

### P0-2: FLOAT PARA DINERO EN PERSISTENCIA

**Ubicación:** 
- `aqorath/models.py` líneas 43-44 (JournalLine)
- `aqorath/models.py` línea 52 (Asset)
- `aqorath/core.py` línea 690 (insert `float()`)

**Descripción:**
```python
class JournalLine(SQLModel, table=True):
    debit: float = 0.0      # ✗ DEBE SER DECIMAL
    credit: float = 0.0     # ✗ DEBE SER DECIMAL

class Asset(SQLModel, table=True):
    value: float            # ✗ DEBE SER DECIMAL

# En _persist_entry()
jl_kwargs["debit"] = float(ln.get("debit") or 0)  # ✗ Convierte a float
```

**Impacto:** 
- Pérdida de precisión decimal en cálculos
- Redondeadores silenciosos durante aritmética
- Diferencias acumulativas en balanzas repetidas

**Clasificación:** **P0 (CRÍTICO)** — Violación directa de Regla 5 (Dinero Exacto).

---

### P0-3: PARÁMETRO `as_of` IGNORADO EN trial_balance()

**Ubicación:** `aqorath/core.py` función `trial_balance(as_of: Optional[str])`

**Descripción:**
- Función acepta `as_of` como parámetro
- Parámetro NO es usado en ninguna cláusula WHERE
- Devuelve balanza con TODOS los movimientos, ignorando fecha

**Impacto:**
```python
trial_balance("2026-03-31")  # ¿Balanza al 31 de marzo?
# Retorna: Balanza con movimientos de MARZO + ABRIL + MAYO + ...
```

- Balanza "al 31 de marzo" incluye movimientos posteriores
- Cierres de período usan esta función → **Asiento de cierre incorrecto**

**Verificación:**
- Movimientos 2026-03-15: Ingreso 100
- Movimientos 2026-04-15: Gasto 50
- `trial_balance("2026-03-31")` debería retornar Ingreso=100, Gasto=0
- Retorna: Ingreso=100, Gasto=50 (INCORRECTO)

**Clasificación:** **P0 (CRÍTICO)** — Afecta cierres contables y comparativas de período.

---

### P0-4: account_code NO VALIDADO CONTRA CATÁLOGO

**Ubicación:** `aqorath/core.py::_verify_accounts()` línea 245-260

**Descripción:**
```python
def _verify_accounts(entry_dict):
    """Verifica que asiento esté balanceado, pero NO valida cuentas"""
    for line in entry_dict['lines']:
        account_code = line.get('account_code')
        # ✗ Si se proporciona solo account_code (texto):
        #   Sistema permite persistencia SIN verificar que existe
        #   en Account/catálogo gobernado
```

**Impacto:**
```
Caso concreto:
1. Usuario proporciona: {"account_code": "9999-XX-INEXISTENTE"}
2. Asiento está balanceado: débitos = créditos ✓
3. Sistema persiste asiento completo
4. Posterior consulta a catálogo muestra código huérfano
5. Reportes filtran cuentas conocidas → dato "desaparece"
6. Estados financieros están incompletos pero no hay error visible
```

**Verificación requerida:**
- Asiento con account_code inexistente
- Balanceado (débitos = créditos)
- Debe ser RECHAZADO con mensaje "Cuenta no existe en catálogo"
- Actual: Permitido (BUG)

**Clasificación:** **P0 (CRÍTICO)** — Permite persistencia de póliza estructuralmente inválida aunque algebraicamente balanceada. Viola Regla 4 (PARTIDA DOBLE COMO INVARIANTE ABSOLUTA) en interpretación estricta: un asiento inválido no debe persistirse.

---

## HALLAZGOS GRAVES P1 (Contradicción Arquitectónica + Fallback Silencioso)

### P1-1: JournalEntry ORM INCOMPATIBLE CON _persist_entry()

**Ubicación:** 
- Modelo: `aqorath/models.py` línea 26-33
- Construcción: `aqorath/core.py` línea 671

**Problema:**
```python
# Modelo requiere:
class JournalEntry(SQLModel, table=True):
    date: datetime          # ✗ REQUERIDO (sin default)
    concept: Optional[str]  # Opcional
    ...

# Código intenta crear:
je = JournalEntry(description=desc, created_at=now)
#    ↑ 'description' no existe en modelo
#    ↑ 'date' no proporcionado (requerido!)
```

**Impacto:**
- ORM path **falla** con TypeError (missing required `date`)
- Fallback silencioso a SQLite directo
- Usuario no ve el error

**Clasificación:** **P1 (GRAVE)** — Causa fallo silencioso, autoridad única comprometida.

---

### P1-2: config.py INTENTA `AppConfig.select()` QUE NO EXISTE

**Ubicación:** `aqorath/config.py` líneas 65, 86

**Problema:**
```python
# SQLModel NO tiene método .select()
row = s.exec(AppConfig.select().where(...))
      ↑ AttributeError en runtime

# Debería ser:
row = s.exec(select(AppConfig).where(...))
```

**Impacto:**
- `read_accounting_model()` lanza exception
- catch Exception genérico → fallback a `~/.local/share/aqorath/config.json`
- Usuario no sabe si está usando BD o archivo JSON (INCONSISTENCIA)

**Clasificación:** **P1 (GRAVE)** — Fallback silencioso a archivo local, autoridad comprometida.

---

### P1-3: CATÁLOGO INMUTABLE BLOQUEA EXTENSIBILIDAD (Regla 10)

**Ubicación:** `aqorath/storage.py` líneas 50-64

**Problema:**
```python
@event.listens_for(Account, "before_insert")
def _prevent_non_catalog_account(...):
    if code not in catalog_codes:
        raise ValueError("Inserción denegada: cuenta no en catálogo")
```

**Impacto:**
- Usuario NO puede crear su propia cuenta "Banco Mi-Cuenta"
- BLOQUEA Regla 10 (Catálogo gobernado Y extensible)
- docs/CATALOG_POLICY.md dice "Inmutable" pero CONSTITUTION Regla 10 dice "Extensible"

**Clasificación:** **P1 (GRAVE)** — Conflicto arquitectónico explícito con CONSTITUTION.

---

### P1-4: FALLBACK EXCEL/PANDAS COMO SEGUNDA AUTORIDAD (CRÍTICO)

**Ubicación:** `modelos/libro.py` + `aqorath/core.py` lineas 700+

**Problema:**
```python
# En aqorath/core.py:
try:
    result = trial_balance_from_sqlite(...)
except Exception:
    result = trial_balance_from_pandas_fallback(...)  # ✗ Fallback silencioso
```

- Si SQLite falla: sistema cae a Pandas/Excel (authority bifurcada)
- Usuario no sabe cuál es la fuente de verdad
- Cambios en Pandas pueden no reflejarse en SQLite (divergencia)
- Datos pueden estar diferentes dependiendo de "qué pasó esta sesión"

**Impacto:**
- Viola Regla 7 (SQLite como fuente contable local)
- Viola Regla 2 (una contabilidad única)
- Dos autoridades compiten → resultados diferentes

**Clasificación:** **P1 (GRAVE)** — Causa bifurcación de autoridad contable. Aunque actualmente funciona, es riesgo estructural que afecta integridad.

---

### P1-5: DUPLICACIÓN test/ + tests/ (Autoridad Única de Tests)

**Ubicación:** Dos carpetas paralelas

**Estado:**
```
test/         16 tests → todos PASSED
tests/        10 tests → todos PASSED
```

**Problema:**
- Dos carpetas de tests que se ejecutan en paralelo
- Posible divergencia de cobertura
- CI debe ejecutar ambas (ineficiente)
- Deprecación de una requiere refactor

**Clasificación:** **P2 (IMPORTANTE)** — No es crítica para integridad de datos (anterior P1-4 es más urgente). Pero viola Regla 24 (una autoridad única) en testing. Consolidar a tests/, deprecate test/ en Phase 1.

---

## HALLAZGOS TÉCNICOS P2 (Deuda Importante)

### P2-1: DEPENDENCIAS NO DECLARADAS (4)

**Verificado directamente contra requirements.txt y código:**

| Paquete | Ubicación | Estado |
|---------|-----------|--------|
| PySide6 | aqorath/desktop.py, aqorath/ui/ | **NO DECLARADO** |
| Jinja2 | aqorath/api.py (fastapi.templating) | **NO DECLARADO** (dependencia transitiva) |
| python-multipart | FastAPI file uploads | **NO DECLARADO** |
| req | requirements.txt línea 8 | DECLARADO pero probablemente accidental |

**Impacto:**
- PySide6 ausente → `aqorath/desktop.py` NO IMPORTABLE
- aqorath/api.py NO IMPORTABLE (falta `reports_jinja`)

**Verificación ejecutada:**
```bash
python -c "import aqorath.api"
# ModuleNotFoundError: No module named 'aqorath.reports_jinja'

python -c "import aqorath.desktop"
# ModuleNotFoundError: No module named 'PySide6'
```

**Clasificación:** **P2 (IMPORTANTE)** — Interfaces quebradas, no testeable.

---

### P2-2: aqorath/api.py IMPORTA reports_jinja CON PATH INCORRECTO

**Ubicación:** `aqorath/api.py` línea 15

**Problema:**
```python
from .reports_jinja import generate_pdf_from_preview
     ↑ Intenta importar como módulo de aqorath/
```

**Realidad:**
```
reports_jinja.py  ← en raíz, no en aqorath/
```

**Impacto:**
- ModuleNotFoundError en import
- `aqorath/api.py` no se puede importar
- FastAPI endpoints no disponibles

**Clasificación:** **P2 (IMPORTANTE)** — API no funcional.

---

### P2-3: main.py ES CLI, NO DESKTOP

**Estado anterior (INCORRECTO):**
- Clasificado como "Desktop entry point"

**Estado actual (CORRECTO):**
- CLI orientada a:
  - `fetch-xsds` (descargar esquemas XSD)
  - `generate-cfdi` (generar CFDI mínimo)
  - `import-timbrado` (importar CFDI timbrado)

**Clasificación:** **Corrección factual** — main.py NO es superficie Desktop.

---

### P2-4: reports_jinja.py UBICACIÓN Y IMPORTS INCONSISTENTES

**Ubicación:** `reports_jinja.py` (raíz del repo)

**Problema:**
```python
# Importadores (aqorath/api.py, aqorath/desktop.py):
from .reports_jinja import generate_pdf_from_preview
     ↑ Intenta importar como subpaquete

# Realidad:
reports_jinja.py está en raíz, no en aqorath/

# Además, reports_jinja.py usa:
from .core import ...
from .company import ...
from .storage import ...
     ↑ Imports relativos que asumen ubicación en aqorath/
```

**Conflicto:**
- `reports_jinja.py` usa imports relativos (`.core`, `.storage`)
- Pero está en raíz, no en `aqorath/`
- Entonces los imports relativos NO resuelven a módulos reales

**Dependencias no declaradas en reports_jinja.py:**
- `jinja2` → para templates
- `weasyprint` → para PDF

**Clasificación:** **P2 (IMPORTANTE)** — Arquitectura/empaquetado de reportes inconsistente. Debe decidirse en Phase 1:
- ¿Mover reports_jinja.py a aqorath/reporting/ ?
- ¿O refactorizar imports relativos?
- ¿O declarar jinja2 + weasyprint en requirements.txt?

---

### P2-5: 29 except Exception GENÉRICAS

**Detectadas en:**
- aqorath/core.py (5+)
- modelos/libro.py (6+)
- modelos/registro.py (4+)
- otros (10+)

**Riesgo:**
- Errores silenciosos, difíciles de debuggear
- Viola Regla 25 (no fallbacks que oculten errores)

**Clasificación:** **P2 (IMPORTANTE)** — Deuda técnica, debugging difícil.

---

## ESTADO DE COMPONENTES (CLASIFICACIÓN REVISADA)

| Componente | Clasificación | Descripción |
|-----------|---|---|
| aqorath/core.py | CANÓNICA | Motor contable, tiene bugs P0 pero reparable |
| aqorath/models.py | TRANSICIONAL | ORM SQLModel, mezcla persistencia+domain. Phase 1 separará. |
| aqorath/templates.py | CANÓNICA | Plantillas de reglas contables, funcional |
| aqorath/storage.py | TRANSICIONAL | Sesión/listener, problemas P1 pero recoverable |
| aqorath/catalog.py | CANÓNICA | Catálogo, funcional aunque bloquea extensibilidad |
| aqorath/exercise.py | TRANSICIONAL | Cierres, requiere bug fix as_of. No es canónica hasta P0-3 esté reparado. |
| aqorath/config.py | TRANSICIONAL | Tiene fallback silencioso (P1-2). Candidato a refactor. |
| aqorath/api.py | ROOTA | NO IMPORTABLE (missing reports_jinja). Candidata a deprecación si se elige desktop. |
| aqorath/desktop.py | RAÍZ | NO IMPORTABLE (missing PySide6). Candidata a deprecación si se elige web. |
| modelos/libro.py | LEGACY | Fallback Pandas/Excel. Debe eliminarse en Phase 1 tras migración. |
| test/ | LEGACY | 16 tests. Merge a tests/ en Phase 1. |
| tests/ | CANÓNICA | 10 tests. Suite objetivo. |
| app.py (root) | RECUPERABLE | Punto de entrada híbrido. Uso actual TBD. |
| api/app.py | PROTOTIPO | FastAPI app stub, candidata a consolidación. |
| reports_jinja.py | RECUPERABLE | Importable pero ubicación inconsistente (ver P2-12). |

**REGLA DE CLASIFICACIÓN:**
- **CANÓNICA:** Componente alineado con ARCHITECTURE_BASELINE_V1, sin bugs críticos, sin fallbacks silenciosos.
- **TRANSICIONAL:** Funciona ahora, pero tiene deuda. Target de refactoring en Phase 1.
- **LEGACY:** Código antiguo, deprecación planeada en Phase 1/2.
- **RECUPERABLE:** Funciona pero ubicación/importación inconsistente con arquitectura. Reparable rápidamente.
- **ROOTA:** No importable, requiere decisión de arquitectura (desktop vs web) para depuración.
- **PROTOTIPO:** Borrador, función no clara, candidata a consolidación o eliminación.

---

## VERIFICACIÓN FINAL

### Tests Ejecutados
```
Command: python -m pytest -v
Result:  26/26 PASSED (0.91s)

test/ (legacy):     16 PASSED
tests/ (new):       10 PASSED
```

### Importabilidad
```
✓ import aqorath.core
✗ import aqorath.api        → ModuleNotFoundError: reports_jinja
✗ import aqorath.desktop    → ModuleNotFoundError: PySide6
```

### Dependencias Usadas pero No Declaradas
```
PySide6                 → aqorath/desktop.py, aqorath/ui/
Jinja2                  → aqorath/api.py (vía fastapi.templating)
python-multipart        → FastAPI file uploads
```

---

## PRIORIDADES P0/P1/P2 REVISADAS

| # | Severidad | Hallazgo | Causa Raíz | Mitigación |
|---|-----------|----------|-----------|-----------|
| 1 | **P0** | Semántica de signos incorrecto (P0-1) | LedgerSignedBalance vs NormalBalanceAmount no separados | Formalizar dos conceptos, reconciliar cálculos |
| 2 | **P0** | Float para dinero en persistencia (P0-2) | Violación Regla 5 | Migrar JournalLine/Asset a Decimal |
| 3 | **P0** | as_of ignorado en trial_balance (P0-3) | Parámetro acepto pero no usado | Aplicar WHERE date <= as_of |
| 4 | **P0** | account_code no validado (P0-4) | verify_accounts solo chequea balance | Validar account_code existe en Account |
| 5 | **P1** | JournalEntry ORM incompatible (P1-1) | Modelo requiere date, código no lo proporciona | Proporcionar date en construcción |
| 6 | **P1** | config.py falla silenciosa (P1-2) | AppConfig.select() no existe en SQLModel | Usar select(AppConfig) de sqlalchemy |
| 7 | **P1** | Catálogo inmutable bloquea (P1-3) | Listener previene inserción fuera catálogo | Cambiar a validador, permitir extensiones |
| 8 | **P1** | Fallback Excel/Pandas bifurca autoridad (P1-4) | Except captura, cae a trial_balance_from_pandas | Eliminar fallback, fallar explícitamente |
| 9 | **P2** | test/ + tests/ duplicados (P1-5 downgrade P2) | Dos suites paralelas | Consolidar a tests/, deprecate test/ |
| 10 | **P2** | Dependencias no declaradas (P2-1) | PySide6, python-multipart no en requirements.txt | Agregar a requirements.txt o requirements-*.txt |
| 11 | **P2** | reports_jinja path inconsistente (P2-4) | En raíz pero usa imports relativos | Ubicar en aqorath/ O refactorizar imports |
| 12 | **P2** | 29 except Exception genéricas (P2-5) | Captura genérica, debugging difícil | Especificar excepciones (ValidationError, etc) |

---

## DECISIONES PENDIENTES

1. ¿CFDI será funcionalidad productiva o educativa?
2. ¿Módulo OSC integrado o separable?
3. ¿Cuándo realizar deprecación de modelos/?
4. ¿Licencia social qué modelo?
5. ¿UI primaria: desktop (PySide) o web (FastAPI)?
6. ¿Multimoneda nunca o Phase 3+?
7. ¿Depreciaciones módulo integrado?

---

## PRÓXIMOS PASOS

**Phase 0.2 (correcciones documentales):** 
- Completar modelo conceptual (30+ elementos)
- Formalizar LedgerSignedBalance vs NormalBalanceAmount
- Separar EntityProfile / FiscalProfile
- Revisar prioridades (account_code es P0, no P1)
- Revisar clasificación de componentes

**Phase 1 (Corregir P0 — INTEGRIDAD CONTABLE):**
1. P0-1: Semántica de signos (LedgerSignedBalance vs Normal)
2. P0-2: Float → Decimal en persistencia
3. P0-3: as_of filtrado en trial_balance()
4. P0-4: account_code validado contra catálogo
5. P1-4: Eliminar fallback Excel/Pandas (bifurcación de autoridad)

**Phase 2 (Corregir P1 + P2-1/2):**
- P1-1: JournalEntry ORM compatible
- P1-2: config.py sin falla silenciosa
- P1-3: Catálogo permitir extensiones
- P1-5: Consolidar test/ → tests/
- P2-1: Declarar dependencias (PySide6, etc)
- P2-4: Ubicar reports_jinja correctamente

**Phase 3 (Deuda técnica):**
- P2-5: Reemplazar 29 except Exception
- Refactorización arquitectónica
- Documentación completa

