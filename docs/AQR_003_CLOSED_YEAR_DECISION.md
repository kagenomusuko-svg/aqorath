# AQR-003 — Correcciones de ejercicios ya cerrados

Estado: decisión contable/de alcance pendiente. PR #36 conserva las correcciones técnicas preparadas, pero no debe declarar AQR-003 DONE hasta resolver esta frontera.

## Decisión exacta

Definir qué debe hacer V1 al corregir una operación cuyo ejercicio ya fue cerrado: admitir reversión mecánica en un período abierto posterior, o exigir un tratamiento explícito de errores de ejercicios anteriores que todavía no está definido.

## Evidencia del repositorio

- AQR-003 y V1-18 exigen original intacto, reversión, sustituto, motivo y AuditEvent; el ejemplo 150→120 no fija ejercicio ni efecto en resultados posteriores.
- AQR-002 prohíbe nuevos postings en períodos cerrados y reapertura implícita; al cerrar cancela resultados y acumula su saldo en 3104.
- Ninguna de esas fuentes define si un error de un ejercicio cerrado afecta resultados del ejercicio de detección, resultados acumulados, o requiere un tratamiento distinto según el caso. Tampoco fija criterios de materialidad ni reexpresión de comparativos.
- `reversal.py` en PR #35 sólo intercambia debit/credit y permite una fecha posterior: no contiene una política específica para errores de ejercicios cerrados.

Caso concreto: venta de 150 en año Y, cierre de Y, corrección a 120 en Y+1. Invertir 150 y registrar 120 sobre las mismas cuentas en Y+1 reduce en 30 los ingresos de Y+1; no modifica el resultado cerrado de Y. La mera validez del período de destino no decide que ese sea el efecto contable querido.

## Alternativas y consecuencias

1. Autorizar en V1 la reversión mecánica y el sustituto en un período posterior abierto, sobre las cuentas originales, con advertencia expresa del efecto en el nuevo ejercicio. Conserva la historia; puede afectar el resultado posterior. Esta opción sería un contrato explícito de producto, no una afirmación de cumplimiento fiscal general.
2. Mantener el rechazo de correcciones automáticas de ejercicios cerrados hasta definir una política específica. Las correcciones de ejercicios abiertos continúan; para los cerrados habrá que especificar clasificación, cuentas, fechas y reportes aplicables antes de habilitarlas.

Recomendación técnica: alternativa 2. Evita elegir una consecuencia contable por la comodidad de invertir líneas. No se toma esa decisión por el usuario: el rechazo actual es preventivo mientras la política siga sin resolver.

No se ofrece reapertura silenciosa: contradice AQR-002.

## Trabajo resoluble preparado

PR #36 corrige defectos reproducibles de PR #35: edición balanceada de líneas posted y ausencia de AuditEvent. Reutiliza listeners, staging, resolvedor temporal y repositorio de auditoría. Añade protección del original reversed y de la identidad, rollback de reversión/auditoría y corrección 150→120 con tres pólizas vinculadas. Una prueba bloquea expresamente la corrección del ejercicio cerrado sin dejar filas parciales. No reescribe historia, no modifica la Constitución ni crea otro motor contable.

Continuidad: AQR-003 sigue siendo el único NEXT; AQR-004 conserva su dependencia. Tras la decisión, terminar la integración y aceptación aquí y continuar AQR-004; no abrir una fase histórica ni reconstruir autoridades.
