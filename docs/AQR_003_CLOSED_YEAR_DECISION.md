# AQR-003 — Correcciones de ejercicios ya cerrados

Estado: **decisión aprobada**. Alternativa 2 aprobada expresamente por el usuario el 2026-09-09. Esta decisión cierra la frontera contable necesaria para AQR-003 sin definir todavía una política sustitutiva para errores de ejercicios anteriores.

## Decisión aprobada

Las operaciones pertenecientes a un ejercicio ya cerrado **no se corrigen automáticamente mediante reversión y sustitución sobre las cuentas originales en un ejercicio abierto posterior**.

Ese comportamiento queda bloqueado preventivamente porque introduciría implícitamente una política sobre errores de ejercicios anteriores y podría trasladar su efecto al resultado del ejercicio corriente sin una decisión contable autorizada.

Por tanto:

- las correcciones de ejercicios cerrados se rechazan antes de crear reversión, sustituto o evidencia parcial;
- las correcciones de ejercicios abiertos continúan disponibles y consumen las autoridades de período ya existentes;
- no se reabren períodos ni ejercicios de manera implícita;
- no se define todavía clasificación, cuentas, fechas, materialidad, reexpresión ni presentación para errores de ejercicios anteriores;
- esa política futura es una **decisión contable separada**, pero no se convierte en `NEXT` ni bloquea AQR-004 una vez integrada AQR-003 sobre los casos válidos ya definidos.

## Evidencia del repositorio

- AQR-003 y V1-18 exigen original intacto, reversión, sustituto, motivo y AuditEvent; el ejemplo 150→120 no fija ejercicio ni efecto en resultados posteriores.
- AQR-002 prohíbe nuevos postings en períodos cerrados y reapertura implícita; al cerrar cancela resultados y acumula su saldo en 3104.
- Ninguna fuente vigente define todavía si un error de un ejercicio cerrado afecta resultados del ejercicio de detección, resultados acumulados, comparativos u otra clasificación.
- `reversal.py` invierte líneas sobre las cuentas originales. Esa mecánica es válida para correcciones dentro de ejercicios abiertos, pero no constituye por sí misma una política autorizada para ejercicios anteriores cerrados.

Caso límite que motiva la decisión: venta de 150 en año Y, cierre de Y, corrección a 120 en Y+1. Invertir 150 y registrar 120 sobre las mismas cuentas en Y+1 reduciría en 30 los ingresos de Y+1 sin modificar el resultado ya cerrado de Y. La mera validez del período de destino no autoriza ese efecto.

## Implementación autorizada en AQR-003

PR #36 reutiliza las autoridades existentes y aplica un rechazo preventivo cuando el `FiscalYear` del asiento original está `closed`. Para ejercicios abiertos, reversión y sustitución continúan pasando por el staging canónico y por el resolvedor de período abierto. No se crea otro motor, otra ruta de posting ni una política contable paralela.

La reversión conserva el original como historia, crea una operación balanceada vinculada, exige motivo y genera `AuditEvent` dentro de la misma transacción. La corrección compuesta conserva original, reversión y sustituto, y añade evidencia de corrección. Los fallos revierten la operación completa.

## Política futura separada

El tratamiento de errores de ejercicios anteriores permanece sin definir. Cuando sea necesario incorporarlo al producto deberá resolverse expresamente como política contable: clasificación, cuentas, fecha de reconocimiento, materialidad, presentación/reexpresión y evidencia aplicable.

No es el `NEXT` actual y no impide continuar AQR-004 después de la integración y aceptación de AQR-003.
