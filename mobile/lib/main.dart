import 'package:flutter/material.dart';

import 'auth/auth_api.dart';
import 'auth/session_controller.dart';
import 'auth/session_store.dart';
import 'config/api_config.dart';
import 'screens/access_page.dart';
import 'screens/account_page.dart';

const ivory = Color(0xFFF7F4EC);
const charcoal = Color(0xFF202C27);
const emerald = Color(0xFF12644E);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    final api = AuthApi(ApiConfig(ApiConfig.defaultBase));
    runApp(
      VestiNovaApp(
        controller: SessionController(api: api, store: SecureSessionStore()),
      ),
    );
  } on FormatException catch (error) {
    runApp(
      MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(error.message),
            ),
          ),
        ),
      ),
    );
  }
}

class VestiNovaApp extends StatefulWidget {
  const VestiNovaApp({
    super.key,
    required this.controller,
    this.restoreOnStart = true,
  });
  final SessionController controller;
  final bool restoreOnStart;
  @override
  State<VestiNovaApp> createState() => _VestiNovaAppState();
}

class _VestiNovaAppState extends State<VestiNovaApp> {
  @override
  void initState() {
    super.initState();
    if (widget.restoreOnStart) _restore();
  }

  Future<void> _restore() async {
    await widget.controller.restore();
    if (!mounted || widget.controller.signedIn || widget.controller.restoring) {
      return;
    }
    if (ApiConfig.initialStore.isNotEmpty) {
      await widget.controller.resolveStore(ApiConfig.initialStore);
    }
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'VestiNova',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: emerald, surface: ivory)
          .copyWith(
            primary: emerald,
            onPrimary: Colors.white,
            onSurface: charcoal,
          ),
      scaffoldBackgroundColor: ivory,
      appBarTheme: const AppBarTheme(
        backgroundColor: ivory,
        foregroundColor: charcoal,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 18,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
    ),
    home: AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) => Scaffold(
        appBar: AppBar(
          title: const Text(
            'VestiNova',
            style: TextStyle(
              fontFamily: 'serif',
              fontSize: 30,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        body: SafeArea(
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 600),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 40),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (widget.controller.busy) ...[
                      const LinearProgressIndicator(
                        semanticsLabel: 'Comprobando acceso',
                      ),
                      const SizedBox(height: 20),
                    ],
                    if (widget.controller.error != null)
                      MessageBox(
                        message: widget.controller.error!,
                        error: true,
                      ),
                    if (widget.controller.notice != null)
                      MessageBox(message: widget.controller.notice!),
                    if (widget.controller.restoring)
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            'Restaurando tu acceso',
                            style: Theme.of(context).textTheme.headlineSmall,
                          ),
                          const SizedBox(height: 12),
                          const Text(
                            'Tu sesión se comprueba con VestiNova antes de mostrar tu cuenta.',
                          ),
                          if (!widget.controller.busy) ...[
                            const SizedBox(height: 20),
                            FilledButton(
                              onPressed: widget.controller.restore,
                              child: const Text('Reintentar conexión'),
                            ),
                          ],
                        ],
                      )
                    else if (widget.controller.signedIn)
                      AccountPage(controller: widget.controller)
                    else
                      AccessPage(controller: widget.controller),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class MessageBox extends StatelessWidget {
  const MessageBox({super.key, required this.message, this.error = false});
  final String message;
  final bool error;
  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: error ? const Color(0xFFFFE9E3) : const Color(0xFFE0EFE6),
        border: Border.all(color: error ? const Color(0xFF873F27) : emerald),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        message,
        style: TextStyle(color: error ? const Color(0xFF662A18) : charcoal),
      ),
    ),
  );
}
