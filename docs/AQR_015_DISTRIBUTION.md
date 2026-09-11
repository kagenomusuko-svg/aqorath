# AQR-015 — Contrato inicial de distribución e instalación

Este documento registra el corte ejecutable vigente de AQR-015. No declara todavía la aceptación final V1 ni sustituye `PRODUCT_ACCEPTANCE_V1.md`.

## Autoridad de packaging

- `pyproject.toml` conserva únicamente el backend de build (`setuptools.build_meta`).
- `setup.cfg` es la autoridad de metadatos instalables, dependencias runtime, package data y console script.
- `aqorath/version.py` es la única autoridad del identificador de versión de paquete.
- El identificador actual `0+aqr015` es deliberadamente un identificador de desarrollo, no una decisión sobre el número semántico final de la release V1. La elección del número final permanece aislada como decisión humana de release y no bloquea los demás gates AQR-015.
- No se declara licencia definitiva: esa decisión continúa pospuesta por la Constitución/backlog.

## Dependencias

Runtime instalado, porque módulos productivos las importan directamente:

- `sqlmodel` y `sqlalchemy` — persistencia/ORM;
- `fastapi` y `uvicorn` — superficie web local y launcher;
- `openpyxl` — reportes XLSX AQR-013/estados financieros;
- `reportlab` — estados financieros PDF;
- `lxml` — ingestión CFDI AQR-010.

Desarrollo/build/mantenimiento, no requisitos de ejecución del producto:

- `pytest`;
- `build`;
- `pyinstaller`;
- `requests` (script de mantenimiento `scripts/fetch_xsds.py`).

`pandas` y `python-dateutil` no se declaran como runtime porque el código productivo vigente no los importa.

## Recursos instalables

El único recurso no-Python requerido por runtime identificado en el primer corte es:

- `aqorath/data/catalogo_base.json`.

Se incluye en wheel mediante `options.package_data` y en sdist mediante `MANIFEST.in`. `aqorath.catalog` es la autoridad de resolución de su ruta. `accounting_rules.py` delega ahora en esa autoridad y deja de depender del working directory.

Los `assets/`, `templates/`, patches y fuentes de generación históricas no se incorporan al paquete sólo por existir en el repositorio. El catálogo XLSX/CSV es material de mantenimiento de desarrollo; el runtime consume el JSON gobernado ya generado.

## Entry point y bootstrap

El console script instalado es:

```text
aqorath -> aqorath.entrypoint:main
```

`entrypoint.main` sólo compone:

1. `product_bootstrap.bootstrap_local_product()`;
2. `local_server.run_local_surface()`.

No contiene reglas contables ni HTTP. El launcher canónico continúa siendo `aqorath.local_server.run_local_surface`, que fija `127.0.0.1` y sirve `aqorath.web_surface:app` con las rutas AQR-014 registradas.

`product_bootstrap` crea únicamente el directorio padre escribible de la DB y delega creación/upgrade a `storage.init_db() -> migrations.migrate_database()`. No contiene DDL, no crea un migrador paralelo y conserva el rechazo de schema futuro y los respaldos pre-migración de la autoridad existente.

La ruta por defecto vigente sigue siendo la autoridad histórica de `storage.py` (`~/.local/share/aqorath/aqorath.db`), con `AQORATH_DB` como override explícito. La instalación no escribe dentro de `site-packages`.

## Onboarding guiado y atomicidad

El onboarding de instalación compone las autoridades existentes de catálogo, Entity/EntityProfile, calendario/períodos, FiscalProfile y account bindings. No crea tablas ni repositorios paralelos.

Toda validación determinística del payload ocurre antes de iniciar escritura. Después, la materialización del catálogo canónico, creación de entidad, declaración del calendario, apertura del primer ejercicio, perfil fiscal y bindings se ejecutan como **una sola transacción propiedad del caso de uso de onboarding**. Las autoridades de entidad/perfil y bindings conservan su comportamiento histórico de auto-commit por defecto, pero admiten staging explícito (`commit=False`) cuando participan en esta composición.

Si cualquier paso tardío falla, la sesión revierte la transacción completa. No puede quedar una entidad activa sin perfil fiscal, calendario o bindings, ni puede un reintento quedar bloqueado por un onboarding parcialmente persistido. Una prueba de fallo inyectado después de haber staged múltiples bindings verifica rollback total y reintento limpio.

## Smoke reproducible inicial

CI construye una sola vez sdist + wheel y ejecuta `scripts/verify_distribution.py` sobre esos artifacts. El smoke:

- valida que el sdist contiene el catálogo gobernado y metadata de build;
- crea un venv limpio;
- instala exclusivamente el wheel construido y sus dependencias declaradas;
- elimina `PYTHONPATH` para impedir que el checkout oculte defectos;
- cambia el working directory a un temporal fuera del repositorio;
- importa Aqorath y módulos que ejercitan dependencias runtime;
- carga el catálogo desde `site-packages`;
- invoca el console script real;
- verifica superficie HTTP en `127.0.0.1:8765`;
- verifica integridad AQR-014 y creación/migración SQLite;
- solicita cierre del proceso y falla si requiere kill forzado.

Este gate acredita sólo el baseline de distribución/instalación. AQR-015 sigue abierto hasta completar upgrade histórico, offline explícito, recorridos V1-01..V1-22, evidencia profesional y prueba humana reproducible.
