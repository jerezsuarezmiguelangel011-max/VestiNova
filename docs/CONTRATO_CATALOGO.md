# Contrato compartido de productos — VestiNova MVP

Acuerdo inicial de integración, 25 de octubre de 2026. Este documento propone el contrato para que ambos integrantes trabajen sobre una API común; no implica una aceptación externa del compañero.

**Ampliación aditiva de CU01 para coordinar con Miguel:** [CONTRATO_CU01_CUENTAS.md](CONTRATO_CU01_CUENTAS.md) define registro/login/cuenta por tienda pública (`/tienda/{slug}/acceso`). El servidor asigna exclusivamente Cliente y valida la tienda; no se usa el selector de personal. No se cambian los endpoints ni campos de producto siguientes. El catálogo actual continúa agregado: acordar con Miguel cómo obtener el slug de tienda y enlazar sus pantallas, sin añadir ni asumir un campo empresarial inexistente en el JSON del producto. No se modificó su frontend ni se afirma que ya integró los enlaces.

## Responsabilidades

- Salet: CU01 **Gestionar cuenta y acceso al sistema** y CU05 **Gestionar catálogo de prendas** en el subflujo administrativo de este contrato; su responsabilidad total es CU01–CU07, CU12 y CU13.
- Miguel: CU08–CU11; sus pantallas públicas de catálogo y detalle corresponden a CU09 **Consultar catálogo y disponibilidad**, consumiendo los endpoints siguientes. Esta revisión conserva su trabajo sin modificar sus archivos.
- Ambas partes: conservar nombres, tipos y semántica del contrato. Proponer cambios aquí y actualizar las pruebas antes de modificar respuestas.

La lista exacta de actores/plataformas y el reparto confirmado están en [CASOS_DE_USO.md](CASOS_DE_USO.md). CU14–CU28 permanecen por confirmar. Los nombres técnicos «productos» de rutas/modelos no cambian por corregir los títulos de los casos.

## Endpoints públicos

Base relativa desde Angular: `/api`. El proxy local apunta a `http://127.0.0.1:8001`.

| Método y ruta | Resultado |
| --- | --- |
| `GET /api/catalogo/productos` | Lista paginada exclusivamente de productos activos. |
| `GET /api/catalogo/productos/{slug}` | Detalle activo; `404` si no existe o está inactivo. |

Listado: parámetros `q` opcional (búsqueda), `limit` (20 por defecto, máximo 100) y `offset` (0 por defecto). Respuesta:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

Cada elemento y el detalle comparten esta forma ilustrativa; los ejemplos no se insertan en la base:

```json
{
  "id": 1,
  "slug": "camisa-lino",
  "nombre": "Camisa de lino",
  "descripcion": "Descripción escrita por el administrador.",
  "precio": "180.00",
  "moneda": "BOB",
  "imagen_url": null,
  "activo": true,
  "creado_en": "2026-10-25T12:00:00Z",
  "actualizado_en": "2026-10-25T12:00:00Z"
}
```

`precio` viaja como cadena decimal exacta con dos decimales; mostrarlo como bolivianos sin recalcularlo para guardarlo. `imagen_url` puede ser nulo: usar un estado visual sin imagen, sin inventar una fotografía de producto. Las fechas son ISO 8601 con zona horaria. El slug identifica la URL pública; el ID identifica las operaciones administrativas.

Los campos de esta respuesta pública se limitan a identidad, descripción, precio, imagen externa opcional y visibilidad. El backend incorpora empresas, variantes e inventario mediante APIs privadas; esos campos no se añaden a esta respuesta ni requieren cambios en las pantallas de Miguel. Compras, ventas, reservas y suscripciones siguen pendientes.

La publicación pública incluye productos activos de empresas activas; el slug conserva unicidad global y el listado su orden de ID descendente. La selección pública por tienda/empresa se coordinará como ampliación posterior. No se expone inventario interno ni pertenencias. La descarga privada independiente se especifica en [CONTRATO_DESCARGA_MOVIL.md](CONTRATO_DESCARGA_MOVIL.md).

Validaciones: nombre entre 3 y 120 caracteres; descripción de hasta 3000; slug entre 3 y 140, con letras ASCII minúsculas, números y guiones simples; precio mayor que cero y máximo `99999999.99`, con dos decimales como máximo; URL de imagen HTTP/HTTPS, sin credenciales y de hasta 2048 caracteres. `q` admite hasta 120 caracteres y busca por nombre, con orden de ID descendente. El servidor genera el slug al registrar si se omite; editar el nombre conserva el slug salvo cambio explícito. Un slug duplicado devuelve `409`; no se cambia de forma silenciosa.

## Endpoints administrativos

Requieren `Authorization: Bearer TOKEN`, sesión vigente y administrador activo, comprobados por el servidor.

La API administrativa comprueba además pertenencia activa a empresa. `X-Empresa-Id` selecciona una empresa autorizada; con una sola pertenencia se conserva la selección automática, con varias la omisión devuelve `409`. La consulta admite las pertenencias de personal `ADMINISTRADOR`, `ENCARGADO_SUCURSAL`, `CAJERO` y `OPERADOR`; el alta y edición requieren `ADMINISTRADOR` empresarial. No se aceptan propietarios arbitrarios en el payload. Los cuerpos y respuestas de producto permanecen compatibles. Ver [base empresarial e inventario](BASE_BACKEND_EMPRESAS_INVENTARIO.md).

| Método y ruta | Operación |
| --- | --- |
| `GET /api/admin/productos` | Lista; admite `q`, `activo`, `limit`, `offset`. |
| `GET /api/admin/productos/{id}` | Obtener los datos para editar. |
| `POST /api/admin/productos` | Crear; `201` y producto persistido. |
| `PATCH /api/admin/productos/{id}` | Actualizar solo campos enviados; devuelve producto persistido. |

Alta: `nombre`, `descripcion`, `precio`; opcionales `slug`, `imagen_url`, `activo`. Si no se envía slug, el servidor lo genera. Moneda fija `BOB`. El formulario administrativo recibe y muestra las validaciones del servidor. No existe borrado físico ni carga de archivos en este alcance.

## Autenticación y errores

- `POST /api/auth/login`: `{ "correo": "...", "password": "..." }` → `access_token`, `token_type: "bearer"`, `expires_at` y `administrador: {id,nombre,correo,rol:"ADMINISTRADOR",activo:true}`.
- `GET /api/auth/me`: identidad del administrador vigente. No devuelve contraseña ni hash.
- `POST /api/auth/logout`: revoca la sesión; respuesta `204`.
- `401`: sesión ausente, vencida, revocada o cuenta inactiva. `403`: actor o permiso insuficiente. `404`: recurso no disponible. `409`: slug ya utilizado. `422`: validación.
- Errores de dominio: `{ "detail": "Mensaje" }`; errores de entrada FastAPI: `detail` es una lista con `loc` y `msg`. No mostrar mensajes SQL ni trazas al usuario.

El catálogo no necesita token. No debe consumir `/api/admin/*` ni guardar credenciales del administrador. Desactivar un producto lo retira de las consultas públicas.
