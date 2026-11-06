# CU08 — Consultar catálogo de prendas

**Referencia funcional:** tabla CU08 del apartado 2.6 de «VestiNova — Segundo Parcial».
**Rama de integración:** `integracion/cu07-cu08-20261106`, basada en CU07 aprobado y sin modificaciones en `miguel`.

## Funcionalidades verificables

| Requisito del CU08 | Implementación |
| --- | --- |
| Actores cliente, administrador, encargado y cajero (web/móvil) | Catálogo público web/PWA y acceso desde panel administrativo; la vista administrativa fuerza la empresa de trabajo y conserva el menú |
| Menú claro | «Consultar catálogo de prendas», sin sufijo CU08. CU07 se muestra «Gestionar inventario y ajustes» |
| Catálogo por empresa | `tienda` en API y copias `public-catalog:<slug>`; la vista de administración impide el contexto global |
| Listado/búsqueda | Nombre, categoría, talla, color, precio base y **temporada**; paginación, vacíos, errores y producto no publicado |
| Atributos | Material, medidas y temporada opcionales registrados en CU04, consultables en CU08; el detalle muestra tallas y colores de variantes activas |
| Precio/promoción | El servidor aplica promociones elegibles y vigentes; la copia offline lleva advertencia de antigüedad |
| Consultar sucursal/variante | Datos acotados a la empresa y sucursales activas, filtro visual por sucursal y variante |
| Unidades comprometidas | El backend distingue existencias físicas de **disponibilidad referencial** (`cantidad > cantidad_comprometida`) |
| Sin stock conocido | «Disponibilidad no verificada»; no se presupone stock ante filas ausentes |
| Agotada y reservada | Distingue saldo agotado de existencias físicas totalmente comprometidas |
| Fuente/fecha | Hora de consulta online, hora del saldo cuando existe, fecha de descarga offline |
| Sin conexión | IndexedDB conserva productos, variantes y sucursales por empresa; no asegura stock vigente. Una descarga interrumpida conserva la copia anterior |
| Sin escrituras de inventario | CU08 no confirma compras, reservas ni ajustes de stock |

## Cambios de esquema y compatibilidad

Migración `c08a4d1f2026`, dependiente de `a07f311c2d26` de CU07. Añade a `productos` tres columnas con valor inicial vacío: `material` (120), `medidas` (500) y `temporada` (60). Los productos y movimientos anteriores se conservan.

El frontend acepta copias IndexedDB antiguas sin dichos atributos; las sucursales guardadas son opcionales y se validan antes de persistir.

## Comprobación local en base demo (sin seed)

1. Detener los servidores y mantener copia de seguridad local si se requiere.
2. Actualizar a `integracion/cu07-cu08-20261106`.
3. Desde `backend`, ejecutar `.\.venv\Scripts\python.exe -m scripts.migrate_demo`.
   **Importante:** el script valida y migra exclusivamente PostgreSQL local `vestinova_pruebas`.
   No debe usarse `seed_demo` para esta revisión ni migrarse `vestinova_mvp`.
4. Iniciar `.\.venv\Scripts\python.exe -m scripts.serve_demo`.
5. En `frontend`, ejecutar `npm.cmd start`.
6. Abrir `http://127.0.0.1:4201/admin/catalogo-consulta`. Verificar la tienda activa, filtros, detalle, stock, promoción y menú.
7. Editar una prenda en CU04 para registrar **material**, **medidas** y **temporada**. Volver a CU08 y comprobar el detalle y filtro de temporada.
8. Abrir el catálogo público de la empresa, descargarlo, desconectar la red y verificar datos y sucursales guardadas con el aviso **Disponibilidad no verificada**.
9. Probar con una empresa diferente y confirmar que no se reutiliza la copia de la anterior.

## Límites que deben declararse

- La disponibilidad es referencial. CU10 gestiona la reserva real y no se promete existencia futura.
- La versión móvil funciona como web adaptable/PWA; **no se certifica un cliente Flutter/SQLite nativo**.
- Los filtros de precio usan el importe base, mientras que las promociones vigentes se presentan aparte.
- El endpoint público de listado genérico sin selección de tienda permanece por compatibilidad con otros flujos heredados; la ruta administrativa de CU08 siempre acota a la empresa seleccionada.
- Las pruebas automatizadas son una regresión; falta aprobación visual manual antes de integrar CU08 en `miguel`.
