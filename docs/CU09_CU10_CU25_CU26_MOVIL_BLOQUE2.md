# VestiNova – Bloque 2 móvil (CU09, CU10, CU25, CU26)

Rama: \`trabajo/movil-bloque2\`. Base: merge de CU08/CU19/CU23/CU24 en \`miguel\` (\`ca76635\`).

## Estado / limitaciones

- **CU09**: Flutter ofrece compra inmediata Stripe Checkout **TEST**, preparación online de tarjeta para cargos futuros mediante Checkout Setup y cola de solicitudes offline SQLite por empresa/Cliente, con UUID persistente. La solicitud offline **no paga, reserva ni descuenta stock**. Al volver a primer plano se intenta sincronizar; también hay botón manual. El servidor verifica tarjeta autorizada, importe aceptado, sesión, empresa, sucursal, stock y precio antes de llamar a Stripe; un pago requiere verificación del servidor. Rechazos o cambios de precio dejan la solicitud sin confirmar. Un cobro confirmado sin venta por cambio de stock deja incidencia para compensación. Un cobro que requiere autenticación adicional no se declara confirmado.
- **CU10**: conserva la cola de reservas offline y los datos SQLite existentes; incorpora consulta de reservas centrales, cancelación de confirmadas y registro de conflictos para origen MOVIL_OFFLINE.
- **CU25**: consulta compras entregadas y valoraciones; permite publicar y editar solo compras confirmadas y **ENTREGADAS** por el servidor. El cliente no puede autoconfirmar una entrega.
- **CU26**: catálogo permite solicitar avisos sobre variante y sucursal verificadas como **AGOTADA**; consulta/cancela suscripciones; añade canal de notificaciones Android por FCM sin modificar Web Push de Angular. **FCM necesita proyecto Firebase y credenciales del servidor antes de funcionar realmente.** Si faltan, Flutter explica la limitación y deshabilita registrar nuevas alertas.

No se han incluido números de tarjeta, CVV, claves Stripe secretas ni archivos Firebase de servicio.

## Actualización segura en Windows

Desde la raíz del repositorio (guardar antes los cambios locales):

\`\`\`powershell
git fetch origin
git switch trabajo/movil-bloque2
git pull --ff-only origin trabajo/movil-bloque2
\`\`\`

Instalar dependencias del backend y migrar exclusivamente la **base demo**:

\`\`\`powershell
cd D:\Proyectos\vestinova-mvp\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.upgrade_demo_mobile
.\.venv\Scripts\python.exe -m pytest tests/test_cu09_mobile_deferred_contract.py tests/test_cu10_reservas_online.py tests/test_cu25_valoraciones.py tests/test_cu26_alertas_push.py -q
\`\`\`

La migración se valida mediante \`scripts.demo_environment.use_demo_database\` antes de ejecutarse y debe apuntar a \`vestinova_pruebas\`. NO ejecutar \`alembic upgrade head\` sobre el entorno operativo sin respaldo y revisión. Para acceso desde Redmi por Wi-Fi, arrancar el backend de demostración en la dirección LAN (red privada y firewall sin puertos públicos):

\`\`\`powershell
.\.venv\Scripts\python.exe -c "from scripts.demo_environment import use_demo_database; use_demo_database(); import uvicorn; uvicorn.run('app.main:create_app',factory=True,host='0.0.0.0',port=8001)"
\`\`\`

En otro PowerShell:

\`\`\`powershell
cd D:\Proyectos\vestinova-mvp\mobile
flutter pub get
dart format lib/commerce lib/storefront lib/reservations
flutter analyze
flutter test
flutter devices
flutter run --dart-define="API_BASE_URL=http://IP_DE_TU_PC:8001/api"
\`\`\`

\`IP_DE_TU_PC\` es la IPv4 de la computadora en la misma red que el Redmi, no la IP del teléfono. Instalar con el dispositivo seleccionado por Flutter.

## Prueba CU09 – conexión y compra diferida

1. Inicia sesión como Cliente de \`demo-moda-andina\`; abre una prenda, elige talla/color y pulsa **Comprar · CU09**.
2. Con Internet y Stripe TEST configurado (\`sk_test_...\` y firma \`whsec_...\` en la configuración privada), pulsa **Preparar tarjeta con Stripe TEST**. Stripe muestra su página segura; autoriza una tarjeta de **prueba**, vuelve a VestiNova y pulsa **Verificar tarjeta autorizada**. No se usa una tarjeta real.
3. Con Internet, pulsa **Pagar online con Stripe TEST**, completa el pago en Checkout y vuelve a **Verificar pago y comprobante**. Nunca deducir el resultado de la redirección.
4. Para diferir: selecciona cantidad y sucursal, marca la casilla de **autorización expresa para cobro posterior** y pulsa **Guardar solicitud pendiente (SQLite)** con el teléfono sin Internet. No se genera compra ni descuento de inventario.
5. Recupera Internet, vuelve a VestiNova y pulsa **Sincronizar solicitudes pendientes** si no se hizo al reanudar. El servidor revalida todo y usa un UUID e idempotency key estables. Solo **CONFIRMADA** significa compra central. Para evitar doble cobro, jamás borrar la cola manualmente ni generar otro UUID para reintentar la misma solicitud.
6. Modifica el stock en la base demo antes de sincronizar otra solicitud: debe quedar en **CONFLICTO/RECHAZADA** sin cobro. Un precio distinto tampoco debe cargarse sin nueva autorización.

El flujo anterior demuestra una compra diferida; no representa que Stripe cobre sin red ni que la tarjeta esté guardada en SQLite. **Autenticación adicional del emisor, fallos de Stripe y compensaciones** requieren verificar el estado oficial y pueden necesitar intervención; no se garantiza un cargo automático exitoso.

## Prueba CU10 – reservas offline

1. En **Cuenta**, inicia sesión como Cliente y busca **Reservas de prendas · CU10**.
2. Con Internet pulsa **Descargar catálogo para reservas offline**. Este caché es separado del catálogo general CU08.
3. Desactiva Wi-Fi y datos móviles. Selecciona prenda, sucursal y cantidad; pulsa **Guardar reserva local pendiente**.
4. Reinicia la app y comprueba que el registro y el UUID siguen allí, sin stock comprometido.
5. Restaura conexión y pulsa **Sincronizar con servidor**. Verifica código central, estado y vencimiento; consulta **Reservas confirmadas en el servidor**. Un fallo de stock debe quedar en conflicto, no confirmado.
6. Prueba cancelar una reserva **CONFIRMADA**. El servidor debe liberar el compromiso una sola vez.

## Prueba CU25 – valoración

Desde el menú de VestiNova (arriba) → **Mis compras y valoraciones**. Una compra Stripe confirmada **no** sirve hasta que personal autorizado haya registrado su entrega desde la web CU25. Selecciona una prenda de una compra \`ENTREGADA\`, publica una puntuación de 1–5 y comentario opcional; vuelve a seleccionar esa compra para editarla. No debe permitirse una valoración duplicada o ajena.

## Prueba CU26 – alertas Android

La API web existente usa Web Push VAPID. La aplicación Flutter usa FCM (tokens de dispositivo); **no** se inventan endpoints Web Push desde Android.

Para recibir notificaciones push reales:

1. Registrar la aplicación Android en un proyecto Firebase; ejecutar \`flutterfire configure\` para configurar el proyecto Android según la documentación oficial de Firebase. Se requiere un teléfono con Google Play Services compatible.
2. Guardar el JSON de **cuenta de servicio** en la PC/backend, fuera del repositorio, y definir \`FIREBASE_SERVICE_ACCOUNT_FILE\` como la ruta absoluta **solo del servidor** (en \`backend/.env\` o en una variable de entorno). No subir el JSON a Git.
3. Compilar Flutter con \`--dart-define\` de identificadores **públicos** obtenidos de Firebase: \`FIREBASE_ANDROID_APP_ID\`, \`FIREBASE_API_KEY\`, \`FIREBASE_SENDER_ID\`, \`FIREBASE_PROJECT_ID\`. No son credenciales de servicio.
4. Entrar como Cliente, abrir detalle de una **variante AGOTADA**, pulsar **Avisarme si hay reposición · CU26** y conceder permisos Android. La app registra el token FCM de ese Cliente/tienda y permite suscribirse a la sucursal agotada.
5. Registrar por vías autorizadas una reposición real en inventario; el backend genera aviso por evento, comprueba el stock central y envía FCM si la configuración es válida. Verificar recepción real en Android. Cancelar suscripción y repetir una reposición: no debe enviar para una alerta cancelada.

Sin configurar Firebase, **CU26 no está validado como push real**. Las suscripciones Web Push existentes de Angular se mantienen intactas.

## Notas para el informe ICONIX

La ficha CU09 oficial exige Internet y solo contempla desconexiones durante un pago iniciado. Para representar el nuevo flujo propuesto, actualizar el apartado 2.6 con: autorización previa del método Stripe para uso \`off_session\`, consentimiento expreso por pedido, solicitud SQLite sin compra/reserva/cobro, validación posterior de precio y stock, idempotencia, 3DS/autenticación requerida, rechazo por stock y compensación de un pago acreditado sin confirmación comercial. **No llamar a una solicitud local “pagada” ni “reservada”**.

## Estado de calidad

Código y pruebas de contrato añadidos; compilación Android, migración demo, pruebas integrales de Stripe y entrega real FCM **todavía pendientes de ejecutar en el equipo del usuario**. No realizar merge a \`miguel\` hasta que él apruebe las pruebas del Bloque 2.
