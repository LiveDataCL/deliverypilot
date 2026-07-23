import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:driver/core/token_storage.dart';
import 'package:driver/features/auth/auth_state.dart';
import 'package:driver/main.dart';

/// Never touches the real flutter_secure_storage platform channel, which
/// isn't available under flutter_test -- AuthController.bootstrap() calls
/// TokenStorage.read() unconditionally on startup, so the real
/// FlutterSecureStorage-backed implementation would throw
/// MissingPluginException before any widget renders.
class _FakeTokenStorage extends TokenStorage {
  AuthTokens? _tokens;

  @override
  Future<AuthTokens?> read() async => _tokens;

  @override
  Future<void> write(AuthTokens tokens) async => _tokens = tokens;

  @override
  Future<void> clear() async => _tokens = null;
}

void main() {
  testWidgets('shows the login form when there is no stored session', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [tokenStorageProvider.overrideWithValue(_FakeTokenStorage())],
        child: const DriverApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Contraseña'), findsOneWidget);
    expect(find.text('Ingresar'), findsOneWidget);
  });
}
