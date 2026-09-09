# Aqorath V1 — superficie local AQR-005

La superficie de AQR-005 es una aplicación local servida exclusivamente en loopback. No necesita Internet y no convierte Aqorath en un servicio multiusuario.

## Arranque de desarrollo

Con la base local ya inicializada y sus bindings configurados:

```bash
python -m aqorath.local_server
```

El launcher usa `127.0.0.1:8765`. El host no es configurable; sólo puede cambiarse el puerto mediante `run_local_surface(port=...)` desde Python.

Abrir en el navegador local:

```text
http://127.0.0.1:8765/
```

El empaquetado/launcher de distribución final pertenece a AQR-015.

## Vista común

La vista común enumera únicamente los hechos que el runtime soporta actualmente mediante `EconomicFact`:

- venta cobrada en efectivo;
- venta a crédito;
- pago de servicios desde banco;
- servicio recibido a crédito;
- cobro a cliente en banco;
- pago a proveedor desde banco.

El usuario proporciona operación, importe y fecha. No captura cuentas, códigos, Debe/Haber, período interno ni SQL. `Revisar antes de contabilizar` prepara una `AccountingDecision`; `Cancelar` descarta sólo el preview; `Confirmar y contabilizar` confirma exactamente ese snapshot y ejecuta AQR-004.

## Vista profesional

La vista profesional puede abrir una póliza por su identidad persistida y presenta:

- estado y concepto;
- fecha y período/ejercicio;
- cuentas con cargos y abonos;
- documentos vinculados;
- relación de reversión, si existe;
- `AuditEvent` general, si existe;
- auditoría fiscalizada, si existe;
- balanza obtenida de la autoridad contable existente.

No existe una segunda base ni una copia profesional del asiento: la vista lee la misma `JournalEntry` y sus autoridades asociadas.

## Límites vigentes

AQR-005 no declara implementadas capacidades que el backlog mantiene en AQR-006 y posteriores. La UI no debe simular partidas abiertas, conciliación bancaria, fondos OSC, CFDI XML, inventario u otras capacidades hasta que sus casos de uso canónicos existan.

Los archivos históricos de raíz `templates/` y `static/` no son utilizados por esta superficie.