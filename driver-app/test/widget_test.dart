import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:driver/core/providers.dart';
import 'package:driver/core/server_config_storage.dart';
import 'package:driver/core/token_storage.dart';
import 'package:driver/features/settings/server_config_state.dart';
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

/// Same rationale as _FakeTokenStorage, for the server-URL secure-storage key.
class _FakeServerConfigStorage extends ServerConfigStorage {
  _FakeServerConfigStorage([this._url]);
  String? _url;

  @override
  Future<String?> read() async => _url;

  @override
  Future<void> write(String baseUrl) async => _url = baseUrl;

  @override
  Future<void> clear() async => _url = null;
}

void main() {
  testWidgets('shows the login form when a server URL is already configured', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          tokenStorageProvider.overrideWithValue(_FakeTokenStorage()),
          serverConfigStorageProvider.overrideWithValue(_FakeServerConfigStorage('http://example.com')),
        ],
        child: const DriverApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Contraseña'), findsOneWidget);
    expect(find.text('Ingresar'), findsOneWidget);
  });

  testWidgets('shows the server config screen first when no URL is stored yet', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          tokenStorageProvider.overrideWithValue(_FakeTokenStorage()),
          serverConfigStorageProvider.overrideWithValue(_FakeServerConfigStorage()),
        ],
        child: const DriverApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('URL del servidor'), findsOneWidget);
    expect(find.text('Guardar'), findsOneWidget);
  });
}
