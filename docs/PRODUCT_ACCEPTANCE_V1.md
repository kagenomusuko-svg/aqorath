# AQORATH — MATRIZ ÚNICA DE ACEPTACIÓN DEL PRODUCTO V1

**Tarea:** AQR-001. **Corte:** 2026-09-09. **Base inspeccionada:** `dce5f4143e9a3a26d0cfff27ba3a22ce2ae9358a` de `main`.

Este documento concreta el contrato de producto solicitado por [PRODUCT_BACKLOG_V1.md](PRODUCT_BACKLOG_V1.md), subordinado a la [Constitución](AQORATH_CONSTITUTION_V1.md) y a [INSTRUCCIONES.md](../INSTRUCCIONES.md). No sustituye el backlog ni crea una secuencia de fases. Los identificadores `V1-xx` son casos de aceptación, no tareas nuevas.

Estado de entrega de AQR-001: **incorporada y aceptada en main mediante PR #31**, merge `bff58de7cad11de6c2ab37c0d3e0b7b6c20ae003`, con autorización expresa del usuario. Esta matriz define resultados futuros: no certifica que hoy estén disponibles.

## 1. Frontera de producto

V1 incluye los flujos marcados **Sí** en la tabla de operaciones, únicamente dentro de sus límites. Una operación no enumerada o una variante expresamente excluida está **fuera de V1**; una operación incluida pero pendiente no debe anunciarse como soportada. Incorporar una variante exige actualizar este contrato y su evidencia, no inferir soporte por la existencia de una plantilla.

Una instalación local, un propietario, una entidad activa, importes en MXN. No se presupone conexión a Internet para capturar, consultar, explicar, respaldar o exportar la contabilidad. Identidad jurídica, finalidad económica, perfil fiscal por fecha y capacidades son componentes; no existe selector binario Comercial/OSC.

| Nicho | Operaciones V1 aplicables | Límite de la promesa |
|---|---|---|
| Autoempleo y microactividades de servicios | V1-01 a V1-06, V1-08 a V1-14, V1-16 a V1-20 según hechos reales | Contabilidad de las operaciones enumeradas; no declaraciones fiscales integrales |
| Pequeño negocio | Los anteriores; venta y compra de mercancías ligadas a V1-21 | Inventario simple incluido; no manufactura ni costos industriales |
| A.C. y OSC | Operaciones comunes que efectivamente realicen, más V1-07, V1-15 y V1-22 | Fondos, fuentes, restricciones y donativos son parte de V1, no un motor separado |
| Donataria autorizada | Los mismos flujos OSC, conservando autorización/perfil y evidencia pertinente | Registrar autorización no implica timbrar recibos ni certificar deducibilidad o cumplimiento integral |

Las operaciones propias de un nicho no se fuerzan sobre otro: una OSC puede tener ingresos propios y una persona autoempleada puede adquirir activos. La aplicabilidad proviene de hechos y perfiles, nunca de una segunda contabilidad.

### Decisiones de alcance documentales

- **Inventario incluido:** se conserva AQR-012 como `TODO`, en coherencia con el pequeño negocio del nicho. V1-21 fija inventario perpetuo de mercancía comprada para reventa y promedio ponderado móvil como único método V1; es un contrato futuro, no una afirmación de implementación. No se necesita elegir entre métodos en la interfaz ordinaria.
- **Fiscalidad acotada:** V1-14 enumera los únicos tratamientos objetivo. Las obligaciones integrales de un régimen no se deducen de una tasa. Fuentes, vigencias y aplicabilidad deben revisarse en AQR-011 antes de declarar soporte; AQR-001 no hace una actualización normativa ni recomienda una liquidación fiscal real.
- **No ampliar por arqueología:** nómina, timbrado, multimoneda y notas de crédito comerciales no entran en V1 por tener scripts o plantillas históricas. La corrección contable por reversión sí entra mediante AQR-003.

## 2. Estados y aceptación transversal

| Estado | Significado |
|---|---|
| Soportada de extremo a extremo | Flujo disponible en producto local, evidencia técnica verde, revisión profesional y prueba humana reproducible aprobadas |
| Fundamento implementado pero flujo incompleto | Hay código/pruebas reutilizables relevantes; falta integración o aceptación de producto |
| Pendiente | No se localizó la capacidad específica completa; el ledger genérico no basta para declararla implementada |
| Fuera de V1 | No comprometida para esta versión; se informa el límite sin inventar un tratamiento |

**Ningún flujo se clasifica hoy como soportado de extremo a extremo:** la auditoría V2 documenta ausencia de superficie productiva y no hay evidencia de aceptación humana de estos recorridos. Esto no rebaja la validez de los fundamentos técnicos ya probados.

Todos los casos incluidos heredan estas condiciones:

1. **Técnica:** Decimal exacto, partida doble, cuentas válidas, SQLite único; rechazo sin escritura parcial ante error; fechas dentro de períodos abiertos; correcciones trazables sin borrar historia. AQR-002/003/004 componen estos contratos sobre las autoridades existentes.
2. **Profesional:** revisar hecho, póliza, saldos, documentos y explicación contra el resultado de cada ficha. Donde aplique fiscalidad, identificar contexto, regla, versión, vigencia, base, redondeo y efecto. Conservar dictamen del revisor y discrepancias; no sustituirlo por contar tests.
3. **Humana:** instalación de prueba limpia y local, datos ficticios, usuario no contador. Ejecutar los pasos de la ficha desde vista común sin códigos ni Debe/Haber; solicitar explicación; confirmar o cancelar; reabrir la aplicación y contrastar en vista profesional. El observador no traduce conceptos ni opera por el participante. Registrar éxito o bloqueo, pasos y evidencia. Hoy todas estas pruebas están pendientes.
4. **Una verdad:** cifras iguales en ambas vistas, reportes y exportaciones; explicación derivada de la misma decisión; reutilización de tercero/documento/importe ya conocido. No doble captura ni SQL manual para completar el recorrido.
5. **Evidencia reproducible:** por caso conservar commit, versión/esquema, fixture, comando y resultado técnico, documento/póliza de salida, fecha, revisor profesional y registro humano. Una prueba parcial acredita sólo su contrato, no toda la ficha.

Los importes de las fichas son fixtures contables sin efecto fiscal salvo V1-14. No implican exención: en uso real, el caso requiere determinar su tratamiento por V1-14 o rechazar explícitamente lo no soportado.

## 3. Matriz de operaciones

| ID | Operación | En V1 | Estado actual | Tareas que completan el flujo, además de AQR-004/005/015 |
|---|---|---|---|---|
| V1-01 | Venta/cobro al contado | Sí | Fundamento implementado pero flujo incompleto | AQR-010/011 cuando hay CFDI/impuestos |
| V1-02 | Venta a crédito y cobranza parcial/total | Sí | Fundamento implementado pero flujo incompleto | AQR-006 |
| V1-03 | Compra/gasto al contado | Sí | Fundamento implementado pero flujo incompleto | AQR-010/011; AQR-012 para mercancía |
| V1-04 | Compra a crédito y pago parcial/total | Sí | Fundamento implementado pero flujo incompleto | AQR-006; AQR-012 para mercancía |
| V1-05 | Transferencia entre cuentas propias | Sí | Pendiente | AQR-007 |
| V1-06 | Bancos y conciliación | Sí | Pendiente | AQR-007 |
| V1-07 | Donativo monetario | Sí | Fundamento implementado pero flujo incompleto | AQR-008/009/013 |
| V1-08 | Adquisición de activo fijo | Sí | Fundamento implementado pero flujo incompleto | AQR-006 si es a crédito |
| V1-09 | Depreciación y estado en libros | Sí | Fundamento implementado pero flujo incompleto | AQR-002/013 |
| V1-10 | Apertura/bloqueo de períodos y cierre anual | Sí | Fundamento implementado pero flujo incompleto | AQR-002 |
| V1-11 | Póliza, diario, mayor, auxiliares y balanza | Sí | Fundamento implementado pero flujo incompleto | AQR-002/006/013 |
| V1-12 | Estados financieros y paquetes | Sí | Fundamento implementado pero flujo incompleto | AQR-013 |
| V1-13 | CFDI como documento fuente | Sí | Fundamento implementado pero flujo incompleto | AQR-010 |
| V1-14 | Tratamiento fiscal explícitamente delimitado | Sí | Fundamento implementado pero flujo incompleto | AQR-010/011/013 |
| V1-15 | Programa, dimensión, fondo y fuente OSC | Sí | Fundamento implementado pero flujo incompleto | AQR-008/013 |
| V1-16 | Backup, restore e integridad | Sí | Fundamento implementado pero flujo incompleto | AQR-014 |
| V1-17 | Exportación y migración de salida | Sí | Fundamento implementado pero flujo incompleto | AQR-013/014 |
| V1-18 | Corrección mediante reversión | Sí | Pendiente | AQR-002/003 |
| V1-19 | Alta de entidad/perfil y reutilización de terceros | Sí | Fundamento implementado pero flujo incompleto | AQR-011 para aplicabilidad fiscal |
| V1-20 | Instalar, actualizar y operar sin Internet | Sí | Fundamento implementado pero flujo incompleto | AQR-014/015 |
| V1-21 | Inventario simple y costo de venta | Sí | Pendiente | AQR-012 |
| V1-22 | Donativo en especie | Sí | Pendiente | AQR-008/009/013 |
| V1-X | Operaciones excluidas, enumeradas en sección 6 | No | Fuera de V1 | Sin implementación por inercia |

## 4. Fichas de aceptación

En cada ficha, **E** identifica pruebas existentes en `tests/` y su alcance; **F** identifica evidencia faltante. Los nombres históricos de los archivos sólo permiten localizar regresiones; no determinan continuidad.

### V1-01 — Venta/cobro al contado

- **Hecho:** «Vendí un servicio por 200 y lo cobré en efectivo»; fecha, descripción y comprobante. V1 incluye cobro inmediato por efectivo o banco.
- **Resultado profesional:** cargo a caja/banco y abono a ingreso por 200; una venta y un reconocimiento de ingreso. La selección del medio determina el recurso recibido.
- **Evidencia y explicación:** comprobante ligado a póliza; explicar qué se vendió, dónde ingresó el dinero y por qué aumentó el ingreso.
- **E:** `aqorath/economic_facts.py` admite `sale/cash`; `test_p2_application_confirmation_posting.py`, `test_p2_posting_execution.py` prueban confirmación/posting. **F:** medio banco en el recorrido común, documentos y prueba transversal completa.
- **Prueba humana:** capturar la frase/datos, revisar 200 recibidos, cancelar sin póliza; repetir y confirmar, localizar la venta al reabrir.
- **Límite:** servicios o mercancía V1-21; sin anticipos, devoluciones comerciales ni moneda extranjera.

### V1-02 — Venta a crédito y cobranza

- **Hecho:** «Vendí 200 a Ana, vence el día 30; cobré 80 y después 120 por banco».
- **Resultado profesional:** clientes +200/ingresos +200; banco +80/clientes −80; banco +120/clientes −120. Pendiente 120 tras primer cobro y cero al final; ingreso total 200, no 400.
- **Evidencia y explicación:** documento de venta, vencimiento, tercero y dos comprobantes aplicados a la misma partida; distinguir ingreso de cobro y mostrar antigüedad a fecha de corte.
- **E:** `test_p3_accounts_receivable_lifecycle_e2e.py` verifica venta y cobro **total** por 200; `test_p3_credit_sale_persistence_e2e.py`, `test_p3_receivable_collection_persistence_e2e.py`. **F:** partidas por tercero/documento, parcialidades, vencimiento, antigüedad y rechazo de sobreaplicación en AQR-006.
- **Prueba humana:** elegir la deuda de Ana, aplicar 80, consultar 120 pendientes y liquidarlos; contrastar auxiliar y balanza.
- **Límite:** sin intereses, factoring ni deterioro de cartera automático; un cobro no se aplica a una deuda inexistente ni superior al saldo.

### V1-03 — Compra/gasto al contado

- **Hecho:** «Pagué 150 de electricidad por banco»; proveedor y comprobante. V1 incluye gasto de servicio/consumo inmediato por caja/banco y compra de mercancía V1-21; activo durable se dirige a V1-08.
- **Resultado profesional:** cargo a gasto de servicios y abono a banco por 150. Una mercancía aumenta inventario, no se transforma automáticamente en gasto.
- **Evidencia y explicación:** recibo/CFDI y pago; explicar destino, medio de pago y distinción gasto/activo/inventario.
- **E:** `test_p3_utility_expense_persistence_e2e.py`, `aqorath/economic_facts.py` cubren servicios básicos por banco; `aqorath/templates.py` contiene compra genérica, sin acreditar una interfaz semántica completa. **F:** selección factual de destinos adicionales, pago en efectivo, documentos y conexión con inventario.
- **Prueba humana:** registrar recibo, verificar reducción de banco por 150 y gasto; importar documento conocido sin recapturar importe.
- **Límite:** no llamar «cualquier compra» al vertical de electricidad; sin gastos prepagados, importación aduanera o costos industriales.

### V1-04 — Compra a crédito y pagos

- **Hecho:** «Debo 1500 al proveedor por servicios; pagué 500 y después 1000 por banco»; vencimiento y documento.
- **Resultado profesional:** gasto +1500/proveedores +1500; proveedores −500/banco −500; proveedores −1000/banco −1000. Gasto reconocido una sola vez y saldo cero al liquidar.
- **Evidencia y explicación:** factura, tercero, vencimiento y aplicaciones; explicar gasto frente a pago. Si se compró mercancía, contrapartida inventario conforme V1-21.
- **E:** `test_p3_accounts_payable_lifecycle_e2e.py` prueba servicios por 1500 y liquidación **total**; `test_p3_supplier_payment_persistence_e2e.py`. **F:** aplicación parcial documental, antigüedad y rechazo de pago excesivo; compra de mercancía integrada.
- **Prueba humana:** consultar deuda, pagar 500, encontrar 1000 abiertos y liquidarlos sin volver a registrar el gasto.
- **Límite:** sin financiamiento con interés ni anticipos; reversión según V1-18, sin borrar partida.

### V1-05 — Cuentas propias

- **Hecho:** «Pasé 300 de caja a mi banco» o entre dos bancos propios.
- **Resultado profesional:** recurso destino +300/origen −300; total de disponibilidades y resultado sin cambio. Comisiones, si existen, son otro hecho documentado.
- **Evidencia y explicación:** comprobante y cuentas propias identificadas; explicar traslado sin ingreso ni gasto.
- **E:** `aqorath/economic_facts.py` no enumera transferencia; el posting genérico no acredita este caso. **F:** caso de uso, identidad bancaria, rechazo de origen=destino, exactitud y atomicidad; AQR-007 lo compone sobre posting existente.
- **Prueba humana:** seleccionar origen/destino por nombre, confirmar 300 y comparar ambas disponibilidades.
- **Límite:** sólo MXN y recursos de la misma entidad; sin conversión cambiaria.

### V1-06 — Conciliación bancaria

- **Hecho:** «Este es el estado de mi cuenta al cierre del mes; quiero compararlo con mis registros».
- **Resultado profesional:** saldo contable 1000, banco 900, depósito en tránsito 100: banco + tránsito = contabilidad. Matching no crea otra póliza ni modifica el ledger.
- **Evidencia y explicación:** archivo importado, período, movimiento externo, vínculo contable y pendientes; explicar diferencia y qué falta comprobar.
- **E:** auditoría V2 no localiza `BankAccount` ni conciliación. **F:** AQR-007: importación CSV con columnas fecha/referencia/importe decimal/saldo cuando exista, duplicados, matching único, pendientes y cierre reproducible. No se promete compatibilidad universal con archivos bancarios.
- **Prueba humana:** importar fixture, vincular movimiento conocido, identificar depósito en tránsito y obtener conciliación por 100.
- **Límite:** sin conexión bancaria automática; una diferencia no se «cuadra» con asiento inventado.

### V1-07 — Donativo monetario

- **Hecho:** «Recibimos 1000 de este donante, por banco, para el programa educativo»; indicar restricción y documento que la establece.
- **Resultado profesional:** banco +1000 y reconocimiento del recurso donativo conforme su naturaleza documentada; restricción se conserva y controla con V1-15, sin ledger duplicado. Fixture base: donativo no condicionado ni reembolsable, reconocido como ingreso por donativo.
- **Evidencia y explicación:** donante reutilizado, comprobante, acuerdo de destino, póliza y reporte; explicar por qué es donativo, dónde está el recurso y cómo puede aplicarse.
- **E:** `aqorath/donation.py`, `aqorath/donation_repository.py`, `test_p6_donation_foundation.py` prueban identidad, importe y donante opcional; **no generan posting ni enlazan fondos**. **F:** AQR-008/009/013: relación documental, posting y reportes reconciliados.
- **Prueba humana:** seleccionar donante/programa, adjuntar acuerdo y recibir 1000; recorrer hasta póliza y saldo disponible por destino.
- **Límite:** restricción de uso no se confunde con obligación de devolver; subvenciones condicionales/reembolsables fuera de este fixture y de V1. No prometer deducibilidad ni timbrado.

### V1-08 — Adquisición de activo fijo

- **Hecho:** «Compré una computadora por 12000, la pagué por banco y la puse en servicio»; fecha, identificación y comprobante.
- **Resultado profesional:** equipo +12000/banco −12000; a crédito, proveedores +12000; no gasto inmediato por el costo completo. Conservar base, residual y vida útil explícitos.
- **Evidencia y explicación:** factura, pago, ficha del activo y póliza; explicar capitalización y liquidación, sin inventar estimaciones de vida útil.
- **E:** `aqorath/fixed_asset_acquisition.py`, `test_p6_fixed_asset_acquisition_confirmation_posting.py`, `test_p6_fixed_asset_acquisition_persistence.py`: clasificación, confirmación e idempotencia. **F:** captura común, vínculos documentales y partida de proveedor cuando corresponda.
- **Prueba humana:** registrar equipo una vez, volver a consultar/reintentar y comprobar que existe una sola adquisición contable.
- **Límite:** clases existentes de mobiliario/equipo, cómputo, maquinaria/herramientas e inmuebles; sin arrendamiento financiero, revaluación o baja/venta de activos V1. Terreno no se deprecia; no inferir depreciación de una clase agrupada terreno/edificio.

### V1-09 — Depreciación

- **Hecho:** «Reconocer el uso de esta computadora durante el mes»; costo 12000, residual 0 y vida útil explícita de 12 meses en el fixture.
- **Resultado profesional:** gasto de depreciación +1000/depreciación acumulada +1000; valor en libros 11000 después del primer mes. Nunca depreciar más que la base ni contabilizar dos veces un período.
- **Evidencia y explicación:** activo, fecha de servicio, método, cálculo/asignación monetaria, período y póliza; explicar costo, residual, vida y saldo.
- **E:** `aqorath/fixed_asset_depreciation.py` usa línea recta mensual; `test_p6_fixed_asset_depreciation_allocation.py`, `test_p6_fixed_asset_depreciation_persistence.py`, `test_p6_fixed_asset_book_state.py`. **F:** períodos abiertos, UI, evidencia del fixture y revisión profesional integrada.
- **Prueba humana:** reconocer primer mes, consultar 11000; repetir solicitud sin duplicación y pedir explicación.
- **Límite:** sólo línea recta contable; sin equivalencia automática con deducción fiscal, deterioro o depreciación de terrenos.

### V1-10 — Períodos y cierre

- **Hecho:** «Abrir el período; cerrar este mes; cerrar el ejercicio terminado».
- **Resultado profesional:** sólo períodos abiertos admiten posting; cierre anual cancela cuentas de resultados y traspasa su saldo conforme catálogo, conserva balance e historia y respaldo previo. Fixture con ingreso 200/gasto 150: resultado 50.
- **Evidencia y explicación:** fechas, estado, póliza de cierre y backup; explicar resultado transferido y qué fechas quedan bloqueadas.
- **E:** `test_aqr002_accounting_periods.py` y `test_p6bp_persistence_hardening.py::test_close_exercise_delegates_accounting_write_to_canonical_staging` acreditan FiscalYear/AccountingPeriod, posting abierto/cerrado, cierre atómico repetible, consultas y fixture 50 (PR #33). **F:** interfaz y prueba humana AQR-005; correcciones AQR-003.
- **Prueba humana:** cerrar período, intentar operación dentro de él y recibir rechazo claro; consultar póliza y respaldo del cierre anual.
- **Límite:** no editar estados con SQL ni reabrir silenciosamente; reglas de corrección se coordinan con V1-18.

### V1-11 — Consultas profesionales

- **Hecho:** «Muéstrame mis movimientos, qué me deben y cómo llegamos a este saldo al día X».
- **Resultado profesional:** póliza balanceada; diario cronológico; mayor con saldo inicial, cargos, abonos y final; auxiliares por tercero reconciliados; balanza con cargos=abonos. Ningún movimiento posterior al corte entra en el saldo.
- **Evidencia y explicación:** referencias a pólizas/documentos originales y parámetros del reporte; explicar saldo a partir de movimientos.
- **E:** `aqorath/reporting_source.py`, `test_p1_trial_balance_authority.py`, `test_p0_trial_balance_as_of.py`, `test_p4_financial_reporting_sqlite_source.py`; acreditan fuente/balanza por fecha, no todas las pantallas ni auxiliares. **F:** navegación póliza-diario-mayor y submayores AQR-006; filtros y presentación AQR-013.
- **Prueba humana:** desde saldo de cliente abrir movimiento y documento, cambiar fecha de corte y comparar ambas vistas.
- **Límite:** sólo datos de la entidad local y dimensiones soportadas; no consolidación multiempresa.

### V1-12 — Estados y paquetes

- **Hecho:** «Genera mis estados a esta fecha y agrega un reporte al paquete que elegí».
- **Resultado profesional:** estado de resultados y balance general reconciliados con balanza; activo=pasivo+patrimonio considerando resultado; paquete es selección editable y no cambia cifras. Reportes OSC por programa/fondo/fuente se incorporan por V1-15.
- **Evidencia y explicación:** ReportDefinition, parámetros, fecha de corte, perfil, formato y totales; explicar composición y naturaleza de cada saldo.
- **E:** `test_p4_formal_financial_statements_e2e.py`, `test_p4_financial_statements_bundle.py`, `test_p6_custom_report_package_foundation.py`. **F:** selección/persistencia de presets de usuario, reportes especializados y aceptación humana/profesional.
- **Prueba humana:** generar a dos fechas, quitar/agregar un reporte del paquete y comparar CSV/XLSX/PDF con la vista profesional.
- **Límite:** estados enumerados y cédulas V1-14/15; no prometer un juego completo de todos los estados normativos o dictamen financiero.

### V1-13 — CFDI fuente

- **Hecho:** «Éste es el XML de mi compra/venta; úsalo para registrar lo ocurrido».
- **Resultado profesional:** importar no equivale a contabilizar; UUID, RFC, fechas, importes e impuestos se extraen una vez y se contrastan con la propuesta confirmada. Segundo ingreso del mismo UUID no duplica documento ni póliza.
- **Evidencia y explicación:** XML local preservado, metadatos, tercero, hecho y póliza vinculados; explicar qué viene del XML y qué resuelve Aqorath, y detenerse ante discrepancia material.
- **E:** `aqorath/cfdi_metadata.py`, `test_p6_cfdi_import_metadata.py` cubren metadatos/UUID único; no parser XML productivo. **F:** AQR-010: fixtures XML, validación estructural local, extracción exacta, deduplicación e integración.
- **Prueba humana:** importar XML CFDI 4.0 de ingreso de una operación incluida, revisar datos reutilizados y confirmar; repetir archivo y observar referencia existente.
- **Límite:** XML CFDI 4.0 de ingreso como fuente de venta/compra/donativo compatible; sin timbrado, consulta SAT obligatoria, cancelación fiscal ni complementos de pago/nómina/comercio exterior. Un archivo fuera de cobertura se rechaza como fuente automatizada; su archivo como evidencia no lo convierte en tratamiento soportado.

### V1-14 — Fiscalidad delimitada

- **Hecho:** describir operación, contraparte, fecha y documento; reutilizar perfiles. La vista común no elige rule_key, tasa ni cargo/abono. Una ambigüedad factual se pregunta; una regla no cubierta detiene el tratamiento.
- **Resultado profesional:** cálculo y asiento derivados de reglas versionadas, con base e impuesto separados, conciliables con documento. Fixture aritmético de base 100 con tasa de prueba 0.16: impuesto 16, total 116. Es evidencia de cálculo, no prueba de aplicabilidad legal.
- **Evidencia y explicación:** XML/documento, contexto, versión, fuente normativa, vigencia, base, redondeo, confirmación y auditoría recuperable. Explicar por qué aplica y cómo cambia importe/contrapartida.
- **E:** `aqorath/fiscal_rule_data_mx.py`, `test_p5_expanded_curated_fiscal_data_mx.py`, `test_p5_fiscalized_application_persistence_e2e.py`, `test_p5_fiscal_write_read_round_trip_e2e.py`. Cubren manifiestos/cálculo y caminos fiscalizados; no acreditan cumplimiento completo de ningún régimen.
- **F:** AQR-011 debe cerrar aplicabilidad factual, vigencias y fuentes revisadas de los tratamientos incluidos abajo; fixtures positivos/negativos por fecha/contexto, cédula base/impuesto/retención/efecto, y contraste CFDI AQR-010. Probar que un caso desconocido no escribe ni se trata como tasa cero.
- **Prueba humana:** importar documento compatible, responder sólo hechos faltantes, leer desglose y explicación; probar otro contexto fuera de cobertura y recibir límite explícito.
- **Límite:** tabla fiscal siguiente; sin presentación de declaraciones, determinación integral mensual/anual de ISR/IVA, acreditamiento automático ni certificación de deducibilidad. En OSC, perfil y registro documental no autorizan extrapolar reglas comerciales.

| Regla existente en el repositorio | Alcance objetivo V1 | Condición de aceptación adicional |
|---|---|---|
| `iva.general_rate` | Sí: operaciones ordinarias gravadas incluidas | Distinguir devengo/cobro/pago y efecto exigible según caso, con fecha y fuente revisadas |
| `iva.zero_rate` | Sí: operaciones incluidas que acrediten esa aplicabilidad | No equiparar tasa cero con exento; falta de regla no significa tasa cero |
| `iva.freight_transport_retention_rate` | Sí: gasto de autotransporte terrestre de bienes en contexto aplicable | AQR-011 completa el hecho de servicio y condición de contraparte; no habilita cualquier flete |
| `isr.professional_services_retention_rate` | Sí: honorarios en contexto aplicable | Verificar personalidades de ambas partes y composición de efectos |
| `isr.resico_retention_rate` | Sí: retención en contexto aplicable | No equivale a cálculo integral de ISR RESICO |
| `iva.exempt.sale.land` | Fuera de V1 como operación de venta de inmueble | Conservar manifiesto/pruebas existentes; no habilitar flujo de venta de activos por ello |
| Retención de IVA de dos terceras partes | Sí, complemento necesario de honorarios cuando aplique | AQR-011 debe representarla exactamente, no sembrar 0.666666 como tasa autoritativa; no figura en los manifiestos actuales |

Las tasas/fechas históricas del archivo son evidencia del código, no certificación de vigencia normativa en este documento. Otros regímenes completos, estímulos, IEPS, comercio exterior y obligaciones particulares de donatarias quedan fuera del cálculo fiscal V1. La contabilidad OSC enumerada permanece incluida.

### V1-15 — Recursos OSC

- **Hecho:** «Estos 1000 vienen de la fuente A para el programa educativo; apliqué 300 a un gasto permitido».
- **Resultado profesional:** recepción y gasto en ledger general; dimensiones/fondo/fuente permiten demostrar recibido 1000, aplicado 300 y disponible restringido 700, sin multiplicar asientos. Clasificaciones no cambian el total general.
- **Evidencia y explicación:** acuerdo de restricción, fuente, fondo, programa, plazo, comprobante y líneas; explicar origen, destino permitido y aplicación. Reporte incluye partidas sin asignar para no esconder diferencias.
- **E:** `aqorath/program.py`, `aqorath/analytical_dimension.py`, `test_p6_program_foundation.py`, `test_p6_analytical_dimension_foundation.py`. **F:** Fund/FundingSource, restricciones, aplicaciones y reporte AQR-008/013; probar aplicación incompatible/excesiva y conciliación exacta.
- **Prueba humana:** elegir programa/fuente conocidos, aplicar 300 y recorrer del reporte al comprobante; intentar destino no permitido y observar rechazo explicable.
- **Límite:** sin contabilidades paralelas; cuotas no reembolsables de miembros y recursos propios se identifican por su fuente/naturaleza en AQR-008, no se rebautizan como donativos. Subvenciones reembolsables quedan excluidas.

### V1-16 — Recuperación local

- **Hecho:** «Respalda mi contabilidad» y «Restaura este respaldo en una instalación de prueba».
- **Resultado profesional:** mismos saldos, entidades, documentos y relaciones soportadas; integridad válida. Archivo corrupto o esquema futuro no reemplaza base sana. Respaldar antes de operación destructiva.
- **Evidencia y explicación:** archivo, versión de esquema, fecha, resultado de integridad y manifiesto de documentos locales; explicar qué contiene y qué se reemplazará.
- **E:** `aqorath/migrations.py`, `test_p1_schema_migration_foundation.py`, `test_p1_migration_hardening.py`. **F:** recorrido de usuario y copia/verificación de archivos fuente externos referenciados, además de DB; restauración completa en instalación limpia AQR-014.
- **Prueba humana:** respaldar fixture, reemplazar DB de prueba, restaurar y abrir el mismo comprobante con idénticos saldos.
- **Límite:** no backup remoto obligatorio; respaldo sólo de SQLite no acredita preservación de documentos externos.

### V1-17 — Salida portable

- **Hecho:** «Quiero entregar mis datos a otro sistema o a mi contador».
- **Resultado profesional:** exportar catálogo, pólizas/líneas, saldos, entidad/perfiles, terceros, documentos y relaciones V1 con identificadores estables, moneda y decimales textuales; conciliar totales y permitir reconstrucción de relaciones sin acceso a Aqorath.
- **Evidencia y explicación:** CSV/JSON documentados, diccionario de campos/esquema, manifiesto de archivos fuente y parámetros; distinguir reporte resumido de exportación de datos completa.
- **E:** `aqorath/reporting_csv.py`, `test_p4_financial_reporting_csv.py`, `test_p4_financial_reporting_xlsx.py`, `test_p4_financial_statements_pdf.py` acreditan reportes. **F:** exportación relacional completa y lectura independiente de fixture AQR-014; no duplicar autoridad contable.
- **Prueba humana:** exportar, abrir índice y documento fuente, contrastar un saldo y referencias con vista profesional.
- **Límite:** no prometer importación automática en cualquier ERP ni tratar Excel como base primaria.

### V1-18 — Corrección

- **Hecho:** «Registré 150 por error; eran 120. Quiero corregirlo indicando el motivo».
- **Resultado profesional:** original intacto, reversión de 150 vinculada y asiento correcto de 120; neto 120, historia reconstruible y efectos documentales/partidas reconciliados.
- **Evidencia y explicación:** original, reversión, sustituto, motivo, fecha y AuditEvent; explicar neto e historial.
- **E:** `aqorath/audit_event.py`, `test_p6_audit_event_foundation.py` acreditan la base de trazabilidad; `aqorath/reversal.py` y `tests/test_aqr003_reversal.py` cubren inmutabilidad, reversión balanceada, vínculo único, motivo, doble reversión y rechazo transaccional por período cerrado. **F:** integración de evidencia AuditEvent y submayores completos en AQR-003.
- **Prueba humana:** localizar operación, corregir con motivo y ver tres asientos vinculados cuyo neto sea 120.
- **Límite:** corrección contable no cancela CFDI ni sustituye trámite fiscal; no editar/borrar posted.

### V1-19 — Inicio y datos reutilizables

- **Hecho:** «Ésta es mi entidad y estos son mis clientes/proveedores/donantes»; perfil con vigencia.
- **Resultado profesional:** una entidad activa y terceros reutilizados en operaciones; perfil histórico correcto por fecha, catálogo gobernado sin pedir códigos al usuario común.
- **Evidencia y explicación:** datos declarados y fuentes pertinentes del perfil, identidad de tercero en documentos; explicar aplicabilidad sin inferir autorización fiscal.
- **E:** `aqorath/entity.py`, `test_p6_entity_profile_foundation.py`, `test_p6_third_party_foundation.py`, `test_p1_catalog_extensibility.py`. **F:** onboarding, resolución de ambigüedades y bindings desde configuración guiada AQR-004/005, no por captura ordinaria de códigos.
- **Prueba humana:** dar de alta entidad, elegir tercero previamente conocido en dos operaciones y comprobar que se reutiliza; segunda entidad activa rechazada.
- **Límite:** monoentidad y monousuario; no cambiar RFC de contabilidad histórica como si fuera preferencia visual.

### V1-20 — Instalación y actualización

- **Hecho:** «Instalar Aqorath; actualizarlo y abrir mi contabilidad sin Internet».
- **Resultado profesional:** instalación limpia inicializa esquema explícito; actualización conserva datos y relaciones; misma consulta contable antes/después y recuperación ante fallo.
- **Evidencia y explicación:** versión del paquete, esquema, respaldo, bitácora de migración y smoke test; informar incompatibilidad sin rellenar datos desconocidos.
- **E:** `aqorath/migrations.py`, `test_p1_schema_migration_foundation.py`; no acreditan release instalable. **F:** AQR-015 define plataforma de distribución y paquete reproducible sobre la superficie local elegida en AQR-005, prueba instalación/actualización/offline sin servidor externo.
- **Prueba humana:** instalar paquete en equipo de prueba limpio, abrir fixture restaurado sin red y ejecutar V1-01/11/16.
- **Límite:** sólo plataformas expresamente probadas al release, sin promesa multiplataforma por anticipado; elección del toolkit no reabre este alcance de operaciones.

### V1-21 — Inventario y costo

- **Hecho:** «Compré 10 unidades a 10 y luego 10 a 20; vendí 4 unidades a 25»; producto, cantidades, fecha y documentos.
- **Resultado profesional:** inventario perpetuo por promedio ponderado móvil: costo total 300/20 unidades = 15 por unidad; salida de 4 cuesta 60; quedan 16 por 240; venta 100 y margen 40 antes de impuestos. Ledger y existencias reconcilian.
- **Evidencia y explicación:** ítem, entradas/salidas, documentos, cálculo exacto y pólizas de compra/venta/costo; explicar diferencia precio/costo y promedio, política de precisión y residuos.
- **E:** no subsistema inventario/costos localizado en auditoría V2; cuentas o plantillas no acreditan control de existencias. **F:** AQR-012: cantidades exactas, costo reproducible, rechazo de salida sin stock, idempotencia, política explícita de redondeo que conserve valor total y conciliación. Activación por capacidades de EntityProfile.
- **Prueba humana:** registrar ambas compras y venta, consultar 16 unidades/240 y pedir desglose del costo 60.
- **Límite:** mercancía comprada para reventa, un almacén lógico, sin stock negativo, manufactura, lotes/series, caducidad, consignación ni métodos alternativos. Este método es decisión de alcance de producto, no prescripción fiscal universal.

### V1-22 — Donativo en especie

- **Hecho:** «Recibimos una computadora donada; ésta es la evidencia de su valor 12000 y su destino».
- **Resultado profesional:** activo +12000/ingreso por donativo +12000 para donativo no condicionado del fixture; sin movimiento de caja. Si es mercancía soportada, reconocer inventario V1-21; si es consumo inmediato, reconocer destino pertinente sin simular efectivo.
- **Evidencia y explicación:** donante, acta/constancia de recepción, método y soporte de valuación, destino/restricción y póliza; explicar valor y naturaleza reconocida. Sin evidencia suficiente no inventar importe.
- **E:** `aqorath/donation.py` sólo donativo monetario como fundamento; `aqorath/fixed_asset_acquisition.py` no equivale a recepción en especie. **F:** AQR-009: InKindDonation, valuación documentada, vinculación al activo/inventario/destino y posting canónico sin duplicar adquisición; reportes AQR-013.
- **Prueba humana:** recibir equipo con evidencia y seleccionar destino; consultar ficha/póliza y comprobar que banco no cambió.
- **Límite:** bienes tangibles en destinos incluidos; sin servicios voluntarios valorizados, intangibles, condiciones de devolución ni deducibilidad automática.

## 5. Evidencia del corte y regla de terminación

- Lectura de instrucciones, Constitución, backlog y auditoría V2; inspección del código y pruebas citados. No se encontró motivo documental para reabrir el runtime validado.
- HEAD de `main`: `dce5f4143e9a3a26d0cfff27ba3a22ce2ae9358a`; [CI de ese HEAD](https://github.com/kagenomusuko-svg/aqorath/actions/runs/34376967511) concluido **success**. El endpoint de runs filtrado sólo a PR no devolvía este run de tipo push; se verificó el run de main directamente.
- Baseline de 1912 pruebas verdes: evidencia heredada de [REPO_AUDIT_V2.md](REPO_AUDIT_V2.md), no una nueva ejecución local de AQR-001. Las pruebas citadas no acreditan las capacidades marcadas F ni una validación humana/profesional.
- AQR-001 modifica documentación de alcance, no runtime ni esquema. AQR-015 sólo puede aceptar producto cuando cada fila incluida tenga las tres evidencias y los límites estén visibles al usuario. Una exclusión futura requiere decisión explícita registrada, no cambiar una fila a «fuera de V1» para ocultar una prueba fallida.
- Dependencias documentales recíprocas AQR-008/013: implementar trazabilidad y datos en AQR-008; consumirlos para reportes en AQR-013. No crear un motor de reportes alterno ni una tarea de roadmap adicional para resolver esa composición.

## 6. Exclusiones cerradas

| Operación o promesa | Estado V1 | Conducta esperada |
|---|---|---|
| Emisión/timbrado, cancelación SAT y complementos CFDI excluidos por V1-13 | Fuera de V1 | Informar límite, no afirmar validez fiscal por archivar un documento |
| Multimoneda y conversión | Fuera de V1 | Rechazar cálculo/posting automatizado fuera de MXN |
| Nómina y obligaciones laborales | Fuera de V1 | No activar plantillas históricas como flujo soportado |
| Fiscalidad integral de cualquier régimen, declaraciones/pagos al SAT, obligaciones completas de donatarias | Fuera de V1 | Declarar sólo tratamientos de V1-14; nunca prometer cumplimiento general |
| Notas de crédito comerciales, anticipos, factoring, intereses, arrendamiento financiero, baja/venta/revaluación de activos | Fuera de V1 | Informar que el hecho no tiene flujo V1; corrección contable sólo V1-18 |
| Manufactura y variantes de inventario excluidas por V1-21 | Fuera de V1 | No inferir costos a partir de venta o compras aisladas |
| Subvenciones condicionales/reembolsables y valuación de servicios voluntarios | Fuera de V1 | No tratarlas automáticamente como donativo simple |
| Multiusuario/RBAC o multiempresa simultánea | Fuera de V1 y prohibido por R8/R9 | No diseñar como capacidad latente |
| DRM o elección definitiva de licencia | Fuera de V1; decisión pospuesta R28 | Conservar la decisión humana pendiente |

## 7. Continuidad de esta entrega

AQR-001 está incorporada mediante PR #31 y queda DONE en el backlog. El siguiente trabajo es la única tarea NEXT allí registrada, inicialmente AQR-002. No reconstruir la matriz ni interpretar las fichas como capacidades de runtime ya terminadas. La continuidad y la autorización operativa se rigen por INSTRUCCIONES.md; la auditoría V2 sólo cambia si cambian materialmente capacidades/arquitectura.
