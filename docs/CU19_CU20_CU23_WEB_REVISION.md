# VestiNova · Revisión funcional del primer grupo web (CU19, CU20 y CU23)

**Alcance:** Angular web + FastAPI + PostgreSQL. El móvil Flutter se realizará posteriormente.
**Rama temporal:** `trabajo/web-cu19-cu20-cu23`, creada desde `miguel`.
**Regla de integración:** no fusionar esta rama a `miguel` hasta que el responsable haya revisado y ejecutado las pruebas locales. El commit final lo realiza el responsable con `git merge --squash`.

## Antes de revisar

1. Desde la rama temporal, ejecutar `git pull --ff-only origin trabajo/web-cu19-cu20-cu23`.
2. Para el backend demo aislado, ejecutar `cd backend` y
   `.\.venv\Scripts\python.exe -m scripts.migrate_demo` para crear la tabla `deseos_cu23` y habilitar el permiso de reportes en roles del sistema.
3. Reiniciar el servidor demo con `.\.venv\Scripts\python.exe -m scripts.serve_demo` (puerto 8001).
4. En `frontend`, ejecutar `npm.cmd run build` y `npm.cmd test`.
5. Ejecutar `.\.venv\Scripts\python.exe -m pytest -q tests/test_cu19_cu20_cu23.py` desde `backend`.
6. La base `vestinova_mvp` permanece intacta mientras se use exclusivamente `scripts.migrate_demo` y `scripts.serve_demo`.

## CU19 · Recomendaciones

- Abrir `http://127.0.0.1:4201/tienda/demo-moda-andina/recomendaciones`.
- Verificar que se muestren únicamente prendas publicadas de esa tienda.
- Abrir una prenda y pulsar «Ver prendas similares · CU19» para usarla como referencia.
- Filtrar por talla/color e intentar un filtro sin coincidencias.
- Sin seleccionar sucursal: disponibilidad no verificada. Con una sucursal seleccionada: solo saldo referencial.
- Comprobar ausencia de alteraciones de inventario o reservas.
- Son recomendaciones basadas en **reglas de similitud del catálogo**. CU21 y CU22 de IA no están incluidos ni alterados.

## CU20 · Reportes comerciales

- Iniciar sesión como Administrador Demo Andina o Encargado Demo Andina.
- Abrir `http://127.0.0.1:4201/admin/reportes-comerciales`.
- Consultar «Resumen», «Ventas», «Reservas» e «Inventario» y cambiar el período.
- Verificar por sucursal los importes de ventas digitales/caja **confirmadas**, estados de reservas y existencias físicas, comprometidas y disponibles.
- Cambiar a Encargado: solo debe ver sucursales autorizadas.
- Probar como Cajero: acceso prohibido.
- Operaciones guardadas solo en IndexedDB/SQLite no se suman como ventas aceptadas.
- Las existencias son una fotografía **actual**, no un histórico calculado por fecha.

## CU23 · Lista de deseos

- Iniciar sesión como **Cliente Demo Andina** en
  `http://127.0.0.1:4201/tienda/demo-moda-andina/acceso`.
- Abrir el catálogo de Andina, elegir prenda, talla y color y pulsar «Guardar en mi lista de deseos».
- Repetir la misma acción: debe informar que la variante ya estaba guardada, sin duplicarla.
- Abrir `http://127.0.0.1:4201/tienda/demo-moda-andina/deseos`.
- Revisar variante, precio vigente, disponibilidad conocida y estado de publicación.
- Eliminarla; la lista debe actualizarse y conservar aislamiento respecto de Moda Urbana.
- Probar sin sesión: debe solicitar acceso y no registrar una variante.
- Guardar un deseo no compromete ni descuenta inventario.

## Límites conocidos

- El flujo es web; las vistas y almacenamiento local Flutter aún no están implementados.
- CU19 no utiliza un modelo de ML ni captura historial de navegación personal. Usa prenda de referencia y preferencias expresas.
- CU20 no inventa indicadores para ventas que todavía no llegaron al servidor. Los reportes no sustituyen la conciliación de CU13.
- CU23 refleja datos actuales del catálogo; una variante despublicada permanece identificada como no disponible.
- Las pruebas de este documento deben **ejecutarse localmente**; la mera existencia del código no certifica su aprobación.

## Comandos para diagnóstico

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git switch trabajo/web-cu19-cu20-cu23
git pull --ff-only origin trabajo/web-cu19-cu20-cu23

cd backend
.\.venv\Scripts\python.exe -m scripts.migrate_demo
.\.venv\Scripts\python.exe -m pytest -q tests/test_cu19_cu20_cu23.py

cd ..\frontend
npm.cmd run build
npm.cmd test
```
