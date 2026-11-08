# Bloque 3 móvil – CU15 Caja presencial / CU13 Conflictos offline (ICONIX)

## Alcance
Este bloque amplía Flutter sin duplicar la validación transaccional de FastAPI.
Los flujos centrales de caja/conciliación ya existían en el backend; el trabajo nuevo añade
pantallas móviles, cache local SQLite, sincronización e identidad de personal previamente
verificada mediante almacenamiento seguro.

### CU15 – Registrar venta en caja
**Actor:** Cajero o Encargado de sucursal, autenticado y con empresa y sucursal autorizadas.

**Interfaz (boundary):** `StaffCashSalePage` (Cuenta → CU15 · Registrar ventas en caja).

**Controladores/servicios:** `StaffCashApi`, `StaffCashSync`, `StaffCashStore` (SQLite).
**Backend:** `GET /api/admin/caja/catalogo?sucursal_id=...`;
`POST /api/admin/caja/ventas`; `GET /api/admin/caja/ventas`.
**Entidades:** `CashInput`, `CashSale`, `Existencia`, `MovimientoInventario`.

Flujo:
1. Selecciona una sucursal **de su contexto autorizado**, descarga un catálogo local
   de variantes y precios y agrega hasta 30 variantes a la venta (máximo 100 unidades por variante).
2. Ingresa el efectivo recibido y confirma un importe mayor o igual al total.
   El cálculo del cambio utiliza **centavos enteros**, no `double`.
3. En línea: crea UUID local, persiste la operación y sincroniza con la API.
   El servidor verifica plan, rol, sucursal, variante, precio vigente, existencias y efectivo,
   registra movimientos de stock y comprobante de forma atómica.
4. Sin red: confirma manualmente que **se recibió realmente el efectivo** y, de corresponder,
   si hubo entrega local; conserva la solicitud SQLite como `PENDIENTE`.
   **No** produce comprobante oficial ni modifica inventario central.
5. Al recuperar conectividad se pulsa *Sincronizar pendientes* o la app lo intenta
   al pasar a primer plano. Se reenvía **el mismo UUID y efectivo**, jamás se genera
   otro ID en el reintento. `CONFIRMADA` contiene comprobante central.
6. Conflicto de stock o precio: se marca `CONFLICTO` y se conserva
   `incidencia_id`; no se reenvía automáticamente un estado final.

No se guardan credenciales JWT, datos bancarios ni números de tarjeta en SQLite.
La sesión de personal verificada se almacena en el almacén seguro del sistema;
si se reabre sin conexión, únicamente habilita **captura local**, nunca autorización
ni cambios centrales. El backend vuelve a validar permisos al sincronizar.

### CU13 – Conciliar conflictos de sincronización
**Actor:** exclusivamente **Encargado de sucursal**.
El Cajero puede observar el conflicto generado en su cola CU15, pero no resolverlo.

**Interfaz (boundary):** `ReconciliationPage` (Cuenta → CU13 · Conciliar conflictos offline).

**Servicio:** `StaffCashApi`. **Backend:** `GET /api/admin/conciliacion`,
`GET /api/admin/conciliacion/{id}`, `POST /api/admin/conciliacion/{id}/resolver`.
**Entidades:** `SyncIncident` y constancia de conciliación en la entidad de incidente.

Flujo:
1. Selecciona una sucursal autorizada y filtra `CONFLICTO`, `RESUELTO` o todos.
2. Examina motivo, UUID original, tipo de operación y datos originales inmutables.
3. Documenta una de tres decisiones:
   `ACUERDO_DOCUMENTADO`, `DEVOLUCION_DOCUMENTADA` o
   `ENTREGA_ALTERNATIVA_DOCUMENTADA`.
4. Aporta una **referencia a constancia existente** y observación suficiente.
5. El servidor revisa rol, empresa, sucursal, rango de campos, duplicados y
   guarda responsable, decisión y auditoría.
6. Un conflicto resuelto no puede recibir una decisión distinta.

La decisión documentada **no ejecuta una devolución económica, no entrega
la mercancía y no altera stock** por sí sola. Estas acciones deben materializarse
en los procesos autorizados y documentarse con evidencia real.

### Pantallas y archivos para diagramas ICONIX
- `mobile/lib/screens/account_page.dart`: entrada y control de visibilidad según rol.
- `mobile/lib/staff/cash_sale_page.dart`: boundary CU15.
- `mobile/lib/staff/cash_models.dart`: modelo local, centavos.
- `mobile/lib/staff/cash_store.dart`: almacenamiento local e identidad de cada operación.
- `mobile/lib/staff/cash_sync.dart`: control de sincronización CU13/CU15.
- `mobile/lib/staff/cash_api.dart`: cliente REST compartido.
- `mobile/lib/staff/reconciliation_page.dart`: boundary CU13.
- `backend/app/operacion_sin_conexion/caja/online.py`: reglas transaccionales.
- `backend/app/operacion_sin_conexion/sincronizacion/reconciliation.py`: resolución.

### Pruebas
- Flutter: `mobile/test/staff_cash_test.dart` (importe, contexto tenant, conflicto,
  mismo UUID ante pérdida de conexión, resolución) y
  `mobile/test/session_controller_test.dart` (restauración de sesión offline).
- Backend: `backend/tests/test_cu14_cu15_cu13_web.py`,
  `backend/tests/test_sync_conflicts_domain.py`.
- CI: `.github/workflows/mobile-bloque3-validation.yml` ejecuta tests/análisis,
  validación backend y compila `VestiNova-Redmi-Bloque3` para pruebas en Redmi
  contra `http://192.168.0.9:8001/api`.
- **Pendiente:** validar en dispositivo con `vestinova_pruebas`, conexión real a la
  LAN, permisos correctos, stock mutable y conflicto generado de manera controlada.
- El APK de GitHub se instala como app de prueba separada y no incorpora el
  `google-services.json` del usuario; no demuestra push real FCM de CU26.

**No integrar en `miguel` ni en `salet` hasta la revisión funcional y el commit
local de Miguel.**
