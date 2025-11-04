```markdown
# Política de Catálogo contable (inmutable)

Decisión de diseño
- El catálogo contable es controlado por el desarrollador y forma parte del código fuente:
  `aqorath/data/catalogo_base.json`.
- El usuario final NO puede modificar la estructura del catálogo desde la aplicación o por scripts incluidos en la distribución.

Cómo se actualiza
- Para cambiar nombres, tipos o agregar cuentas, el desarrollador:
  1. Modifica `assets/catalogo.xlsx` localmente (o la hoja fuente),
  2. Ejecuta `python scripts/convert_catalog_xlsx_to_json.py --input assets/catalogo.xlsx --out aqorath/data/catalogo_base.json`,
  3. Revisa `aqorath/data/catalogo_base.json`, commitea y publica una nueva release.
  4. En instalaciones destino, ejecutar `python scripts/init_catalog_db.py` (o dejar que el instalador lo haga).

Uso en tiempo de ejecución
- El sistema lee el catálogo embebido (JSON) para decidir el nombre mostrado por modo (OSC/Comercial).
- La tabla `account` contiene la fila única por código (un id por code). Las importaciones iniciales añaden los codes que falten.

Razonamiento
- Mantener catálogo inmutable asegura consistencia y reduce posibilidad de errores por parte de usuarios sin formación contable.

## Sincronización de Esquema

El sistema incluye una herramienta (`scripts/sync_schema.py`) que mantiene sincronizado el esquema de la base de datos SQLite con los modelos definidos en el código fuente.

### ¿Cuándo ejecutarla?

- Después de actualizar el código a una nueva versión
- Después de agregar nuevas columnas a los modelos (Account, JournalEntry, JournalLine, etc.)
- Si aparecen errores de tipo "no such column" en consultas SQLite

### Uso

```bash
# Vista previa (no hace cambios)
python scripts/sync_schema.py --dry-run

# Aplicar cambios reales
python scripts/sync_schema.py
```

La herramienta:
1. Compara las definiciones de los modelos SQLModel con el esquema actual de la BD
2. Detecta columnas faltantes
3. Añade columnas automáticamente cuando es seguro (columnas nullable o con defaults)
4. Reporta columnas que requieren migración manual

### Columnas que requieren atención manual

Si una columna tiene `NOT NULL` sin valor por defecto, la herramienta no puede añadirla automáticamente a una tabla existente con datos. En estos casos, el script reportará:

```
⚠️  Column 'nueva_columna' (type: TEXT, NOT NULL) - Cannot auto-add
    Manual migration required: This column has NOT NULL constraint without default.
```

Pasos para resolver:
1. Modificar el modelo para hacer la columna nullable o agregar un default
2. O ejecutar una migración SQL manual para poblar valores

## Modelo de Contabilidad (accounting_model)

La selección del modelo de contabilidad (OSC vs Comercial) es **irreversible** una vez que se han registrado transacciones en el sistema.

### Razones de la Irreversibilidad

1. **Estructura del catálogo**: OSC y Comercial usan diferentes estructuras de cuentas
2. **Reglas fiscales**: Los cálculos de impuestos difieren entre ambos modelos
3. **Reportes**: Los reportes financieros se generan según el modelo seleccionado
4. **Timbrado CFDI**: Los requisitos fiscales varían según el tipo de entidad

### Recomendaciones

- **Antes de registrar transacciones**: Verifique cuidadosamente qué modelo necesita
- **OSC**: Para asociaciones civiles, donatarias autorizadas, y organizaciones sin fines de lucro
- **Comercial**: Para personas físicas y morales con actividad empresarial

### ¿Qué hacer si necesita cambiar?

Si ya tiene transacciones registradas y necesita cambiar de modelo:

1. **Exportar datos**: Exporte todos sus registros a Excel/CSV
2. **Respaldar base de datos**: Haga una copia de seguridad completa
3. **Nueva instalación**: Cree una nueva base de datos con el modelo correcto
4. **Migración manual**: Importe los datos adaptándolos al nuevo catálogo

**Nota**: Este proceso puede requerir ajustes manuales en las cuentas contables y debe ser supervisado por un contador.

## Cierre de Ejercicio

El cierre del ejercicio es una operación **irreversible** que:

1. Transfiere el saldo de la cuenta 3103 (Resultado del ejercicio) a la cuenta 3104
2. Crea un respaldo automático de la base de datos
3. Genera los asientos contables correspondientes

### Antes de ejecutar el cierre

- Verifique que todas las transacciones del ejercicio estén registradas
- Revise el balance de la cuenta 3103
- Confirme que las cuentas 3103 y 3104 existan en su catálogo
- Tenga a la mano el respaldo manual por si acaso

### Ejecución

Desde la interfaz de usuario: **Configuración → Cierre del ejercicio**

O programáticamente:
```python
from aqorath.exercise import close_exercise

result = close_exercise()
if result["status"] == "success":
    print(f"Cierre completado. Respaldo en: {result['backup_path']}")
else:
    print(f"Error: {result['message']}")
```

### Después del cierre

- El respaldo se guarda en `<db_path>/backups/`
- Se crea un asiento con doc_ref="CIERRE_AUTO"
- La cuenta 3103 queda cerrada
- La cuenta 3104 refleja el resultado acumulado

**Importante**: No se puede deshacer. Si necesita corregir, debe hacerlo mediante asientos de ajuste en el nuevo ejercicio.
```