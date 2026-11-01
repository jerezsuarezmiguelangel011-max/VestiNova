# Contrato de descarga operacional privada — VestiNova

Versión del contrato: **1.0**. Bloque de backend para web y futuro móvil, 25 de octubre de 2026. Este documento describe la descarga; no implementa la aplicación Flutter, reservas, ventas offline ni sincronización de operaciones.

Flutter propio cubre cuenta/acceso de CU01; la persistencia comercial offline sigue pendiente. Según [CASOS_DE_USO.md](CASOS_DE_USO.md), esta descarga es base compartida para CU14 **Preparar información para operar sin conexión**, con responsable por confirmar. El inventario es soporte de CU08 **Gestionar inventario por sucursal**, de Miguel; este contrato no declara completo ese caso ni modifica sus pantallas.

## Identidad, empresa y sucursales

El acceso conserva `POST /api/auth/login`, `GET /api/auth/me` y `POST /api/auth/logout`. El token sigue siendo Bearer. Cada petición privada comprueba en el servidor la cuenta activa y la sesión vigente/no revocada; la pertenencia activa a una empresa y los permisos no se confían al contenido enviado por el cliente.

Enviar `X-Empresa-Id` cuando el usuario tenga varias pertenencias activas. Si se omite y existe una sola empresa activa autorizada, el backend la selecciona para conservar el flujo web actual. Con más de una devuelve `409`; sin pertenencia activa devuelve `403`. Un ID enviado en la cabecera no concede acceso.

- Una membresía `ADMINISTRADOR` permite administrar productos e inventario de su empresa y consultar sus sucursales activas.
- Las membresías `OPERADOR`, `ENCARGADO_SUCURSAL` y `CAJERO` solo consultan y descargan las sucursales activas asignadas. Este bloque no les permite registrar movimientos de inventario.
- La superadministración de plataforma no evita la comprobación de pertenencia para descargar información empresarial.
- Empresa o pertenencia inactiva impiden descargar. La revocación o los cambios de permisos se comprueban en cada petición online.

La identidad devuelta por el login conserva la forma anterior; su campo técnico `rol: "ADMINISTRADOR"` no sustituye el rol de la pertenencia empresarial. Para descubrir las empresas autorizadas se utiliza `GET /api/empresas`.

## Petición

```http
GET /api/movil/descarga?limit=50&offset=0&sucursal_ids=10&sucursal_ids=11&producto_ids=25&producto_ids=26
Authorization: Bearer TOKEN
X-Empresa-Id: 3
```

| Parámetro | Tipo y límite | Semántica |
| --- | --- | --- |
| `limit` | Entero de 1 a 100; por defecto 50. | Cantidad máxima de productos de la página. |
| `offset` | Entero desde 0; por defecto 0. | Desplazamiento dentro del subconjunto de productos filtrado. |
| `producto_ids` | Lista de enteros positivos mediante parámetros repetidos; hasta 100 IDs. | Opcional. Restringe la descarga a esos productos activos de la empresa. Si se omite, pagina todos los activos autorizados. |
| `sucursal_ids` | Lista de enteros positivos mediante parámetros repetidos; hasta 100 IDs. | Opcional. Selecciona sucursales activas autorizadas. Si se omite, se incluyen las sucursales activas autorizadas del usuario, sujeto al límite de respuesta. |

No enviar listas separadas por comas. Pedir un producto o sucursal no disponible para ese usuario/empresa rechaza la petición completa con `404`; no se devuelve una descarga parcial que oculte silenciosamente el ID inválido. Si el usuario no tiene ninguna sucursal activa autorizada, devuelve `403`.

La respuesta está limitada a 100 sucursales y 2000 variantes activas en la página. Si el subconjunto supera los límites de respuesta, devuelve `413`: seleccionar menos sucursales/productos o reducir `limit`. La paginación cuenta productos, no variantes ni filas de existencias.

Los productos se ordenan por ID ascendente. Solicitar explícitamente un producto inactivo también devuelve `404`; no se utiliza la descarga para recuperar borradores.

## Respuesta

`200 OK`, `Cache-Control: no-store`. El siguiente ejemplo ilustra el formato y no inserta registros en la base:

```json
{
  "version_contrato": "1.0",
  "empresa": {
    "id": 3,
    "slug": "empresa-ejemplo",
    "nombre": "Empresa de ejemplo"
  },
  "sucursales": [
    {
      "id": 10,
      "empresa_id": 3,
      "codigo": "CENTRO",
      "nombre": "Sucursal Centro",
      "activo": true,
      "creado_en": "2026-10-25T12:00:00+00:00"
    }
  ],
  "productos": [
    {
      "id": 25,
      "slug": "camisa-lino",
      "nombre": "Camisa de lino",
      "descripcion": "Descripción registrada por la empresa.",
      "precio": "180.00",
      "moneda": "BOB",
      "imagen_url": null,
      "activo": true,
      "creado_en": "2026-10-25T12:00:00+00:00",
      "actualizado_en": "2026-10-25T12:00:00+00:00",
      "variantes": [
        {
          "id": 40,
          "producto_id": 25,
          "talla": "M",
          "color": "VERDE",
          "activo": true,
          "creado_en": "2026-10-25T12:00:00+00:00",
          "existencias": [
            {
              "sucursal_id": 10,
              "cantidad": 5,
              "registrada": true,
              "actualizado_en": "2026-10-25T12:10:00+00:00"
            }
          ]
        }
      ]
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0,
  "generado_en": "2026-10-25T12:15:00+00:00",
  "moneda": "BOB"
}
```

| Campo | Regla para el consumidor |
| --- | --- |
| `version_contrato` | Versión del formato operacional. Comprobar compatibilidad antes de guardar/usar la descarga. |
| `empresa` | Contexto empresarial validado en servidor. Separar los datos locales por empresa; nunca mezclar descargas de empresas distintas. |
| `sucursales` | Solo sucursales activas autorizadas y seleccionadas. No implica autorización para cualquier sucursal de esa empresa. |
| `productos` | Productos activos de la empresa seleccionada; conservan los campos del contrato de producto y añaden `variantes` exclusivamente en esta respuesta operacional. |
| `variantes` | Variantes activas necesarias para operar. Talla y color se normalizan a mayúsculas; la identidad estable es el ID, no el texto. Un producto sin variantes activas puede tener una lista vacía y todavía no permite una operación por variante. |
| `precio` / `moneda` | Precio vigente del producto, heredado por sus variantes en este bloque. Cadena decimal exacta de dos decimales y moneda fija `BOB`; no convertir a un flotante para calcular/persistir dinero. No hay precio especial por variante. |
| `existencias` | Una entrada por sucursal incluida para cada variante. Es el saldo de inventario conocido en la lectura, no una promesa de disponibilidad futura ni una reserva de stock. |
| `cantidad` | Entero no negativo de unidades. No descuenta reservas futuras porque este bloque todavía no implementa reservas. |
| `registrada` | `true` si existe un saldo persistido, incluso si es cero. `false` indica que todavía no se registraron movimientos para esa combinación variante/sucursal. |
| `actualizado_en` en existencia | Fecha UTC del último cambio del saldo; `null` si `registrada` es `false`. En ese caso `cantidad` es `0` y no debe presentarse como un conteo físico auditado. |
| `generado_en` | Fecha UTC de la descarga. El móvil debe conservarla para informar cuándo obtuvo los datos. Es una propuesta de presentación útil para existencias conocidas, no una confirmación posterior de una venta. |
| `total`, `limit`, `offset` | Total de productos del subconjunto antes de paginar, límite y desplazamiento solicitados. Un offset posterior al total produce `productos: []`, conservando los metadatos. |

La lectura mantiene una vista consistente dentro de una petición en PostgreSQL. **No hay una instantánea congelada entre varias páginas**: productos, precios o permisos pueden cambiar entre peticiones. La versión `1.0` no incorpora cursor de instantánea, sincronización incremental, tombstones ni descarga de imágenes binarias. Una URL de imagen no garantiza que esa imagen esté disponible offline.

El consumidor debe guardar cada descarga y sus relaciones localmente de forma transaccional. No debe borrar operaciones pendientes al reemplazar catálogo ni interpretar la ausencia en una página como eliminación. La política completa para sustituir conjuntos locales y tratar productos desactivados queda por desarrollar con la sincronización. No se descargan datos de clientes en este contrato; ese requisito del parcial sigue pendiente.

## Errores

| Código | Situación |
| --- | --- |
| `401` | Token ausente, inválido, vencido, sesión revocada o cuenta inactiva. |
| `403` | Sin pertenencia activa, empresa inactiva o sin sucursales activas autorizadas. |
| `404` | Producto/sucursal solicitado no disponible en el contexto autorizado; no revela datos ajenos. |
| `409` | Varias empresas posibles sin `X-Empresa-Id`. |
| `413` | Subconjunto demasiado grande para una respuesta. |
| `422` | Parámetros inválidos o fuera de límites. |
| `503` | Base de datos temporalmente no disponible. No anunciar descarga completada. |

Se conservan errores `{ "detail": "Mensaje" }`; en validación FastAPI, `detail` puede ser una lista. No mostrar SQL, credenciales ni trazas al usuario.

## Existencias con trazabilidad

El saldo no se edita directamente desde la API. Se registra mediante entradas/salidas de inventario, en una transacción que guarda el movimiento y actualiza su saldo. Cada movimiento conserva ID único, empresa, sucursal, variante, usuario responsable, motivo, delta, saldo resultante y fecha. Las salidas que producirían saldo negativo se rechazan. El historial es la evidencia de por qué cambió la cantidad.

| Método y ruta administrativa | Uso |
| --- | --- |
| `GET /api/admin/productos/{producto_id}/variantes` | Lista variantes de un producto propio, incluidas las inactivas. |
| `POST /api/admin/productos/{producto_id}/variantes` | Crea una combinación de talla/color; requiere administración empresarial. |
| `PATCH /api/admin/variantes/{variante_id}` | Actualiza un subconjunto no vacío de `talla`, `color` y `activo`. Solo permite corregir talla/color si la variante todavía no tiene existencias ni movimientos asociados; el estado sí puede cambiar conservando su identidad histórica. |
| `POST /api/admin/inventario/movimientos` | Registra una entrada/salida con trazabilidad; requiere administración empresarial. |
| `GET /api/admin/inventario/existencias?sucursal_id=10` | Consulta saldos persistidos de una sucursal autorizada. Devuelve `{items,total,limit,offset}`. |
| `GET /api/admin/inventario/movimientos?sucursal_id=10&variante_id=40` | Consulta el historial autorizado; `variante_id` es opcional. Devuelve la misma envoltura paginada. |

Ejemplo ilustrativo de movimiento:

```json
{
  "id": "9e7681c7-86e5-4002-baf5-4bd82570ed29",
  "sucursal_id": 10,
  "variante_id": 40,
  "tipo": "ENTRADA",
  "cantidad": 5,
  "motivo": "Ingreso inicial comprobado"
}
```

`tipo` admite `ENTRADA` o `SALIDA`; la cantidad enviada siempre es positiva, entera y como máximo `1000000000`. El servidor deriva el signo y el usuario responsable. El saldo resultante debe estar entre cero y `2000000000`. No enviar `empresa_id`, `usuario_id`, saldo o delta arbitrarios.

El primer registro devuelve `201`; reenviar el mismo ID y contenido con el mismo usuario devuelve `200` y el movimiento original, sin aplicar otro cambio. Reutilizar el ID con otros datos devuelve `409`. Corregir un ingreso se hace con otro movimiento compensatorio y motivo, nunca editando/eliminando el historial. El alta de una variante no inventa unidades iniciales. La idempotencia de este movimiento administrativo no equivale a una API de sincronización de ventas o reservas ya implementada.

La edición de variantes no cambia esta descarga ni el catálogo público. Talla/color mantienen límites 30/60, normalización exterior/mayúsculas y unicidad por prenda, incluidas variantes inactivas. Una identidad referenciada, incluso con saldo cero, devuelve `409` al intentar corregirla; se conserva la original y se crea otra variante cuando corresponda. No hay traslado automático de inventario.

## Integración y trabajo compartido

- El contrato público de Miguel conserva `GET /api/catalogo/productos`, paginación `{items,total,limit,offset}`, detalle por `slug`, precio como cadena y `BOB`. Esta descarga no sustituye esas rutas ni requiere cambiar sus pantallas.
- Las respuestas públicas solo incluyen los datos publicados; no exponen pertenencias, sucursales internas o movimientos. La selección futura de tienda/tenant público y una posible evolución de la unicidad del slug deben acordarse aparte.
- Flutter propio y PWA pueden consumir esta descarga privada según sus permisos y usar sus mecanismos locales de persistencia distintos. No hay una app móvil nueva ejecutable por el mero hecho de existir este contrato.
- Se respeta el reparto: Salet CU01–CU07, CU12 y CU13; Miguel CU08–CU11. La asignación de CU14–CU28 sigue por confirmar. Definir interfaces no asigna esos casos a Miguel ni implica su entrega completa en la primera presentación.
- API móvil: emulador Android `http://10.0.2.2:8001/api`; teléfono LAN `http://IP_LAN_DE_LA_PC:8001/api`, con backend accesible. Ver [mobile/README.md](../mobile/README.md).

Referencias: [contrato público](CONTRATO_CATALOGO.md), [cuenta/acceso](CONTRATO_CU01_CUENTAS.md) y [base empresarial](BASE_BACKEND_EMPRESAS_INVENTARIO.md). La sincronización comercial requiere un contrato posterior; esta descarga no la implementa.
