# CU08: contrato del primer incremento de inventario

Este incremento implementa reglas de dominio y contratos de aplicación comprobables
localmente. Es un avance parcial de CU08, sin conexión con FastAPI, PostgreSQL,
Angular ni la autenticación actual. No crea endpoints ni tablas de inventario.

## Alcance y referencias

- Código: `backend/app/inventory/{domain,ports,service}.py` y su paquete.
- Pruebas: `backend/tests/inventory/`, con adaptadores en memoria exclusivos de tests.
- Empresa, sucursal y variante son referencias opacas, sin nuevas tablas maestras.
- Una referencia admite texto no vacío o entero positivo; `bool` no es un entero válido.
- Los identificadores conservan su tipo: no se equipara el entero `1` con el texto `"1"`.
- Un producto actual no se reinterpreta como una variante.
- La integración deberá resolver que sucursal y variante pertenecen a la empresa
  correspondiente, mediante los contratos de sus entidades reales.

## Saldo y cantidades

Los objetos de dominio son inmutables (`frozen`). Las cantidades de stock actual,
reservado y recuento son enteros estrictos: no admiten booleanos, flotantes ni
conversiones automáticas desde texto.

```text
stock_actual >= 0
reservado >= 0
reservado <= stock_actual
disponible = stock_actual - reservado
```

Disponible se calcula; no constituye un tercer saldo modificable por separado.
Cada saldo corresponde a una combinación de empresa, sucursal y variante.

## Ajuste por recuento

El ajuste recibe el stock contado absoluto, no una variación. Conserva la cantidad
reservada y rechaza un recuento inferior a ella. También rechaza un recuento igual
al stock actual, porque no existe un cambio que registrar.

Un ajuste válido produce un nuevo saldo y un movimiento de tipo fijo
`AJUSTE_RECUENTO`, con identificadores UUID de movimiento y operación, actor
validado, fecha con zona horaria UTC y motivo obligatorio después de recortar
espacios. Conserva los valores anteriores, posteriores y sus deltas.
Los deltas pueden tener signo; los saldos resultantes deben seguir siendo no negativos.

El incremento no implementa reservas, ventas, compras ni sus movimientos. El origen
y actualización del reservado deberán acordarse con los casos responsables.

## Contexto autorizado y unidad de trabajo

El contrato recibe un contexto confiable con actor, empresa, sucursales autorizadas
y permisos para consultar o ajustar. Debe comprobar el alcance de los recursos y
su pertenencia antes de aceptar la operación. No basta con recibir identificadores
de empresa o sucursal enviados por un cliente.

Este contexto es una interfaz de integración; no añade roles, claims JWT ni permisos
reales a la sesión administrativa actual. Las pruebas usan contextos y resolutores
controlados para verificar aceptación y rechazo entre ámbitos distintos.

La unidad de trabajo prepara el guardado del saldo y el agregado del movimiento,
y confirma ambos mediante un solo `commit`. Un rechazo no debe producir cambios
confirmados ni un movimiento aislado. El adaptador en memoria vive únicamente
en las pruebas; no acredita atomicidad, bloqueo ni concurrencia en PostgreSQL.
El UUID de operación tampoco acredita idempotencia persistente.

## Ejecución local del incremento

Desde un entorno backend ya preparado, ejecutar:

```powershell
Set-Location 'D:\Proyectos\vestinova-mvp\backend'
.\.venv\Scripts\python.exe -m pytest tests/inventory -q --tb=short
```

Adaptar la ruta al clon propio. Esta batería comprueba dominio y contratos con
fixtures en memoria, sin leer secretos ni acceder a la base operativa. No necesita
iniciar FastAPI, aplicar migraciones, crear administradores ni insertar semillas
o maestros ficticios.

Verificación del incremento en `miguel`: 178 casos nuevos de CU08 aprobados
(148 de dominio y 30 de servicio). La suite completa del backend pasó 266 casos
y la regresión del frontend pasó 168. Las pruebas completas del backend usan su
SQLite aislado para los módulos existentes; CU08 utiliza únicamente los dobles
en memoria de `tests/inventory/`, sin PostgreSQL ni migraciones.

## Integración pendiente

Antes de conectar el módulo deben acordarse los contratos reales compartidos con
CU04, CU05, CU07, CU12 y CU13, sin duplicar sus funcionalidades ni deducirlas por
su numeración. Quedan pendientes las claves foráneas y restricciones SQL, las
garantías de concurrencia e idempotencia persistente, la autorización integrada,
la API, los filtros y pantallas, el kardex persistido y los diagramas ICONIX.

El cumplimiento completo de CU08 requiere verificar esas integraciones y sus
flujos de consulta y ajuste; las reglas locales por sí solas no completan el caso.
