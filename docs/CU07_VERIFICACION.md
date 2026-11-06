# CU07 — Validación contra la tabla del capítulo 2.6

Rama de revisión: `trabajo/cu07-miguel`. No fusionar hasta ejecutar pruebas y revisar la interfaz.

## Flujos normales

1–3. Acceso por empresa, rol y sucursal; filtros por nombre, producto, variante y categoría.
4. Saldos por variante: físico, comprometido, disponible = físico − comprometido.
5. Detalle del producto y kardex filtrado por variante (solo lectura).
6–7. Formulario explícito «Registrar ajuste»: incremento o disminución, cantidad positiva y motivo obligatorio.
8–9. Bloqueo transaccional; se conserva `físico >= comprometido`; movimiento, saldo y auditoría en un commit.
10. Confirmación del movimiento y recarga de existencias y kardex.

## Flujos alternativos

- 2A. Rechazo 404 de sucursal o recurso explícito de otra empresa o fuera del ámbito autorizado.
- 4A. Cero resultados informa que no se encontraron existencias sin fabricar saldos.
- 5A / 6A. Consultas de existencias y kardex no modifican el inventario ni permiten editar el historial.
- 6B. Reingreso asociado a una postventa completada, autorizada, apta y coincidente en variante y cantidad, una sola vez por origen y variante.
- 6C. El permiso de consulta no permite ajustar; `inventario.ajustar` se concede al administrador y encargado autorizado.
- 7A. Campos inválidos y motivo vacío o solo espacios devuelven 422 sin persistencia.
- 8A. Si la disminución consumiría unidades comprometidas devuelve 409 y mantiene el stock.
- 8B. Tras concurrencia se revalida bajo bloqueo de fila y se rechaza conflicto con petición de actualización.
- 8C. Mismo UUID y contenido: 200 sin duplicado. Mismo UUID con datos distintos: 409.
- 9A. Un fallo de escritura o auditoría revierte la transacción.

## Pasos de prueba local

1. Comprobar `git branch --show-current` en `trabajo/cu07-miguel`.
2. Respaldar `vestinova_pruebas` antes de migrar.
3. Desde `backend`, detener el servidor y ejecutar `.\.venv\Scripts\python.exe -m scripts.seed_demo` para aplicar Alembic sin borrar los registros de demo.
4. Desde `backend`, ejecutar `.\.venv\Scripts\python.exe -m pytest tests/inventory tests/test_tenancy_inventory.py -q`.
5. Desde `frontend`, ejecutar `npm.cmd run build` y `npm.cmd test`.
6. Iniciar `scripts.serve_demo` y Angular; revisar interfaz con Administrador y Encargado.

## Integración todavía pendiente

CU10 reservas contiene dominio y contratos pero no tiene adaptador de persistencia central en producción. CU07 persiste y protege `cantidad_comprometida`, pero las futuras reservas deben integrarse con ese campo en la misma transacción para que refleje compromisos reales. Cero representa ausencia de compromisos centrales contabilizados, no una verificación de reservas externas.

Referencia corregida en el Google Docs del capítulo 2.6: el flujo alternativo 6B se coordina con CU17 (cambios y devoluciones), no con CU19 (recomendaciones). La entrada por postventa se registra una sola vez mediante CU07. Esta corrección documental no acredita que la integración de reservas CU10 esté terminada.
