# Guion de demostración · VestiNova · CU19, CU20 y CU23

**Objetivo:** demostrar funcionamiento sin navegar, comprar ni registrar
manualmente todas las operaciones. Se preparan escenarios ficticios con
identificadores estables, únicamente en PostgreSQL local `vestinova_pruebas`.

La rama de trabajo es `trabajo/web-cu19-cu20-cu23`. No integrar a `miguel`
antes de revisar las pantallas y aprobar las pruebas.

## 1. Actualizar, migrar, probar y sembrar datos

PowerShell (desde la raíz del repositorio):

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git switch trabajo/web-cu19-cu20-cu23
git pull --ff-only origin trabajo/web-cu19-cu20-cu23

cd backend
.\.venv\Scripts\python.exe -m scripts.migrate_demo
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_cu19_cu20_cu23.py tests/test_seed_fashion_catalog_demo.py tests/test_seed_demo_cu19_cu20_cu23.py

# Ejecutar las siguientes instrucciones solo si las pruebas pasan:
.\.venv\Scripts\python.exe -m scripts.seed_fashion_catalog_demo
.\.venv\Scripts\python.exe -m scripts.seed_demo_cu19_cu20_cu23
```

El segundo script:
- Habilita en la **cuenta ficticia** Cliente Demo Andina la personalización de CU19
  y registra visitas sintéticas a dos poleras y una camisa.
- Añade dos artículos a la lista de deseos de esa cuenta.
- Crea **tres ventas de contado ficticias** en Andina Centro, con comprobantes
  `VN-DEMO-CU20-01` a `-03`, y genera sus movimientos de inventario.
  **Nadie paga ni se conecta a Stripe.** Las ventas sintéticas se muestran
  etiquetadas DEMO en reportes y comprobantes.

Es **repetible**: el mismo escenario no duplica comprobantes ni vuelve a
descontar stock. No borra ni reinicia ventas, reservas, ajustes o historial
anterior; en caso de stock insuficiente en una prenda del escenario, revierte
la transacción completa e informa qué elemento necesita revisión.

## 2. CU19: recomendaciones de prendas

**Pantalla:** http://127.0.0.1:4201/tienda/demo-moda-andina/recomendaciones

**Cuenta demo:** `cliente.andina@vestinova.test`, con la contraseña de la
semilla original. Iniciar sesión como Cliente Demo Andina antes de visitar
la pantalla.

**Simulación que crea el script:**
- Polera básica manga corta · 5 visitas.
- Polera deportiva liviana · 4 visitas.
- Camisa de lino natural · 1 visita.

**Qué debe observarse:**
- El bloque «Recomendaciones según tus visitas» aparece habilitado para la
  cuenta demo por el script y la API devuelve `REGLAS_HISTORIAL_CONSENTIDO`.
- Las otras poleras publicadas deben ganar prioridad gracias a similitud de
  categoría y material. Las prendas visitadas se excluyen de las sugerencias
  personales para proponer otras alternativas.
- Al escribir `M` en talla y `Azul` en color, se filtran productos que
  tienen una variante concreta con **ambos** atributos.
- Desde el detalle de una prenda se puede abrir «Ver prendas similares»:
  ese recorrido usa una **prenda de referencia** en vez del historial.
- Si desactivas la personalización se borran las visitas guardadas. Al
  reactivarla habrá que navegar de nuevo o volver a ejecutar el script demo.
- Un cliente nuevo o anónimo recibe sugerencias generales y no es vigilado
  automáticamente. El seguimiento de vistas solo ocurre con aceptación
  explícita del cliente autenticado.

**Cómo explicarlo a la ingeniera:**
«Este CU propone prendas de la misma empresa a partir de características
reales. Con el consentimiento del cliente también utiliza las categorías
que ha consultado para priorizar productos relacionados. No inventa prendas
ni utiliza un modelo de inteligencia artificial entrenado. No se modifican
ventas, inventario, carritos ni reservas».

## 3. CU20: reportes comerciales

**Pantalla:** http://127.0.0.1:4201/admin/reportes-comerciales

**Cuenta demo:** `admin.andina@vestinova.test`. Para probar alcance,
también `encargado.andina@vestinova.test`. El Cajero no tiene acceso.

Selecciona reporte «Ventas confirmadas» o «Resumen general», fecha de hoy
(en UTC) y sucursal «Andina Centro».

**Datos ficticios insertados por la semilla del escenario:**

| Producto | Talla | Color | Unidades | Precio unitario | Importe |
|---|---|---|---:|---:|---:|
| Polera deportiva liviana | M | Azul | 2 | Bs 99.00 | Bs 198.00 |
| Polera oversize lisa | L | Negro | 1 | Bs 112.00 | Bs 112.00 |
| Camisa de lino natural | M | Crema | 1 | Bs 189.00 | Bs 189.00 |
| **Total del escenario** | | | **4** | | **Bs 499.00** |

El reporte debe contar **tres comprobantes nuevos**, cuatro unidades y
Bs 499.00 de ingresos **ficticios de demostración**, distinguiendo las
tres combinaciones de talla y color. Los totales reales del reporte pueden
ser mayores si ya existían ventas de prueba en el período: **el reporte
no elimina esas operaciones anteriores**.

**Cómo leerlo:**
- «Ventas confirmadas»: cantidad de comprobantes aceptados en el servidor.
- «Digitales»: compras asentadas después de un pago verificado.
- «Efectivo»: ventas centrales de contado (incluidas las de demo).
- «Importe registrado»: suma de importes de las ventas del período.
- «Prendas vendidas por color y talla»: unidades/importe por combinación
  de prenda y variante; las filas DEMO se indican expresamente.
- «Reservas confirmadas»: reservas que siguen en estado CONFIRMADA y
  cuya creación cae en el período indicado.
- «Reservas atendidas»: reservas con estado actual ATENDIDA.
- «Stock físico»: unidades que existen ahora en la sucursal.
- «Stock comprometido»: unidades reservadas que no se pueden vender.
- «Disponible»: físico menos comprometido.
- El inventario es un **corte actual**, aunque el período de ventas sea
  histórico. No es el inventario que existía en aquella fecha.

**Cómo explicarlo a la ingeniera:**
«Los indicadores se calculan leyendo operaciones reales o ficticias de
demostración ya persistidas. El sistema diferencia las operaciones
pendientes de sincronización y no las incluye en ventas confirmadas,
respeta la empresa y las sucursales autorizadas, y permite filtrar
fechas y tipos de reporte».

## 4. CU23: lista de deseos

**Pantalla:** http://127.0.0.1:4201/tienda/demo-moda-andina/deseos

**Cuenta demo:** Cliente Demo Andina.

La semilla agrega:
- Polera oversize lisa, talla M, color Negro.
- Zapatillas urbanas, talla 39, color Blanco.

**Pruebas visuales:**
1. Se muestran ambos elementos con datos actuales del catálogo.
2. Pulsar «Ver prenda» abre su detalle, con talla/color elegibles.
3. Pulsar «Eliminar de mi lista» quita el deseo, **sin borrar el producto
   del catálogo ni modificar stock**.
4. Para volver a añadirlo, abre su detalle, selecciona la variante y
   pulsa «Guardar en mi lista de deseos». Un segundo intento no duplica
   ese registro.
5. Cerrar sesión: ya no se debe acceder a la lista privada.
6. Iniciar sesión en Moda Urbana con otra cuenta: no debe mostrar los deseos
   guardados para Andina.

**Explicación breve:** «La lista de deseos es un conjunto privado de
variantes favoritas, no una compra ni una reserva. Guardarlas no bloquea
existencias ni fija el precio; el cliente ve el precio y disponibilidad
vigentes cuando vuelve».

## 5. URLs para imágenes de demostración

La semilla guarda una URL HTTPS en `Producto.imagen_url`. Ejemplo:

`https://images.pexels.com/photos/3944690/pexels-photo-3944690.jpeg?auto=compress&cs=tinysrgb&w=640`

La función `photo_url()` la construye usando el ID de una fotografía de
referencia de Pexels; las URLs se asignan solo cuando el producto no tiene
ya una imagen. Los 26 modelos nuevos de cada empresa comparten el mismo
mapa de 26 referencias; una foto representa **el modelo**, no todas las
variantes de color de forma exacta.

Las fotos son orientativas, no mercancía ni marcas reales de VestiNova.
El navegador necesita conexión para mostrar imágenes remotas si aún no
las ha descargado. Una defensa sin Internet requiere almacenarlas
localmente y revisar las reglas de cacheo, tarea distinta a esta semilla.

Fuentes: https://www.pexels.com/legal-pages/license/
Consulta las fotografías originales en
`https://www.pexels.com/photo/<id>/` antes de una presentación final y
sustituye cualquiera que no represente adecuadamente el artículo.

## 6. Alcance y revisión final

Los datos del escenario son exclusivamente de demostración. Las
operaciones de venta insertadas son **registros sintéticos** con
movimientos coherentes; no equivalen a una prueba end-to-end de caja,
Stripe o flujo de compra, que tienen sus pruebas propias.

El script crea historial ficticio para una cuenta demo autorizada por
el escenario. Para cuentas reales la personalización es opcional y la
pueden desactivar/borrar.

**No integrar a `miguel` hasta completar pruebas locales y revisar
las pantallas.** El responsable del proyecto realiza el commit squash
final en su computadora.
