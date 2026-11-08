# CU10 — Gestionar reservas de prendas

> **Actualización offline en esta rama:** se añadieron IndexedDB, sincronización de
> reservas y copia de catálogo en Angular PWA, junto con SQLite y reservas de
> clientes en Flutter. Los detalles, la matriz de requisitos, pruebas y límites
> están en [CU10_OFFLINE_WEB_MOVIL.md](CU10_OFFLINE_WEB_MOVIL.md).
>
> **Estado:** código implementado pero NO aprobado: faltan build/tests nuevos,
> pruebas Android y aceptación de concurrencia PostgreSQL. No fusionar aún a miguel.


## Estado de este incremento

Rama: `trabajo/cu10-miguel`, creada desde `miguel` después de integrar CU09.
**No integrar a `miguel` hasta ejecutar pruebas, revisar la migración y realizar
un recorrido manual de confirmación y cancelación.**

La fuente funcional es la tabla CU10 del punto 2.6 del documento
**VestiNova — Segundo Parcial**: reserva confirmada con vencimiento configurable,
stock comprometido sin descontar stock físico, cancelación y vencimiento
idempotentes, control multitenant y trazabilidad.

### Incluido en esta entrega

- API de cliente `/api/tiendas/{slug}/reservas`: registrar, listar, consultar y cancelar.
- API interna `/api/admin/reservas`: registrar para un cliente de la misma
  empresa, listar por sucursal autorizada, consultar y cancelar.
  Los perfiles admitidos en esta etapa son administrador, encargado de sucursal
  y cajero, con validación de pertenencia y sucursal.
- `reservas_cu10`: UUID, código, cliente, empresa, sucursal, variantes,
  cantidades, estado, vencimiento e historial de eventos.
- Bloqueos y revalidación de existencias; el alta incrementa
  `cantidad_comprometida` y deja `cantidad` intacta.
- Reenvío idempotente por UUID y huella de contenido; no permite cambiar
  variante, cantidad, cliente, sucursal ni empresa utilizando el mismo UUID.
- Cancelación y vencimiento liberan una única vez; ninguna operación genera
  un movimiento físico de venta.
- Angular: borrador local, envío autenticado, código y fecha de vencimiento,
  historial y cancelación.
- Horas de vigencia configuradas por `RESERVATION_TTL_HOURS` (1 a 720,
  valor predeterminado 24).

### Dependencias y pendientes

1. El borrador web **no es una reserva offline sincronizable**: se guarda en
   `sessionStorage` y no garantiza persistencia permanente. Falta la cola
   local persistente, el proceso de sincronización y su manejo de conflictos
   con CU13/CU15 según la tabla documental.
2. La interfaz Flutter no está integrada en este incremento.
3. La interfaz administrativa está incluida en `/admin/reservas`, pero
   requiere pruebas visuales y de permisos. El registro solicita el ID del
   cliente; mejorar la búsqueda de clientes por correo antes del despliegue.
4. El vencimiento se procesa al consultar o crear reservas. Se incluye
   `python -m scripts.expire_reservations_demo` para barrer la base demo;
   falta programar su ejecución automática en un entorno desplegado.
5. La atención física y entrega de reservas se realizará en el caso de uso
   correspondiente; CU10 **no debe** descontar el inventario físico.
6. Requiere pruebas de concurrencia con PostgreSQL real, pruebas web
   manuales, y validar las reglas finales de vencimiento/cancelación
   con la documentación aprobada.

## Cómo probar en el equipo, sin tocar la base principal

```powershell
cd D:\Proyectos\vestinova-mvp
git fetch origin
git switch trabajo/cu10-miguel
git pull --ff-only origin trabajo/cu10-miguel

cd backend
.\.venv\Scripts\python.exe -m scripts.migrate_demo
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cu10_reservas_online.py
.\.venv\Scripts\python.exe -m scripts.expire_reservations_demo
.\.venv\Scripts\python.exe -m scripts.serve_demo
```

En otra terminal:

```powershell
cd D:\Proyectos\vestinova-mvp\frontend
npm.cmd run build
npm.cmd start
```

Entrar a una empresa demo desde la portada, escoger una prenda, ir a
`/catalogo/acciones/reserva?tienda=demo-moda-andina&slug=<slug>`,
guardar borrador e ingresar como cliente de esa empresa. Confirmar y
verificar código y fecha. Después cancelar y consultar el historial.

**La migración `scripts.migrate_demo` se aplica exclusivamente a
`vestinova_pruebas`**. No usar `scripts.init_db` ni ejecutar Alembic
contra `vestinova_mvp` para estas pruebas.

Verificar en la base demo que `existencias.cantidad` permanece
constante y `cantidad_comprometida` aumenta al confirmar y disminuye
al cancelar o vencer. No crear datos de prueba sobre producción.

## Criterios de aprobación

- Ninguna reserva sin autenticación, empresa y sucursal válidas.
- Nunca comprometer más cantidad que el stock físico libre.
- Nunca registrar dos reservas con la misma operación UUID.
- Lecturas y cancelaciones limitadas al cliente o personal autorizado.
- Cancelaciones y vencimientos sin doble liberación.
- Enlace con checkout CU09: compra solo sobre `cantidad -
  cantidad_comprometida`.
- Web, Flutter y offline solo se consideran completos después de pruebas
  propias; los tests SQLite no sustituyen PostgreSQL concurrente.

**Autoría:** la integración definitiva a `miguel` será realizada por el
usuario mediante `git merge --squash`, `git commit` y `git push`,
para generar un commit propio sin reescribir el historial.
