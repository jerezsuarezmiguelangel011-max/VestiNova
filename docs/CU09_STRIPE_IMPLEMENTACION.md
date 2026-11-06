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

## Plan para enriquecer la demostración

Primero validar el recorrido real con las dos empresas de demostración.
Después crear un **script opcional e idempotente de datos visuales demo**,
separado de `seed_demo`, con categorías, prendas, variantes por talla/color,
existencias, promociones en vigencia e imágenes de fuentes autorizadas.

Ese script no debe sobrescribir clientes, roles ni inventario existentes,
ni modificar `vestinova_mvp`, ni exigir que se recree `vestinova_pruebas`.
Las imágenes no deben depender de URLs de terceros sin permiso.

