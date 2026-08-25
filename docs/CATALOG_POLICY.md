# Política de Catálogo contable

## Estructura en dos capas

A partir de Phase 1C.3B, Aqorath soporta:

### A. CATÁLOGO CANÓNICO (gobernado)

**Ubicación:** `aqorath/data/catalogo_base.json`

**Características:**
- Controlado por el desarrollador / Aqorath
- Clasificación estructural del Plan de Cuentas
- Naturaleza contable (Deudora/Acreedora)
- Tipos y subtipos (Activo, Pasivo, Patrimonio, Ingreso, Gasto, etc.)
- Determinista y versionado
- NO modificable por operaciones normales de runtime

**Cómo se actualiza:**
1. Desarrollador modifica `assets/catalogo.xlsx` (u origen)
2. Ejecuta: `python scripts/convert_catalog_xlsx_to_json.py --input assets/catalogo.xlsx --out aqorath/data/catalogo_base.json`
3. Revisa y commitea cambios
4. Publica nueva release
5. En destino: ejecutar `python scripts/init_catalog_db.py`

### B. PLAN PARTICULAR DE LA ENTIDAD (extensible)

**Modelo:** Account con origin="entity"

**Características:**
- Extensiones legítimas del catálogo canónico
- Creadas por usuarios a través de API pública
- Sólo bajo una cuenta canónica padre
- Código generado automáticamente: `parent_code.NNN` (ej: 1101.001, 1101.002)
- Naturaleza heredada del padre (no editable)
- parent_id explícito (vínculo al padre)
- Una sola profundidad actualmente (canonical → entity, no multinivel)
- NO modifica `catalogo_base.json`

**Ejemplo:**

```
1101 Bancos (canonical, Deudora)
  ├─ 1101.001 BBVA (entity, Deudora)
  ├─ 1101.002 Banamex (entity, Deudora)
  └─ 1101.003 Nu (entity, Deudora)

4101 Ventas al contado (canonical, Acreedora)
  ├─ 4101.001 Empresa A (entity, Acreedora)
  └─ 4101.002 Empresa B (entity, Acreedora)
```

**Cómo se crea:**

```python
from aqorath.catalog import create_entity_account
from aqorath.core import get_session

with get_session() as session:
    bbva = create_entity_account(
        session=session,
        parent_code="1101",
        name="BBVA"
    )
```

El usuario proporciona:
- **parent_code:** código de cuenta canónica (ej: "1101")
- **name:** nombre particular de la entidad (ej: "BBVA")

Aqorath determina:
- **code:** generado como "1101.001" (siguiente disponible)
- **nature:** heredada de 1101 (Deudora)
- **origin:** "entity"
- **parent_id:** id del padre canónico

**Restricciones:**
- Padre debe ser canónico (origin="canonical")
- Padre debe existir en catálogo oficial
- No se permite crear entidades bajo otras entidades (una sola profundidad)
- Naturaleza no es editable (heredada)
- Código no es editable (generado)
- parent_id no es editable (estructural)

## Razonamiento

**Catálogo canónico inmutable:** Asegura consistencia del Plan de Cuentas oficial y reduce errores por usuarios sin formación contable.

**Extensiones de entidad:** Permite flexibilidad operativa para discriminar hechos particulares (bancos, clientes, proyectos) sin modificar estructura oficial.

## Gobernanza en tiempo de ejecución

- La tabla `account` contiene: canónicas (origin="canonical") y entidades (origin="entity")
- Validación antes_inserción impide:
  - Cuentas canónicas no en JSON
  - Entidades sin padre válido
  - Entidades bajo otras entidades
  - Códigos malformados
- Validación antes_actualización protege:
  - code (no editable)
  - origin (no editable)
  - parent_id (no editable)
  - nature (para entidades: debe mantener del padre)
- Reporting: Entidades heredan clasificación del padre (ej: 1101.001 → Activo)