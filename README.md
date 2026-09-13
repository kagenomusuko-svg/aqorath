# Aqorath

Aqorath es un ERP contable profesional, local-first, explicable, monousuario y monoentidad.

Su principio de producto es:

> **Aqorath pregunta hechos; Aqorath resuelve contabilidad.**

La simplicidad está en la interacción; la contabilidad conserva rigor profesional, trazabilidad, exactitud monetaria y una única fuente de verdad local.

## Empezar aquí

Para continuar desarrollo o auditar el proyecto, respetar el orden de autoridad canónico:

1. [`docs/AQORATH_CONSTITUTION_V1.md`](./docs/AQORATH_CONSTITUTION_V1.md) — reglas arquitectónicas no negociables.
2. [`INSTRUCCIONES.md`](./INSTRUCCIONES.md) — protocolo canónico de ejecución, continuidad y `SIGUIENTE`.
3. [`docs/PRODUCT_BACKLOG_V1.md`](./docs/PRODUCT_BACKLOG_V1.md) — tareas de producto pendientes y estado.
4. [`docs/REPO_AUDIT_V2.md`](./docs/REPO_AUDIT_V2.md) — corte verificable de capacidades implementadas y gaps.
5. [`docs/ARCHITECTURE_BASELINE_V1.md`](./docs/ARCHITECTURE_BASELINE_V1.md) — arquitectura objetivo y modelo conceptual.

No reconstruir el estado del proyecto a partir de conversaciones, ramas antiguas o PR históricos cuando estos documentos ya contienen la autoridad necesaria.

## Estado actual

`main` incorpora el runtime y las capacidades aceptadas de `AQR-002` a `AQR-014`. El único trabajo autorizado como `NEXT` por `INSTRUCCIONES.md` y el backlog es:

> **AQR-015 — Empaquetado, instalación y aceptación V1**

AQR-015 se desarrolla en una rama/PR propios y todavía no implica que Aqorath V1 esté declarado listo para producción. Su aceptación exige completar los gates técnicos, profesionales y humanos definidos por el repositorio.

Para conocer SHAs, suites y runs de CI del corte vigente no usar números históricos copiados en este README: consultar `INSTRUCCIONES.md`, `docs/PRODUCT_BACKLOG_V1.md` y `docs/REPO_AUDIT_V2.md`, que son las autoridades de continuidad.

## Desarrollo

La suite se ejecuta con:

```bash
python -m pytest
```

Antes de implementar una capacidad nueva, comprobar el único elemento `NEXT` del backlog y revisar la implementación existente para evitar autoridades duplicadas.

Durante AQR-015, los contratos de distribución, instalación y aceptación se documentan en [`docs/AQR_015_DISTRIBUTION.md`](./docs/AQR_015_DISTRIBUTION.md) y en la matriz V1 ya congelada en [`docs/PRODUCT_ACCEPTANCE_V1.md`](./docs/PRODUCT_ACCEPTANCE_V1.md).
