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

```