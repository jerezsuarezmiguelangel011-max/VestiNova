# VestiNova – prueba de notificaciones CU09 y push CU26 en Android

Esta guía utiliza únicamente **Stripe TEST** y la base local de demostración
`vestinova_pruebas`. No ejecutar estos ejercicios sobre `vestinova_mvp`.

## 1. Tipos de notificación

- **CU09 local**: al guardar una solicitud en SQLite (sin Internet), el Redmi
  muestra **Solicitud guardada**. No significa que la prenda esté reservada ni
  que se haya pagado.
- **CU09 local**: cuando el servidor confirma `CONFIRMADA`, muestra **Compra
  confirmada** y mantiene entrega pendiente.
- **CU09 local**: un conflicto por falta de stock/precio puede producir
  `CONFLICTO` o `RECHAZADA`, con mensaje **No se confirmó tu compra**.
  **INCIDENCIA** indica posible pago sin venta confirmada: requiere revisión,
  no generar otro UUID ni repetir el cargo.
- **CU26 FCM**: reposición confirmada en inventario, enviada desde el servidor
  a un token Android asociado a una alerta activa. Necesita un proyecto Firebase.

Los avisos locales CU09 no necesitan Firebase. Necesitan conceder permiso a
Android (en Redmi: Ajustes → Aplicaciones → VestiNova → Notificaciones).

## 2. Flujo de compra sin Internet

1. Con el backend demo en `8001` y Stripe TEST, entrar en el Redmi a
   `demo-moda-andina` como **Cliente**, abrir una variante y elegir sucursal.
2. Con Internet, pulsar **Preparar tarjeta con Stripe TEST** y verificar la
   autorización para cobros futuros. No utilizar una tarjeta bancaria real.
3. Apagar Wi-Fi y datos móviles.
4. Autorizar expresamente el importe de esa solicitud y pulsar **Guardar
   solicitud pendiente (SQLite)**.
5. Android solicitará permiso para notificaciones si aún no se ha concedido.
   Debe aparecer el aviso **Solicitud guardada**.
6. Verificar `PENDIENTE`. Desconectar, cerrar o bloquear el teléfono **no**
   crea compra ni compromiso de stock.

## 3. Prueba de conflicto por stock, exclusivamente en DEMO

1. Antes de desconectar, consultar el detalle de la variante para identificar
   la **misma sucursal** que utilizará el pedido; anotar talla y color.
2. Guardar la solicitud en el Redmi **sin Internet** como arriba.
3. Mientras el Redmi sigue desconectado, desde Angular administrativo conectado
   a **`vestinova_pruebas`**, usar el módulo autorizado de inventario para
   registrar una salida de unidades disponibles de **esa misma variante y
   sucursal** hasta dejar el stock neto en cero. Alternativa más realista: hacer
   que otro cliente compre el último saldo **en Stripe TEST**, respetando los
   flujos normales de VestiNova.
4. Comprobar que el API público de disponibilidad refleja que no hay
   disponibilidad para esa combinación de sucursal/variante. Evitar ajustes
   manuales de SQL sobre `cantidad_comprometida`, porque falsean reservas.
5. Activar Internet del Redmi, mantener VestiNova abierta y observar el
   procesamiento automático; si Android lo retrasa, pulsar **Sincronizar
   solicitudes pendientes**.
6. El servidor debe rechazar con `CONFLICTO` o `RECHAZADA`, **sin nueva
   compra confirmada y sin efectuar un cargo nuevo** cuando detecta stock
   insuficiente antes de cobrar. Android muestra aviso local. Revisar el UUID
   y el mensaje exacto; una incidencia de cobro exige conciliación.
7. Restaurar el inventario demo mediante un movimiento administrativo normal
   si se requiere repetir la demostración.

El script/backend del repositorio no tiene acceso automático al PostgreSQL
local del usuario; el cambio de stock requiere ejecución en su propia PC.

## 4. Sincronización automática y límites reales

- **App abierta**: escucha cambios de conectividad y, al volver del navegador,
  reposar la app o reabrirla, intenta sincronizar.
- **App en segundo plano**: registra una tarea Android WorkManager, limitada
  por conectividad y las políticas de ejecución/batería del sistema.
- **No se promete inmediatez** con app cerrada: Android y MIUI pueden diferir
  ejecución. El botón manual queda disponible.
- Cada operación conserva su UUID. Stripe recibe una clave de idempotencia
  derivada de ese UUID para reducir duplicados.
- Las operaciones locales no contienen CVV, números de tarjeta ni JWT.
- El aviso local solo aparece si Android ha concedido permisos.

## 5. Configurar Firebase Cloud Messaging para CU26

En la **consola Firebase**, crear/seleccionar un proyecto y registrar la
aplicación Android con el ID **`com.vestinova.vestinova_mobile`**. Seguir
`flutterfire configure` desde `D:\Proyectos\vestinova-mvp\mobile` (seleccionar
Android y el proyecto correcto). La configuración pública de Firebase debe
corresponder a ese mismo proyecto.

En el proyecto Firebase, consultar los siguientes **identificadores públicos**:
`apiKey`, `appId` de Android, `messagingSenderId` y `projectId`.
La implementación actual Flutter los recibe en la compilación mediante:

```powershell
flutter run --dart-define="API_BASE_URL=http://192.168.0.9:8001/api" `
  --dart-define="FIREBASE_ANDROID_APP_ID=VALOR_PUBLICO_APP_ID" `
  --dart-define="FIREBASE_API_KEY=VALOR_PUBLICO_API_KEY" `
  --dart-define="FIREBASE_SENDER_ID=VALOR_PUBLICO_SENDER_ID" `
  --dart-define="FIREBASE_PROJECT_ID=VALOR_PUBLICO_PROJECT_ID"
```

Para enviar push real, descargar la clave privada de **cuenta de servicio**
Firebase mediante la consola y **guardarla fuera del repositorio**, solamente
en la PC del backend. Antes de arrancar el backend demo:

```powershell
$env:FIREBASE_SERVICE_ACCOUNT_FILE="D:\ClavesPrivadas\vestinova-firebase-admin.json"
```

Nunca publicar ni enviar el contenido JSON privado al chat/GitHub. El backend
usa `firebase-admin` y conserva Web Push VAPID de Angular por separado.

Reiniciar backend y Flutter después de configurar. Iniciar sesión como Cliente,
abrir una prenda de una variante **AGOTADA**, pulsar **Avisarme si hay
reposición · CU26**, elegir sucursal y aceptar notificaciones. Registrar un
movimiento real de **ENTRADA** en esa sucursal hasta que vuelva a existir saldo
neto. Comprobar que el backend haya despachado los eventos pendientes y que
Android reciba el push. Cancelar la alerta y repetir: no debe enviar para una
alerta cancelada.

**La recepción FCM real no se declara probada** hasta ejecutar con las
credenciales privadas y un teléfono conectado.

## 6. Control ICONIX

- CU09: solicitud local, autorización previa Stripe, precio y stock central,
  pago eventual, idempotencia, conflicto e incidencia.
- CU10: reserva offline es **independiente** de compra offline; requiere su
  propio catálogo, UUID, sincronización y compromiso de stock posterior.
- CU25: historial de compra y entrega no equivalen a valoración habilitada.
- CU26: alerta de reposición no crea una reserva.
