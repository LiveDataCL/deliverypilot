import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../../models/user.dart';
import '../settings/server_config_state.dart';
import 'auth_repository.dart';

// Only reachable once ServerConfigSet -- AppGate doesn't mount anything that
// watches authControllerProvider (and so doesn't construct AuthController,
// whose constructor kicks off _bootstrap()'s fetchMe() call) until the
// server config state is confirmed set. That ordering matters: without it, a
// stored session could get wrongly wiped by a bootstrap request firing
// against an empty/unknown baseUrl before the real one is known.
final apiClientProvider = Provider((ref) {
  final serverConfig = ref.watch(serverConfigProvider);
  final baseUrl = serverConfig is ServerConfigSet ? serverConfig.baseUrl : '';
  return ApiClient(baseUrl: baseUrl, tokenStorage: ref.watch(tokenStorageProvider));
});

final authRepositoryProvider = Provider(
  (ref) => AuthRepository(
    apiClient: ref.watch(apiClientProvider),
    tokenStorage: ref.watch(tokenStorageProvider),
  ),
);

sealed class AuthState {
  const AuthState();
}

class AuthUnknown extends AuthState {
  const AuthUnknown();
}

class AuthUnauthenticated extends AuthState {
  const AuthUnauthenticated();
}

class AuthAuthenticated extends AuthState {
  const AuthAuthenticated(this.user);
  final User user;
}

/// Thrown-as-state, not exceptions: the login screen reads this to show a
/// message without wrapping every call site in try/catch.
class AuthError extends AuthState {
  const AuthError(this.message);
  final String message;
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._repository) : super(const AuthUnknown()) {
    _bootstrap();
  }

  final AuthRepository _repository;

  Future<void> _bootstrap() async {
    if (!await _repository.hasStoredSession()) {
      state = const AuthUnauthenticated();
      return;
    }
    try {
      final user = await _repository.fetchMe();
      state = await _stateForUser(user);
    } catch (_) {
      await _repository.logout();
      state = const AuthUnauthenticated();
    }
  }

  Future<void> login(String email, String password) async {
    try {
      final user = await _repository.login(email, password);
      state = await _stateForUser(user);
    } on InvalidCredentialsException {
      state = const AuthError('Email o contraseña incorrectos');
    } catch (_) {
      state = const AuthError('No se pudo iniciar sesión. Intenta de nuevo.');
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    state = const AuthUnauthenticated();
  }

  /// Fail-closed: a valid token pair for a non-driver account (owner/
  /// dispatcher testing their own login, most likely) never reaches an
  /// authenticated state in this app, and doesn't linger in storage as if
  /// it were a valid driver session either.
  Future<AuthState> _stateForUser(User user) async {
    if (!user.isDriver) {
      await _repository.logout();
      return const AuthError('Esta app es solo para repartidores.');
    }
    return AuthAuthenticated(user);
  }
}

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>(
  (ref) => AuthController(ref.watch(authRepositoryProvider)),
);
