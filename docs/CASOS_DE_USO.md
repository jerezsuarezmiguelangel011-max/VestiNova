# Lista vigente de casos de uso de VestiNova

Fuente: lista proporcionada expresamente por el usuario el 25 de octubre de 2026. Se conservan los nombres, actores y plataformas indicados; esta lista sustituye correspondencias provisionales y numeración heredada de diagnósticos anteriores. Los identificadores técnicos de archivos, modelos y pruebas no se renombran por esta corrección documental.

| Código | Nombre exacto | Actores | Plataforma | Responsabilidad confirmada |
| --- | --- | --- | --- | --- |
| CU01 | Gestionar cuenta y acceso al sistema | Superadministrador SaaS, Administrador de empresa, Encargado de sucursal, Cajero, Cliente | Web y Móvil | Salet |
| CU02 | Gestionar usuarios, roles y permisos | Administrador de empresa | Web | Salet |
| CU03 | Consultar bitácora del sistema | Administrador de empresa | Web | Salet |
| CU04 | Gestionar ciudades y sucursales | Administrador de empresa | Web | Salet |
| CU05 | Gestionar catálogo de prendas | Administrador de empresa | Web | Salet |
| CU06 | Gestionar promociones | Administrador de empresa | Web | Salet |
| CU07 | Gestionar proveedores y abastecimiento | Administrador de empresa, Encargado de sucursal | Web | Salet |
| CU08 | Gestionar inventario por sucursal | Administrador de empresa, Encargado de sucursal | Web | Miguel |
| CU09 | Consultar catálogo y disponibilidad | Cliente, Administrador de empresa, Encargado de sucursal, Cajero | Web y Móvil | Miguel |
| CU10 | Realizar compra digital | Cliente, Pasarela de pagos | Web y Móvil | Miguel |
| CU11 | Gestionar reservas de prendas | Cliente, Administrador de empresa, Encargado de sucursal, Cajero | Web y Móvil | Miguel |
| CU12 | Gestionar empresas contratantes | Superadministrador SaaS | Web | Salet |
| CU13 | Gestionar planes y suscripciones | Superadministrador SaaS, Administrador de empresa | Web | Salet |
| CU14 | Preparar información para operar sin conexión | Cliente, Administrador de empresa, Encargado de sucursal, Cajero | Web y Móvil | Por confirmar |
| CU15 | Gestionar sincronización y conflictos | Cliente, Administrador de empresa, Encargado de sucursal, Cajero | Web y Móvil | Por confirmar |
| CU16 | Gestionar atención de reservas en sucursal | Encargado de sucursal, Cajero | Web | Por confirmar |
| CU17 | Registrar venta presencial | Cajero | Web y Móvil | Por confirmar |
| CU18 | Consultar historial de compras | Cliente | Web y Móvil | Por confirmar |
| CU19 | Gestionar cambios y devoluciones de prendas | Cliente, Cajero, Encargado de sucursal, Pasarela de pagos, Servicio de notificaciones push | Web y Móvil | Por confirmar |
| CU20 | Utilizar vestidor virtual | Cliente | Móvil | Por confirmar |
| CU21 | Obtener asistencia y recomendaciones inteligentes | Cliente, Servicio de inteligencia artificial | Web y Móvil | Por confirmar |
| CU22 | Consultar indicadores y reportes convencionales | Administrador de empresa, Encargado de sucursal | Web | Por confirmar |
| CU23 | Generar reportes mediante lenguaje natural | Administrador de empresa, Encargado de sucursal, Servicio de inteligencia artificial | Web | Por confirmar |
| CU24 | Consultar analítica inteligente del negocio | Administrador de empresa | Web | Por confirmar |
| CU25 | Gestionar lista de deseos | Cliente | Web y Móvil | Por confirmar |
| CU26 | Comparar prendas | Cliente | Web y Móvil | Por confirmar |
| CU27 | Publicar valoraciones verificadas | Cliente | Web y Móvil | Por confirmar |
| CU28 | Gestionar avisos de disponibilidad | Cliente, Servicio de notificaciones push | Web y Móvil | Por confirmar |

## Uso de esta lista y prioridades

Salet tiene CU01–CU07, CU12 y CU13. Miguel tiene CU08–CU11; se respeta su trabajo de catálogo y detalle. Los responsables de CU14–CU28 están **por confirmar**: no se asignan automáticamente a ninguno de los dos integrantes.

El avance acumulado incluye selector de empresa, flujo administrativo de CU05 y cuenta/acceso de CU01 en web y Flutter propio. El usuario reportó login/restauración/cierre Android para Cliente y una cuenta de personal mixta SaaS/Administrador empresarial; la aceptación de CU01 sigue parcial por cobertura pendiente de otros perfiles y recorridos. La base de inventario es soporte compartido para CU08, sin autorización para modificar las pantallas de Miguel. CU02 se retomará cuando el usuario confirme el push de `salet`.

Esta tabla enumera el alcance acordado; no declara implementados sus casos ni supone que los 28 deban demostrarse en la primera presentación. La priorización no elimina obligaciones del enunciado. Flutter propio cubre cuenta/acceso de CU01; SQLite comercial, catálogo local, reservas/ventas offline y sincronización continúan pendientes. No se renumeran casos ni se cambian actores, plataformas o responsables.

El [README](../README.md) resume lo ejecutable; los contratos compartidos describen la API. Los informes de avance y evidencias se conservan localmente. Los títulos vigentes son exclusivamente los de esta tabla.
