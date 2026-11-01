# Backend: empresas, sucursales e inventario trazable

Implementación propia del 25 de octubre de 2026. Rama `salet`, sin commits ni push. Este bloque amplía la base compartida para web y móvil; no incluye nuevas pantallas, reservas, ventas, compras ni sincronización comercial.

Correspondencia vigente: [CASOS_DE_USO.md](CASOS_DE_USO.md). Salet tiene CU01–CU07, CU12 y CU13; Miguel CU08–CU11; CU14–CU28 por confirmar. La base de inventario de este bloque es soporte compartido para CU08 **Gestionar inventario por sucursal**, no un cambio de responsable ni autorización para desarrollar sus pantallas. Los títulos anteriores se conservan solo como referencias históricas; no se renombran rutas/modelos técnicos.

## Migración y datos actuales

`0002_empresas_inventario` se aplica después de `0001_base`, que permanece intacta. Conserva IDs, campos comerciales, precios, hashes, contraseñas, secreto JWT y sesiones existentes.

La migración crea un contexto técnico explícito:

- Empresa `vestinova-inicial`, nombre `VestiNova (entorno inicial)`.
- Sucursal `PRINCIPAL`, nombre `Sucursal inicial`, sin dirección ni unidades inventadas.
- Todos los productos previos pertenecen a esa empresa. Todos los administradores previos conservan pertenencia administrativa en ella.
- La cuenta previa con menor ID obtiene la autoridad inicial de superadministración de plataforma. No se concede esa autoridad a todas las cuentas ni se cambia su estado activo.
- No se deducen tallas/colores de nombres ni se crean variantes o saldos ficticios.

Los nombres técnicos pueden reemplazarse por los datos reales mediante la API. No se reinterpretan como datos de una empresa del código heredado. Para separar productos en otras empresas hace falta una operación de traslado diseñada expresamente; no hay PATCH de propietario.

Aplicar sobre una instalación existente desde `backend`, conservando su `.env`:

```powershell
.\.venv\Scripts\python.exe -m scripts.init_db
```

No ejecutar `configure_local` ni recrear el administrador para actualizar el esquema. La migración PostgreSQL es transaccional y no contiene borrados de datos existentes. No tiene downgrade destructivo automático: no ejecutar downgrade para volver a una versión anterior. No editar migraciones ya aplicadas; cualquier cambio posterior necesita otra revisión Alembic.

Si hay una instancia antigua de Uvicorn sin recarga, detenerla en su propia terminal con Ctrl+C y volver a ejecutar:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

No iniciar una segunda instancia sobre el mismo puerto. API y pruebas solo utilizan `vestinova_mvp`; no se conecta a bases remotas heredadas ni a `vestinova`.

## Autorización y contexto

Se conservan login/me/logout y su respuesta actual. El rol técnico `ADMINISTRADOR` del login identifica el tipo de cuenta heredado del MVP; **los permisos empresariales se obtienen de la pertenencia**, no de ese campo ni de valores enviados por el cliente.

`GET /api/empresas` devuelve únicamente empresas activas con pertenencia activa del usuario, incluyendo `rol` empresarial. Enviar `X-Empresa-Id: ID_REAL` en peticiones empresariales. Si solo existe una empresa autorizada, se selecciona automáticamente para conservar la web actual. Si hay varias y no se envía cabecera, responde `409`; si la empresa no está autorizada, `403`. El servidor valida sesión, cuenta, empresa y pertenencia en cada petición.

| Autoridad | Permisos de este bloque |
| --- | --- |
| Superadministración de plataforma | Crear empresas con un administrador inicial existente y cambiar su estado activo. No accede a sus productos/inventario sin pertenencia. |
| Pertenencia `ADMINISTRADOR` | Gestionar su empresa, productos, variantes, sucursales y pertenencias; registrar movimientos; acceder a todas las sucursales activas de esa empresa. |
| Pertenencia `OPERADOR`, `ENCARGADO_SUCURSAL` o `CAJERO` | Consultar productos de la empresa y consultar/descargar solo sucursales activas asignadas. Este bloque no habilita escritura de productos, variantes, pertenencias o inventario para esos roles. |

Se rechaza con `404` el acceso a IDs de productos, variantes o sucursales no disponibles en el contexto, sin revelar recursos ajenos. Las relaciones compuestas en PostgreSQL impiden mezclar sucursal/producto/variante/pertenencia de empresas diferentes, incluso al insertar datos directamente. La membresía del responsable también se referencia desde el historial.

Las pertenencias se desactivan en vez de borrarse. No se permite retirar o degradar al último administrador activo de una empresa. La actualización de pertenencia reemplaza sus permisos de sucursal atómicamente y no permite que un operador se eleve a administrador. La autoridad de plataforma no se concede por este endpoint.

## Endpoints de organización

Todos requieren sesión; las operaciones administrativas comprueban la autoridad indicada arriba.

| Método y ruta | Datos o resultado |
| --- | --- |
| `GET /api/empresas` | Lista de `{id,nombre,slug,activo,rol}` autorizados. |
| `POST /api/plataforma/empresas` | Superadministración; `{nombre,slug,administrador_id}`. Crea la empresa y su pertenencia administrativa inicial en una transacción. |
| `PATCH /api/plataforma/empresas/{id}/estado` | Superadministración; `{activo}`. Permite suspender/reactivar el entorno. |
| `GET /api/admin/empresa` | Empresa seleccionada y autorizada. |
| `PATCH /api/admin/empresa` | Administración empresarial; `{nombre}`. |
| `GET /api/admin/sucursales` | Solo sucursales activas autorizadas. |
| `POST /api/admin/sucursales` | Administración empresarial; `{codigo,nombre}`. Código ASCII único en su empresa. |
| `PATCH /api/admin/sucursales/{id}` | Administración empresarial; cambios de `nombre` y/o `activo`, incluyendo reactivación propia. |
| `GET /api/admin/pertenencias` | Administración empresarial; usuarios, roles, estado y permisos explícitos de sucursal de su empresa. |
| `POST /api/admin/pertenencias` | Administración empresarial; crea/actualiza `{administrador_id,rol,activo,sucursal_ids}` para una cuenta existente. Reemplaza los permisos de sucursal. |

Para `ADMINISTRADOR`, `sucursal_ids` debe estar vacío porque accede a todas las sucursales activas propias. Para `OPERADOR`, `ENCARGADO_SUCURSAL` y `CAJERO`, una lista vacía no autoriza sucursales. Nunca se aceptan IDs de otra empresa. No hay registro público de personal ni correos/hashes en las listas de pertenencias. El [registro público Cliente](CONTRATO_CU01_CUENTAS.md) es independiente y no concede permisos de personal.

## Provisionamiento local de cuentas

El script mantiene contraseña oculta, política central y Argon2. Para una nueva instalación, la primera cuenta recibe autoridad de plataforma y pertenencia a la empresa inicial. Cuentas posteriores solo reciben autoridad de plataforma si se pide explícitamente desde la terminal confiable.

Desde `backend`, ejemplos con IDs reales obtenidos en la API:

```powershell
$EmpresaId = Read-Host 'ID de la empresa activa del nuevo administrador'
.\.venv\Scripts\python.exe -m scripts.create_admin --empresa-id $EmpresaId
```

Para un operador:

```powershell
$SucursalId = Read-Host 'ID de la sucursal autorizada de esa empresa'
.\.venv\Scripts\python.exe -m scripts.create_admin --empresa-id $EmpresaId --rol OPERADOR --sucursal-id $SucursalId
```

`--sucursal-id` se puede repetir. Omitir `--empresa-id` crea la pertenencia en el entorno inicial; no omitirlo para una cuenta de otra empresa. Para una empresa nueva, la superadministración puede crearla con una cuenta administrativa existente como responsable inicial; luego provisionar la nueva cuenta con el ID de esa empresa. Las pertenencias adicionales o su retiro se gestionan explícitamente, conservando un administrador activo. No hay flujo web de invitación/aceptación ni alta conjunta de empresa y cuenta.

El frontend tiene selector `/admin/empresa` y añade `X-Empresa-Id` al flujo de CU05 **Gestionar catálogo de prendas**. No hay formularios de organizaciones/inventario: esas operaciones se consultan mediante Swagger y su autorización de servidor. No se modificaron pantallas de Miguel. Ver [contrato público](CONTRATO_CATALOGO.md) y [cuenta/acceso](CONTRATO_CU01_CUENTAS.md).

## Variantes, saldos y movimientos

Cada producto pertenece a una empresa. Una variante identifica talla y color normalizados a mayúsculas, combinación única dentro del producto, incluidas variantes inactivas. No tiene precio independiente: hereda el precio vigente del producto, decimal exacto en BOB. `PATCH /api/admin/variantes/{id}` admite talla/color/estado; corrige identidad solo antes de que exista una fila de existencias o un movimiento asociado. Después devuelve `409` ante cambios de identidad, incluso con saldo cero. El estado activo sí puede cambiar. No incorpora movimientos ni pantallas de CU08.

Las existencias se llevan por empresa, sucursal y variante. **No hay endpoint para sobrescribir la cantidad.** Se usa `POST /api/admin/inventario/movimientos` con ID UUID, sucursal, variante, `ENTRADA`/`SALIDA`, cantidad positiva y motivo. El servidor toma el responsable de la sesión y deriva el signo.

Una transacción guarda el movimiento y actualiza el saldo. El primer movimiento crea la fila de saldo bajo protección de concurrencia; las operaciones posteriores bloquean esa fila hasta terminar. Se rechazan saldo negativo o mayor que 2000000000. El historial conserva usuario, motivo, fecha, delta y saldo resultante. No se editan ni eliminan movimientos por API; un error se corrige con un nuevo movimiento compensatorio.

El mismo ID y contenido del mismo usuario devuelve el movimiento original sin volver a afectar existencias (`200`; primera aplicación `201`). Un ID reutilizado con otros datos produce `409`. Esta idempotencia administrativa no implementa sincronización de ventas/reservas.

Un alta de variante no crea unidades. La descarga expresa ausencia de movimientos como `cantidad:0, registrada:false, actualizado_en:null`; un saldo cero que sí tiene historial es `registrada:true`. Ninguno reserva unidades para ventas futuras. Las consultas administrativas de saldos muestran solo filas persistidas.

Los endpoints y ejemplos exactos están en [CONTRATO_DESCARGA_MOVIL.md](CONTRATO_DESCARGA_MOVIL.md), que también documenta consulta de historial. Los ingresos manuales justificados son la base de este bloque; todavía no sustituyen compras a proveedores, comprobantes, ventas o transferencias.

## Descarga privada

`GET /api/movil/descarga` devuelve empresa, sucursales autorizadas, productos/variantes activos, precios y existencias conocidas, con `version_contrato:1.0`, fecha UTC y paginación por productos. Permite seleccionar subconjuntos y rechaza peticiones que incluyan un recurso ajeno. La lectura y autorización comparten una vista consistente PostgreSQL por petición; no se congelan varias páginas entre solicitudes.

No se agregan variantes, stock ni pertenencias al JSON público consumido por Miguel. Se conservan lista `{items,total,limit,offset}`, detalle por slug, precio como cadena y moneda BOB. El catálogo sigue publicando deliberadamente los productos activos de empresas activas: la selección pública por tienda se coordinará antes de cambiar rutas o unicidad de slug. Los datos operacionales permanecen privados.

## Verificación y pendientes

Pruebas automatizadas en bases aisladas: cuentas/productos de dos empresas, permisos por sucursal, cambio/revocación de pertenencia, IDs ajenos, ausencia de sesión, contrato público, ledger/saldo, reintentos, rechazo de salidas excesivas y descarga autorizada. PostgreSQL temporal verifica migración con datos y concurrencia real. Son pruebas de API, no acreditan pantallas comerciales completas.

Para repetir, desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m scripts.test_postgres --pg-bin 'C:/Program Files/PostgreSQL/18/bin'
```

Las pruebas PostgreSQL crean su propia instancia temporal en otro puerto y no usan las credenciales ni registros operativos. Los datos ficticios de prueba no se insertan en la base del usuario.

Pendientes: abastecimiento, reservas, ventas offline, SQLite comercial, PWA, sincronización/recepción comercial, conflictos y planes/suscripciones. La cuenta Cliente y Flutter de CU01 existen; no completan esas operaciones. La sincronización comercial todavía no tiene endpoints acordados. `empresa.activo` no equivale a un plan contratado. Respetar CU08–CU11 de Miguel y confirmar responsables de CU14–CU28 antes de asignarlos.

Fundamento técnico: [bloqueos de fila PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS) y [transacciones de lectura SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#setting-read-only-deferrable).
