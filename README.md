# VestiNova

Monorepositorio propio: FastAPI/SQLAlchemy/PostgreSQL en `backend/`, Angular en `frontend/`, Flutter en `mobile/` y contratos en `docs/`. No incorpora código ni historial heredados. Utiliza exclusivamente la base local `vestinova_mvp`.

Cuenta/acceso de personal y Cliente por tienda en web y Flutter propio. Correo Cliente único por empresa; Argon2 y sesiones revocables. El personal selecciona empresa después del login. CU01 mantiene aceptación parcial por verificaciones pendientes de actores/recorridos.

## Preparación local — PowerShell

Entorno comprobado: Python 3.14, Node.js 24 y PostgreSQL 18. Requisitos de Node en `frontend/package.json`; requisitos móviles en [mobile/README.md](mobile/README.md).

Desde la raíz del repositorio, en una instalación nueva:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m scripts.configure_local
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m scripts.create_admin
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

Las contraseñas se introducen ocultas en la terminal. Cada integrante configura su `.env`; no compartir credenciales. Si ya está configurado, conservar `.env`, administrador y datos; aplicar migraciones con `scripts.init_db` sin recrear cuentas. No usar `create_all()` ni editar migraciones aplicadas.

En otra terminal, desde la raíz:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd start
```

- Personal: http://127.0.0.1:4201/admin/login
- Cliente: http://127.0.0.1:4201/tienda/vestinova-inicial/acceso
- API/Swagger: http://127.0.0.1:8001/docs
- Salud y PostgreSQL: http://127.0.0.1:8001/api/health/db

Angular usa `/api` y su proxy apunta a `127.0.0.1:8001`. No iniciar otra instancia sobre un puerto ya ocupado. El móvil usa la misma API y su configuración se explica en su README.

## Contratos para trabajar en equipo

- [Casos de uso y responsables](docs/CASOS_DE_USO.md).
- [Catálogo y detalle públicos](docs/CONTRATO_CATALOGO.md): paginación, slug, precio decimal como cadena y moneda BOB.
- [Cuenta y acceso por tienda](docs/CONTRATO_CU01_CUENTAS.md).
- [Empresas, pertenencias, sucursales e inventario](docs/BASE_BACKEND_EMPRESAS_INVENTARIO.md).
- [Descarga privada, existencias y movimientos](docs/CONTRATO_DESCARGA_MOVIL.md).

Salet: CU01–CU07, CU12 y CU13. Miguel: CU08–CU11; conserva sus pantallas de catálogo/detalle. CU14–CU28 siguen por confirmar. No cambiar contratos públicos sin coordinar. Reservas, compras/ventas, sincronización comercial y planes siguen pendientes según el alcance acordado; disponer de una API parcial no completa sus casos de uso.

## Verificación

Desde `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.test_postgres --pg-bin 'C:/Program Files/PostgreSQL/18/bin'
```

El runner usa PostgreSQL temporal, separado de la base operativa. Desde `frontend/`: `npm.cmd test` y `npm.cmd run build`. Las pruebas controladas de DOM/widgets se distinguen de recorridos reales contra la API. El móvil documenta sus propias comprobaciones.

## Git y configuración privada

Repositorio `saletty/VestiNova`; ramas `main`, `pruebas`, `salet` y `miguel`. Cada integrante trabaja en su rama. Proponer la integración en `pruebas` y después en `main`; no sobrescribir el trabajo del compañero ni publicar otras ramas por accidente.

Se versionan fuentes, migraciones, scripts, pruebas, ejemplos sin secretos y lockfiles. `.env`, entornos, dependencias instaladas, compilados/APK y claves están ignorados. Los informes de avance, auditorías y evidencias permanecen locales: Git contiene solo estos README y los contratos compartidos.
