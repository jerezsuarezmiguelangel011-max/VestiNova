# Contrato compartido de cuenta y acceso — CU01

Decisión de diseño confirmada por Salet el 25 de octubre de 2026. El enunciado no especifica el mecanismo de alta del Cliente: elegimos registro público **dentro de cada tienda**. Este contrato es aditivo al [catálogo de Miguel](CONTRATO_CATALOGO.md); no modifica paginación, detalle por `slug`, precio decimal como cadena ni moneda `BOB`.

## Contextos e identidades

El personal conserva `/api/auth/login`, `/api/auth/me` y `/api/auth/logout`, con selección de empresa **después** de autenticarse. El campo técnico histórico `administrador.rol = ADMINISTRADOR` identifica la clase de cuenta; no concede administración empresarial. La autorización comercial procede de una pertenencia activa comprobada en cada solicitud. La respuesta añade `es_superadministrador`; el superadministrador no adquiere automáticamente pertenencia a otras empresas.

`GET /api/empresas` enumera únicamente pertenencias activas a empresas activas. El rol por empresa puede ser `ADMINISTRADOR`, `ENCARGADO_SUCURSAL`, `CAJERO` u `OPERADOR` (compatibilidad histórica; no se reasigna automáticamente). `X-Empresa-Id` solo selecciona una pertenencia ya autorizada.

`GET /api/auth/contexto`, con token de personal y `X-Empresa-Id`, devuelve:

```json
{
  "empresa": {"id": 1, "nombre": "Nombre de tienda", "slug": "nombre-de-tienda", "activo": true, "rol": "CAJERO"},
  "sucursales": [{"id": 1, "empresa_id": 1, "codigo": "CENTRO", "nombre": "Sucursal Centro", "activo": true}]
}
```

Los identificadores son ilustrativos, no datos iniciales. Solo se incluyen sucursales activas autorizadas. El administrador empresarial ve todas las de su empresa; el resto necesita concesión explícita por sucursal. Esta consulta acredita acceso, sin implementar operaciones de CU08.

## Cuenta del cliente por tienda

El enlace web propio será `/tienda/{slug}/acceso`; Miguel podrá enlazarlo desde su tienda sin mostrar el selector administrativo. El móvil recibe el mismo identificador público. Resolver `GET /api/tiendas/{slug}` devuelve exclusivamente `{ "slug": "nombre-de-tienda", "nombre": "Nombre de tienda" }` para una empresa activa, o `404`.

| Operación | Endpoint | Entrada / salida |
| --- | --- | --- |
| Registro público | `POST /api/tiendas/{slug}/cuenta/registro` | `{nombre, correo, password}` → `201`, sesión y cliente. |
| Inicio de sesión | `POST /api/tiendas/{slug}/cuenta/login` | `{correo, password}` → `200`, sesión y cliente. |
| Restaurar / consultar cuenta | `GET /api/tiendas/{slug}/cuenta/me` | Bearer de cliente → `200`, cliente. |
| Cierre de sesión | `POST /api/tiendas/{slug}/cuenta/logout` | Bearer de cliente → `204`; revoca la sesión persistida. |

Registro e inicio devuelven:

```json
{
  "access_token": "TOKEN_OPACO_PARA_EL_FRONTEND",
  "token_type": "bearer",
  "expires_at": "2026-10-25T20:00:00Z",
  "cliente": {
    "id": 1, "nombre": "Nombre del cliente", "correo": "cliente@example.test", "rol": "CLIENTE",
    "empresa": {"slug": "nombre-de-tienda", "nombre": "Nombre de tienda"}
  }
}
```

`me` devuelve solo el objeto `cliente`. El registro inicia la sesión tras guardar el hash Argon2. El frontend no necesita interpretar el JWT.

## Reglas que ambos frontends deben conservar

- El servidor resuelve la tienda mediante el `slug` público. No se recibe `empresa_id`, `rol`, permisos, sucursales ni indicadores de personal en el registro. Se rechazan campos extra; el único rol posible es `CLIENTE`.
- El correo se recorta y normaliza a minúsculas. Su unicidad se comprueba por `(empresa_id, correo)` en PostgreSQL: un mismo correo en otra tienda es una cuenta independiente, con contraseña y sesiones propias. También es independiente de una eventual cuenta de personal.
- La contraseña nueva no se recorta. Debe tener entre 8 y 128 caracteres, mayúscula, minúscula, número y signo o símbolo. El mensaje acordado es: **La contraseña debe tener entre 8 y 128 caracteres e incluir una mayúscula, una minúscula, un número y un carácter especial.** La regla no se aplica al login ni altera hashes previos.
- La sesión del cliente tiene tipo, audiencia y registro propios. No se envía a `/api/admin/*`, `/api/auth/*`, `/api/empresas`, `/api/plataforma/*` ni a dominios externos. Nunca se acompaña de `X-Empresa-Id`.
- Cada petición privada comprueba cuenta, empresa, sesión y expiración; la tienda de la URL debe coincidir con la cuenta y el token. Cambiar el enlace no cambia la pertenencia ni concede acceso a otra tienda.
- `401`: credenciales incorrectas o sesión no válida; `404`: tienda no disponible; `409`: correo ya registrado en esa tienda; `422`: campos inválidos. No mostrar trazas ni contraseñas en errores. Un fallo de conexión no acredita cierre o restauración de sesión.
- La interfaz debe mostrar tienda e identidad, estados de carga/error, reintento de cierre fallido y navegación protegida. El cliente nunca utiliza el menú ni selector administrativo.

## Coordinación con Miguel y límites

Miguel mantiene sus pantallas de catálogo y detalle. Solo debe coordinar el origen del `slug` de tienda y los enlaces de acceso/cuenta; este bloque no modifica sus pantallas. El catálogo público actual agrega prendas publicadas y todavía no se redefine como catálogo por tienda: acordar ese filtro cuando se desarrolle su navegación comercial. No deducir la tienda desde un campo nuevo del producto que el contrato actual no contiene.

No se incorporan recuperación por correo, verificación de correo, cambio de contraseña, reservas, compra, sincronización ni catálogo móvil como requisitos nuevos de CU01. Si se acuerdan, se especificarán y probarán en su propio avance. Flutter/SQLite comercial, reservas/ventas offline y sincronización permanecen pendientes; [CASOS_DE_USO.md](CASOS_DE_USO.md) conserva el reparto.

Este documento define el contrato de integración. El [README](../README.md) contiene los comandos de ejecución/verificación; las evidencias detalladas de Salet permanecen locales. CU01 no se declara completo por disponer de estos endpoints.
