# Auditoría CU10 — Web PWA (apartado 2.6)

Fecha de revisión: 7/8 de noviembre de 2026.
Rama de revisión: `trabajo/cu10-miguel`. Sin cambios a `miguel`.
Fuente normativa: documento VestiNova, tabla CU10 del apartado 2.6. El código en ramas de trabajo no reemplaza esa especificación.

## Matriz de cumplimiento

| Escenario | Evidencia en código | Evaluación |
|---|---|---|
| 1–5: actor, selección de tienda/sucursal/variante, condiciones | `reservation-draft.ts`, `reservation-staff-page.ts`, endpoint `/politica` | Implementado en web. Cliente prepara una o varias variantes de una prenda; personal puede registrar varias variantes del catálogo. La interacción real aún requiere aceptación visual. |
| 6–9: permisos, stock físico/comprometido, código, vencimiento | `backend/app/compras_reservas/reservas/online.py` | Implementado en backend, sin descontar unidades físicas. |
| 10–12: listado, consulta, cancelación, liberación | Rutas de cliente y personal en `online.py` y pantallas Angular | Implementado. Se debe validar experiencia de usuario con cuentas de distintos roles. |
| 3A: inválidos | Formularios Angular y Pydantic | Implementado. |
| 6A/6B: solicitud offline y ausencia de copia local | IndexedDB de `reservation-offline-store.service.ts` y catálogo conocido | Implementado. Reservas sin sesión validada se conservan solo como borradores; no se confirman ni retienen existencias. |
| 6C: sincronización posterior | `reservation-offline-sync.service.ts`, reintentos UUID | Implementado para reservas CU10, pendiente validación real de PWA instalada y concurrencia PostgreSQL. La conciliación integral de CU13 todavía es otro caso de uso. |
| 6D/10A: aislamiento de empresa/cliente/sucursal | `current_customer_session`, `require_tenant`, `authorized_branch`, y revisión de respuestas asíncronas en personal | Implementado en backend. Requiere pruebas end-to-end adicionales. |
| 7A: stock insuficiente | Respuesta 409 con disponible/solicitado para variantes sin stock | Implementado, se conserva el registro local conflictivo. |
| 7B: concurrencia de inventario | `SELECT ... FOR UPDATE` en PostgreSQL, bloqueo ordenado | Diseñado e implementado; falta prueba concurrente real en PostgreSQL. |
| 8A/8B: idempotencia y reversión | `_fingerprint`, UUID, transacciones y pruebas | Implementado, con escenarios de reintento y error. |
| 11A: vencimiento | `expire_due` y tarea periódica de FastAPI cada 60 segundos | Implementado al operar la API. Requiere pruebas al ejecutar FastAPI y observar una reserva vencida; frecuencia aproximada, no exactamente al segundo. |
| 11B: atención y entrega | Exclusivo de CU14 | No corresponde cerrar aquí. |
| 12A: cancelación no permitida | `_cancel` devuelve 409 sin liberar stock nuevamente | Implementado. |

## Alcance importante

- **Cliente web:** desde el producto seleccionado, puede añadir hasta 30 variantes diferentes **de esa prenda**, todas de la misma sucursal. No existe todavía un selector único que combine productos distintos en el mismo formulario del cliente. El backend acepta líneas de varios productos. Esta experiencia puede ampliarse si la evaluación exige una reserva mixta entre productos.
- **Personal web:** las variantes consultadas mediante `/api/catalogo/variantes` permiten seleccionar varias referencias; la pantalla consulta hasta los primeros 100 registros. Para catálogos más extensos hacen falta búsqueda o paginación de variantes.
- **Sin conexión:** las operaciones guardadas en IndexedDB sobreviven a recargas normales. Una solicitud PENDIENTE no es una reserva central. El acceso a la cola asociada a un cliente requiere revalidar la sesión al volver a utilizarla. El flujo de CU13 para todas las clases de operación (especialmente ventas de contado cobradas localmente) no está cubierto por esta implementación de CU10.
- **Vencimiento:** el trabajo periódico funciona mientras el proceso FastAPI esté activo. Para despliegues reales deben supervisarse workers y logs del servidor. El script `scripts/expire_reservations_demo.py` es una alternativa manual demo.
- **Entrega / caja / pago:** el retiro CU14 y las ventas en caja CU15 no deben mezclarse con la confirmación de reservas CU10. Stripe solo interviene en la compra digital en línea.
- **No confirmar CU10 web al 100 % todavía:** correr las nuevas pruebas de esta rama y una prueba de aceptación PWA real con `vestinova_pruebas`, incluyendo cambios de empresa, vencimiento y competencia por la última unidad.

## Pruebas recomendadas

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git pull --ff-only origin trabajo/cu10-miguel
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cu10_reservas_online.py tests/test_stripe_checkout_request.py
cd ..\frontend
npm.cmd run build
npm.cmd test
```

### Prueba funcional web para aceptar

1. En el catálogo público de Moda Andina abrir una prenda ya consultada y elegir sucursal. Añadir dos variantes (talla/color), revisar plazo.
2. Guardar solicitud y comprobar que permanece en IndexedDB con las dos líneas y un UUID.
3. Con cliente autenticado sincronizar; comprobar código, estado, vencimiento y compromiso de ambas variantes en PostgreSQL.
4. Cancelar una sola vez, comprobar liberación y rechazo al segundo intento.
5. Repetir desconectando la PWA antes de guardar; actualizar o reabrir PWA instalada; verificar PENDIENTE y reintento con UUID original.
6. Con dos sesiones, solicitar en paralelo la última unidad; solo un intento debe confirmarse.
7. Cambiar entre Moda Andina y Moda Urbana con usuario interno; comprobar que ninguna respuesta tardía presenta reservas de otra empresa.
8. Vencer una reserva demo y comprobar que la tarea del backend la libera aun sin consultar reservas desde una página.

## Siguiente caso propio para el trabajo web

CU11 y CU12 son de Salet según el documento. Los siguientes casos de Miguel son **CU13 — Conciliar conflictos de sincronización**, **CU14 — Atender retiro de reservas** y **CU15 — Registrar venta en caja**. CU13 depende de operaciones persistentes de CU10 y CU15, mientras CU14 depende de las reservas confirmadas de CU10. Avanzar con CU14 tras las pruebas de CU10 permite demostrar el ciclo completo de reservar y retirar; luego CU15 y CU13 completan la caja y la conciliación offline.
