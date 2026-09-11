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

La restauración sigue `DETECT → EXPLAIN → STOP`. `restore_database_backup()` de
`migrations.py` conserva una responsabilidad estrictamente SQLite; AQR-014 coordina
por encima de esa autoridad la base y las evidencias documentales sin crear un
segundo motor de restore.

Antes del punto de commit deben estar demostrados:

1. ZIP, `manifest.json`, nombres de miembros, formato y SHA-256 del snapshot;
2. integridad SQLite y compatibilidad de schema; un schema futuro se rechaza;
3. migración **en staging** mediante `migrate_database()` cuando el snapshot use un
   schema histórico soportado;
4. `foreign_key_check` y correspondencia exacta manifest ↔ `DocumentReference`;
5. existencia y SHA-256 de todas las evidencias locales incluidas;
6. rutas finales de restore ya persistidas en la base staging, sin cambiar identidad,
   hash, vínculo al asiento ni hechos económicos;
7. estado previo del target: backup preventivo mediante `create_database_backup()`
   si la instalación es sana, o copia byte-preservada si el archivo previo no puede
   demostrarse íntegro;
8. evidencias nuevas preparadas en el directorio único
   `.aqorath_documents/restored/<package_id>/...`.

Sólo entonces `restore_database_backup(staged_db, target_db)` ejecuta la sustitución
SQLite validada y atómica mediante archivo temporal + `os.replace`. Ese retorno es
el **commit point** compuesto de AQR-014. Tras él se vuelve a validar schema,
integridad relacional y documentos instalados.

Si una validación posterior al commit falla, AQR-014 compensa explícitamente:

- **target sano previo**: restaura el backup preventivo con la autoridad canónica,
  vuelve a validar la instalación recuperada y sólo entonces elimina el managed root
  perteneciente al restore fallido;
- **instalación limpia previa**: elimina la DB recién instalada y el managed root,
  volviendo al estado sin DB activa;
- **target previo corrupto/no demostrablemente íntegro**: reinstala de forma atómica
  los bytes preservados sin fingir que constituyen un backup SQLite válido y elimina
  el managed root sólo después de recuperar ese estado previo.

Si la compensación de DB también falla, los documentos nuevos **no se eliminan**:
la DB que quedó instalada puede seguir referenciándolos. Se conservan la evidencia,
los backups disponibles y el estado investigable, y se emite un
`RecoveryIntegrityError` compuesto con el fallo original, el fallo de rollback y las
ubicaciones de recuperación. No se oculta la segunda excepción.

El composition root dispone el pool SQLAlchemy antes de la conmutación y lo
reconstruye después contra la DB que haya sobrevivido, incluida una DB recuperada por
compensación.

Un paquete corrupto, una relación rota o un schema futuro no sustituyen una base
sana. Un fallo pre-commit deja intactos DB y documentos anteriores y elimina las
evidencias nuevas preparadas.

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

El launcher conserva `aqorath.web_surface:app` como superficie local canónica.
`recovery_web` se importa antes de servir para registrar sobre **esa misma app** las
rutas AQR-014 y decorar el acceso a `/recovery`; no existe una segunda aplicación
local autoritativa.

Desde `/recovery` el usuario puede:

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
