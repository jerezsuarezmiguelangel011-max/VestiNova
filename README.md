# VestiNova

Implementación nueva y reducida con Angular, FastAPI, SQLAlchemy y PostgreSQL. Todo el trabajo de esta versión vive en esta carpeta. No importa ni reutiliza módulos del proyecto heredado y utiliza exclusivamente la base local `vestinova_mvp`.

La raíz local `vestinova-mvp` se propone como el único repositorio GitHub **VestiNova**, con `backend`, `frontend`, `mobile` y `docs`. La carpeta `mobile` contiene únicamente una reserva documentada: el Flutter heredado no está incorporado. Consulta [la revisión móvil](docs/REVISION_MOVIL.md), [la ejecución y URLs de API](docs/EJECUCION_Y_API.md) y [los comandos de publicación en PowerShell](docs/PUBLICACION_GITHUB.md). La publicación pública todavía no se ha ejecutado.

Repositorio acordado: **`saletty/VestiNova`**; colaborador: `jerezsuarezmiguelangel011-max`. Se preparó el uso de cuatro ramas: `main`, `pruebas`, `salet` y `miguel`. Su creación y flujo de integración están en [RAMAS_Y_COLABORACION.md](docs/RAMAS_Y_COLABORACION.md); todavía no se ejecutaron commits ni push.

## Alcance

Implementado: inicio/restauración/cierre de sesión de administrador; protección de rutas y API; listado, registro y edición de productos; catálogo público con búsqueda por nombre, paginación y detalle; migración inicial versionada y creación local del administrador con hash Argon2.

El primer incremento de CU09 ofrece las pantallas públicas `/catalogo` y `/catalogo/{slug}`, conforme a [docs/CONTRATO_CATALOGO.md](docs/CONTRATO_CATALOGO.md). Muestra datos publicados, precios BOB e imágenes cuando existen, con estados de carga, vacío, error y producto no disponible. La raíz del frontend conserva su redirección administrativa. Siguen pendientes variantes, empresas, promociones, disponibilidad por sucursal y consulta sin conexión por empresa y usuario; este incremento no completa el CU09 académico. La confirmación productiva de compras y los flujos integrados de inventario, pagos, reservas y SaaS siguen sujetos a las dependencias de cada incremento.

El incremento limitado de CU14 permite descargar explícitamente el catálogo público completo en IndexedDB y consultarlo sin conexión, con búsqueda, paginación, detalle y fecha de descarga. La PWA prepara la apertura y recarga del catálogo en el mismo navegador y origen. No implementa el alcance académico de datos autorizados por empresa y usuario. La preparación en Windows, las comprobaciones manuales y las limitaciones están en [docs/CU14_OFFLINE.md](docs/CU14_OFFLINE.md).

- Primer incremento limitado de CU08: reglas de stock y ajuste por recuento, contratos de autorización y unidad de trabajo, con adaptadores en memoria exclusivos de pruebas. Sin API, UI ni persistencia integradas; alcance en [docs/CONTRATO_INVENTARIO.md](docs/CONTRATO_INVENTARIO.md).

CU10 incorpora selección temporal de prendas en `/catalogo/acciones/compra?slug=SLUG_REAL`, API y dos tablas propias de compras mediante la revisión `cu10_01_compras`. La confirmación permanece bloqueada (`503`) sin proveedores reales de contexto autorizado e inventario. CU15 ofrece una cola persistente de actualizaciones del catálogo público en `/catalogo/acciones/sincronizacion`, con procesamiento manual y detección de conflictos de la copia local. Alcance, dependencias y recorrido PWA en [docs/CU10_CU15_INCREMENTOS.md](docs/CU10_CU15_INCREMENTOS.md).

## Estructura

```text
vestinova-mvp/
  backend/
    app/                  # Configuración, modelos, autenticación y productos
    migrations/           # Alembic; esquema propio, sin create_all en instalación
    scripts/              # Configuración privada, base, administrador y pruebas PostgreSQL
    tests/                # API y reglas con SQLite aislado
    tests_postgres/       # Migración y persistencia sobre PostgreSQL temporal
  frontend/
    src/app/auth/         # Acceso, sesión, guardas e interceptor
    src/app/catalog/      # Catálogo público, búsqueda, paginación y detalle
    src/app/layout/       # Navegación y sesión administrativa
    src/app/products/     # Listar, registrar y editar
  mobile/
    README.md             # Aplicación pendiente de decisión; sin código heredado
  docs/
```

## Preparación en Windows / PowerShell

Requisitos verificados localmente: Python 3.14, Node.js 24 y PostgreSQL 18 en ejecución. No se necesitan las dependencias instaladas del proyecto heredado.

Desde `vestinova-mvp/backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m scripts.configure_local
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m scripts.create_admin
```

`configure_local` solicita servidor, puerto, usuario y contraseña de PostgreSQL; la contraseña se introduce oculta. Escribe únicamente `backend/.env`, genera un secreto JWT y codifica correctamente caracteres especiales de la conexión `postgresql+psycopg`. Para cambiar tu contraseña de conexión, vuelve a ejecutar este comando; reemplazar el secreto JWT invalida las sesiones anteriores.

`init_db` crea `vestinova_mvp` si falta y aplica `alembic upgrade head`. Si ya existe, conserva sus datos. Requiere permiso de creación de base cuando todavía no existe. La configuración rechaza otras bases, servidores remotos y parámetros que sustituyan el destino. No lee el `.env` heredado ni modifica `vestinova`.

`create_admin` solicita nombre, correo y contraseña nueva dos veces, con entrada oculta. Solo persiste el hash Argon2 y verifica ese hash antes de guardar. Si el correo ya existe, no sobrescribe la cuenta ni su contraseña. No hay credenciales predeterminadas ni registros de demostración.

La política de contraseñas nuevas está centralizada en `backend/app/password_policy.py`. El mensaje y la regla son:

> La contraseña debe tener entre 8 y 128 caracteres e incluir una mayúscula, una minúscula, un número y un carácter especial.

Los extremos 8 y 128 son válidos. Un espacio no cuenta como carácter especial; no se recorta ni transforma la contraseña. Se exige esta política al crear el administrador. Actualmente no existen otros flujos de creación/cambio de contraseña ni formularios frontend para ellos. El login mantiene su validación de acceso y puede verificar contraseñas anteriores sin imponer la política de alta ni cambiar sus hashes.

Desde `vestinova-mvp/frontend`:

```powershell
npm.cmd ci
```

El `.gitignore` excluye `.env`, claves privadas, `.venv`, `node_modules`, archivos de ejecución y resultados de compilación. Se versionan `.env.example`, migraciones, código, pruebas, configuraciones y `package-lock.json`.

`requirements.lock.txt` fija las versiones directas y transitivas verificadas, incluidas las herramientas de pruebas. `requirements.txt` y `requirements-dev.txt` conservan la selección directa para actualizarla de forma explícita; después de actualizar, regenerar el lock y repetir pruebas.

El frontend fija Angular 22.2.3, CLI/build 22.2.4 y un override de parche Vite 8.3.3 para las herramientas de desarrollo. Ese conjunto pasó build, pruebas y auditoría npm sin avisos de vulnerabilidad. Revisar el override cuando se actualice Angular, en lugar de ejecutar `npm audit fix --force` sin comprobar compatibilidad.

## Ejecutar

Terminal del backend, desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

Terminal del frontend, desde `frontend`:

```powershell
npm.cmd start
```

| Revisión | Dirección |
| --- | --- |
| Catálogo público | http://127.0.0.1:4201/catalogo |
| Detalle público | `http://127.0.0.1:4201/catalogo/SLUG_REAL` |
| Preparar compra | `http://127.0.0.1:4201/catalogo/acciones/compra?slug=SLUG_REAL` |
| Cola pública de sincronización | http://127.0.0.1:4201/catalogo/acciones/sincronizacion |
| Acceso del administrador | http://127.0.0.1:4201/admin/login |
| Listado | http://127.0.0.1:4201/admin/productos |
| Registro | http://127.0.0.1:4201/admin/productos/nuevo |
| Edición | `http://127.0.0.1:4201/admin/productos/ID_REAL/editar` |
| Documentación API | http://127.0.0.1:8001/docs |
| Estado de PostgreSQL | http://127.0.0.1:8001/api/health/db |
| API del catálogo público | http://127.0.0.1:8001/api/catalogo/productos |

El frontend usa URLs relativas `/api` y su proxy local apunta al puerto 8001. Estos puertos permiten conservar los servidores heredados sin confundir ambos proyectos.

## Sesión y permisos

Cada petición administrativa comprueba JWT firmado, expiración, tipo de sesión, administrador activo y una sesión persistida no revocada. El logout revoca esa sesión en PostgreSQL. Volver a usar su token responde `401`. No hay registro público de administradores.

Angular restaura la identidad mediante `/api/auth/me` antes de abrir rutas protegidas. Guarda el token en `sessionStorage`; el interceptor lo envía exclusivamente a los endpoints administrativos/de sesión. Las consultas públicas no reciben ese token. Si falla temporalmente la revocación al salir, muestra el error y permite reintentar; no anuncia un cierre confirmado por el servidor.

## Productos y diseño

Productos tiene nombre, slug único, descripción, precio decimal positivo, moneda fija BOB, imagen externa opcional y visibilidad. El precio se almacena en `NUMERIC(10,2)` y viaja como cadena decimal; el frontend no usa flotantes para construirlo. El PATCH envía solo cambios. La API pública oculta productos inactivos.

Identidad visual: marfil `#f6f4ed`, carbón `#202a25`, esmeralda `#116149`; títulos Georgia y controles Segoe UI/Arial, sin fuentes externas. Los estilos comunes definen botones, campos, tarjetas y alertas. Formularios con etiquetas visibles, foco por teclado, controles cómodos en móvil y estados de espera, vacío, error y confirmación a partir de respuestas reales.

## Pruebas y compilación

Desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m scripts.test_postgres --pg-bin 'C:/Program Files/PostgreSQL/18/bin'
```

La segunda orden levanta y detiene una instancia PostgreSQL temporal en un puerto distinto, aplica Alembic y verifica persistencia. No utiliza las credenciales del `.env` ni limpia bases del usuario. Conserva registros ignorados por Git en `backend/.runtime`.

Desde `frontend`:

```powershell
npm.cmd test
npm.cmd run build
```

Las pruebas cubren reglas de contraseña nueva, compatibilidad de acceso, revocación, rutas privadas, validaciones, precios y registro/edición/listado. El estado final de ejecución se documenta en [docs/AVANCES.md](docs/AVANCES.md).

## Migraciones y trabajo compartido

La migración `0001_base` crea administradores, sesiones y productos, con claves, índices y restricciones. Esta implementación no requiere procedimientos, triggers ni datos heredados. No usar `create_all()` para instalar la aplicación ni editar una migración ya aplicada: añadir la siguiente revisión Alembic cuando cambie el esquema.

El repositorio Git local se inicializó únicamente aquí. No se configuró publicación ni se hizo push durante la preparación original. Para cada avance incluir código, pruebas, migraciones, documentación y archivos de dependencias que necesite ese estado ejecutable. Una ruta o importación nunca debe referenciar un archivo omitido del commit. El MVP de acceso y productos ya cuenta con el primer incremento del catálogo y detalle públicos sobre el contrato compartido. Las ampliaciones académicas de CU09 siguen pendientes. No se crean copias ni ZIP por entrega.

Referencias técnicas: [Angular: compatibilidad](https://angular.dev/reference/versions), [FastAPI: JWT y hash](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [Alembic: migraciones](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
