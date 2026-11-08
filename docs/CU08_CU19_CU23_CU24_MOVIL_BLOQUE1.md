# Bloque 1 móvil – VestiNova

**Casos:** CU08, CU19, CU23 y CU24 (Flutter).
**Rama:** `trabajo/movil-bloque1`
**Base:** `af8c06b1da089f2c6a7733f4c654110d87c08321` – incluye `fix: conciliar pagos Stripe TEST pendientes`.

## Componentes

- `mobile/lib/storefront/`: catálogo paginado, filtros, fichas, stock referencial, recomendaciones, consentimiento, deseos por variante, comparación por producto y caché público SQLite aislado por tienda.
- `mobile/lib/main.dart`: incorpora navegación comercial conservando el controlador original de acceso y el componente de reservas CU10.
- `mobile/test/storefront_api_test.dart`, `storefront_widgets_test.dart` y actualización de `access_widget_test.dart`: pruebas de contratos API y recorridos de acceso.

No se han modificado endpoints del backend, migraciones, archivos Angular ni la BD SQLite de reservas.

## Probar en la computadora

Desde la raíz del repositorio, con Git y Flutter instalados:

```powershell
git fetch origin
git switch --track origin/trabajo/movil-bloque1
cd mobile
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8001/api
```

Si la rama local ya existe, utilizar `git switch trabajo/movil-bloque1` y `git pull --ff-only` después de `git fetch origin`. El valor `10.0.2.2` es para el emulador Android; en otros dispositivos debe usarse una URL accesible al servidor.

## Comprobación funcional

1. Abrir la tienda sin iniciar sesión y consultar catálogo, filtros, ficha y stock referencial.
2. Consultar sugerencias generales y similares, sin registrar visitas si no hay consentimiento.
3. Seleccionar 2 a 4 productos y comparar sus características.
4. Iniciar sesión como Cliente de esa tienda, añadir una variante a deseos, revisarla y quitarla.
5. Descargar catálogo para consulta local, desconectar Internet y comprobar el aviso de datos desactualizados.
6. Comprobar que las reservas CU10, accesos del personal y sesión siguen disponibles.
7. Probar el flujo de Stripe TEST y su conciliación en el backend/web por separado.

**Estado de calidad:** archivos publicados y contratos revisados estáticamente. Aún requieren `flutter analyze`, `flutter test` y ejecución local; no se afirma que estén validados en Android.
