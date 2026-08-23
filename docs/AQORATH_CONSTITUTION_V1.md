# AQORATH CONSTITUTION V1

## Propósito

Este documento codifica los 28 principios fundacionales de Aqorath como **reglas arquitectónicas no negociables** que vinculan las decisiones de diseño con la naturaleza del sistema.

Toda arquitectura, API, interfaz y motor contable debe poder justificarse contra estas reglas. Una característica que viola una regla no debe ser aceptada, incluso si funciona o resulta conveniente.

**Nota importante:** Esta Constitución es NORMATIVA y ATEMPORAL. No describe el estado actual del código. Eso corresponde a REPO_AUDIT_V1.md. Esta Constitución define QUÉ DEBE SER Aqorath, independientemente de dónde esté hoy.

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

## 28 PRINCIPIOS FUNDACIONALES COMO REGLAS ARQUITECTÓNICAS

### R1: PRIMACÍA DEL HECHO ECONÓMICO

**Regla:** "Aqorath pregunta hechos; Aqorath resuelve contabilidad."

**Consecuencia arquitectónica:**
- El usuario proporciona: hechos económicos (vendí, compré, cobré, pagué, recibí donativo)
- El usuario NO proporciona: Debe/Haber, códigos contables, naturaleza de cuenta
- El sistema **infiere determinísticamente** la representación contable correcta
- Toda interfaz de usuario debe operar en lenguaje de hechos económicos y roles semánticos

**Violación ejemplar:**
- Pedir al usuario "¿Es este un débito o un crédito?"
- Mostrar campo "Naturaleza de cuenta" en interfaz común
- Requerir códigos contables como input

---

### R2: UNA CONTABILIDAD PROFESIONAL, DOS INTERFACES

**Regla:** No existen dos motores contables. Existe **una sola contabilidad y una sola persistencia.**

**Consecuencia arquitectónica:**
- Motor contable único y definitivo
- Fuente única de datos (SQLite local)
- DOS interfaces sobre la misma realidad:
  - **A) Interfaz común:** lenguaje cotidiano, roles, hechos económicos
  - **B) Interfaz profesional:** pólizas, cuentas, Debe/Haber, auxiliares, referencias, períodos, documentos, impuestos, dimensiones analíticas
- Cambiar de interfaz jamás puede alterar la sustancia contable
- Ambas interfaces consumen los mismos servicios/casos de uso del dominio

**Validación:**
- Si un número aparece diferente en interfaz común vs profesional, el sistema está roto
- Si una operación es válida en una interfaz pero inválida en la otra, es violación de esta regla

---

### R3: RIGOR PROFESIONAL

**Regla:** La simplicidad vive en la **interacción**, no en la contabilidad. La vista profesional debe resultar reconocible y defendible para un contador.

**Consecuencia arquitectónica:**
- Aqorath debe poder soportar progresivamente: catálogo de cuentas, pólizas, diario, mayor, auxiliares, balanza, estados financieros, ejercicios, períodos, cierres, bancos, conciliaciones, cuentas por cobrar, cuentas por pagar, ventas, compras, inventarios, costos, activos, depreciaciones, impuestos, CFDI, trazabilidad, auditoría, respaldos, documentos y reportes.
- Esta lista define la **dirección del producto**, no lo que debe implementarse ahora
- No aceptar soluciones que sean "suficientemente buenas para software gratuito"
- Una función no está terminada cuando "el código funciona"; debe resultar defendible profesionalmente

---

### R4: PARTIDA DOBLE COMO INVARIANTE ABSOLUTA

**Regla:** Nunca podrá persistirse un asiento descuadrado. La partida doble es invariante no negociable.

**Consecuencia arquitectónica:**
- TODO estado persistido (entry + lines) debe cumplir: Σ(débitos) = Σ(créditos)
- Si hay inconsistencia: DETECTAR → EXPLICAR → DETENER LA OPERACIÓN
- Nunca corregir silenciosamente, nunca crear fallbacks que permitan persistencia de inconsistencias
- Tests deben validar que asientos inbalanceados son rechazados

---

### R5: DINERO EXACTO (Decimal)

**Regla:** Los valores monetarios persistentes y los cálculos contables no deben depender de float binario.

**Consecuencia arquitectónica:**
- Valores monetarios en persistencia: usar Decimal (SQL NUMERIC, DECIMAL o equivalente)
- Cálculos intermedios: usar Decimal Python
- Float permitido SOLO para: display temporal, transmisión por API, operaciones no críticas
- Cuantización: 2 decimales para dinero (0.01)

---

### R6: LOCAL-FIRST

**Regla:** La información contable pertenece al usuario. La fuente primaria de datos debe residir localmente.

**Consecuencia arquitectónica:**
- Aqorath debe funcionar sin Internet
- Aqorath debe funcionar aunque servidores de Meriadock estén caídos
- Ningún servicio central de Meriadock puede ser requisito para leer contabilidad existente
- Usuario tiene control total sobre backup y restauración

---

### R7: SQLITE COMO FUENTE CONTABLE LOCAL

**Regla:** La arquitectura objetivo utilizará SQLite local como fuente de verdad contable de la instalación.

**Consecuencia arquitectónica:**
- Excel, CSV, XLSX, JSON: solo para importación/exportación/respaldo auxiliar
- NO deben coexistir como fuentes primarias competidoras
- Eliminar dependencia de fallbacks a DataFrames o sistemas alternativos
- Consolidar cálculos de trial_balance en motor único

---

### R8: MONOUSUARIO

**Regla:** Una instalación está diseñada para un propietario/usuario local.

**Consecuencia arquitectónica:**
- NO construir arquitectura de concurrencia multiusuario
- NO implementar usuarios, roles, permisos, auditoría por usuario (aún)
- La existencia de mecanismos administrativos NO debe convertir Aqorath accidentalmente en multiusuario
- APIs deben ser locales (IPC, localhost) no expuestas en red

---

### R9: MONOENTIDAD

**Regla:** Una instalación representa una entidad económica activa.

**Consecuencia arquitectónica:**
- Una DB por instalación = una entidad
- NO crear "modo seleccionar empresa" en UI
- NO implementar tabla clientes/empresas en Aqorath
- Cambiar de entidad requiere procedimiento explícito (migración, no "abrir otra empresa en lista")
- Invariante: Nunca debe existir más de una fila Company activa en una instalación
- Persistencia debe garantizar monoentidad (constraint UNIQUE si es necesario)

---

### R10: CATÁLOGO GOBERNADO Y EXTENSIBLE

**Regla:** Abandonar catálogo absolutamente cerrado. Requerir distinción entre estructura canónica protegida y extensiones legítimas.

**Consecuencia arquitectónica:**
- A) Estructura contable canónica protegida (Activo/Pasivo/Patrimonio/Ingresos/Gastos)
- B) Cuentas/extensiones creadas por usuario para su realidad concreta
- Usuario puede describir "Mi cuenta BBVA" → Sistema la ubica en estructura canónica sin pedir código
- El listener debe **validar estructura** NO **prevenir creación**
- Extensiones deben poder marcarse como is_canonical=false
- Estructura canónica (tipos, subtipos, naturaleza) no puede romperse

---

### R11: EXPLICABILIDAD DETERMINÍSTICA

**Regla:** Toda operación importante debe poder responder: ¿qué ocurrió? ¿qué interpretó Aqorath? ¿Qué cuentas afectó? ¿Por qué? ¿Qué efecto económico/fiscal produjo?

**Consecuencia arquitectónica:**
- La explicación NO es una verdad independiente
- Derivarse de la misma estructura/rule set que produjo el resultado
- NO puede ser generada por IA genérica al azar
- Cada operación debe poder retornar su justificación
- Explicación estructurada, no solo texto libre

---

### R12: CONSENTIMIENTO INFORMADO CONTABLE

**Regla:** Cuando Aqorath realice traducción contable/fiscal desconocida, debe poder explicarla antes de consolidarla.

**Consecuencia arquitectónica:**
- Modo "acompañado" (explica cada paso)
- Modo "operativo" (usuario experimentado omite explicaciones)
- Usuario experimentado puede pedir "Explícame esto" en cualquier momento
- Configuración respeta preferencia del usuario

---

### R13: PROGRESIVIDAD PEDAGÓGICA

**Regla:** El sistema puede registrar localmente qué conceptos ya han sido presentados para ajustar nivel de explicación.

**Consecuencia arquitectónica:**
- NO gamificación infantil
- Objetivo: usuario debe saber más de su actividad económica después de meses usando Aqorath
- Aprendizaje integrado y natural
- Transiciones documentadas en help/documentación

---

### R14: ARQUITECTURA FISCAL VERSIONADA

**Regla:** Las reglas fiscales mexicanas cambian. No deben mezclarse irreversiblemente con contabilidad universal.

**Consecuencia arquitectónica:**
- Reglas fiscales: versionadas (por fecha/decreto)
- Debe saberse qué conjunto de reglas aplicaba en período determinado
- Cambio fiscal NO exige reescribir núcleo contable
- FiscalRuleSet separable del modelo de entidad
- JournalEntry referencia FiscalRuleSet usado en su fecha

---

### R15: ENTIDAD ≠ "MODO COMERCIAL / OSC"

**Regla:** La identidad contable NO se reduce a comercial vs no-lucrativo. Debe poder describirse por componentes.

**Consecuencia arquitectónica:**
- Naturaleza económica/jurídica (componente A)
- Régimen fiscal (componente B)
- Características especiales (componente C)
- Capacidades/módulos aplicables (componente D)
- Una donataria autorizada NO es "otro motor contable"
- Es una entidad no lucrativa con características, reglas, controles y obligaciones adicionales
- Mismo catálogo, mismo motor, DIFERENTES nombres/reportes por perfil

---

### R16: OSC COMO CIUDADANO DE PRIMERA CLASE

**Regla:** Aqorath debe diseñarse genuinamente para OSC, NO como ERP comercial rebautizado.

**Consecuencia arquitectónica:**
- La arquitectura debe poder soportar progresivamente:
  - Programas, proyectos, fondos
  - Fuentes de recursos (donativas, propias, etc.)
  - Donantes, donativos, donativos en especie
  - Restricciones/destinos de recursos
  - Cuotas de miembros
  - Patrimonio
  - Aplicación de recursos
  - Gastos administrativos
  - Trazabilidad documental
  - Reportes propios de entidades no lucrativas
- NO es un módulo separable/opcional
- Está integrado desde el diseño

---

### R17: DIMENSIONES ANALÍTICAS SIN DUPLICAR CONTABILIDAD

**Regla:** Una misma operación puede tener dimensiones adicionales SIN generar contabilidades paralelas.

**Consecuencia arquitectónica:**
- Una línea contable = múltiples dimensiones (programa, fuente, etc.)
- NO múltiples asientos/cuentas ficticias
- Reportes pueden filtrar/agrupar por dimensión
- Validación: dimensiones no pueden quebrantar estructura contable

---

### R18: DOCUMENTOS COMO UNIDADES INDEPENDIENTES

**Regla:** Un documento/reporte es unidad generable con datos, parámetros, período, formato, reglas de disponibilidad, naturaleza de entidad aplicable.

**Consecuencia arquitectónica:**
- ReportDefinition: qué documento existe (invariante)
- ReportRequest: qué generar esta vez (parámetros concretos)
- Reporte es reutilizable, generable múltiples veces
- Formato (PDF/Excel/JSON) es parámetro, no parte de definición
- Disponibilidad condicional por EntityProfile/FiscalRuleSet

---

### R19: PAQUETES COMO PRESETS, NO COMO LÍMITES

**Regla:** Un paquete de documentos es SELECCIÓN INICIAL, NO contenedor cerrado.

**Consecuencia arquitectónica:**
```
PAQUETE ("Bancos")
  → INITIAL SELECTION (sugiere documentos)
  → PERSONALIZATION (usuario quita, agrega, cambia)
  → CUSTOM PACKAGE (usuario guarda selección)
  → GENERATION REQUEST (genera)
```
- Usuario puede comenzar en "Bancos" y añadir documentos de "Asamblea"
- No hay "paquetes bloqueados"

---

### R20: REUTILIZACIÓN DE INFORMACIÓN

**Regla:** Un dato capturado correctamente una vez debe reutilizarse en todos los lugares donde corresponda.

**Consecuencia arquitectónica:**
- Si Aqorath conoce al tercero/importe/CFDI, no los pide nuevamente
- Caché local de "datos recientes/comunes"
- UI debe autocompletar/sugerir basado en historial
- Nunca re-preguntar dato ya conocido

---

### R21: INTEROPERABILIDAD Y AUSENCIA DE LOCK-IN

**Regla:** Usuario debe poder extraer su información. Aqorath no debe impedir que usuario que creció migre hacia otros ERP.

**Consecuencia arquitectónica:**
- Exportar datos: suficientemente estructurados para revisión profesional
- Migración debe ser posible hacia otros sistemas
- "Graduación" de Aqorath puede ser resultado exitoso
- NO intentar retener usuario con lock-in
- Formatos abiertos (CSV, JSON, XML) con especificación documentada

---

### R22: SEGURIDAD E INTEGRIDAD LOCAL

**Regla:** Para un ERP de años de contabilidad, respaldo, restauración, migración e integridad son capacidades centrales.

**Consecuencia arquitectónica:**
- Migración de esquema NO depende de "adivinar columnas"
- NO rellenar silenciosamente campos desconocidos
- NO continuar ante inconsistencias estructurales
- Migración: versionada explícitamente
- Cada versión de schema tiene compatibilidad clara
- Validación de integridad referencial antes de operaciones destructivas
- Backups automáticos antes de cambios

---

### R23: SEPARACIÓN DE CAPAS

**Regla:** La arquitectura debe tender a separación clara:

```
PRESENTATION (UI/API/CLI)
    ↓
APPLICATION (Casos de uso / servicios)
    ↓
DOMAIN (Motor de negocio)
    ↓
INFRASTRUCTURE (Persistencia)
```

**Consecuencia arquitectónica:**
- UI/API/CLI NO contienen lógica contable
- Domain NO depende de PySide, FastAPI, SQLite directo, pandas, Excel, PDF
- Persistencia es intercambiable (SQLite ahora, otra en futuro)
- Inversión de dependencias (Infrastructure implementa Domain contracts)

---

### R24: UNA SOLA AUTORIDAD DE NEGOCIO

**Regla:** NO existen múltiples implementaciones de la misma regla dependiendo de dónde entró.

**Consecuencia arquitectónica:**
- Todas las superficies consumen MISMOS casos de uso/reglas
- Un asiento es un asiento, sin importar si entró por UI, API, importador
- Application layer es autoridad única
- Todas las capas de presentación son thin wrappers

---

### R25: NO FALLBACKS QUE OCULTEN ERRORES ESTRUCTURALES

**Regla:** Distinguir entre tolerancia razonable y "capturar Exception, adivinar, rellenar y continuar".

**Consecuencia arquitectónica:**
- Fallbacks permitidos SOLO para:
  - Migración de formato (old schema → new schema)
  - Falta de opcional import (templates no disponibles)
  - Opcionalidad de infraestructura (ORM vs sqlite)
- Fallbacks PROHIBIDOS para:
  - Validación fallida (rechaza explícitamente)
  - Estructura desconocida (aborta con diagnostico)
  - Inconsistencia detectada (no la "repara")
- Logging de TODA operación de fallback
- Usuario puede ver si estamos en "modo degradado"

---

### R26: CALIDAD DE NICHO

**Regla:** Aqorath NO necesita solucionar toda operación imaginable. Debe declarar qué soporta.

**Consecuencia arquitectónica:**
- Dentro de nicho: resultado correcto, experiencia excelente, explicación clara
- Fuera de nicho: Aqorath debe reconocer el límite
- NUNCA inventar solución contable/fiscal para continuar
- Documentación de límites en help/manual
- Rechazo explícito de operaciones fuera de nicho con motivo

---

### R27: PRUEBA TRIPLE DE ACEPTACIÓN

**Regla:** Una función NO está terminada solo porque el código funciona. Debe superar:

**A) PRUEBA TÉCNICA**
- Tests automatizados
- Invariantes mantenidos

**B) PRUEBA PROFESIONAL**
- Un contador puede revisar el resultado y considerarlo defendible

**C) PRUEBA HUMANA**
- Una persona sin conocimientos contables puede completar flujo ordinario
- Sin traducción externa necesaria

**Consecuencia arquitectónica:**
- Capacidad futura de probar todas las capas
- Integración continua debe rodar tests A+B
- Prueba C es manual pero debe poder repetirse

---

### R28: LICENCIA SOCIAL (DECISIÓN PENDIENTE)

**Regla:** Existe intención institucional de mantener Aqorath gratuito para beneficiarios.

**Consecuencia arquitectónica:**
- NO implementar restricciones de licencia aún
- NO seleccionar unilateralmente una licencia
- NO diseñar DRM
- Mantener opción abierta
- Registrar esta decisión como pendiente

---

## SÍNTESIS

Estas 28 reglas forman un **sistema coherente**. Toda decisión arquitectónica debe justificarse contra ellas.

