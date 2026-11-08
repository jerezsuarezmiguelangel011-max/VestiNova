# Semilla ampliada del catálogo de VestiNova (demostración)

Esta semilla agrega datos ficticios únicamente en la base **vestinova_pruebas**.
No modifica **vestinova_mvp**, ni crea compras o reservas, ni borra ventas, ajustes
de inventario, deseos o conflictos de sincronización anteriores.

## Qué se incorpora

- Moda Andina Demo: 26 modelos adicionales, con variantes de talla/color y
  existencias en Andina Centro y Andina Norte.
- Moda Urbana Demo: 26 modelos adicionales, con variantes y existencias en
  Urbana Centro, Urbana Norte y Urbana Sur.
- Seis categorías generales por empresa (solo moda masculina): **Poleras, Camisas, Pantalones,
  Abrigos, Calzado y Accesorios**.
- Ejemplos: polera oversize, camisa de lino, pantalón cargo, jean amplio,
  chompa tejida, parka, zapatillas, botines, gorra, billetera y chalina.
- Tallas de ropa (S/M/L), de pantalón (38/40/42), de calzado (37/39/41)
  y talla única para accesorios.
- Dos colores por modelo, con disponibilidad variada por sucursal y algunos
  saldos en cero para comprobar reservas rechazadas y futuras alertas.
- Los productos existentes de demostración como «Jean recto» y «Chaqueta
  corta» se reclasifican de las antiguas categorías «Jeans» y «Chaquetas» a
  «Pantalones» y «Abrigos», **solo si todavía conservan su clasificación
  anterior**. No se cambian sus precios, variantes, compras ni existencias.
- Las categorías antiguas quedan inactivas solo si no contienen ningún
  producto; si contienen productos que añadiste, permanecen activas.

**Límite funcional actual:** el sistema admite una sola categoría por producto,
sin campos padre/hija. Por eso los *tipos de prenda* están en el nombre y la
descripción, pero **no son subcategorías navegables reales**. Esa jerarquía
requeriría un cambio separado de CU04, esquema y UI.

**Fotos:** las prendas nuevas se crean sin fotografías externas. La interfaz
debe conservar su tratamiento de imágenes opcionales. Se sustituyen las imágenes previas asignadas por la propia semilla; se
conservan las fotografías introducidas manualmente por un administrador.

## Comandos de Windows / PowerShell

Desde la rama de trabajo temporal, con cambios locales importantes
guardados antes de modificar de rama:

```powershell
cd D:\Proyectos\vestinova-mvp
git status --short
git switch trabajo/web-cu19-cu20-cu23
git pull --ff-only origin trabajo/web-cu19-cu20-cu23

cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_seed_fashion_catalog_demo.py
.\.venv\Scripts\python.exe -m scripts.seed_fashion_catalog_demo
```

La segunda orden Python amplía datos de `vestinova_pruebas`; no pide
contraseñas ni cambia las credenciales existentes de las cuentas demo.
Antes deben existir las tiendas, sucursales y el administrador del
`scripts.seed_demo` original. Si falta alguno, la semilla informa el
problema y revierte toda la transacción.

La semilla se puede repetir: únicamente inserta productos, variantes o
saldos **ausentes**, y nunca repone automáticamente existencias que hayas
vendido, reservado o ajustado en una prueba.

## Revisión visual

1. Visitar `/tienda/demo-moda-andina/catalogo` y buscar «cargo», «lino»
   y «sombrero».
2. Revisar las categorías generales en el filtro de catálogo.
3. Elegir una variante con talla de pantalón (40), de camisa (M) o
   de calzado (39), según el producto.
4. Cambiar la sucursal y consultar existencias referenciales.
5. Abrir `/tienda/demo-moda-urbana/catalogo` y comprobar que no
   aparecen los productos etiquetados como Andina.
6. Revisar `/tienda/demo-moda-andina/recomendaciones` para obtener
   sugerencias basadas en productos publicados.
7. Volver a ejecutar la semilla y confirmar que las cantidades no se
   restablecieron tras cualquier operación válida realizada.

Los estilos y cantidades son **datos sintéticos de demostración**, no
inventario de tiendas reales.


## Ajuste del 8 de noviembre: solo moda masculina

- El catálogo de **Moda Andina Demo** y **Moda Urbana Demo** ofrece
  prendas y accesorios para hombre.
- El antiguo modelo de demostración `bolso-cruzado` se **despublica**
  si mantiene su nombre original de la semilla; no se borran sus
  existencias, compras, reservas, movimientos o deseos.
- Se agrega `billetera-clasica` en lugar del bolso dentro de los
  26 modelos activos de demostración por tienda.
- El modelo `jean-wide-leg` pasa a denominarse «Jean relaxed fit masculino».
  Los registros y variantes existentes conservan sus identificadores.
- Las fotografías se actualizarán al repetir la semilla **solo si la URL
  anterior coincidía con la que colocó la semilla vieja**. Si el administrador
  asignó una fotografía personalizada, no se sobrescribe.
- Las portadas del portal y de cada tienda usan fotografías editoriales
  masculinas distintas; Moda Andina utiliza un estilo cálido y Moda Urbana,
  un estilo streetwear.
- Las páginas de CU19 y CU23 utilizan el componente de imagen del catálogo,
  con una ilustración alternativa si una foto remota falla.

### Actualización

```powershell
cd D:\Proyectos\vestinova-mvp
git switch trabajo/web-cu19-cu20-cu23
git pull --ff-only origin trabajo/web-cu19-cu20-cu23

cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_seed_fashion_catalog_demo.py
.\.venv\Scripts\python.exe -m scripts.seed_fashion_catalog_demo
```

**Nota:** el comando de siembra solo se debe ejecutar cuando haya pasado
la prueba anterior. El script vuelve a utilizar la base `vestinova_pruebas`.
Si el navegador no actualiza las fotografías, haz una recarga completa de la
página para descartar recursos antiguos de caché.
