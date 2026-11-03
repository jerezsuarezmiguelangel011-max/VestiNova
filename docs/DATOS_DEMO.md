# Datos de demostración de VestiNova

Este entorno sirve para **comprobar los casos de uso con datos consistentes**, sin escribir en la base real de trabajo `vestinova_mvp`.

## Garantías

- Utiliza solamente PostgreSQL local, con el nombre de base `vestinova_pruebas`.
- No modifica el archivo `backend/.env` ni la base `vestinova_mvp`.
- Crea la base demo si falta y le aplica las mismas migraciones Alembic.
- No borra registros, no reemplaza contraseñas y no duplica datos identificados por claves estables.
- Nunca publica contraseñas: se pide una clave mediante entrada oculta en la terminal.
- Los registros de ventas, compras y reservas deberán generarse **mediante la aplicación** para validar reglas de negocio, idempotencia, inventario y auditoría. El poblado base no los simula fraudulentamente.

## Preparación (PowerShell)

En primer lugar, detener el Backend que esté escuchando en `8001` con `Ctrl+C`. El Frontend puede permanecer abierto.

Desde la carpeta del repositorio actualizado en `pruebas`:

```powershell
cd D:\Proyectos\vestinova-mvp\backend
.\.venv\Scripts\python.exe -m scripts.seed_demo
```

El programa usa la conexión **local** definida en `backend/.env`, pero dirige las escrituras a **`vestinova_pruebas`**. Solicita una contraseña de prueba conforme a la política vigente y la confirmación de esta. El texto de las contraseñas no se muestra. Si lo ejecutas nuevamente, las contraseñas de las cuentas existentes no cambian.

Para iniciar FastAPI conectado a los datos de demostración:

```powershell
.\.venv\Scripts\python.exe -m scripts.serve_demo
```

Espera a que aparezca el inicio correcto del servidor. Comprueba `http://127.0.0.1:8001/api/health/db`: debe indicar `vestinova_pruebas`.

En otra terminal, si Angular no está iniciado:

```powershell
cd D:\Proyectos\vestinova-mvp\frontend
npm.cmd start
```

Panel del personal: `http://127.0.0.1:4201/admin/login`

## Usuarios de prueba

Todas las identidades nuevas reciben la **misma contraseña que introdujiste en la terminal**; en ejecuciones posteriores no se restablece automáticamente.

| Perfil | Correo | Empresa |
| --- | --- | --- |
| Superadministrador SaaS | saas.demo@vestinova.test | Acceso de plataforma y Moda Andina |
| Administrador | admin.andina@vestinova.test | Moda Andina |
| Encargado | encargado.andina@vestinova.test | Moda Andina |
| Cajero | cajero.andina@vestinova.test | Moda Andina |
| Cliente | cliente.andina@vestinova.test | Moda Andina |
| Administrador | admin.urbana@vestinova.test | Moda Urbana |
| Encargado | encargado.urbana@vestinova.test | Moda Urbana |
| Cajero | cajero.urbana@vestinova.test | Moda Urbana |
| Cliente | cliente.urbana@vestinova.test | Moda Urbana |

Las cuentas cliente se usan desde `/tienda/<slug>/acceso`, no desde el login de empleados. Las cuentas de personal tienen permisos específicos y no reciben privilegios SaaS, salvo `saas.demo`.

## Registros base

- Empresa `demo-moda-andina`: plan Básico, 2 sucursales.
- Empresa `demo-moda-urbana`: plan Profesional, 3 sucursales.
- Cada empresa cuenta con roles del sistema, 3 empleados y 1 cliente.
- Cada una dispone de 3 categorías, 3 productos con variante talla/color y saldos independientes por sucursal, incluyendo un artículo agotado.
- Las existencias iniciales positivas tienen movimientos de entrada que las respaldan.
- Cada empresa tiene un proveedor, una orden pendiente y una promoción vigente del 10 %.

## Cómo comprobar el CU01

1. Inicia sesión con `admin.andina@vestinova.test`.
2. Entra en `/admin/usuarios`: deben verse solo los usuarios de Moda Andina.
3. Entra en `/admin/roles`: revisa permisos y protección de roles del sistema.
4. Registra un **nuevo empleado adicional desde la pantalla**; verifica su listado, edición y auditoría.
5. Intenta asignarle un rol o una sucursal no autorizados y registra el resultado.
6. Inicia sesión con ese empleado para verificar que no pueda acceder a lo que no le corresponde.
7. Repite comprobaciones de aislamiento con la cuenta de Moda Urbana.

No desactives el único administrador de una empresa al probar el bloqueo: crea otro administrador de prueba o usa pruebas automatizadas aisladas.

## Volver al Backend normal

Detén el servidor demo con `Ctrl+C`, luego arranca el habitual:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

El Backend habitual lee nuevamente `backend/.env` y usa `vestinova_mvp`.

**Limitación:** los datos precargados no sustituyen pruebas funcionales. El ingreso de compras, reservas, retiros, ventas y devoluciones debe probarse con la UI/API en escenarios controlados.
