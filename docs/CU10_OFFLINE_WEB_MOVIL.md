# CU10 — Reservas de prendas con y sin conexión

**Rama:** `trabajo/cu10-miguel` (no fusionar todavía con `miguel`).
**Fuente de verdad:** tabla 2.6 CU10 de VestiNova - Segundo Parcial y desafíos II/III del enunciado de la ingeniera.

## Alcance implementado en la rama temporal

| Requisito | Código |
|---|---|
| Alta, consulta, cancelación y vencimiento real | `backend/app/compras_reservas/reservas/online.py` |
| Stock comprometido sin disminuir cantidad física | `_balances`, `_create`, `_release`, `expire_due` |
| Reintento idempotente por UUID | `_fingerprint` y comprobación de `ReservationRecord.id` |
| Registro de origen y fecha local | campos opcionales `origen` y `solicitado_en`, guardados en `eventos` |
| Política pública de vencimiento | `GET /api/tiendas/{slug}/reservas/politica` |
| Web PWA: registro y consulta de solicitudes offline | `reservation-offline-store.service.ts` (IndexedDB) |
| Web PWA: sincronización posterior | `reservation-offline-sync.service.ts` |
| Web PWA: consulta de variantes conocidas | copia de producto, disponibilidad y política en IndexedDB |
| Flutter Android: registro persistente | `reservation_sqlite.dart` (SQLite) |
| Flutter Android: catálogo conocido | `reservation_mobile_service.dart`, hasta 20 productos por descarga |
| Flutter Android: bandeja y sincronización | `customer_reservations_page.dart` |
| Flutter Android: reapertura sin Internet | copia de identidad anteriormente validada en almacén seguro |
| Seguridad multitenant | tienda, cliente y sucursal comprobados por API y colas locales |

## Modelo comercial

- **BORRADOR_LOCAL:** el usuario todavía no tiene identidad de cliente comprobada en esa tienda; se guarda persistentemente y se asocia cuando vuelva a identificarse.
- **PENDIENTE:** petición local con UUID. No bloquea ni descuenta inventario central.
- **ENVIANDO:** intento de sincronización. Si se interrumpe, se vuelve a PENDIENTE con el mismo UUID.
- **CONFIRMADA:** solo tras respuesta verificable de FastAPI; entonces PostgreSQL ha comprometido el stock.
- **CONFLICTO:** el servidor reportó 409. Conserva la operación y requiere revisar stock/UUID; no se reintenta alterando el registro.
- **RECHAZADA:** datos o referencias no válidos; registro local conservado.
- **ERROR:** respuesta incierta, red perdida, 5xx; reintentar con UUID intacto.
- **REQUIERE_ACCESO:** sesión inválida o insuficiente; reautenticarse antes de reintentar.

Los datos locales nunca representan una confirmación ni un cobro. Stripe pertenece exclusivamente al flujo digital online CU09. Las ventas de contado offline, sus comprobantes y conciliación corresponden a CU15 y CU13, no a CU10.

## Pruebas en Windows

Antes de probar, verificar que tu Git actual no tenga cambios sin guardar y que estás en la rama correcta:

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git fetch origin
git switch trabajo/cu10-miguel
git pull --ff-only origin trabajo/cu10-miguel
```

### Backend (pruebas SQLite en memoria)

```powershell
cd D:\Proyectos\vestinova-mvp\backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cu10_reservas_online.py tests/test_stripe_checkout_request.py
```

La tabla `reservas_cu10` ya se generó mediante `scripts.migrate_demo` cuando se probó el CU10 online. Estos nuevos cambios no añaden columnas ni requieren otra migración. Seguir usando `vestinova_pruebas` para la integración y NO `vestinova_mvp`.

### Angular

```powershell
cd D:\Proyectos\vestinova-mvp\frontend
npm.cmd run build
npm.cmd test
npm.cmd run preview:pwa -- --port 4301
```

Comprobar que se ejecuta `reservation-offline-store.service.spec.ts`.

### Flutter Android

```powershell
cd D:\Proyectos\vestinova-mvp\mobile
flutter pub get
flutter analyze
flutter test
```

`flutter pub get` actualizará `mobile/pubspec.lock`; este cambio debe quedar en el commit final del usuario. Flutter debe probarse en un emulador Android o dispositivo físico porque `sqflite` usa plugins nativos y la API demo necesita ser accesible.

## Recorrido de aceptación web (PWA)

1. Con backend/Angular disponibles, iniciar sesión como cliente de Moda Andina.
2. Abrir Jean recto / variante L Azul y pulsar Preparar reserva. La consulta descarga el producto, stock referencial y plazo a IndexedDB.
3. En DevTools > Network activar Offline (sin desconectar los demás servicios de tu computadora).
4. Volver a la pantalla de reserva y comprobar que aparece la copia local. Crear una solicitud: debe indicar PENDIENTE y UUID, no CONFIRMADA.
5. Actualizar la página y comprobar que el registro sigue en la cola. Para comprobar recarga completamente offline con Service Worker, abrir la compilación de producción desde `http://127.0.0.1:4301` con `npm.cmd run preview:pwa -- --port 4301`, visitarla online primero y después activar Offline; `ng serve` de desarrollo no demuestra ese comportamiento.
6. Desactivar Offline y pulsar Sincronizar pendientes. El servidor responde CONFIRMADA con código y vencimiento, o CONFLICTO/RECHAZADA.
7. Sin modificar el UUID, reintentar el mismo request y comprobar que solo existe una reserva central y un compromiso.
8. Agotar previamente el stock central para un segundo escenario y comprobar conflicto sin stock negativo. Usar únicamente `vestinova_pruebas`.
9. Cerrar y abrir navegador y comprobar persistencia. Cambiar de cliente/empresa y verificar que no aparecen pendientes ajenos.
10. Cancelar una reserva confirmada y verificar que la cantidad física no disminuye; solo se libera `cantidad_comprometida`.

Nota: el API público guarda snapshots por prenda visitada; para usar una prenda offline hay que haberla consultado en línea anteriormente.

## Recorrido de aceptación móvil

1. Ejecutar la app con la API demo accesible, iniciar sesión en Moda Andina.
2. En Cuenta, abrir Reservas; pulsar Descargar catálogo (subconjunto inicial de hasta 20 productos).
3. Guardar una solicitud con Internet desconectado. Debe persistir en SQLite con PENDIENTE y UUID.
4. Forzar cierre y reabrir la app sin conexión; la cuenta se restaura como identidad local anteriormente validada, sin afirmar que el servidor la aceptó.
5. Reconectar y sincronizar; comprobar confirmación, rechazo o conflicto, con registro retenido.
6. Repetir la sincronización para verificar idempotencia; probar otra empresa para comprobar separación de datos.

## No aprobado todavía / dependencias

- Falta evidencia de ejecución de tests nuevos, build web y `flutter analyze` en el entorno del usuario.
- Requiere prueba con PostgreSQL real, especialmente concurrencia de dos dispositivos.
- Los conflictos definitivos se conservan; su **conciliación comercial autorizada** es CU13.
- La atención y entrega física de una reserva es CU14.
- El módulo móvil CU10 aquí implementa la experiencia del **cliente**; queda ampliar y probar la modalidad de personal en Flutter si se exige por rol.
- En web, después de cerrar una sesión de navegador, el acceso a colas vinculadas al cliente requiere volver a autenticarse para no mostrar datos a terceros. Los registros SQLite e IndexedDB permanecen intactos.
- La PWA de producción debe instalarse y verificarse por separado (Service Worker no queda comprobado por `ng serve`).

## Integración de autoría

No modificar `miguel` ni hacer push a ella sin aprobación. Tras resultados verdes y aceptación, el usuario realizará `git merge --squash trabajo/cu10-miguel`, seguido de `git commit` y `git push` sobre `miguel`, conservando su autoría.
