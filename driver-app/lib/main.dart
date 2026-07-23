import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'features/auth/auth_state.dart';
import 'features/auth/login_screen.dart';
import 'features/home/home_screen.dart';
import 'features/settings/server_config_screen.dart';
import 'features/settings/server_config_state.dart';

void main() {
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
