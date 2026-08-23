# REPO AUDIT V1 — ARQUEOLOGÍA Y ESTADO ACTUAL

**Fecha de auditoría:** 2026-08-23
**Rama:** main
**Commit:** HEAD
**Estado de tests:** 26/26 PASSED

---

## RESUMEN EJECUTIVO

Aqorath es un **ERP contable en transición arquitectónica** con hallazgos críticos que **afectan integridad contable**.

**Estado:** Funcional para casos básicos, pero con **3 riesgos P0** y **4 riesgos P1** que deben resolverse antes de producción.

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

## HALLAZGOS GRAVES P1 (Contradicción Arquitectónica)

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

### P1-4: DUPLICACIÓN test/ + tests/ (Autoridad Única)

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

**Clasificación:** **P1 (GRAVE)** — Viola Regla 24 (una autoridad única).

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

### P2-4: 29 except Exception GENÉRICAS

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

## ESTADO DE COMPONENTES

| Componente | Clasificación | Descripción |
|-----------|---|---|
| aqorath/core.py | CANÓNICA | Motor contable, reparable |
| aqorath/models.py | CANÓNICA | ORM SQLModel, requiere Decimal |
| aqorath/templates.py | CANÓNICA | Plantillas, funcional |
| aqorath/storage.py | CANÓNICA | Sesión, listener problemático |
| aqorath/catalog.py | CANÓNICA | Catálogo, funcional |
| aqorath/exercise.py | CANÓNICA | Cierres, requiere as_of fix |
| aqorath/config.py | CANÓNICA | Config, falla silenciosa en BD |
| aqorath/api.py | ROOTA | NO IMPORTABLE (missing reports_jinja) |
| aqorath/desktop.py | RAÍZ | NO IMPORTABLE (missing PySide6) |
| modelos/libro.py | LEGACY | Fallback DataFrames, debe eliminarse |
| test/ | LEGACY | Migrate a tests/, deprecate |
| tests/ | CANÓNICA | Suite actual, 26 tests PASSED |
| app.py (root) | LEGACY | Parece CLI/híbrido, unclear |
| api/app.py | PROTOTIPO | FastAPI app stub |

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

| # | Severidad | Hallazgo | Mitigación |
|---|-----------|----------|-----------|
| 1 | **P0** | Semántica de signos incorrecto | Reconciliar cálculos de saldos con naturaleza |
| 2 | **P0** | Float para dinero | Migrar JournalLine/Asset a Decimal |
| 3 | **P0** | as_of ignorado | Aplicar date filter en trial_balance() |
| 4 | **P1** | JournalEntry ORM incompatible | Proporcionar date en construcción |
| 5 | **P1** | config.py falla silenciosa | Usar select() correcto de SQLModel |
| 6 | **P1** | Catálogo inmutable bloquea | Cambiar listener a validador |
| 7 | **P1** | test/ + tests/ duplicados | Consolidar a tests/, deprecate test/ |
| 8 | **P2** | Dependencias no declaradas | PySide6, python-multipart en requirements.txt |
| 9 | **P2** | reports_jinja path incorrecto | Usar import relativo correcto |
| 10 | **P2** | 29 except Exception genéricas | Reemplace con excepciones específicas |

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

**Phase 0.1 (esta auditoría):** Completar SOLO documentación.
**Phase 1:** Corregir P0 (semántica, float, as_of).
**Phase 2:** Corregir P1 (ORM, config, catálogo, tests).
**Phase 3:** Deuda técnica y refactorización.

