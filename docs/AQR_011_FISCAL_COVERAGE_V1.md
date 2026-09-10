# AQR-011 — Cobertura fiscal V1 declarada y versionada

**Estado de esta evidencia:** matriz normativa de implementación.  
**Versión de revisión:** `mx-fiscal-v1.2026-09-10`.  
**Fecha de consulta de fuentes:** 2026-09-10.  
**Ventana de cobertura automatizada inicial de Aqorath:** 2026-01-01 a 2026-09-10, inclusiva.

Esta matriz gobierna AQR-011. No certifica cumplimiento fiscal integral ni convierte un dato de CFDI en conclusión jurídica. La cobertura automatizada se restringe a los tratamientos enumerados por V1-14 y a los hechos que Aqorath puede acreditar. Una operación fuera de la ventana revisada, con hechos insuficientes o sin regla V1 aplicable se detiene explícitamente; no se interpreta como impuesto cero.

## 1. Fuentes oficiales revisadas

| Fuente | Disposición material | Uso limitado en AQR-011 |
|---|---|---|
| Cámara de Diputados, [Ley del Impuesto al Valor Agregado, texto vigente](https://www.diputados.gob.mx/LeyesBiblio/pdf/LIVA.pdf) | arts. 1, 1-A, 1-B, 2-A, 11 y 17 | actos gravados, tasa general, retenciones, flujo efectivo, tasa 0% y momento de causación de los verticales V1 |
| Cámara de Diputados, [historial oficial de reformas LIVA](https://www.diputados.gob.mx/LeyesBiblio/ref/liva.htm) | reformas publicadas en DOF | provenance de reforma y control de que el texto consultado es vigente |
| DOF 07-12-2009, decreto fiscal que reforma LIVA | art. séptimo, art. 1 LIVA | tasa general de 16%; vigencia desde 2010-01-01 |
| Cámara de Diputados, [Reglamento de la LIVA, texto vigente](https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LIVA_250914.pdf) | art. 3, frs. I y II | dos terceras partes del IVA trasladado en servicios personales independientes y 4% de contraprestación pagada en autotransporte terrestre de bienes |
| DOF 04-12-2006, [Reglamento de la LIVA](https://dof.gob.mx/nota_detalle.php?codigo=4939297&fecha=04/12/2006) | art. 3 | publicación de las mecánicas anteriores; Reglamento vigente al día siguiente de publicación conforme a su transitorio primero |
| Cámara de Diputados, [Ley del Impuesto sobre la Renta, texto vigente](https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf) | arts. 100, 106 y 113-E/113-J | definición V1 de servicio profesional, retención 10% PF→PM y retención 1.25% PF RESICO→PM |
| Cámara de Diputados, [historial oficial de reformas LISR](https://www.diputados.gob.mx/LeyesBiblio/ref/lisr.htm) | publicación original 11-12-2013 y reforma 12-11-2021 | provenance y temporalidad de reglas ISR |
| DOF 11-12-2013, [expedición de la LISR](https://www.dof.gob.mx/nota_detalle.php?codigo=5325373&fecha=11/12/2013) | art. 106 | retención 10% por servicios profesionales PF→PM; vigencia de la nueva LISR desde 2014-01-01 |
| DOF 12-11-2021, [reforma fiscal RESICO](https://dof.gob.mx/nota_detalle_popup.php?codigo=5635286) | art. 113-J LISR | retención 1.25% PF RESICO→PM, sin considerar IVA; vigencia desde 2022-01-01 |

Las fechas normativas históricas anteriores son provenance de la norma; **no amplían por sí mismas la ventana de cobertura automatizada de Aqorath**. AQR-011 sólo promete cálculo automático dentro de la ventana revisada indicada arriba. Esto impide reinterpretar silenciosamente operaciones históricas o futuras con una revisión normativa de 2026.

## 2. Invariantes de cobertura

1. `operation_date → versión de cobertura → regla jurídica → cálculo` es determinista.
2. `CfdiTaxEvidence` es evidencia documental declarada; nunca selecciona una regla por sí misma.
3. La vista común aporta hechos materiales. No recibe `rule_key`, artículo, tasa, cuenta ni Debe/Haber.
4. Tasa 0% es un tratamiento positivo acreditado; no es fallback y no equivale a exención.
5. Las retenciones de honorarios ISR e IVA son efectos separados.
6. La retención de autotransporte es `4% × contraprestación efectivamente pagada`, no `4% × IVA trasladado`.
7. La retención IVA de honorarios se representa exactamente como `2/3 × IVA trasladado y efectivamente pagado`; `0.666666` no es dato legal autoritativo.
8. RESICO V1 sólo cubre la retención del art. 113-J; no calcula ISR mensual/anual del régimen.
9. Ante contexto insuficiente o contradicción documental: **DETECT → EXPLAIN → STOP**, sin posting fiscal parcial.
10. `iva.exempt.sale.land` permanece fuera de flujo V1 aunque el manifiesto histórico se conserve para regresión.

## 3. Matriz normativa por tratamiento

### 3.1 `iva.general_rate`

| Campo | Cobertura V1 |
|---|---|
| Supuesto normativo | PF o PM realiza en territorio nacional un acto/actividad del art. 1 LIVA que no esté sujeto a tasa 0%, exento o fuera de objeto. |
| Sujetos relevantes | contribuyente que realiza el acto y adquirente/receptor. |
| Acto/actividad V1 | venta de servicio ordinario o prestación independiente ordinaria identificada expresamente como gravada general dentro de un flujo V1. |
| Momento | para enajenación y servicios V1, cuando la contraprestación se cobra efectivamente (arts. 11 y 17; art. 1-B para cobro efectivo). |
| Base | valor de la contraprestación antes del IVA para el cálculo V1. |
| Tasa/mecánica | `base × 0.16`. |
| Retención | ninguna por esta regla aislada; una retención requiere regla separada aplicable. |
| Efecto | IVA trasladado separado del ingreso/base y del recurso/cuenta por cobrar. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10; fuera de esa ventana: no soportado por AQR-011. |
| Fuente | LIVA arts. 1, 1-B, 11 y 17; reforma de tasa general DOF 07-12-2009. |
| Hechos necesarios | fecha, tipo de acto, territorio MX, base, condición de cobro/pago y ausencia de una subcategoría V1 distinta. |
| Ya conocido | `EconomicFact`, fecha de operación, `Entity`, tercero/CFDI cuando exista. |
| Falta pedir | naturaleza fiscal reconocible del acto y, cuando el flujo no lo acredite, si la contraprestación fue efectivamente cobrada/pagada. |
| Negativos | documento con IVA pero acto no soportado; operación no cobrada cuando el efecto exige flujo; tasa 0% acreditada; contexto territorial no MX. |
| Fuera de soporte | acreditamiento general, declaraciones, ajustes mensuales, operaciones no enumeradas V1. |

### 3.2 `iva.zero_rate`

AQR-011 **no incorpora el catálogo entero del art. 2-A**. La única subcategoría V1 positiva inicialmente identificable sin pedir una conclusión jurídica es:

`own_edited_books_periodicals_magazines_sale` = enajenación de libros, periódicos o revistas editados por el propio contribuyente, art. 2-A fr. I inc. i LIVA.

| Campo | Cobertura V1 |
|---|---|
| Supuesto normativo | enajenación de libros, periódicos o revistas que edite el propio contribuyente. |
| Sujetos | contribuyente editor que enajena; adquirente. |
| Acto V1 | venta de publicación propia inequívocamente clasificada por hechos de producto/editor. |
| Momento/base | contraprestación de la enajenación; flujo conforme a LIVA cuando corresponda. |
| Tasa | 0%. Produce los efectos legales de actos por los que se paga IVA conforme al propio art. 2-A; no se modela como exención. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10. |
| Fuente | LIVA art. 2-A fr. I inc. i, texto vigente; historial oficial de reformas LIVA. |
| Hechos necesarios | venta; publicación ∈ {libro, periódico, revista}; el contribuyente es quien la edita; territorio MX; fecha. |
| Ya conocido | hecho/fecha; identidad de la entidad. |
| Falta pedir | tipo de publicación y condición factual de edición propia si no existe metadata de producto. |
| Negativos | simple reventa de libro de tercero; servicio editorial; cualquier producto no incluido; falta de acreditación de edición propia. |
| Fuera de soporte | las demás fracciones/incisos del art. 2-A hasta que una tarea autorizada amplíe el contrato. |

**Distinción obligatoria:** `sin regla aplicable ≠ tasa 0`; `tasa 0 ≠ exento`.

### 3.3 `iva.freight_transport_retention_rate`

| Campo | Cobertura V1 |
|---|---|
| Supuesto | una persona moral recibe servicios de autotransporte terrestre de bienes prestados por PF o PM; LIVA art. 1-A fr. II c y RLIVA art. 3 fr. II. |
| Sujetos | receptor: PM; prestador: PF o PM. |
| Acto | servicio de autotransporte terrestre **de bienes**, no cualquier gasto denominado flete. |
| Momento | al pago efectivo de la contraprestación. |
| Base | valor de la contraprestación efectivamente pagada. |
| Mecánica | `base × 0.04`. |
| Efecto | IVA retenido, separado del IVA trasladado y del gasto/base. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10. |
| Fuente | LIVA art. 1-A fr. II c; RLIVA art. 3 fr. II; Reglamento DOF 04-12-2006. |
| Hechos necesarios | receptor PM; prestador PF/PM; servicio de autotransporte terrestre; objeto transportado = bienes; monto efectivamente pagado. |
| Ya conocido | personalidad de la entidad; tercero y documento cuando existan; importe/fecha. |
| Falta pedir | naturaleza precisa del servicio si el documento no la acredita; personalidad de contraparte si no está persistida. |
| Negativos | mensajería no acreditada como autotransporte; transporte de personas; simple concepto “flete”; receptor no PM; no pagado. |
| Fuera de soporte | otras retenciones de IVA no enumeradas. |

### 3.4 `isr.professional_services_retention_rate`

| Campo | Cobertura V1 |
|---|---|
| Supuesto | PF presta servicio profesional a PM; art. 106 LISR. Servicio profesional V1 conserva la definición del art. 100 fr. II: servicio personal independiente cuyos ingresos no estén en capítulo de salarios. |
| Sujetos | prestador PF; receptor/pagador PM. |
| Acto | servicio profesional personal independiente. |
| Momento/base | pago efectuado; monto del pago sin deducción. |
| Tasa | 10%. |
| Efecto | ISR retenido como efecto separado. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10. |
| Fuente | LISR arts. 100 fr. II y 106; publicación DOF 11-12-2013. |
| Hechos necesarios | servicio profesional; prestador PF; receptor PM; pago/base. |
| Ya conocido | entidad, tercero/documento, importe/fecha. |
| Falta pedir | naturaleza personal-profesional y personalidad del prestador si no están persistidas. |
| Negativos | prestador PM; servicio empresarial no profesional; receptor no PM; mera etiqueta “honorarios” sin hechos suficientes. |
| Fuera de soporte | cálculo integral de ISR del prestador. |

### 3.5 Retención de IVA de dos terceras partes en honorarios

| Campo | Cobertura V1 |
|---|---|
| Supuesto | PM recibe servicios personales independientes de PF y el IVA trasladado ha sido efectivamente pagado; LIVA art. 1-A fr. II a y RLIVA art. 3 fr. I a. |
| Sujetos | prestador PF; receptor PM. |
| Acto | servicio personal independiente. |
| Momento | pago efectivo. |
| Base normativa de la fórmula | IVA trasladado y efectivamente pagado, no la contraprestación. |
| Fórmula exacta | `retención = 2/3 × IVA trasladado_pagado`. Se persiste/explica como fracción 2/3, nunca como decimal periódico truncado. |
| Efecto | IVA retenido, separado de IVA trasladado e ISR retenido. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10. |
| Fuente | LIVA art. 1-A fr. II a y último párrafo; RLIVA art. 3 fr. I a. |
| Hechos necesarios | prestador PF; receptor PM; servicio personal independiente; IVA trasladado; pago efectivo. |
| Ya conocido | CFDI puede aportar IVA declarado y RFC, sólo como evidencia; hecho/fecha/importe. |
| Falta pedir | hechos de personalidad/naturaleza cuando no estén persistidos. |
| Negativos | prestador PM; IVA documental sin contexto; no pagado; servicio que no sea personal independiente. |
| Fuera de soporte | retenciones de comisiones/arrendamiento aunque el Reglamento también las contemple. |

**Redondeo V1:** la fracción se evalúa con aritmética Decimal/racional explícita y el resultado monetario se redondea mediante la autoridad `FiscalRoundingPolicy`; la fórmula legal permanece 2/3 y el redondeo no altera su representación normativa.

### 3.6 `isr.resico_retention_rate`

| Campo | Cobertura V1 |
|---|---|
| Supuesto | PF que tributa en la sección RESICO del art. 113-E realiza actividad empresarial, profesional o uso/goce temporal a PM; ésta efectúa la retención del art. 113-J. |
| Sujetos | prestador/proveedor PF RESICO; receptor/pagador PM. |
| Acto | actividad empresarial, profesional o uso/goce temporal incluida por art. 113-J y por un flujo V1. |
| Momento/base | pago efectuado, sin considerar IVA. |
| Tasa | 1.25%. |
| Efecto | ISR retenido separado; no equivale al ISR mensual/anual de RESICO. |
| Temporalidad Aqorath | 2026-01-01..2026-09-10. |
| Fuente | LISR arts. 113-E y 113-J; reforma DOF 12-11-2021. |
| Hechos necesarios | prestador PF; pertenencia a RESICO acreditada como hecho declarado/persistido; receptor PM; acto permitido; base sin IVA; pago. |
| Ya conocido | documento puede declarar régimen, pero no concluye por sí mismo aplicabilidad; entidad, tercero, importe/fecha. |
| Falta pedir | pertenencia al supuesto RESICO si no existe una autoridad persistida fiable. |
| Negativos | régimen inferido por RFC/nombre/tasa CFDI; prestador PM; receptor no PM; acto no incluido; falta de acreditación del régimen. |
| Fuera de soporte | tarifa RESICO, límites de ingresos, obligaciones integrales y declaración mensual/anual. |

## 4. Composición de tratamientos V1

Una operación puede requerir más de un efecto fiscal sin crear otra operación económica. En particular, un servicio profesional PF→PM pagado puede requerir, según hechos acreditados:

- IVA trasladado conforme a la regla positiva que corresponda;
- ISR retenido 10% **o**, si el prestador está acreditado en el supuesto RESICO aplicable, la retención 1.25% correspondiente; no ambas por inferencia automática;
- retención IVA de 2/3 cuando se satisfaga su supuesto.

Cada efecto conserva su propia fuente, versión, base/fórmula y explicación. La composición se confirma y postea por la autoridad fiscalizada existente en una sola póliza.

## 5. CFDI: evidencia frente a conclusión

Datos reutilizables: RFC, fecha, total/subtotal, impuestos declarados, régimen declarado, UsoCFDI y demás campos soportados por AQR-010. La presencia de un traslado de IVA **no autoriza** seleccionar `iva.general_rate`. La evidencia se contrasta después de resolver una regla por hechos.

Casos de prueba obligatorios:

- CFDI con IVA + contexto no soportado → rechazo, cero escritura fiscal;
- regla soportada + impuesto CFDI divergente → DETECT → EXPLAIN → STOP;
- regla soportada + evidencia coincidente → una sola composición/póliza.

## 6. Fuera de cobertura V1

Permanecen fuera: `iva.exempt.sale.land` como flujo; determinación integral mensual/anual ISR/IVA; declaraciones; acreditamiento automático general; deducibilidad; IEPS; comercio exterior; estímulos no contratados; regímenes completos; obligaciones particulares de donatarias; reglas no enumeradas en V1-14.

Mensaje canónico de rechazo de producto:

> Aqorath no tiene una regla fiscal V1 declarada para este caso.

## 7. Correspondencia exigida con runtime

La implementación AQR-011 debe derivar de esta matriz y reutilizar las autoridades existentes:

`hechos → cobertura/aplicabilidad V1 → FiscalRuleSet/registry por fecha → cálculo/fórmula → redondeo → efectos fiscales → composición → explicación → consentimiento → posting fiscalizado → auditoría`

La matriz no autoriza tasas implícitas, fallbacks, selección desde XML, ni una segunda persistencia fiscal. Cualquier divergencia futura entre esta evidencia versionada y el runtime es una regresión.