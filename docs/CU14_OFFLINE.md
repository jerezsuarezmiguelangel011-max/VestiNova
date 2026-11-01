# CU14: incremento público para consulta sin conexión

Este incremento prepara una copia del catálogo público de VestiNova y la apertura de sus pantallas mediante PWA. Comprende `/catalogo` y `/catalogo/{slug}`. Permite consultar prendas descargadas, buscar por nombre, paginar y abrir su detalle cuando falla la conexión.

El alcance académico completo de CU14 contempla información autorizada por empresa y usuario, variantes, precios, últimas existencias y sucursales. El backend actual no ofrece esas entidades ni ese contexto de autorización. Esta implementación guarda únicamente el catálogo público; no representa aislamiento entre empresas, autorización por usuario, inventario ni implementación móvil Flutter/SQLite.

## Datos guardados y actualización

El botón **Descargar catálogo** inicia peticiones `GET /api/catalogo/productos` con `limit=100` y offsets sucesivos desde cero, sin parámetro `q`. Descarga el conjunto público completo aunque haya una búsqueda activa en pantalla. El botón pasa a **Actualizar catálogo local** cuando existe una copia. La navegación habitual no reemplaza ni amplía esa copia automáticamente.

Cada página se comprueba antes de guardar: total y paginación coherentes, cantidad esperada de elementos, productos activos válidos, IDs descendentes y ausencia de IDs o slugs duplicados. Solo se copian estos campos públicos:

| Campo | Contenido |
| --- | --- |
| `id`, `slug`, `nombre`, `descripcion` | Identidad y descripción de la prenda. |
| `precio`, `moneda` | Cadena decimal exacta y moneda `BOB`; no se convierte el importe a flotante. |
| `imagen_url` | URL HTTP/HTTPS o `null`; no se descarga el archivo de imagen. |
| `activo` | Debe ser `true`. |
| `creado_en`, `actualizado_en` | Fechas del contrato público. |

Los campos adicionales que puedan aparecer en una respuesta no se persisten. No se guardan tokens, cabeceras HTTP, credenciales, identidad administrativa ni respuestas de `/api/admin/*` o `/api/auth/*`.

IndexedDB utiliza la base **`vestinova-public-catalog`**, versión 1, almacén `snapshots`. Un solo registro con `scope: "public-catalog"` contiene `schemaVersion`, `downloadedAt`, `total` y `products`. La lista y sus metadatos se reemplazan en una única transacción, después de recibir y validar todas las páginas. Una descarga interrumpida, inválida o que no pueda escribirse conserva la copia anterior completa. También se conserva la copia ante una denegación de acceso; conservarla no implica mostrarla como sustituto de esa denegación.

Cuando el navegador ofrece Web Locks, una exclusión compartida protege la descarga y el guardado entre pestañas del mismo origen. Otra pestaña recibe un mensaje para esperar. Sin esa API se evita el doble envío en la instancia actual; no se garantiza coordinación entre varias pestañas en esos navegadores.

Antes de incorporar contexto multitenant será necesario versionar el almacenamiento, separar claves por empresa y usuario —y alcance de sucursales autorizado— e invalidar o migrar expresamente la copia pública global. No debe reinterpretarse esta copia como información privada autorizada. Las políticas de revocación y conservación de datos autorizados sin conexión quedan pendientes de ese contexto.

Un catálogo publicado con cero prendas produce una **copia válida vacía** y puede reemplazar la copia anterior. Se distingue de no haber descargado ningún catálogo y de un error de almacenamiento. Un detalle cuyo slug no figura en la copia informa que la prenda no está incluida; no genera productos de ejemplo.

La fecha `downloadedAt` se guarda en formato ISO con zona horaria, al completar la descarga. La interfaz la muestra en hora de Bolivia, UTC−04:00, junto con el aviso de que la información puede estar desactualizada. Esta fecha corresponde al equipo que descarga, no a una versión transaccional certificada por PostgreSQL.

La API utiliza `limit`/`offset` y no ofrece una instantánea transaccional para toda la descarga. Las validaciones detectan cambios en totales, duplicados y otras inconsistencias observables, pero no garantizan que todas las páginas correspondan al mismo instante. Un cambio concurrente que conserve el total puede pasar inadvertido. Ante inconsistencias detectadas, se solicita repetir la descarga y se conserva la copia anterior.

## Elección entre red y copia local

Cada consulta intenta acceder primero a la API. Una respuesta correcta muestra información de red. Solo un fallo de transporte representado por `HttpErrorResponse` con estado `0` permite consultar IndexedDB. No se decide el origen únicamente mediante `navigator.onLine`.

Las consultas públicas incluyen la cabecera `ngsw-bypass: true`: el service worker deja pasar su transporte directamente y no transforma el fallo de red en un `504` sintético. Esto permite distinguir una desconexión de un `5xx` real del servidor, sin añadir respuestas de API a Cache Storage.

Las respuestas HTTP `401`, `403`, `404` y `5xx` se muestran como errores o recurso no disponible, según corresponda; no se ocultan mostrando la copia anterior. En la misma ejecución, una denegación `401`/`403` recordada también impide convertir un fallo posterior de transporte en acceso local hasta que una consulta pública correcta restablezca el acceso.

La consulta local busca por nombre, ordena por ID descendente y pagina sobre el conjunto descargado. La pantalla indica **Copia local**, la última descarga y la posible desactualización. Un precio descargado no acredita que siga vigente. Las fotografías externas pueden faltar sin conexión: se conserva su URL y la interfaz usa su alternativa visual cuando no puede cargarlas. La función no garantiza fotografías disponibles sin red ni descarga sus binarios.

## Apertura del catálogo mediante PWA

El service worker se habilita en producción. Precarga `index.html`, JavaScript —incluidos los chunks de rutas aún no visitadas—, CSS, manifest e iconos VN. La navegación que puede resolver sin red se limita a `/catalogo` y sus rutas hijas. `/api`, `/admin` y sus rutas están excluidos de ese reemplazo de navegación.

No hay grupos de caché de datos API ni patrones para guardar recursos remotos. El código estático compartido puede formar parte de los bundles precargados; las respuestas administrativas y las sesiones no se almacenan en esa caché. La apertura de una ruta administrativa sin red no forma parte del incremento.

Hay dos preparaciones independientes: descargar datos en IndexedDB y preparar el shell con el service worker. Para cerrar, recargar o volver a abrir el catálogo sin conexión, ambas deben haber terminado. Guardar datos desde `ng serve` no acredita que el shell esté preparado para una reapertura sin red.

El aviso **Apertura sin conexión preparada** requiere comprobar que todos los recursos de precarga del manifiesto de producción estén presentes en Cache Storage. El resultado de `checkForUpdate()` por sí solo no basta. Al abrir estando ya sin conexión, la interfaz distingue la aplicación abierta con recursos guardados de una preparación nueva.

## Preparación en Windows

Usar Node.js 24 compatible con el proyecto —24.15.0 o posterior de esa línea— y una instalación del MVP cuyo backend ya esté configurado. En otro clon, instalar las dependencias del frontend mediante el lockfile:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\frontend'
node --version
npm.cmd ci
```

Adaptar la ruta al clon propio. En una terminal separada, iniciar el backend normal, si no está ya atendiendo el puerto 8001:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

Esta comprobación no requiere nuevas migraciones, recrear la base, regenerar `.env` ni volver a crear administradores. No agrega productos de demostración ni modifica el esquema. Si el clon todavía no tiene backend configurado, su preparación inicial se trata en el [README](../README.md), fuera de esta comprobación del catálogo local.

En la terminal del frontend:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\frontend'
npm.cmd run build
npm.cmd run preview:pwa
```

Abrir **http://127.0.0.1:4201/catalogo**. El preview sirve el build de producción y reenvía `/api` a `http://127.0.0.1:8001`. Si `ng serve` ocupa el puerto 4201, detener esa instancia con `Ctrl+C` en su propia terminal o elegir otro puerto para el preview:

```powershell
npm.cmd run preview:pwa -- --port 4301
```

En ese caso, usar **http://127.0.0.1:4301/catalogo** durante toda la prueba. No alternar entre `localhost` y `127.0.0.1`, ni entre puertos: IndexedDB y el registro del service worker pertenecen al origen exacto. Una copia guardada en 4201 no es la copia de 4301. Utilizar el mismo perfil de navegador; el modo privado o borrar datos puede eliminar la copia.

## Comprobación manual del recorrido principal

1. Con la red y el backend disponibles, abrir el catálogo en el origen elegido. Buscar una prenda si se desea y pulsar **Descargar catálogo**. En Network, comprobar que las solicitudes de descarga usan `limit=100`, recorren los offsets necesarios y no llevan `q` ni `Authorization`.
2. Esperar el mensaje **Catálogo local actualizado** y comprobar cantidad y fecha de última descarga. Un catálogo vacío debe confirmar cero prendas guardadas. Esperar también **Apertura sin conexión preparada**; ese mensaje es independiente de haber terminado la descarga.
3. En DevTools, abrir **Application → Service Workers** y comprobar que el worker del mismo origen esté activo. Mantener desmarcada la opción **Bypass for network**. En Network, desmarcar **Disable cache** y seleccionar **Offline**.
4. Recargar normalmente la página, con el botón de recarga o `Ctrl+R`. No utilizar `Ctrl+Shift+R`, una recarga forzada ni opciones que omitan el service worker. Debe abrirse el catálogo y aparecer **Copia local**, la fecha en hora de Bolivia y el aviso de desactualización.
5. Buscar por nombre, limpiar la búsqueda y recorrer páginas. Si la copia contiene más de 20 prendas, comprobar el cambio de página. La cantidad de resultados de búsqueda corresponde a los datos descargados.
6. Abrir el detalle de una prenda incluida. Comprobar también una URL directa `/catalogo/SLUG_REAL`, preferentemente de una prenda cuyo detalle no se haya visitado antes de desconectarse. Recargar esa ruta normalmente: el chunk del detalle debe estar disponible porque se precargó. Una URL con un slug ausente de la copia debe informar esa ausencia.
7. Cerrar y volver a abrir la pestaña usando el mismo perfil y origen, sin borrar almacenamiento. Si DevTools restablece la red para la pestaña nueva, volver a seleccionar Offline antes de repetir la recarga. Para comprobar una reapertura sin disponibilidad de los servidores locales, también pueden detenerse los procesos de preview y backend iniciados para esta prueba y volver a abrir el navegador con el mismo perfil. El catálogo debe abrirse desde el shell preparado y consultar la copia local.
8. Restaurar la conexión y los procesos detenidos. Una consulta pública correcta vuelve a mostrar datos de red. La copia solo cambia cuando se pulsa **Actualizar catálogo local** y termina correctamente la nueva descarga.

Si el catálogo real está vacío, comprobar el estado de copia vacía. Las comprobaciones de detalle, resultados de búsqueda y varias páginas requieren datos reales ya existentes o el entorno de fixtures de la prueba de navegador; no es necesario insertar registros en PostgreSQL para acreditar el comportamiento del código.

## Comprobaciones negativas

**Sin copia, conservando el shell.** Después de preparar el service worker, abrir Application → IndexedDB y eliminar únicamente la base **`vestinova-public-catalog`** del origen de prueba. Conservar el registro del service worker y Cache Storage; no usar **Clear site data**, **Unregister** ni el borrado general del perfil. Con Network Offline, recargar normalmente `/catalogo`. El shell debe abrirse y explicar que no hay un catálogo descargado, sin mostrar una lista vacía como si fuese una descarga válida. Después, volver a conectarse y descargar para recuperar el escenario principal.

**Actualización fallida.** Con una copia válida, anotar su fecha y cantidad. Bloquear temporalmente las solicitudes de descarga en DevTools o utilizar el entorno de API controlado de la prueba de navegador; pulsar **Actualizar catálogo local**. La interfaz debe informar el fallo y la copia anterior debe conservar sus datos y metadatos. Al consultar sin conexión, debe seguir estando disponible esa copia. Restaurar los bloqueos al terminar. Un fallo en una página intermedia tampoco debe dejar una copia parcial.

**Respuesta HTTP en línea.** Mediante una API de prueba controlada, responder `403` a una consulta teniendo una copia previa. Debe mostrarse la denegación y no las prendas locales. Comprobar del mismo modo que `401`, `404` y `5xx` no activan fallback. Desconectar Network simula un fallo de transporte, no una respuesta `403`; no sustituye esta comprobación. No cambiar permisos, autenticación ni endpoints del backend operativo para provocarla.

**Separación del almacenamiento.** Inspeccionar el registro de IndexedDB: debe contener únicamente los campos públicos y metadatos descritos. Revisar Cache Storage: el service worker debe guardar el shell y sus recursos estáticos, sin entradas de `/api/*`, cuerpos de respuestas administrativas, cabeceras de autorización o tokens de sesión. No hace falta mostrar ni copiar credenciales para realizar esta inspección.

**Almacenamiento no disponible.** Si el navegador bloquea IndexedDB o no puede escribir, debe aparecer un error de almacenamiento. La aplicación no debe confirmar una descarga que no se haya guardado. El navegador puede expulsar datos por espacio o políticas del perfil; mantener un perfil persistente no garantiza conservación indefinida.

## Comprobaciones automatizadas disponibles

Desde `frontend`, después de instalar las dependencias:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:pwa:config
npm.cmd run test:pwa
```

La comprobación de configuración inspecciona el build generado: manifest, tamaños de iconos, precarga de todos los bundles y exclusión de API y navegación administrativa. La prueba de navegador utiliza Edge mediante CDP, un perfil de prueba y respuestas HTTP controladas como fixtures. No necesita consultar FastAPI ni PostgreSQL, ni escribe datos en la base operativa. Requiere que Edge esté instalado y que el build ya exista.

Estos comandos describen cómo verificar el incremento; este documento no atribuye resultados aún no ejecutados. Los resultados concretos de validación se registran en [AVANCES.md](AVANCES.md).
