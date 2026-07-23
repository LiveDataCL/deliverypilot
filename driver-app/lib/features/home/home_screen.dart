import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_state.dart';

/// Placeholder post-login screen -- just enough to prove the login flow
/// works end-to-end on a real device. The delivery list/detail (SPEC.md App
/// Flutter checklist) is a separate, later checkpoint.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    final email = state is AuthAuthenticated ? state.user.email : '';

    return Scaffold(
      appBar: AppBar(
        title: const Text('DeliveryPilot Repartidor'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Cerrar sesión',
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(child: Text('Sesión iniciada como $email')),
    );
  }
}
