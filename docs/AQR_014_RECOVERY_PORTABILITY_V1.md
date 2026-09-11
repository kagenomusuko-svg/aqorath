# AQR-014 — Backup, restore, integridad y portabilidad V1

## 1. Autoridad

SQLite continúa siendo la única fuente primaria de verdad de Aqorath. AQR-014 no
introduce JSON, ZIP, CSV ni ningún archivo auxiliar como persistencia runtime.

Los artefactos de AQR-014 tienen dos usos estrictamente acotados:

- **backup V1**: snapshot de recuperación Aqorath → Aqorath;
- **portable export V1**: fotografía relacional autocontenida para lectura e
  intercambio fuera de Aqorath.

Ninguno se consulta durante la operación contable ordinaria ni puede sustituir las
autoridades de ledger, migración, fiscalidad, inventario o documentos.

## 2. Integridad de instalación

La superficie `/recovery` expone una verificación explícita que informa:

- resultado de `PRAGMA integrity_check`;
- versión `PRAGMA user_version` y compatibilidad con `CURRENT_SCHEMA_VERSION`;
- `PRAGMA foreign_key_check`;
- cada `DocumentReference.file_path` local, existencia del archivo y SHA-256;
- correspondencia con `DocumentReference.file_hash` cuando existe hash persistido.

Una instalación sólo se presenta como `healthy` cuando el schema es el vigente,
SQLite es íntegro, no hay relaciones rotas y toda evidencia local referenciada puede
ser demostrada. Un fallo se reporta; no existe fallback silencioso.

## 3. Backup V1

El backup se construye desde `create_database_backup()` de `migrations.py`, por lo
que el snapshot SQLite usa la autoridad ya existente de backup consistente. El ZIP
incluye:

- `database/aqorath.db`: snapshot SQLite consistente;
- `documents/<document_reference_id>/...`: archivos locales referenciados;
- `manifest.json`: versión de formato, versión de schema, SHA-256 del snapshot y
  correspondencia exacta entre `DocumentReference` y cada evidencia empaquetada.

Si una referencia local apunta a un archivo inexistente o su hash contradice el
`file_hash` persistido, la creación del backup se detiene. Un backup parcial no se
presenta como válido.

Los CFDI importados cuyo XML canónico vive en `CfdiSourceRecord.xml_bytes` ya forman
parte del snapshot SQLite. No se inventa una segunda copia externa para ellos.

## 4. Restore V1

La restauración sigue `DETECT → EXPLAIN → STOP` y no reemplaza la base activa hasta
que el candidato está completamente validado.

Secuencia:

1. validar ZIP, `manifest.json`, nombres de miembros y SHA-256 del snapshot;
2. validar integridad SQLite y rechazar schema futuro;
3. si el snapshot usa un schema histórico soportado, migrarlo **en staging** con
   `migrate_database()`; no existe un migrador alternativo;
4. comprobar `foreign_key_check` y correspondencia exacta del manifiesto con las
   `DocumentReference` persistidas;
5. extraer y verificar las evidencias locales a un directorio administrado nuevo
   `.aqorath_documents/restored/<package_id>/...`;
6. actualizar, dentro de la base staging, únicamente la ubicación física
   `DocumentReference.file_path` para esos archivos. Identidad, hash, vínculo al
   asiento y hechos económicos no se reinterpretan;
7. si existe una base sana, crear antes un backup preventivo mediante la autoridad
   de `migrations.py`; si la base instalada está corrupta, preservar sus bytes como
   evidencia antes de recuperar;
8. sustituir la base mediante `restore_database_backup()`, que usa base temporal y
   `os.replace`;
9. reconstruir el pool SQLAlchemy para que nuevas sesiones abran el archivo
   restaurado y no un descriptor del inode anterior.

Los documentos restaurados se escriben en un directorio nuevo antes de la
conmutación de la base. Por eso el estado anterior no pierde ni sobrescribe sus
archivos documentales. La sustitución SQLite es el punto de conmutación autoritativo.

Un paquete corrupto, una relación rota o un schema futuro no sustituyen una base
sana.

## 5. Portable export V1

La exportación portable es distinta de los reportes JSON/XLSX de AQR-013. Parte de
un snapshot SQLite consistente y recorre **todas las tablas de usuario** del schema,
no una selección manual que pueda omitir relaciones nuevas.

El ZIP contiene:

- `schema.json`: DDL, columnas, primary keys y foreign keys por tabla;
- `data/<tabla>.json`: filas completas con celdas tipadas;
- `reconciliation.json`: conteos y totales débito/crédito derivados para verificar
  reconciliación, nunca como ledger paralelo;
- evidencias locales referenciadas y su manifiesto SHA-256;
- `manifest.json`: versión de schema, tablas, conteos y reglas de codificación.

Codificación de celdas:

- `integer`: entero SQLite en texto base 10;
- `real`: representación round-trip del `REAL` SQLite;
- `text`: UTF-8 exacto; los importes monetarios que Aqorath persiste como `TEXT`
  permanecen texto decimal exacto;
- `blob-base64`: BLOB en Base64 RFC 4648;
- `null`: `null`.

Así pueden conservarse IDs estables, monedas, valores decimales, XML CFDI binario y
relaciones sin depender de SQLModel ni de una instalación Aqorath para leer el
artefacto. AQR-014 no habilita importar esos JSON como ruta de persistencia: para
recuperar una instalación Aqorath se usa el backup SQLite gobernado.

## 6. Superficie de usuario

El launcher local carga `aqorath.recovery_web:app`. La aplicación principal expone
un acceso a `/recovery`, desde donde el usuario puede:

- verificar integridad;
- descargar backup completo;
- seleccionar y restaurar un backup con confirmación destructiva explícita;
- descargar exportación relacional portable.

Endpoints locales:

- `GET /api/system/integrity`;
- `POST /api/system/backup`;
- `POST /api/system/restore`, que exige `X-Aqorath-Confirm-Restore: RESTORE`;
- `POST /api/system/portable-export`.

La protección loopback del `web_surface` existente aplica también a estas rutas.
