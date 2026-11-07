# CU09 — Realizar compra digital (Stripe Checkout)

## Rama y alcance
Trabajo independiente en `trabajo/cu09-miguel`, basada en el commit de CU08 aprobado
`635d6d2`. La rama `miguel` **no se modifica** hasta revisión y aprobación.

La implementación usa **Stripe Checkout exclusivamente en modo de prueba**.
No admite claves `sk_live_` y nunca confirma pagos a partir de una redirección del navegador.

La empresa VestiNova de demostración opera en Bolivia. Según la lista oficial de
Stripe, Bolivia actualmente no figura entre los países habilitados para abrir
cuentas comerciales de Stripe Payments. Esta integración permite documentar y
probar la arquitectura; **no se declara operativa para cobrar dinero real**.

## Verificación contra la tabla 2.6

| Flujo | Comportamiento |
| --- | --- |
| 1–3: catálogo, variantes, carrito | Nueva pantalla de compra con varias prendas, talla/color, cantidad y edición de selección |
| 4: capacidades, precio y stock | Solo el backend calcula promociones, total BOB y disponible físico menos comprometido; rechaza falta de saldo |
| 5: retiro o entrega | Elección de sucursal, modalidad y dirección mínima para domicilio |
| 6–7: pago | Sesión de Stripe Checkout por pedido UUID y clave de idempotencia; retorno a VestiNova |
| 8: transacción final | Webhook firmado; vuelve a validar productos, precio y stock; registra cabecera y líneas de compra, descuenta inventario y genera movimientos de kardex con actor cliente en una transacción |
| 9: comprobante | Consulta autenticada y acotada a empresa/cliente; solo muestra «CONFIRMADA» al existir registro tras webhook; entrega sigue pendiente |
| 4A: no configurado | Sin claves de prueba válidas, capacidades deshabilitadas y API 503, sin iniciar checkout |
| 4B: stock insuficiente antes del cobro | Error 409, sin sesión de pago |
| 7B: pérdida de respuesta | Idempotencia por UUID y consulta posterior del estado; sin inferir pago por volver del navegador |
| 8A: acreditado sin venta | Estado persistente INCIDENCIA, ID de Stripe y causa para compensación o reembolso; sin crear compra ni reducir stock |
| 9A: entrega posterior | La confirmación de pago no se transforma en ENTREGADA; se requiere flujo de entrega separado |

**Pendiente para aprobación de CU09 completo**: gestión operativa automatizada del
reembolso/compensación en Stripe con seguimiento financiero; constancia de entrega
en los módulos logísticos; ensayos manuales reales en sandbox de Stripe con cuenta
y webhook del equipo autorizado. Las pruebas con mocks no sustituyen a Stripe real.

## Configuración segura en desarrollo

1. Mantener el `.env` personal de `backend` fuera de Git.
2. El titular **autorizado** de una cuenta de Stripe de pruebas puede configurar
   `STRIPE_SECRET_KEY` (`sk_test_...`) y `STRIPE_WEBHOOK_SECRET` (`whsec_...`).
   No copiar estos valores al frontend, mensajes, documentos ni GitHub.
3. En `backend`, actualizar dependencias y aplicar migración sobre la base demo:
   ` .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt `
   ` .\.venv\Scripts\python.exe -m scripts.migrate_demo `
4. Iniciar API: ` .\.venv\Scripts\python.exe -m scripts.serve_demo `.
5. Iniciar Angular en otra terminal: `npm.cmd start` desde `frontend`.
6. Ingresar con una cuenta de cliente de la tienda seleccionada y abrir
   `http://127.0.0.1:4201/catalogo?tienda=demo-moda-andina`.
7. Seleccionar prenda y pulsar «Seleccionar para comprar». Elegir variante,
   sucursal y entrega. Si falta configuración Stripe, se presenta aviso sin cobro.
8. Para pruebas integradas, el titular autorizado de Stripe puede configurar el
   envío de eventos **firmados** a
   `POST http://127.0.0.1:8001/api/webhooks/stripe` a través de su entorno
   de pruebas. Los eventos deben coincidir con el pedido y la firma; un retorno
   al navegador por sí solo no confirma la compra.

## ¿Por qué aparece Stripe deshabilitado?

El endpoint público `GET /api/tiendas/demo-moda-andina/compras/capacidades`
solo responde `habilitado: true` cuando el backend encuentra **ambas**
variables de prueba en el entorno o en `backend/.env`:

- `STRIPE_SECRET_KEY`, de prueba, comienza por `sk_test_`.
- `STRIPE_WEBHOOK_SECRET`, procedente del receptor de eventos de prueba,
  comienza por `whsec_`.

Para saber qué falta **sin revelar claves**, ejecutar desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_stripe_demo
```

El diagnóstico no conecta a Stripe ni garantiza que las claves sean
aceptadas por el proveedor; únicamente informa sobre su presencia y formato.
En el navegador el carrito ahora distingue también requisitos incompletos:
sesión de cliente, variantes, sucursal, cantidades, dirección y conexión con
el backend. No se debe habilitar el cobro desactivando esta validación.

El titular autorizado de las credenciales debe configurar y verificar la
recepción de webhooks firmados de sandbox. El redirect de Checkout nunca
equivale a pago confirmado. Para empresas radicadas en Bolivia, la
documentación oficial de Stripe debe revisarse antes de cualquier despliegue
comercial: estar disponible la moneda BOB no equivale a poder abrir una
cuenta de Stripe Payments desde Bolivia.

## Seguridad

- No se aceptan precio, empresa, cliente ni moneda desde el navegador como
  fuente de autoridad.
- Tokens de personal y de cliente no se intercambian.
- Webhook verifica firma con Stripe SDK y rechaza eventos no asociados a sesión.
- Stock final se bloquea y revalida en el servidor antes de confirmar la compra.
- La misma sesión/pago no descuenta inventario más de una vez.
- El carrito en sessionStorage conserva únicamente identificadores públicos
  y cantidades, sin tokens, claves, números de tarjeta ni direcciones.

## Migración

`c09a4d1f2026` depende de `c08a4d1f2026`. Agrega
`checkout_stripe_intentos` y permite identificar al cliente en los
movimientos de ventas digitales, sin borrar registros anteriores.
La migración a `vestinova_pruebas` no vuelve a ejecutar semillas;
`vestinova_mvp` no debe modificarse durante estas pruebas.

## Portal público multitenant y navegación de compra

La ruta `/` ahora muestra una portada de VestiNova y el directorio dinámico
obtenido de `/api/catalogo/tiendas` (sin nombres de empresas hardcodeados).

Cada empresa comparte la misma plantilla angular:

- `/tienda/demo-moda-andina`: catálogo y sucursales de Moda Andina.
- `/tienda/demo-moda-urbana`: catálogo y sucursales de Moda Urbana.
- `/tienda/<slug>/prenda/<producto-slug>`: detalle de producto de la empresa.
- `/tienda/<slug>/acceso`: registro o acceso del cliente. Si llegó desde
  el carrito con `continuar=compra`, retorna a CU09, sin redirecciones externas.
- `/catalogo/acciones/compra?tienda=<slug>`: carrito y Stripe Checkout (CU09).

El selector de sucursal comienza en **Todas las sucursales**. Nunca bloquea
el catálogo y solo preselecciona la consulta de disponibilidad. En el carrito
se sugiere la misma sucursal, pero la confirmación y todo acceso al stock se
revalidan en backend por empresa, sucursal y variante.

Administración tiene un botón **Ver mi tienda pública** que abre en una pestaña
separada la empresa activa. El carrito en memoria se vacía al cambiar de empresa.

El portal utiliza transiciones CSS progresivas y admite
`prefers-reduced-motion: reduce`. No se requieren nuevas migraciones para
esta navegación: se aprovechan las APIs públicas existentes de CU08.

## Interfaz pública centrada en cliente y vitrina enriquecida

Las rutas vigentes son:

- `/`: inicio general VN, información de VestiNova y directorio de empresas
  activas con suscripción SaaS vigente.
- `/tienda/<slug>`: portada individual reutilizable con novedades,
  categorías y promociones activas obtenidas del catálogo de CU08.
- `/tienda/<slug>/catalogo`: lista completa con filtros y precio BOB.
- `/tienda/<slug>/catalogo?categoria=<id>`: categoría de esa empresa.
- `/tienda/<slug>/prenda/<producto-slug>`: ficha comercial, consulta de
  variantes y disponibilidad; agregar al carrito con notificación.
- `/catalogo/acciones/compra?tienda=<slug>`: carrito CU09, sucursal
  y enlace a Stripe de prueba.
- `/tienda/<slug>/acceso?continuar=compra`: acceso con retorno al carrito;
  añadir `&registro=1` para abrir directamente Crear cuenta.
- `/admin/login`: personal y Superadministrador SaaS. **No aparece como
  botón prioritario en el portal público**; permanece accesible directamente.

En Administración, **Ver mi tienda pública** sigue disponible para la empresa
seleccionada. El diseño comparte los componentes de catálogo y no duplica
lógica del backend.

La vista individual abre con novedades y ofertas **reales** de la API
(`precio_promocional`); no se inventan colecciones ni descuentos. Si no
hay promociones se indica. Las fotos ausentes se reemplazan solo en los datos
demo mediante ilustraciones SVG originales, nunca en catálogos reales.

### Seed opcional de exhibición: solo vestinova_pruebas

Este script NO se ejecuta al iniciar la aplicación ni desde `seed_demo`.
Solo después de probar las pantallas, el operador puede ejecutarlo manualmente
en el backend, con su PostgreSQL local:

```powershell
cd D:\Proyectos\vestinova-mvp\backend
.\.venv\Scripts\python.exe -m scripts.migrate_demo
.\.venv\Scripts\python.exe -m scripts.seed_showcase_demo
```

La ejecución usa `use_demo_database()` para asegurar el destino
`vestinova_pruebas`. Añade **12 prendas nuevas por empresa** (24 en total),
tres variantes con talla/color por prenda, stock inicial en las sucursales
existentes y tres promociones por empresa. Completa imágenes faltantes solo en
los seis productos originales de `seed_demo`, con SVG originales servidos
por Angular desde `frontend/public/demo-fashion/`. No se borran ni regeneran
usuarios, contraseñas, ventas, pedidos, reservas, ajustes ni existencias
existentes; la repetición del script conserva lo ya creado.

Las ilustraciones son representaciones originales para **pruebas locales,
no fotografías de mercancía real**. Los enlaces
`http://127.0.0.1:4201/demo-fashion/` son deliberadamente locales
y deben sustituirse antes de desplegar la vitrina fuera del ordenador.

El script exige un plan activo, valida cupos de productos y usa una transacción.
Si falla, el procesamiento de esa ejecución se revierte.

### Validación manual del recorrido

1. Abrir `http://127.0.0.1:4201/`. Verificar logo **VN** y que los
   botones «Cómo funciona», «Descubrir tiendas» y «Explorar tiendas» desplazan
   correctamente.
2. Abrir Moda Andina desde su tarjeta. «Explorar colección» debe bajar a
   novedades de **esa tienda**, sin cambiar a la vista general.
3. Revisar categorías y promociones, y abrir una prenda.
4. Elegir talla/color, añadir al carrito y usar el aviso «Revisar carrito».
   Probar la ruta inversa «Seguir explorando».
5. Sin sesión, desde el carrito elegir iniciar sesión o crear cuenta;
   comprobar que vuelve a CU09 y conserva la variante.
6. Cambiar a Moda Urbana y comprobar que el carrito de Andina NO aparece.
7. En Administración, seleccionar empresa y pulsar «Ver mi tienda pública».
8. Probar tamaños de pantalla y **prefers-reduced-motion**. Ninguna animación
   debe impedir la lectura.
9. Stripe: nunca simular un pago real; la confirmación depende del webhook
   firmado. Sin claves de prueba autorizadas, debe permanecer deshabilitado.

Las pruebas automatizadas incluyen la seed repetida y su protección de
saldos, aislamiento de carrito y consulta pública por tenant, pero la
aprobación visual y las pruebas manuales de sandbox siguen pendientes.

## Stripe Sandbox — error de noviembre 2026 al crear Checkout

Si `stripe logs tail` muestra `400 invalid_request_error` con
`Param: payment_method_types` y el mensaje de que el parámetro ya no
está admitido, el problema procede de la solicitud de nuestra API,
**no** de `STRIPE_SECRET_KEY` o `STRIPE_WEBHOOK_SECRET`.

El backend omite `payment_method_types` en `stripe.checkout.Session.create`
para que Stripe use los métodos habilitados en el Dashboard del Sandbox.
No se cambia la moneda `bob`, el cálculo de importes, ni el tratamiento
de webhooks firmados. Se versionó la clave de idempotencia a
`vestinova-cu09-v2-` para no reutilizar una posible respuesta de error
almacenada con la clave de la solicitud antigua.

Para verificar en el equipo, actualizar exclusivamente la rama temporal
`trabajo/cu09-miguel`, reiniciar `scripts.serve_demo`, mantener
`stripe listen` en el Sandbox y volver a pulsar «Proceder al pago».
Una respuesta `POST /v1/checkout/sessions` correcta debe generar una
URL de Stripe Checkout; **no** confirma la compra por sí sola.
Si Stripe presenta otro rechazo, consultar `stripe logs tail` sin
copiar claves ni detalles sensibles.

La prueba automatizada `backend/tests/test_stripe_checkout_request.py`
impide reintroducir el parámetro rechazado.
