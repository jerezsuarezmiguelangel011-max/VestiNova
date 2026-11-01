# CU11: contrato del núcleo de reservas

Fuente funcional: ficha oficial de CU11 del Capítulo II, transcrita por el usuario
en esta conversación. Este documento resume el alcance autorizado; no atribuye
su contenido a un PDF ni a una ficha almacenada en el repositorio.

El incremento comprende reglas y contratos en `backend/app/reservations/` para
registrar, consultar y cancelar reservas por empresa, sucursal, cliente y variantes.
Es un núcleo local sin ORM, migraciones, endpoints FastAPI ni pantallas Angular.
No constituye por sí solo la entrega completa de CU11.

## Referencias y autorización

Se reutilizan `Identifier`, `validate_identifier`, `InventoryKey`, `StockBalance`,
`BranchReference` y `VariantReference` del primer incremento de CU08, sin modificarlo.
No se reinterpreta un producto como una variante ni se crean tablas maestras ficticias.
Los identificadores mantienen su representación; no hay coerción entre entero y texto.

Los contratos deben resolver el actor autorizado, la empresa, la sucursal, el cliente
y las variantes. Deben comprobar pertenencia y alcance antes de consultar o cambiar
una reserva. El contexto confiable proviene del futuro adaptador de autorización,
no de identificadores aceptados sin validar desde un cliente. No se añaden roles
ni claims JWT a la autenticación administrativa actual.

Los actores oficiales son Cliente, Administrador de empresa, Encargado de sucursal
y Cajero. Su rol y los permisos efectivos los verifica el adaptador; el núcleo no
otorga permisos automáticamente por un nombre de rol. El alcance de clientes es
explícito, para impedir que un cliente consulte o modifique reservas ajenas.

Cada línea identifica una variante en la sucursal y empresa de la reserva, con
una cantidad válida. La referencia de cliente también debe corresponder al ámbito
autorizado. Los puertos resuelven esas relaciones; este incremento no implementa
la administración de clientes, sucursales, empresas ni catálogo de variantes.

Las cantidades son enteros positivos estrictos, sin booleanos ni conversiones desde
texto. Las líneas repetidas de una variante se consolidan antes de validar el total.
Una reserva confirmada conserva código, solicitud UUID, referencias, cantidades,
fecha central, vencimiento y eventos inmutables con actor, transición y fecha UTC.
El repositorio debe garantizar UUID y código únicos; no hay persistencia SQL todavía.

## Estados y transiciones

| Origen | Operación o resultado | Destino | Efecto en inventario |
| --- | --- | --- | --- |
| Registro en línea válido | Confirmar todas las líneas | `CONFIRMADA` | Comprometer todas las cantidades juntas. |
| Registro sin conexión | Conservar intención con UUID | `PENDIENTE_SINCRONIZACION` | Ningún compromiso de stock. |
| `PENDIENTE_SINCRONIZACION` | Validación correcta del servidor | `CONFIRMADA` | Comprometer todas las líneas al confirmar. |
| `PENDIENTE_SINCRONIZACION` | Resultado de validación del servidor | `RECHAZADA` o `EN_CONFLICTO` | Ningún compromiso de stock. |
| `CONFIRMADA` | Cancelación autorizada y permitida por la política | `CANCELADA` | Liberar su compromiso una sola vez. |
| `CONFIRMADA` | Vencimiento comprobado según la política | `VENCIDA` | Liberar su compromiso una sola vez. |

`RECHAZADA`, `EN_CONFLICTO` y `PENDIENTE_SINCRONIZACION` no representan stock
comprometido. Repetir una cancelación o vencimiento no debe liberar cantidades
adicionales. Una transición inválida o denegada no cambia reserva ni inventario.
La clasificación del resultado de validación debe respetar la ficha y el contrato
de servidor; un registro local no puede declararse confirmado por su cuenta.

La validación central devuelve `RECHAZADA` ante autorización o referencias inválidas
y `EN_CONFLICTO` ante disponibilidad insuficiente o UUID usado con otro contenido.
Estos resultados son objetos para la futura integración CU15, no nuevas reservas
centrales ni escrituras de datos privados para un actor denegado. Los fallos técnicos
o de configuración se propagan y dejan intacta la solicitud pendiente para reintentar.

`ATENDIDA` se reconoce únicamente como referencia terminal del CU16. No se añade
un método de atención ni se implementa su flujo en CU11. Ese estado no habilita
la cancelación o liberación de stock propia de una reserva confirmada.

## Compromiso, liberación y políticas

Confirmar aumenta el reservado de cada `StockBalance`, sin reducir el stock físico
actual. El disponible continúa siendo `stock_actual - stock_reservado`. Se deben
verificar todas las líneas y mantener saldos no negativos, sin superar el stock
actual con el reservado. Si falla una línea, no debe confirmarse ninguna parcialmente.

Cancelar o vencer libera únicamente las cantidades comprometidas por esa reserva,
manteniendo el físico. El cambio de estado y los cambios de saldo se preparan
en una misma unidad de trabajo y se confirman juntos mediante un solo `commit`.

La fecha de vencimiento depende de una política configurable. No se fija un plazo
numérico predeterminado. La posibilidad de cancelar se consulta mediante una política
explícita; no se inventan ventanas, penalizaciones, anticipos ni condiciones de pago.

El registro sin conexión conserva un UUID y requiere validación posterior del servidor.
No bloquea unidades localmente ni garantiza disponibilidad futura. CU15 queda como
dependencia de sincronización: este incremento no implementa una cola, reintentos
automáticos ni un protocolo de sincronización en producción.

Reenviar el mismo UUID y contenido devuelve la reserva central existente sin volver
a comprometer ni renovar su plazo. Se verifica nuevamente la autorización antes de
devolverla. Cambiar el contenido con el mismo UUID produce conflicto. La fecha del
dispositivo no determina el vencimiento: este se obtiene de la política al confirmar
con el reloj central. No se exige que ambos relojes estén sincronizados.

## Comprobación local y límites

Las pruebas cubren referencias y autorización, aislamiento entre ámbitos,
transiciones válidas e inválidas, compromiso de varias líneas, falta de disponibilidad,
cancelación permitida o denegada, vencimiento configurable y liberación única.
También deben comprobar que un fallo no deje saldos o reservas parciales y que
una intención sin conexión no comprometa inventario.

Los adaptadores de inventario y unidad de trabajo en memoria pertenecen únicamente
a las pruebas. No sustituyen PostgreSQL ni acreditan concurrencia o idempotencia
persistente. La integración SQL, autorización real, API, UI y sincronización completa
siguen pendientes. El vencimiento dispone de una operación explícita; el proceso
automático que la invocará y la persistencia local de solicitudes aún no se implementan.

Verificación ejecutada en `miguel`: 101 casos nuevos de CU11 correctos (42 de dominio
y 59 de servicio), 367 casos correctos en toda la suite backend y 168 en el frontend.
Los dobles prueban rollback de varias líneas, compromiso sin descuento físico,
liberación única, UUID/código únicos y reenvíos, y dos solicitudes simultáneas sobre
la última unidad. Su RLock no acredita todavía bloqueos ni garantías PostgreSQL.

Desde `backend`, la batería específica se ejecuta con
`.\.venv\Scripts\python.exe -m pytest tests/reservations -q --tb=short`.
