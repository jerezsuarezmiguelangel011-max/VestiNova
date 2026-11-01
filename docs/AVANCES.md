# Avances verificables

25 de octubre de 2026. Versión propia dentro de `vestinova-mvp`.

## Terminado

- Incremento limitado de CU10: selección temporal de prendas, API y persistencia propia de compras mediante `cu10_01_compras`; confirmación productiva bloqueada sin proveedores reales de autorización e inventario. [Contrato y recorrido](CU10_CU15_INCREMENTOS.md).
- Incremento limitado de CU15: cola IndexedDB de actualización del catálogo público, con UUID, estados persistidos, procesamiento/reintento manual y conflicto ante cambios en la fecha local. Sin sincronización de escrituras privadas ni reservas; [alcance y comprobación manual](CU10_CU15_INCREMENTOS.md).
- Primer incremento limitado de CU08: dominio inmutable, ajuste por recuento y contratos de autorización/unidad de trabajo verificables con adaptadores en memoria solo de pruebas. Sin conexión con API, UI, PostgreSQL o autenticación actual; [contrato y alcance pendiente](CONTRATO_INVENTARIO.md).
- Estructura independiente Angular/FastAPI/SQLAlchemy/PostgreSQL, configuraciones y dependencias fijadas.
- Base nueva `vestinova_mvp`, con Alembic `0001_base`; inicialización repetible sin borrar registros.
- Configuración `.env` privada y creación local del administrador con entrada de contraseña oculta y hash Argon2. El usuario confirmó la creación del administrador del MVP.
- Autenticación de administrador, restauración y revocación persistida al cerrar sesión; validación de cuenta activa y autorización en cada operación privada.
- Listado de productos con búsqueda, visibilidad y paginación real; registro y edición parcial con persistencia, validaciones y precios decimales.
- Endpoints públicos que solo devuelven productos activos y contrato compartido para catálogo/detalle.
- Primer incremento de CU09 en la rama `miguel`: pantallas públicas `/catalogo` y `/catalogo/{slug}`, búsqueda por nombre, paginación de servidor, precios BOB, imágenes opcionales y estados de carga, vacío, error y producto no disponible.
- Incremento limitado de CU14: descarga explícita del catálogo público completo en IndexedDB, consulta local con fecha y preparación del shell mediante PWA. No incluye datos por empresa/usuario ni completa el CU14 académico. Alcance y procedimiento de comprobación en [CU14_OFFLINE.md](CU14_OFFLINE.md).
- Interfaz administrativa marfil/carbón/esmeralda, formularios con etiquetas, foco visible, estados reales y adaptación a móvil.
- Política centralizada para contraseñas nuevas: 8–128 caracteres, mayúscula, minúscula, número y carácter especial. Mensaje exacto solicitado; login y hashes previos conservados.
- `.gitignore` comprobado: excluye credenciales, entorno virtual y dependencias; no excluye archivos necesarios para reproducir la aplicación.

## Comprobaciones de la base inicial

| Comprobación | Resultado |
| --- | --- |
| Backend: `pytest tests -q` | 88 pruebas correctas: autenticación, permisos, productos, configuración y política de contraseñas. |
| PostgreSQL temporal: `scripts.test_postgres` | 3 pruebas correctas: Alembic repetible, revocación persistida y registro/edición consultados desde sesiones nuevas. |
| Frontend: `npm.cmd test` | 45 pruebas correctas, incluidas rutas privadas y login con contraseña anterior corta. |
| Producción: `npm.cmd run build` | Compilación correcta. |
| Dependencias frontend: `npm.cmd audit` | Sin vulnerabilidades reportadas con el lockfile definitivo. |
| Base operativa nueva | `/api/health/db` responde `ok` sobre `vestinova_mvp`; catálogo inicialmente vacío, sin productos ficticios. |
| Datos anteriores | No se accedió ni se escribió en `vestinova`; el código heredado no se modificó durante esta implementación nueva. |

Las comprobaciones iniciales de UI usaron DOM. El incremento de CU14 añade una prueba de navegador real y capturas de escritorio/móvil con fixtures; la revisión manual con datos propios sigue siendo útil.

## Verificación del primer incremento de CU09

Comprobaciones ejecutadas el 25 de octubre de 2026 en la rama `miguel`, con Node.js 24.15.0:

- `npm.cmd test`: 67 pruebas de frontend correctas, incluidas 22 nuevas para contrato público, navegación sin sesión, listado, búsqueda, paginación, detalle, errores e imágenes. Incluyen el retroceso cuando se reduce el catálogo mientras se navega.
- `npm.cmd run build`: compilación de producción correcta.
- Backend: `python -m pytest tests/test_products.py -k 'public_contract or filters_pagination or search_does_not or missing_products' -q --tb=short`: 4 pruebas correctas y 31 no seleccionadas. Usan SQLite aislado, sin modificar PostgreSQL ni datos operativos.

No se añadieron datos de demostración, dependencias ni cambios en autenticación, pantallas administrativas, esquema de base de datos o diagramas ICONIX. No se realizaron commits ni push. La comprobación visual con los productos propios en un navegador queda como revisión manual.

## Verificación del incremento público de CU14

Comprobaciones ejecutadas el 25 de octubre de 2026 en `miguel`, con Node.js 24.15.0:

| Comprobación | Resultado |
| --- | --- |
| `npm.cmd test` | 168 pruebas correctas en 15 archivos, incluidas IndexedDB, rollback, descargas paginadas y fallidas, consulta local, fechas, rechazos de autorización y preparación PWA. |
| `npm.cmd run build` | Compilación de producción correcta. |
| `npm.cmd run test:pwa:config` | 20 recursos precargados verificados; navegación offline solo de catálogo y sin caché de respuestas API. |
| `npm.cmd run test:pwa` | 10 comprobaciones correctas en Edge sin ventana, con perfil temporal, API de fixtures y servidor de la aplicación detenido durante el recorrido offline. |
| Revisión visual | Capturas de catálogo en escritorio y detalle en móvil, con los avisos locales y la identidad visual de VestiNova. |

La prueba de navegador descargó 121 productos de prueba en dos páginas y verificó que una actualización fallida conserva productos y fecha; un `403` no permite consultar la copia; el catálogo y un detalle no visitado se abren sin red; otra pestaña conserva la consulta; Cache Storage no contiene respuestas API; y la ausencia de copia tiene mensaje propio. Los fixtures solo existen en el servidor temporal de la prueba: no se utilizó FastAPI ni PostgreSQL, ni se insertaron registros operativos.

Los módulos administrativos, el backend, las migraciones y los diagramas ICONIX permanecen sin cambios. No se hicieron commits ni push. El [procedimiento manual](CU14_OFFLINE.md) explica cómo comprobar el build PWA desde el navegador y diferencia este incremento público del CU14 académico completo.

## Verificación del primer incremento de CU08

- Núcleo y contratos nuevos en `backend/app/inventory/`, sin registro de rutas, modelos ORM ni integración de autenticación.
- `python -m pytest tests -q --tb=short`: 266 pruebas correctas, incluidas 178 nuevas de CU08 (148 de dominio y 30 de servicio).
- `npm.cmd test`: 168 pruebas de frontend correctas para conservar CU09 y CU14.
- Las pruebas de CU08 verifican cantidades, cálculo de disponible, ajustes por recuento, autorización por contrato, referencias incompatibles, trazabilidad y conservación de saldo/movimientos ante fallos simulados.
- No se modificaron frontend, módulos administrativos, tablas, migraciones ni diagramas; no se ejecutaron migraciones ni se hicieron commits o push. La persistencia y concurrencia PostgreSQL siguen pendientes.

Reglas y límites en [CONTRATO_INVENTARIO.md](CONTRATO_INVENTARIO.md).

## Verificación del primer incremento de CU11

- Dominio, servicio y contratos nuevos en `backend/app/reservations/`, basados en la ficha oficial transcrita por el usuario y sin modificar CU08, CU09 ni CU14.
- `python -m pytest tests/reservations -q --tb=short`: 101 casos correctos, 42 de dominio y 59 de servicio.
- `python -m pytest tests -q --tb=short`: 367 pruebas backend correctas; `npm.cmd test`: 168 pruebas frontend correctas.
- Confirmación central, consulta, cancelación, vencimiento explícito y validación de solicitudes offline. Configuración de plazo obligatoria, sin duración predeterminada ni anticipos inventados.
- Se verificaron aislamiento por empresa/sucursal/cliente, stock insuficiente, rollback conjunto, reenvíos idempotentes por UUID, código único, liberación una sola vez y concurrencia sobre la última unidad con dobles de prueba.
- Reutiliza referencias y `StockBalance` de CU08; el contrato de inventario compromete unidades sin descontar el físico. Ningún adaptador ficticio se instala en producción.
- Pendientes: persistencia y concurrencia PostgreSQL, autorización real, API/UI, cola y almacenamiento offline/CU15, proceso automático de vencimiento e integración con CU16. No se crearon migraciones ni se hicieron commits, push o integración de ramas.

Fuente, reglas y límites en [CONTRATO_RESERVAS.md](CONTRATO_RESERVAS.md).

## Verificación de los incrementos mínimos de CU10 y CU15

Comprobaciones ejecutadas el 25 de octubre de 2026 en `miguel`, con Node.js 24.15.0:

| Comprobación | Resultado |
| --- | --- |
| `python -m pytest tests -q --tb=short` | 461 pruebas backend correctas; 94 corresponden a compras. Incluyen autorización, aislamiento, idempotencia, reenvío concurrente, persistencia y rollback conjunto con inventario de pruebas. |
| `python -m scripts.test_postgres --pg-bin 'D:\PostgreSQL\bin'` | 6 pruebas correctas sobre un clúster temporal: migraciones repetibles, precisión decimal, FK interna por empresa y rollback, además de la regresión administrativa. |
| `npm.cmd test` | 233 pruebas frontend correctas en 19 archivos, incluidas selección, comprobantes, IndexedDB, procesamiento de cola, reintentos, conflictos y Web Locks. |
| `npm.cmd run build` | Compilación de producción correcta. |
| `npm.cmd run test:pwa:config` | 22 recursos precargados; las respuestas API siguen fuera de CacheStorage. |
| `npm.cmd run test:pwa` | 14 comprobaciones correctas en Edge: selección sin confirmaciones artificiales, cola pública real, actualización exitosa, conflicto, persistencia offline y regresión completa de CU14. API temporal sin utilizar PostgreSQL operativo. |

La revisión visual de las capturas de compra y sincronización confirma el uso de
la tipografía y los colores actuales de VestiNova. Los archivos generados de prueba
quedan en `frontend/.angular/`, fuera del código versionado.

La base local `vestinova_mvp` quedó actualizada mediante la revisión aditiva
`cu10_01_compras`; `alembic current` confirma esa revisión como `head`. Solo se
añadieron `compras_digitales` y `compras_digitales_lineas`, sin crear maestros,
insertar compras de demostración ni modificar las tablas de otros módulos.
CU15 conserva únicamente metadatos del catálogo público en IndexedDB y no añade
tablas PostgreSQL. La confirmación productiva de CU10 sigue bloqueada mientras
no se conecten los proveedores reales; los escenarios confirmados de pruebas no
habilitan ventas en la aplicación.

No se cambiaron autenticación, pantallas administrativas, núcleos de CU08/CU11 ni
diagramas ICONIX. No se hicieron commits, push ni integración de ramas. El
[recorrido manual y alcance pendiente](CU10_CU15_INCREMENTOS.md) explica cómo
comprobar ambas pantallas sin atribuirles integraciones todavía inexistentes.

## Pendiente

- CU10/CU15 completos: conectar clientes, empresas, sucursales, variantes e inventario reales para confirmar compras; integrar contexto por empresa/usuario y sincronización de escrituras privadas. La selección y cola pública implementadas no sustituyen esas dependencias.
- CU11 completo: conectar el núcleo ya probado con persistencia y autorización reales, API/UI, almacenamiento local y sincronización de CU15, automatización de vencimientos y atención de CU16. Alcance del incremento en [CONTRATO_RESERVAS.md](CONTRATO_RESERVAS.md).
- CU09 académico completo: integración con categorías/variantes de CU05, promociones de CU06, disponibilidad por variante/sucursal de CU08, aislamiento empresarial y copia local autorizada por empresa/usuario de CU14. La copia pública del incremento limitado de CU14 no cubre esas integraciones.
- Prueba manual con productos reales: crear, editar, recargar, salir y comprobar que una URL privada exige nuevo acceso. No se insertaron registros de muestra en la base operativa.
- Funciones pendientes como flujos productivos completos: cambio/recuperación de contraseña, altas de administradores desde la web, gestión de roles, carga de archivos, inventario integrado, compras con proveedores reales, ventas, reservas integradas y SaaS. Los núcleos y pantallas parciales se describen en sus respectivos incrementos.

## Commits y entregas

El repositorio local solo se inicializó en esta carpeta; no hay commits, remoto ni push realizados. Antes del primer commit, incluir juntos todos los archivos ejecutables de este MVP: frontend, backend, migración, scripts, tests, ejemplos de configuración, lockfiles y documentación. Las importaciones actuales enlazan acceso y productos, por lo que no debe excluirse un módulo necesario para intentar separar artificialmente ese estado inicial.

Primer avance propuesto: `feat(mvp): iniciar acceso administrativo y gestión de productos`. El catálogo público y el detalle del primer incremento de CU09 ya están implementados y verificados como se describe arriba; sus siguientes ampliaciones requieren las integraciones pendientes. Revisar `git status --short` y ejecutar las pruebas antes de confirmar. No versionar `.env`, `.venv`, `node_modules`, `dist` ni `.runtime`; no generar copias ni ZIP por avance.

## Preparación de repositorio compartido

Se preparó la estructura `backend`, `frontend`, `mobile` y `docs` dentro de esta raíz para el futuro GitHub público `VestiNova`. `mobile` solo reserva la ubicación: la aplicación Flutter heredada permanece fuera y no se copió, movió o restauró. Su estado no ejecutable y las diferencias de contrato están en [REVISION_MOVIL.md](REVISION_MOVIL.md). No se encontró una rúbrica del segundo parcial que permita certificar funciones móviles.

Se revisaron repositorios e historial, se ampliaron exclusiones para Flutter/firmas/copias de configuración y se conservaron datos y credenciales privadas. El ejemplo público de configuración tiene marcadores explícitos. El [resumen de auditoría](AUDITORIA_GIT_Y_SECRETOS.md), la [guía de ejecución y API](EJECUCION_Y_API.md) y los [comandos de publicación](PUBLICACION_GITHUB.md) distinguen lo listo para incluir de las decisiones pendientes. El informe histórico detallado queda ignorado en `docs/_local/`. No se ejecutaron staging, commits, creación de remoto, push ni invitaciones.

Se confirmó el repositorio público `saletty/VestiNova`, el colaborador `jerezsuarezmiguelangel011-max` y las ramas `main`, `pruebas`, `salet` y `miguel`. Se actualizaron los comandos para crearlas desde el primer commit y publicarlas juntas, con `main` predeterminada. El [flujo de colaboración](RAMAS_Y_COLABORACION.md) propone integrar las ramas personales en `pruebas` y después en `main`. Estas operaciones siguen pendientes de ejecución por el usuario.
