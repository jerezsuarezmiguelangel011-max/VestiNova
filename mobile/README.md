# VestiNova móvil — cuenta y acceso

Flutter/Dart propio para CU01. El Flutter heredado permanece separado. Incluye Cliente por tienda y personal, selección empresarial posterior al login, identidad/rol/sucursales, restauración validada por API y cierre revocable. No implementa catálogo móvil, reservas, ventas offline ni sincronización.

## Preparar

Entorno comprobado: Flutter 3.47.1, Dart 3.13.1, Java de Android Studio 25.0.2, Gradle 9.3.1. Android mínimo API 24. Conservar `pubspec.lock` y el wrapper; SDK, cachés, APK y claves no se versionan.

Desde `mobile/`:

```powershell
flutter pub get
flutter analyze
flutter test
```

## API y ejecución

Se configura mediante `--dart-define=API_BASE_URL=...`, con `/api` una sola vez. Nunca introducir contraseña de PostgreSQL o secreto JWT en la app.

- Emulador Android: `http://10.0.2.2:8001/api`.
- Teléfono por Wi-Fi: `http://IP_DE_LA_PC:8001/api`, misma red y API escuchando en `0.0.0.0:8001`. `localhost` del teléfono apunta al teléfono.

Para Wi-Fi, en `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8001
```

Consultar `ipconfig` y abrir `http://IP_DE_LA_PC:8001/api/health` desde el teléfono. No abrir PostgreSQL ni puertos en el router. Si el firewall bloquea, permitir exclusivamente TCP 8001 para la red privada de confianza. CORS no se aplica a Flutter nativo.

En `mobile/`, para generar el APK Wi-Fi sin fijar la IP en fuentes:

```powershell
$VestiNovaPC = Read-Host 'IPv4 Wi-Fi de la PC'
flutter build apk --debug "--dart-define=API_BASE_URL=http://${VestiNovaPC}:8001/api"
```

Resultado: `build/app/outputs/flutter-apk/app-debug.apk`. Transferir solo ese archivo mediante una cuenta privada de Drive u otro medio, descargarlo en Android y autorizar a la app que abre el archivo para instalarlo. HTTP local está permitido en debug; distribución requiere HTTPS y firma propia. Si cambia la IP, recompilar. No desactivar protecciones para eludir errores de instalación.

## Recorridos y límites

- Cliente: introducir slug/enlace público → Abrir mi tienda → Crear cuenta de cliente o Iniciar sesión. No utiliza selector administrativo.
- Personal: Acceso del personal → credenciales → empresa autorizada si corresponde. Rol empresarial y autoridad SaaS son independientes.
- Restauración: con sesión vigente, forzar detención sin cerrar sesión ni borrar datos; abrir nuevamente y esperar validación del servidor.
- Cierre: Cerrar sesión, esperar confirmación; al reabrir no debe restaurar la identidad cerrada.

Contratos: [cuenta/acceso](../docs/CONTRATO_CU01_CUENTAS.md), [descarga privada](../docs/CONTRATO_DESCARGA_MOVIL.md) y [catálogo web](../docs/CONTRATO_CATALOGO.md). La app guarda el token con `flutter_secure_storage`; no persiste contraseñas ni concede acceso offline por conservar un token.

Pruebas anteriores: 41 controladas y 2 Dart HTTP reales mediante el runner aislado de backend (`--mobile-http --flutter-bin RUTA_FLUTTER`). Estas últimas usan almacén en memoria, no KeyStore nativo. El usuario reportó login/restauración/cierre Android para Cliente y una sola cuenta mixta SaaS/Administrador empresarial. CU01 sigue con aceptación parcial por otros actores/recorridos; iOS no se compiló ni verificó en Windows. La evidencia detallada permanece local.
