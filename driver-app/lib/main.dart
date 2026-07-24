import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'features/auth/auth_state.dart';
import 'features/auth/login_screen.dart';
import 'features/home/home_screen.dart';
import 'features/settings/server_config_screen.dart';
import 'features/settings/server_config_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // No explicit FirebaseOptions: android/app/google-services.json + the
  // google-services Gradle plugin already provide everything
  // Firebase.initializeApp() needs on Android (the only platform this app
  // targets -- see pubspec.yaml).
  await Firebase.initializeApp();
  runApp(const ProviderScope(child: DriverApp()));
}

class DriverApp extends StatelessWidget {
  const DriverApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DeliveryPilot Repartidor',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue)),
      home: const AppGate(),
    );
  }
}

/// Gates on the server URL before anything auth-related: AuthGate (and the
/// authControllerProvider it watches) is only ever built once the server
/// config is confirmed set -- see the note on apiClientProvider in
/// auth_state.dart for why that ordering matters.
class AppGate extends ConsumerWidget {
  const AppGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final serverConfig = ref.watch(serverConfigProvider);

    return switch (serverConfig) {
      ServerConfigUnknown() => const Scaffold(body: Center(child: CircularProgressIndicator())),
      ServerConfigUnset() => const ServerConfigScreen(),
      ServerConfigSet() => const AuthGate(),
    };
  }
}

class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);

    return switch (authState) {
      AuthUnknown() => const Scaffold(body: Center(child: CircularProgressIndicator())),
      AuthAuthenticated() => const HomeScreen(),
      AuthUnauthenticated() || AuthError() => const LoginScreen(),
    };
  }
}
