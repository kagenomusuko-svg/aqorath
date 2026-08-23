# AQORATH CONSTITUTION V1

## Propósito

Este documento codifica los 28 principios fundacionales de Aqorath como **reglas arquitectónicas no negociables** que vinculan las decisiones de diseño con la naturaleza del sistema.

Toda arquitectura, API, interfaz y motor contable debe poder justificarse contra estas reglas. Una característica que viola una regla no debe ser aceptada, incluso si funciona o resulta conveniente.

---

## MISIÓN Y NICHO

**Aqorath** es un ERP contable profesional, local-first, explicable, monousuario y monoentidad, desarrollado en el contexto institucional de Meriadock A.C.

**Nicho principal:**
- Personas autoempleadas
- Microactividades económicas
- Pequeños negocios
- Asociaciones civiles
- Organizaciones sin fines de lucro
- Donatarias autorizadas

**Dentro del nicho: excelencia profesional comparable a sistemas comerciales.**

---

## REGLAS ARQUITECTÓNICAS EXPLÍCITAS (28)

### R1: PRIMACÍA DEL HECHO ECONÓMICO

**Regla:** "Aqorath pregunta hechos; Aqorath resuelve contabilidad."

- Usuario proporciona: vendí, compré, cobré, pagué, recibí donativo
- Usuario NO proporciona: Debe/Haber, códigos, naturale za contable
- Sistema infiere determinísticamente la representación contable correcta

**Arquitectura:** Toda interfaz opera en lenguaje de hechos y roles semánticos (bank, sales, expense).

**Estado:** CUMPLE (templates.py, core.py generate_preview)

---

### R2: UNA CONTABILIDAD, DOS INTERFACES

Motor único. Persistencia única. DOS interfaces:
- A) Común (lenguaje cotidiano)
- B) Profesional (pólizas, Debe/Haber, auxiliares)

Cambiar de interfaz jamás altera sustancia contable.

**Estado:** CUMPLE (core.py es motor único; desktop.py + api.py son interfaces)

---

### R3: RIGOR PROFESIONAL

Simplicidad en interacción, rigor en contabilidad. Vista profesional reconocible a contador. Directriz hacia: catálogo, pólizas, diario, mayor, auxiliares, balanza, estados financieros, ejercicios, cierres, bancos, conciliaciones, impuestos, CFDI, trazabilidad, auditoría.

**Estado:** PARCIAL (catálogo existe; falta: mayores, auxiliares, balanza formal, impuestos complejos, CFDI productivo)

---

### R4: PARTIDA DOBLE COMO INVARIANTE

Nunca persistir asiento descuadrado. Detectar → Explicar → Detener. Nunca corregir silenciosamente.

**Implementación:** _persist_entry() valida antes de insertar.

**Estado:** CUMPLE con advertencia (no hay mensaje de error muy explícito)

---

### R5: DINERO EXACTO (Decimal)

Persistencia: Decimal. Cálculos: Decimal. Float solo display temporal.

**Estado:** ✗ INCUMPLIMIENTO CRÍTICO (P0)
- Líneas 43-44 models.py: `debit: float`, `credit: float`
- Línea 52 models.py: `value: float`
- core.py línea 690: convierte a float para insert

**Migración requerida:** Cambiar a Decimal en BD + ORM

---

### R6: LOCAL-FIRST

Funcionar sin Internet. Servidores Meriadock caídos no impiden usar contabilidad.

**Implementación:** SQLite local, fallback sqlite en core.py, backups automáticos.

**Estado:** CUMPLE

---

### R7: SQLITE COMO FUENTE CONTABLE LOCAL

Excel/CSV/JSON: solo importación/exportación. NO como fuentes primarias competidoras.

**Estado:** CUMPLE (SQLite primary; JSON catálogo es copia; DataFrames son fallback legacy)

---

### R8: MONOUSUARIO

NO arquitectura multiusuario. NO usuarios/roles/permisos (aún).

**Estado:** CUMPLE (no hay tabla User, no hay autenticación)

---

### R9: MONOENTIDAD

Una DB = una entidad. NO gestor de múltiples clientes. Cambiar entidad = migración, no "seleccionar empresa".

**Estado:** CUMPLE (tabla Company, monoentidad)

---

### R10: CATÁLOGO GOBERNADO Y EXTENSIBLE

Estructura canónica protegida + extensiones legítimas del usuario. Usuario describe "BBVA" → Aqorath la ubica.

**Estado:** ✗ CONFLICTO (P1)
- Actual: catálogo inmutable (storage.py listener líneas 50-64)
- Requerido: extensible con validación de estructura

**Documentación del conflicto:** docs/CATALOG_POLICY.md vs Constitución Principio 10

---

### R11: EXPLICABILIDAD DETERMINÍSTICA

Cada operación importante: ¿qué ocurrió? ¿Por qué? ¿Qué cuentas? ¿Qué efectos? Explicación derivada de MISMA regla que resultado.

**Estado:** PARCIAL (generate_preview retorna líneas; falta explicación de por qué)

---

### R12: CONSENTIMIENTO INFORMADO

Modo "acompañado" (explica) + modo "operativo". Usuario puede pedir "Explícame esto" en cualquier momento.

**Estado:** NO IMPLEMENTADO

---

### R13: PROGRESIVIDAD PEDAGÓGICA

Registrar qué conceptos ya presentados. Usuario aprende sobre su actividad económica. Sin gamificación infantil.

**Estado:** NO IMPLEMENTADO

---

### R14: ARQUITECTURA FISCAL VERSIONADA

Reglas fiscales: versionadas, no fusionadas con contabilidad universal. Cambio fiscal no exige reescribir core.

**Estado:** PROTOTIPO (tax.py, CFDI.py; no versionado)

**En Phase 0:** Solo diseñar separación

---

### R15: ENTIDAD ≠ "COMERCIAL / OSC"

Identidad multicomponente: naturaleza jurídica + régimen fiscal + características + capacidades. Una donataria NO es otro motor.

**Estado:** PARCIAL (catálogo tiene name_osc/name_comercial; falta EntityProfile)

---

### R16: OSC COMO CIUDADANO DE PRIMERA CLASE

Soportar: programas, proyectos, fondos, donantes, donativos, restricciones, cuotas, aplicación de recursos, trazabilidad, reportes OSC.

**Estado:** PROTOTIPO (catálogo OSC-ready; falta módulo integrado)

---

### R17: DIMENSIONES ANALÍTICAS SIN DUPLICAR CONTABILIDAD

Una línea → múltiples dimensiones (programa, fuente). UNA asiento contable, NO múltiples ficticios.

**Estado:** NO IMPLEMENTADO

---

### R18: DOCUMENTOS COMO UNIDADES INDEPENDIENTES

Documento = ReportDefinition (datos, parámetros, período, formato, reglas, disponibilidad por EntityProfile).

**Estado:** PARCIAL (reportes.py genera algunos; falta arquitectura generalizada)

---

### R19: PAQUETES COMO PRESETS, NO LÍMITES

Paquete = selección inicial reutilizable. Usuario personaliza, guarda como nuevo paquete. No bloqueados.

**Estado:** NO IMPLEMENTADO

---

### R20: REUTILIZACIÓN DE INFORMACIÓN

Dato capturado → reutilizar en todos lados. Si Aqorath conoce tercero/importe/CFDI, no re-preguntar.

**Estado:** PARCIAL (templates resuelven roles; falta caché de datos recientes)

---

### R21: INTEROPERABILIDAD Y AUSENCIA DE LOCK-IN

Exportar datos para migración. NO impedir "graduación" a otros ERP. Formato abierto.

**Estado:** PARCIAL (test_asientos.py::test_export_asiento_csv_and_xlsx; falta catalogación completa y docs de formato)

---

### R22: SEGURIDAD E INTEGRIDAD LOCAL

Respaldo, restauración, migración, integridad: centrales no accesorios. NO adivinar columnas, NO rellenar silenciosamente, NO continuar ante inconsistencias.

**Estado:** RIESGO (exercise.py backups ✓; core.py detecta esquema dinámicamente = flexible pero frágil)

---

### R23: SEPARACIÓN DE CAPAS

```
INTERFAZ → APLICACIÓN/CASOS DE USO → DOMINIO → PERSISTENCIA
```

UI/API NO contienen lógica contable. Dominio NO depende de PySide/FastAPI/SQLite/pandas.

**Estado:** PARCIAL (core.py motor intermedio ✓; modelos/libro.py legacy, mezcla de capas)

**Estructura requerida:** domain/, application/, infrastructure/, presentation/

---

### R24: UNA SOLA AUTORIDAD DE NEGOCIO

NO múltiples implementaciones de misma regla. Todas superficies consumen MISMOS casos de uso.

**Estado:** RIESGO (core.py base ✓; posibles rutas paralelas en desktop.py/modelos/libro.py)

---

### R25: NO FALLBACKS QUE OCULTEN ERRORES ESTRUCTURALES

Permitir: tolerancia prevista (migración formato), falta opcional (templates). 
PROHIBIR: exception genérica + adivinar + rellenar + continuar.

**Estado:** RIESGO (29 except Exception genéricas detectadas; core.py fallbacks semi-silenciosos)

---

### R26: CALIDAD DE NICHO

Declarar qué soporta. Dentro nicho: resultado correcto, experiencia excelente. Fuera: rechazar con motivo.

**Estado:** PARCIAL (catálogo base ✓; falta documentación de límites)

---

### R27: PRUEBA TRIPLE DE ACEPTACIÓN

A) Técnica (tests). B) Profesional (contador valida). C) Humana (persona sin contabilidad completa flujo).

**Estado:** A+B existen ✓; C depende de UI (desktop.py esquelética)

---

### R28: LICENCIA SOCIAL (PENDIENTE)

Intención: gratuito para beneficiarios. En estudio: licencia social/source-available. NO implementar aún: restricciones técnicas, DRM.

**Estado:** SIN DECISIÓN (no hay licencia en repo, sin restricción técnica)

---

## SÍNTESIS Y REFERENCIAS

Estas reglas son **no negociables**. Toda decisión arquitectónica debe justificarse contra ellas. Ver ARCHITECTURE_BASELINE_V1.md para diseño de separación de capas y REPO_AUDIT_V1.md para estado actual vs riesgo.

