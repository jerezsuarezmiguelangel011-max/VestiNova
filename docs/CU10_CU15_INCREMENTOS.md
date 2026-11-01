# Incrementos de CU10 y CU15

Fuente de alcance: instrucciones y requisitos mínimos proporcionados y aprobados
por el usuario en esta conversación. No se atribuye este contrato a una ficha o PDF
académico almacenado en el repositorio.

## CU10: selección y contrato de compra

El núcleo `backend/app/purchases/` separa reglas, puerto de integración, persistencia
y API. La compra identifica su solicitud mediante UUID, agrupa productos repetidos,
valida cantidades enteras positivas y conserva nombres y precios como instantáneas.
Los precios y totales son decimales exactos en BOB. El registro `CONFIRMADA` no
acredita un pago cobrado; no se añade una pasarela de pagos a este incremento.

La interfaz pública permite preparar una selección temporal de prendas, cambiar
cantidades y quitar elementos en `/catalogo/acciones/compra`. El parámetro opcional
`?slug=SLUG_REAL` añade una prenda del catálogo. La selección se mantiene en memoria
mientras se navega dentro de la aplicación; no constituye una compra guardada ni
una cola de compras sin conexión. Los precios visibles son referenciales, con aviso
cuando proceden de la copia local de CU14.

| Operación | Contrato |
| --- | --- |
| `GET /api/compras/capacidades` | Informa si está configurada la integración necesaria. |
| `POST /api/compras` | Recibe `{id, items:[{producto_id,cantidad}]}`; responde `201` y comprobante confirmado. |
| `GET /api/compras/{id}` | Consulta el comprobante únicamente en el contexto autorizado. |

El frontend no fija empresa, cliente, sucursal, precios ni total de una compra.
El gateway debe resolver esos datos desde una sesión de cliente autorizada,
obtener ofertas de la empresa y variantes reales y comprobar inventario disponible.
Se reutilizan las referencias y saldos de CU08; no se crean maestros de empresa,
cliente, sucursal o variante para completar artificialmente la integración.

La configuración predeterminada no instala un gateway productivo. Por tanto,
capacidades informa `habilitado: false` y confirmar o consultar compras responde
`503`, sin registrar compras ni descontar inventario. La existencia del endpoint
y las tablas propias de compras no implica habilitar operaciones productivas.
La pantalla conserva la selección, explica la dependencia y mantiene deshabilitada
la confirmación mientras capacidades no informe disponibilidad. No se instala un
proveedor ficticio para hacer aparecer compras confirmadas en la aplicación real.

Con gateway configurado, las peticiones requieren credenciales de cliente válidas.
Los errores de autenticación/autorización son `401`/`403`; la validación del cuerpo
es `422`; la falta de disponibilidad o reutilización incompatible del UUID es `409`.
Una compra de otro contexto no debe revelar su comprobante. No se acepta un precio
enviado por el navegador como sustituto de la oferta validada por el servidor.

La confirmación consume únicamente stock disponible, mantiene los compromisos ajenos
y registra compra y líneas en la misma sesión SQL que utiliza el gateway para el
descuento y su trazabilidad. Los métodos del gateway no hacen `commit` independiente.
Si falla cualquier parte, se revierte la transacción completa. Un reenvío con el
mismo UUID, contexto y selección devuelve el comprobante previo sin volver a consumir;
una selección distinta con ese UUID se rechaza.

La persistencia incorpora únicamente las tablas propias `compras_digitales` y
`compras_digitales_lineas`, mediante la revisión Alembic `cu10_01_compras`, posterior
a `0001_base`. La FK interna vincula líneas con su compra y empresa; no se crean
tablas maestras ni claves foráneas hacia maestros inventados. El descuento real y su control de
concurrencia requieren el adaptador productivo integrado con el esquema compartido.
La batería utiliza SQLite aislado y un gateway con stock y movimientos exclusivos
de pruebas para comprobar el contrato y rollback. Esos fixtures no habilitan ventas
reales ni se incorporan como inventario de la aplicación.

## CU15: cola operable del catálogo público

La pantalla `/catalogo/acciones/sincronizacion` permite registrar y procesar
manualmente operaciones de tipo `ACTUALIZAR_CATALOGO`. La cola se guarda en
IndexedDB, base `vestinova-public-sync`, con UUID de operación, ámbito público,
fechas, estado y fecha de descarga que la operación espera encontrar
(`expectedDownloadedAt`, o `null` si todavía no había copia).
Las operaciones sobreviven a otras visitas en el mismo perfil y origen.

| Estado | Significado |
| --- | --- |
| `PENDIENTE` | Operación registrada, todavía sin procesar. |
| `PROCESANDO` | Se está comprobando y descargando el catálogo. |
| `SINCRONIZADA` | La descarga terminó y la copia pública quedó actualizada. |
| `CONFLICTO` | La fecha de la copia local cambió desde que se registró la operación. |
| `ERROR` | El procesamiento no pudo completarse; puede reintentarse explícitamente. |

Registrar una operación funciona sin red y no descarga datos. Procesarla requiere
acceder al catálogo público del servidor. La comprobación de fecha y la descarga
usan el mismo Web Lock que protege la actualización de CU14. Si la copia actual
ya no coincide con `expectedDownloadedAt`, la operación queda en `CONFLICTO` y
no sobrescribe esa copia. La comprobación es optimista y se refiere a la versión
local identificada por su fecha, no a una versión transaccional de PostgreSQL.

Una descarga fallida mantiene intacta la copia anterior y deja la operación en
`ERROR`. La interfaz permite reintentar errores de forma manual. Un conflicto no
se resuelve sobrescribiendo automáticamente: requiere revisar la copia vigente y
registrar una nueva intención si se desea otra actualización. Cambiar el estado de
una operación no confirma una compra ni compromete stock de una reserva.

Este alcance utiliza los GET públicos del catálogo y no necesita un endpoint nuevo
de backend para CU15. No sincroniza escrituras privadas, compras o reservas, ni
simula contextos de empresa, cliente o usuario. CU11/CU15 completos, aislamiento por
empresa/usuario y resolución de escrituras privadas siguen pendientes de sus
integraciones reales. La cola contiene únicamente metadatos de actualización del
catálogo público; no guarda tokens ni cabeceras de autorización.

## Recorrido manual en Windows

Utilizar Node.js 24 compatible, un perfil de navegador persistente y el mismo origen
durante todo el recorrido. No alternar `localhost`/`127.0.0.1` ni puertos: las copias,
la cola y el service worker pertenecen al origen exacto. La preparación general y
el uso de DevTools sin omitir el worker se explican en [CU14_OFFLINE.md](CU14_OFFLINE.md).

Con el backend ya configurado y la revisión `cu10_01_compras` aplicada en esta
instalación, iniciar el servicio habitual si no está atendiendo el puerto 8001:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

En otra terminal, con dependencias ya instaladas:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\frontend'
npm.cmd run build
npm.cmd run preview:pwa -- --port 4301
```

Adaptar las rutas al clon propio y usar `http://127.0.0.1:4301` durante toda la prueba.
Detener solo una instancia propia previa si ocupa ese puerto. Este recorrido no
requiere repetir migraciones ni crear datos de ejemplo o proveedores productivos.

1. Abrir `/catalogo` y esperar la preparación de apertura sin conexión. Descargar
   el catálogo y esperar la confirmación de CU14. La copia vacía también es válida.
2. Si hay una prenda real publicada, abrir
   `/catalogo/acciones/compra?slug=SLUG_REAL`. Cambiar cantidad, añadir otras prendas
   navegando por el catálogo y quitar alguna de la selección. Comprobar la indicación
   de precio referencial y la dependencia de compras. Con la configuración actual,
   capacidades devuelve `habilitado: false` y la confirmación queda deshabilitada;
   una petición directa a compras responde `503`. No debe aparecer un comprobante
   ni registrarse una compra por preparar la selección.
3. Abrir `/catalogo/acciones/sincronizacion`, seleccionar Offline en DevTools y
   registrar una actualización. Debe quedar `PENDIENTE`. Recargar normalmente o
   volver a visitar la pantalla, conservando worker y almacenamiento: la operación
   debe continuar en la cola.
4. Restaurar la red y procesar manualmente la operación. Debe pasar por `PROCESANDO`
   y terminar `SINCRONIZADA` cuando finalice correctamente la descarga pública.
   La copia de CU14 debe reflejar su nueva fecha.
5. Para provocar un conflicto, registrar otra operación y, antes de procesarla,
   actualizar el catálogo mediante el botón habitual de CU14. Esperar su confirmación.
   Procesar después la operación pendiente: debe quedar `CONFLICTO` y conservar la
   copia más reciente, sin reemplazarla mediante esa operación antigua.
6. Para comprobar el fallo, registrar una operación nueva y bloquear temporalmente
   las solicitudes públicas o desconectar la red al procesarla. Debe quedar `ERROR`
   conservando productos y fecha anteriores. Restaurar la red y utilizar el reintento
   manual. Si otra actualización cambió la fecha entretanto, el resultado correcto
   es un conflicto, no una sobrescritura silenciosa.

Los fixtures de pruebas son exclusivos del entorno aislado. No habilitan un gateway
real, no agregan inventario productivo y no certifican la integración completa de
los casos académicos. Los resultados concretos de pruebas se registran por separado
en [AVANCES.md](AVANCES.md).
