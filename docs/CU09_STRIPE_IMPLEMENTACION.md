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
