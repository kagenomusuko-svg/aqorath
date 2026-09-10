from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# PRODUCT_BACKLOG_V1.md
path = Path("docs/PRODUCT_BACKLOG_V1.md")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "## AQR-011 — Cobertura fiscal V1 declarada y versionada\n\n**Estado:** `NEXT`",
    "## AQR-011 — Cobertura fiscal V1 declarada y versionada\n\n**Estado:** `DONE`",
    "AQR-011 status",
)
text = replace_once(
    text,
    "## AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera\n\n**Estado:** `TODO`",
    "## AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera\n\n**Estado:** `NEXT`",
    "AQR-012 status",
)
text = replace_once(
    text,
    "## SIGUIENTE ACTUAL\n\n`AQR-011 — Cobertura fiscal V1 declarada y versionada`.",
    "## SIGUIENTE ACTUAL\n\n`AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera`.",
    "backlog NEXT",
)
anchor = "### Dependencias\n\nAQR-001 y AQR-010 para flujos CFDI.\n\n---\n\n## AQR-012"
closeout = """### Dependencias

AQR-001 y AQR-010 para flujos CFDI.

### Cierre de aceptación

Implementado y fusionado mediante PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`, head definitivo revisado `527934106b6b852b67f51d4a708435c3e4897aec`. CI del head definitivo run 498 verde; CI post-merge de `main` run 499 verde; suite completa Python 3.12 registrada: **2092 passed, 8 warnings**.

AQR-011 declara y versiona la cobertura fiscal mexicana V1 y falla cerrado fuera de soporte. Conserva la fórmula exacta de dos terceras partes cuando corresponde, modela `vat_pending_credit`, usa `ThirdParty` persistido como autoridad factual y mantiene CFDI AQR-010 como evidencia documental, no como inferencia jurídica. Posting, vínculo documental y auditoría son atómicos; las superficies común y profesional exponen la misma verdad sin pedir al usuario común tasas, cuentas ni Debe/Haber.

---

## AQR-012"""
text = replace_once(text, anchor, closeout, "AQR-011 closeout insertion")
if text.count("**Estado:** `NEXT`") != 1:
    raise SystemExit("backlog must contain exactly one NEXT")
path.write_text(text, encoding="utf-8")


# INSTRUCCIONES.md — sólo continuidad vigente.
path = Path("INSTRUCCIONES.md")
text = path.read_text(encoding="utf-8")
old_heading = "**`AQR-011 — Cobertura fiscal V1 declarada y versionada`**"
new_heading = "**`AQR-012 — Inventario y costos cuando el perfil de entidad lo requiera`**"
text = replace_once(text, old_heading, new_heading, "INSTRUCCIONES NEXT heading")
old_para = "AQR-011 debe declarar y versionar exactamente la cobertura fiscal mexicana V1, con vigencias, fuentes, aplicabilidad, pruebas fechadas y rechazo explícito de casos fuera de soporte. No debe inferir tratamiento fiscal únicamente desde los impuestos declarados por un CFDI."
new_para = "AQR-011 quedó incorporada mediante PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`, head revisado `527934106b6b852b67f51d4a708435c3e4897aec`, CI verde runs 498/499 y suite completa **2092 passed, 8 warnings**. AQR-012 es el único siguiente trabajo: inventario perpetuo y costos por promedio ponderado móvil, activados cuando el perfil de entidad lo requiera, siempre reconciliados con el ledger canónico y sin crear autoridad monetaria paralela."
text = replace_once(text, old_para, new_para, "INSTRUCCIONES continuity paragraph")
path.write_text(text, encoding="utf-8")


# REPO_AUDIT_V2.md — actualización material acotada a AQR-011.
path = Path("docs/REPO_AUDIT_V2.md")
text = path.read_text(encoding="utf-8")
text = replace_once(text, "**Runtime material vigente:** AQR-002 a AQR-010", "**Runtime material vigente:** AQR-002 a AQR-011", "audit runtime range")
text = replace_once(
    text,
    "AQR-010 incorporó CFDI XML como evidencia externa verificable y lo vinculó a esas autoridades sin convertirlo en ledger ni regla fiscal.",
    "AQR-010 incorporó CFDI XML como evidencia externa verificable y lo vinculó a esas autoridades sin convertirlo en ledger ni regla fiscal. AQR-011 cerró la cobertura fiscal mexicana V1 mediante matriz normativa versionada, aplicabilidad factual fail-closed, cálculo exacto y superficies común/profesional sobre la misma autoridad contable.",
    "audit executive AQR-011",
)
text = replace_once(
    text,
    "- **Estado de producción:** **NO declarado listo para producción**; una suite verde no sustituye aceptación profesional/humana ni cobertura fiscal declarada.\n- **Gap de producto principal inmediato:** la cobertura fiscal mexicana V1 todavía debe delimitarse por aplicabilidad, vigencia y fuente normativa revisada.\n- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-011.",
    "- **Estado de producción:** **NO declarado listo para producción**; una suite verde no sustituye la aceptación profesional/humana restante.\n- **Cobertura fiscal V1:** cerrada por AQR-011 con vigencias/fuentes versionadas, aplicabilidad factual y rechazo explícito fuera de soporte.\n- **Continuidad:** `PRODUCT_BACKLOG_V1.md` contiene exactamente un `NEXT`: AQR-012.",
    "audit executive result",
)
needle = "- impuestos del XML presentados sólo como evidencia; no se declara aplicabilidad fiscal ni consulta SAT.\n\n---\n\n## 3. Ledger y persistencia"
replacement = """- impuestos del XML presentados sólo como evidencia; no se declara aplicabilidad fiscal ni consulta SAT.

### AQR-011 — cobertura fiscal V1 declarada y versionada

- PR #46, merge `5dc5640734d46b685ccf8dd9adf9f77206557481`;
- head definitivo revisado `527934106b6b852b67f51d4a708435c3e4897aec`;
- CI del head run 498 verde; CI post-merge de `main` run 499 verde;
- suite completa Python 3.12: **2092 passed, 8 warnings**;
- cobertura fiscal V1 declarada/versionada con fuentes y vigencias explícitas;
- aplicabilidad factual fail-closed y rechazo explícito de contextos fuera de soporte;
- fórmula exacta de retención de dos terceras partes cuando corresponde y `vat_pending_credit` como efecto explícito;
- `ThirdParty` persistido como autoridad factual para condiciones que dependen de contraparte;
- CFDI permanece evidencia documental y no selector jurídico;
- posting fiscal, documento/CFDI y auditoría se componen atómicamente sobre las autoridades existentes;
- superficies común/profesional reconstruyen la misma verdad fiscal persistida.

---

## 3. Ledger y persistencia"""
text = replace_once(text, needle, replacement, "audit AQR-011 evidence")
text = replace_once(text, "Estado: **ARQUITECTURA Y FLUJOS IMPLEMENTADOS; COBERTURA V1 NO CERRADA**", "Estado: **ARQUITECTURA, FLUJOS Y COBERTURA FISCAL V1 IMPLEMENTADOS**", "audit fiscal status")
old_pending = "### Pendiente real\n\nAQR-011 debe cerrar aplicabilidad y cobertura fiscal V1. Lo no soportado debe fallar explícitamente."
new_pending = "### Cobertura V1 cerrada\n\nAQR-011 declara los tratamientos soportados por fuente/vigencia y resuelve aplicabilidad con hechos persistidos; lo no soportado falla explícitamente. CFDI no selecciona por sí mismo la norma aplicable y la autoridad monetaria continúa en `JournalEntry` / `JournalLine`."
text = replace_once(text, old_pending, new_pending, "audit fiscal closeout")
path.write_text(text, encoding="utf-8")
