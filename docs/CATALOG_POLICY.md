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

Schema Synchronization
- El sistema incluye un helper de sincronización de esquema (`scripts/sync_schema.py`) que detecta columnas faltantes en la base de datos comparando con los modelos SQLModel.
- Para sincronizar el esquema: `python scripts/sync_schema.py` o `python scripts/sync_schema.py --dry-run` para ver los cambios sin aplicarlos.
- SQLite tiene limitaciones: solo soporta ALTER TABLE ADD COLUMN. No se pueden eliminar o modificar columnas existentes sin recrear la tabla.
- Si una migración requiere cambios complejos, puede ser necesario realizar pasos manuales (consultar la documentación del script).

Accounting Model Selection
- La selección del modelo contable (OSC vs Comercial) debe realizarse al inicio y es inmutable durante el ejercicio.
- Una vez seleccionado el modelo y cargado el catálogo, no debe cambiarse sin cerrar el ejercicio actual.
- Esta restricción asegura consistencia en los reportes fiscales y previene errores contables.
```