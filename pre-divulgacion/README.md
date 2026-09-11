# Aqorath — cierre de atribución previo a divulgación

> **Naturaleza de este documento:** recordatorio de cierre institucional. No forma parte de `INSTRUCCIONES.md`, no modifica la Constitución de Aqorath, no crea una tarea `AQR-###` y no altera el orden del backlog.
>
> **Momento de ejecución:** únicamente al final del desarrollo de V1 y **justo antes de la primera divulgación pública** del software, repositorio, release o documentación técnica asociada.

## Objetivo

Antes de hacer público Aqorath debe quedar preparada una referencia canónica que permita a terceros identificar, citar y atribuir correctamente el desarrollo a **Centro Multidisciplinario Meriadock Formación y Asesoría, A.C.** y a las personas autoras que corresponda.

La finalidad no es introducir una barrera de uso ni convertir Aqorath en un producto comercial. La finalidad es preservar autoría, prioridad documental y trazabilidad académica/institucional del desarrollo.

## Cierre mínimo antes de divulgación

Inmediatamente antes de la primera publicación pública deberán revisarse y, cuando proceda, completarse conjuntamente los siguientes elementos:

1. **Referencia canónica del software.** Definir título oficial, autores, titular o institución responsable, versión, año y forma recomendada de cita.
2. **`CITATION.cff`.** Incorporar en la raíz del repositorio un archivo de citación compatible con GitHub, con la referencia canónica de Aqorath y, si existe, una `preferred-citation` hacia la publicación técnica principal.
3. **DOI de la versión pública o de la publicación técnica.** Si la versión V1, un informe técnico o ambos se depositan en un repositorio que asigne DOI, incorporar ese identificador a la cita canónica y al `CITATION.cff`.
4. **Filiación institucional visible.** La documentación pública debe identificar inequívocamente que Aqorath fue desarrollado en el marco de Centro Multidisciplinario Meriadock Formación y Asesoría, A.C.
5. **Aviso de atribución y licencia.** Revisar que la licencia elegida y el README público sean coherentes con el objetivo de permitir el uso del software sin perder la atribución documental de su origen.
6. **Referencia histórica estable.** La primera versión divulgada debe conservar versión, fecha, commit o tag de referencia y documentación suficiente para que la prioridad del desarrollo pueda reconstruirse posteriormente.

## Criterio de salida

Aqorath no debería pasar de privado/no divulgado a divulgación pública hasta que exista una forma simple y visible de responder a estas preguntas:

- ¿Cómo se cita Aqorath?
- ¿Quién lo desarrolló?
- ¿Qué versión se está citando?
- ¿Dónde está la referencia persistente de esa versión o de su publicación técnica?
- ¿Qué institución debe recibir la atribución?

Este documento es deliberadamente independiente de las instrucciones de continuidad del proyecto. Durante el desarrollo ordinario puede permanecer sin cambios. Su contenido debe retomarse sólo como **último control previo a divulgación**.