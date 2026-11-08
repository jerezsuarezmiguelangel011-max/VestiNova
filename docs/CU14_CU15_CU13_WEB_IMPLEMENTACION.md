# Implementación WEB CU14 → CU15 → CU13

Rama: `trabajo/cu10-miguel`. No fusionada a `miguel`.
Fuente: apartado 2.6 del documento oficial VestiNova.
Alcance de esta iteración: Angular PWA + FastAPI + PostgreSQL. Flutter queda para después.

> Estado: **implementado en código, pendiente de ejecutar las pruebas de esta iteración y
> la aceptación visual**. No declarar los tres CU cerrados hasta validar
> migración, pruebas y operación en la base aislada.

## CU14 — Atender retiro de reservas

- Backend: `backend/app/compras_reservas/reservas/attention.py`.
- Frontend: `/admin/atencion-reservas`, exclusivo de Encargado/Cajero.
- Busca por código, cliente y sucursal autorizada; muestra detalles y vencimiento.
- Requiere identidad verificada y constancia de comprobación. Una reserva
  `PENDIENTE`, `VENCIDA`, `CANCELADA` o `ATENDIDA` no puede generar otra salida.
- Transacción única: `cantidad -= n`, `cantidad_comprometida -= n`,
  movimiento físico con UUID derivado de la reserva y variante, estado `ATENDIDA`,
  evento con responsable y bitácora.
- Repetición de entrega ya procesada devuelve el estado sin descontar dos veces.
- Cancelación: motivo obligatorio, liberación única de compromiso, mismo commit de auditoría.
- El backend sigue verificando empresa, sucursal y permiso, no depende del menú.

## CU15 — Registrar venta presencial de contado

- Backend: `backend/app/operacion_sin_conexion/caja/online.py`.
- Frontend: `/admin/caja`; `cash-sale-api.service.ts`,
  `cash-sale-offline-store.service.ts`, `cash-sale-sync.service.ts`.
- Consulta variantes, precios y promociones centrales por sucursal autorizada,
  guarda una copia mínima en IndexedDB asociada a `empresa_id + usuario_id + sucursal_id`.
- Permite incluir hasta 30 líneas distintas, cliente opcional y efectivo realmente recibido;
  calcula total y cambio en centavos enteros para evitar errores de redondeo en Angular.
- **El cajero confirma que recibió el efectivo antes de guardar**. La venta queda
  `PENDIENTE` con UUID, fecha y comprobante **PROVISIONAL** en IndexedDB.
- Si el servidor responde `CONFIRMADA`, la salida física, movimientos, comprobante
  central y bitácora se registran en una única transacción.
- El backend revalida precio promocional, permisos, empresa, cliente,
  sucursal, suscripción y saldo físico libre (descontando compromisos).
- UUID procesado con mismos datos devuelve el comprobante original; contenido diferente 409.
- Si no hay stock o difieren precios de una venta offline, NO se confirma ni
  descuenta stock; se persiste incidencia central de CU13 con evidencia del
  cobro capturado y se conserva copia local.
- No usa Stripe, ni afirma que un comprobante local sea venta confirmada.

## CU13 — Sincronización y conciliación

- Reservas CU10 conservan su cola IndexedDB y el mismo UUID; stock insuficiente
  durante su sincronización genera también una incidencia central de tipo RESERVA.
- Caja CU15 usa su cola IndexedDB con estados `PENDIENTE`, `ENVIANDO`,
  `CONFIRMADA`, `CONFLICTO`, `RECHAZADA`, `ERROR` y `REQUIERE_ACCESO`.
- Al perder respuesta, conserva UUID. Al volver la conexión intenta sincronizar
  sin duplicar la operación. Cada resultado se guarda individualmente.
- Bandeja de Encargado: `/admin/conciliacion`; backend
  `backend/app/operacion_sin_conexion/sincronizacion/reconciliation.py`.
- Los conflictos centrales se filtran por empresa y sucursal autorizada.
- Solo Encargado autorizado documenta decisión, referencia y observación.
  Resolución idempotente si se reenvía el mismo contenido. Una decisión distinta
  posteriormente recibe 409.
- La resolución documenta una devolución/entrega alternativa/acta **ya comprobada**.
  No devuelve dinero ni modifica stock automáticamente, ni borra el registro original.

## Migraciones

La migración `c15a4d1f2026_caja_conflictos.py` parte de
`c10a4d1f2026` y crea:

- `ventas_contado_cu15`: comprobantes e importes efectivos centrales.
- `conflictos_cu13`: operación original, motivo, identidad,
  sucursal, responsable y decisión documentada.

La migración posterior `c15b4d1f2026_caja_redondeo_centavos.py`
corrige la restricción de validación de cambio para usar `ROUND(..., 2)`.
Así se evita que SQLite rechace importes válidos como 200,00 − 160,20 = 39,80
por representación binaria. Se conserva la validación estricta de centavos
en PostgreSQL sin eliminar ni reiniciar registros de ventas.

La migración usa downgrade protector porque eliminar estas tablas perdería
evidencia comercial. CU14 reutiliza la reserva CU10 y los movimientos existentes.

**Aplicar únicamente sobre `vestinova_pruebas`**:

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git pull --ff-only origin trabajo/cu10-miguel

cd backend
.\.venv\Scripts\python.exe -m scripts.migrate_demo
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cu10_reservas_online.py tests/test_cu14_cu15_cu13_web.py tests/test_stripe_checkout_request.py

cd ..\frontend
npm.cmd run build
npm.cmd test
```

## Pruebas manuales después de los tests automatizados

1. **CU10:** como cliente Moda Andina registra reserva de 2 unidades de una variante.
2. **CU14:** como Cajero de esa empresa abre `/admin/atencion-reservas`,
   busca código, verifica identidad y entrega. Comprueba `ATENDIDA`,
   inventario físico disminuido 2, comprometido disminuido 2 y movimiento único.
3. **CU14 negativo:** reenvía entrega y comprueba que no descuenta dos veces;
   intenta entregar reserva vencida/cancelada y debe rechazarse.
4. **CU15:** como Cajero abre `/admin/caja`, selecciona sucursal,
   descarga catálogo, añade dos prendas, calcula total, cobra el efectivo
   y registra. El comprobante local aparece PROVISIONAL antes de confirmarse;
   el servidor devuelve un código `VN-C-` cuando hay stock.
5. **CU15 offline:** tras preparar catálogo, DevTools > Network > Offline,
   registra una venta de contado y marca entrega física si corresponde.
   La venta queda en IndexedDB y no se descuenta centralmente.
6. **CU13:** restablece red, pulsa sincronizar. Si hay stock/precio vigente,
   confirma; si no, conserva comprobante e incidencia de conflicto.
7. **CU13 conciliación:** como Encargado abre `/admin/conciliacion`,
   revisa la incidencia, consulta la evidencia y registra una decisión
   solo después de contar con constancia real.
8. **Multitenant:** cambia empresa/cuenta/sucursal; ninguna acción de caja,
   atención ni conciliación debe consultar registros ajenos.
9. **PWA instalada:** confirmar persistencia en IndexedDB después de recarga;
   `ng serve` solo no valida Service Worker de producción.
10. **PostgreSQL real:** verificar bloqueos concurrentes sobre última unidad
    para reserva, venta y entrega desde dos sesiones simultáneas.

## Pendientes y límites declarados

- Falta ejecutar pruebas nuevas en el entorno del usuario; no confundir creación
  de tests con su resultado.
- Se recomienda probar concurrencia real en PostgreSQL; SQLite de pruebas
  no reproduce todos los bloqueos `SELECT FOR UPDATE`.
- Una reapertura totalmente offline de `/admin/caja` tras perder una sesión
  web exige estrategia adicional de autorización local previamente validada.
  El almacenamiento IndexedDB ya persiste, pero el guard actual de la app
  intenta validar sesión en línea al abrir un navegador nuevo.
- Las copias de caja incluyen hasta 300 variantes de la sucursal; para catálogos
  mayores se requiere descarga paginada.
- El manejo de precios mayoristas no tiene una regla tarifaria configurable
  implementada en CU15; se validan precio base y promociones activas.
- La conciliación documenta acuerdos reales y no ejecuta automáticamente
  la devolución de efectivo ni el cambio físico de mercancía.
- CU13 mobile Flutter/SQLite sigue pendiente por acuerdo expreso del usuario.
- Los cambios quedan solo en `trabajo/cu10-miguel`; no modificar `miguel`
  hasta probarlos y obtener aprobación.
