# Aqorath

Aqorath es un ERP contable profesional, local-first, explicable, monousuario y monoentidad.

Su principio de producto es:

> **Aqorath pregunta hechos; Aqorath resuelve contabilidad.**

La simplicidad está en la interacción; la contabilidad conserva rigor profesional, trazabilidad, exactitud monetaria y una única fuente de verdad local.

## Empezar aquí

Para continuar desarrollo o auditar el proyecto, leer en este orden:

1. [`INSTRUCCIONES.md`](./INSTRUCCIONES.md) — protocolo canónico de continuidad y `SIGUIENTE`.
2. [`docs/AQORATH_CONSTITUTION_V1.md`](./docs/AQORATH_CONSTITUTION_V1.md) — reglas arquitectónicas no negociables.
3. [`docs/PRODUCT_BACKLOG_V1.md`](./docs/PRODUCT_BACKLOG_V1.md) — tareas de producto pendientes y estado.
4. [`docs/REPO_AUDIT_V2.md`](./docs/REPO_AUDIT_V2.md) — corte actual de capacidades implementadas y gaps.
5. [`docs/ARCHITECTURE_BASELINE_V1.md`](./docs/ARCHITECTURE_BASELINE_V1.md) — arquitectura objetivo y modelo conceptual.

No reconstruir el estado del proyecto a partir de conversaciones, ramas antiguas o PR históricos cuando estos documentos ya contienen la autoridad necesaria.

## Estado del baseline

El baseline de runtime revisado incorpora PR #30 (`Phase 6BP persistence hardening`) sobre `main`.

- Merge de runtime: `7623e4eb0636064cdab0582ce3c98e7b9c844e93`
- Suite completa verificada antes del merge: **1912 passed, 0 failed**
- P0 actuales conocidos en el corte de auditoría 2026-09-09: **ninguno identificado**

Esto no significa que Aqorath V1 esté terminado. Las capacidades de producto faltantes están enumeradas en `docs/PRODUCT_BACKLOG_V1.md`.

## Desarrollo

La suite se ejecuta con:

```bash
python -m pytest
```

Antes de implementar una capacidad nueva, comprobar el único elemento `NEXT` del backlog y revisar la implementación existente para evitar autoridades duplicadas.
