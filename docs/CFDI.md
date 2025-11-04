```markdown
# CFDI (facturación electrónica) — Guía de uso (sistema SistemaContable)

Este documento explica cómo usar la funcionalidad de generación de comprobantes (CFDI skeleton) y cómo preparar / entregar los archivos para timbrado.

Nota: el sistema soporta dos tipos de contabilidad en el mismo motor: "OSC" y "Comercial". Los requisitos técnicos para generar el XML son los mismos; si la contabilidad opera con reglas fiscales o catálogos distintos, los contadores podrán adaptar las claves y parámetros. En las secciones que siguen indico claramente los campos requeridos; si aplica, añade la información relevante para OSC/Comercial en los parámetros del libro.

Requisitos previos
- Archivo de datos: `datos/Sistema_Contable.xlsx` (el App crea uno de ejemplo si no existe).
- Parámetros fiscales (hoja `ParametrosFiscales`) deben contener, como mínimo:
  - Emisor_RFC
  - Emisor_Nombre
  - Emisor_Regimen (opcional; 601 por defecto)
  - Receptor_RFC (si se desea prefijar)
  - Receptor_Nombre
  - Receptor_UsoCFDI (p. ej. P01)
  - LugarExpedicion
  - IVA_general (tasa en %)
  - IVA_trasladado_cuenta (ej. 2080) — para inferir impuestos en el skeleton

Campos mínimos a llenar para generar un CFDI desde un asiento
- Emisor:
  - Emisor_RFC
  - Emisor_Nombre
  - Emisor_Regimen (recomendado)
- Receptor:
  - Receptor_RFC
  - Receptor_Nombre
  - Receptor_UsoCFDI (p. ej. P01, G03, etc.)
- Asiento: debe contener las líneas (conceptos) con descripción e importes; idealmente las cuentas que representan impuestos (ej. 2080) para que el sistema calcule IVA.

Generación de comprobantes (desde la app / CLI)
- Generar XML (skeleton), CSV y PDF de verificación:
  - CLI: `python main.py generate-cfdi --id <id_asiento> --emisor-rfc RFC --emisor-nombre NAME --receptor-rfc RFC --receptor-nombre NAME --out datos/cfdi`
  - Programa: `from modelos.cfdi import generate_cfdi_from_asiento; generate_cfdi_from_asiento(libro, id_asiento, 'datos/cfdi')`
- Resultado:
  - `asiento_<id>.xml` (skeleton sin timbrar)
  - `asiento_<id>.csv` (resumen)
  - `asiento_<id>.pdf` (resumen humano para revisión)

Qué hacer para timbrar (opciones)
1. Timbrado por contador / PAC (recomendado para AC que trabajan con contadores):
   - Entregar los archivos XML (skeleton) y PDF o CSV al contador o al PAC.
   - El contador/PAC firma y timbra (obtiene UUID / sello SAT) y devuelve el XML timbrado.
   - Importar el XML timbrado en el sistema (ver sección abajo "Importar timbrados").

2. Timbrado por el propio usuario (si tiene PAC/CSD):
   - El usuario debe tener CSD (archivo .cer/.key y contraseña) y credenciales PAC o servicio de timbrado.
   - Firmar y timbrar mediante el PAC (fuera del alcance de este software en esta versión).

Importar XML timbrado (flujo)
- Cuando el PAC/proveedor devuelva el XML timbrado, importar el archivo en el sistema:
  - CLI: `python main.py import-timbrado --id <id_asiento> --file path/to/timbrado.xml`
  - Esto:
    - Copia el XML timbrado a `datos/cfdi/timbrados/`
    - Extrae UUID y SelloSAT (TimbreFiscalDigital) y marca el asiento con metadatos `timbrado` (uuid, sello, xml_path, imported_at)
    - Opcional: el sistema puede guardar el UUID en la hoja `Asientos` en el XLSX (en futuras mejoras).

Notas específicas para OSC vs Comercial
- El proceso técnico es el mismo.
- Diferencias prácticas:
  - OSC suelen emitir comprobantes por donativos, ingresos por aportaciones, etc.; validar que el uso CFDI y clasificadores sean correctos.
  - Comercial suele requerir más campos (forma de pago, condiciones de pago, moneda distinta) según operaciones de venta.
- Recomendación: mantener los datos de Emisor y parámetros fiscales (hoja `ParametrosFiscales`) actualizados para la naturaleza de la entidad.

Buenas prácticas
- No almacenar claves privadas en texto plano en el archivo `ParametrosFiscales`.
- Mantener backups activados (`datos/backups`); el sistema guarda zips por defecto.
- Revisar el PDF resumen antes de enviar el XML al PAC/contador.
- Guardar los XML timbrados devueltos por el PAC en `datos/cfdi/timbrados` y adjuntarlos al asiento correspondiente.

## Validación de Campos Fiscales

El sistema incluye validadores automáticos para movimientos marcados con `has_cfdi` o `has_invoice`:

### Campos Requeridos
Cuando un movimiento está marcado como factura/CFDI, se requieren los siguientes campos:

- **emitter_rfc**: RFC del emisor (mínimo 12 caracteres)
- **receiver_rfc**: RFC del receptor (mínimo 12 caracteres)
- **serie**: Serie del comprobante (ej. "A", "B")
- **folio**: Folio del comprobante (número consecutivo)
- **subtotal**: Subtotal antes de impuestos (debe ser > 0)
- **total**: Total incluyendo impuestos (debe ser > 0)
- **tax_breakdown**: Desglose de impuestos aplicados

### Uso en la UI

La interfaz de usuario verifica automáticamente estos campos antes de permitir guardar un movimiento marcado como CFDI. Si falta algún campo o el formato es inválido, se mostrará un mensaje descriptivo al usuario.

### Uso Programático

```python
from modelos.registro import Registro

reg = Registro.create(
    fecha="2024-01-01",
    cuenta="4101",
    cantidad=1000.0,
    descripcion="Venta con factura"
)

# Marcar como CFDI y agregar campos fiscales
reg.extra.update({
    "has_cfdi": True,
    "emitter_rfc": "XAXX010101000",
    "receiver_rfc": "VECJ880128KM5",
    "serie": "A",
    "folio": "001234",
    "subtotal": 1000.0,
    "total": 1160.0,
    "tax_breakdown": {"IVA_16": 160.0}
})

# Validar
ok, msgs = reg.validate()
if not ok:
    for msg in msgs:
        print(f"Error: {msg}")
```

## Sincronización de Esquema

El sistema incluye una herramienta para sincronizar el esquema de la base de datos con los modelos definidos en el código:

```bash
# Vista previa de cambios (dry-run)
python scripts/sync_schema.py --dry-run

# Aplicar cambios
python scripts/sync_schema.py
```

Esta herramienta:
- Detecta columnas faltantes en las tablas existentes
- Añade columnas automáticamente cuando es posible
- Reporta columnas que requieren migración manual (ej. NOT NULL sin default)
- Crea logs de las operaciones realizadas

**Nota**: Ejecute esta herramienta después de actualizar los modelos de datos para mantener el esquema sincronizado.

Siguientes pasos (opcional, para implementaciones futuras)
- Integrar API de PAC para timbrado automático (requerirá credenciales del proveedor).
- Validar contra catálogos oficiales del SAT (ClaveProdServ, ClaveUnidad).
- Marcar asientos en el libro como "timbrado" con la información completa del CFDI (UUID, Fecha Timbrado).
# CFDI — Requisitos mínimos y pre-validación

Esta sección aclara los campos mínimos que el sistema comprobará antes de generar un CFDI skeleton
(pre-validación) y qué se espera que complete la AC o el contador antes de timbrar.

IMPORTANTE: El timbrado (firma del XML y obtención del UUID/SelloSAT/Certificado/NoCertificado)
siempre lo realiza un PAC o el Buzón Tributario. El sistema genera un "skeleton" XML que sirve
para revisión y para que el contador/PAC lo timbren.

1) Plantilla mínima (ParametrosFiscales)
Coloca estos valores en la hoja `ParametrosFiscales` del XLSX (o mediante la API ParametroFiscal):
- Emisor_RFC: RFC del emisor (ej. ACME010101ABC)
- Emisor_Nombre: Nombre o razón social
- Emisor_Regimen: 601 (general) u otro régimen aplicable
- Receptor_RFC: RFC receptor (XAXX010101000 para público en general)
- Receptor_Nombre: Nombre del receptor
- Receptor_UsoCFDI: P01, G01, G03, etc.
- Receptor_DomicilioFiscalReceptor: Código Postal del receptor (5 dígitos)
- Receptor_RegimenFiscal: (opcional)
- FormaPago: código SAT (ej. "03" = Transferencia)
- MetodoPago: "PUE" por defecto
- TipoDeComprobante: "I" (Ingreso), "E" (Egreso), "N" (Nomina) según corresponda
- Moneda: "MXN" (por defecto)
- LugarExpedicion: Código Postal del emisor (5 dígitos)
- IVA_general: 16 (tasa por defecto)
- IVA_trasladado_cuenta: cuenta del catálogo que representa IVA trasladado (ej. "2080")
- ObjetoImp_default: clave de objeto de impuesto (ej. "01")

2) Pre-validación (`is_cfdi_ready_for_timbrado`)
Antes de generar y enviar al PAC, el sistema realiza una pre-validación que comprueba:
- Emisor_RFC y Emisor_Nombre están presentes y RFC tiene formato aproximado.
- FormaPago y LugarExpedicion están definidos.
- Receptor_DomicilioFiscalReceptor (CP) y UsoCFDI están presentes.
- Cada concepto (línea) tiene importe y se puede derivar ClaveProdServ/ClaveUnidad;
  se recomienda completar NoIdentificacion y confirmar ObjetoImp para cada concepto.

3) Flujo recomendado
- Usuario completa ParametrosFiscales y registra movimientos/pólizas en la app.
- Ejecutar generate-cfdi con `--pre-validate`:
  - Si hay errores en pre-validación, el proceso devuelve la lista de errores y no genera el XML.
  - Si solo hay advertencias, el sistema genera el XML y advierte los puntos a revisar.
- Enviar XML generado al contador/PAC para timbrado (ellos añadirán Sello/Certificado/NoCertificado).
- Importar XML timbrado con `import-timbrado` para adjuntar UUID/Sello al asiento en el libro.

4) Notas OSC vs Comercial
- Técnica: los requisitos técnicos del XSD son los mismos para ambos tipos; sin embargo:
  - OSC pueden emitir comprobantes por donativos, recibos de aportaciones o servicios sin IVA.
  - Comercial emite facturas de venta con mayor frecuencia y debe prestar atención a FormaPago, Moneda y TipoDeComprobante.
- Recomendación: mantener los parámetros fiscales actualizados en `ParametrosFiscales` según el tipo de entidad.

5) Validación XSD local
- Descarga los XSD oficiales del SAT en `datos/xsds` (hay un script `scripts/fetch_xsds.py`).
- Usar la función `validate_xml_against_schema(xml, xsd, xsds_dir)` para una validación estricta
  (requiere `lxml` instalado). La validación XSD fallará hasta que el XML esté timbrado si faltan
  atributos obligatorios (Sello, Certificado, NoCertificado, Exportacion, etc.). Úsala como
  comprobación final o para detectar problemas de estructura/tipos.

6) Ejemplo CLI
- Generar con pre-validación:
  python main.py generate-cfdi --id 3 --pre-validate --out datos/cfdi
- Generar y validar XSD (si tienes XSD y lxml):
  python main.py generate-cfdi --id 3 --validate-xsd datos/xsds/sitio_internet/cfd/4/cfdv40.xsd --out datos/cfdi
- Importar timbrado:
  python main.py import-timbrado --id 3 --file datos/cfdi/asiento_3_timbrado.xml --out datos/cfdi/timbrados

```# CFDI — Guía rápida y ejemplos

Este documento describe cómo utilizar las utilidades para manejar XSDs, generar esqueletos CFDI y procesar timbrado en este repositorio.

## 1) Descargar XSDs

El script para descargar XSDs está en `scripts/fetch_xsds.py`. Para usarlo, crea un manifiesto con las URLs (una por línea), por ejemplo `datos/xsds_urls.txt`:

https://example.org/path/to/schema1.xsd
https://example.org/path/to/schema2.xsd local_name.xsd

Uso:
```
python scripts/fetch_xsds.py --manifest datos/xsds_urls.txt --verify --shafile datos/xsds/sha256.txt
```

- `--verify`: descargará temporalmente y comprobará si hay cambios; si no hay cambios no reemplaza el fichero.
- `--shafile`: ruta para escribir el manifiesto con SHA256 (formato: `<sha256>  <relative-path>`).

El CLI general `main.py` ofrece el atajo:
```
python main.py fetch-xsds --manifest datos/xsds_urls.txt --verify --shafile datos/xsds/sha256.txt
```

## 2) Generar esqueletos CFDI (ejemplos)
El comando `generate-cfdi` genera esqueletos para tipos comunes (RESICO, PM, AC):

```
python main.py generate-cfdi --kind RESICO
```

Genera archivos en `datos/cfdi_examples/` con ejemplos básicos que puedes usar como punto de partida.

## 3) Importar timbrado
Para importar resultados de timbrado (XML), usa:

```
python main.py import-timbrado datos/timbrado/resultado_timbrado.xml
```

Los archivos se copiarán a `datos/timbrado_imported/`.

## 4) Seguridad: tokens y revocación
- Nunca incluyas tokens en commits o issues públicos.
- Si generas un PAT o token para automatizar acciones, revócalo cuando ya no lo necesites y almacénalo únicamente en Secrets del repo.
- Instrucción rápida para revocar un PAT: GitHub > Settings > Developer settings > Personal access tokens.

## 5) Mantener XSDs actualizados
- Programar ejecuciones periódicas del script (por ejemplo, con GitHub Actions o cron) para mantener los XSDs actualizados.
- Mantener el archivo `datos/xsds/sha256.txt` en un lugar seguro o usarlo solo como referencia local.

## 6) Tests
- Se recomienda ejecutar `pytest` localmente. Si los tests fallan por falta de red o servicios externos, ejecútalos offline o mockea las dependencias tal como se documenta en los tests.
