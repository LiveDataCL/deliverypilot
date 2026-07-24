import 'dart:async';

import 'package:dio/dio.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show debugPrint, kDebugMode;
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
    } on DioException catch (e) {
      // Full detail to the log (dio's own LogInterceptor already covers the
      // request/response in debug builds -- this covers cases where the
      // error never reached that far, e.g. before a response exists at
      // all), a specific-but-clean message to the screen instead of one
      // generic string for every kind of failure.
      if (kDebugMode) debugPrint('Login failed: ${e.type} ${e.message} ${e.error}');
      state = AuthError(_messageForDioException(e));
    } catch (e) {
      if (kDebugMode) debugPrint('Login failed with an unexpected error: $e');
      state = const AuthError('No se pudo iniciar sesión. Intenta de nuevo.');
    }
  }

  String _messageForDioException(DioException e) {
    return switch (e.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.receiveTimeout =>
        'El servidor no respondió a tiempo. Verifica la URL en Configurar servidor.',
      DioExceptionType.connectionError =>
        'No se pudo conectar al servidor. Verifica que el teléfono esté en la '
            'misma red y que la URL en Configurar servidor sea correcta.',
      DioExceptionType.badCertificate => 'Error de certificado del servidor.',
      DioExceptionType.badResponse =>
        'El servidor respondió con un error (${e.response?.statusCode ?? "desconocido"}).',
      DioExceptionType.cancel => 'La solicitud fue cancelada.',
      DioExceptionType.unknown ||
      DioExceptionType.transformTimeout =>
        'No se pudo conectar al servidor. Verifica la URL en Configurar servidor.',
    };
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
    // Fire-and-forget: covers both a fresh login and an already-authenticated
    // app relaunch (this runs on both _bootstrap()'s and login()'s path to
    // AuthAuthenticated). Never awaited/blocking -- a missing token (no
    // Google Play Services, notification permission not granted yet --
    // that onboarding is a separate, later SPEC.md checklist item) must
    // never delay or fail login, same graceful-degradation tolerance
    // fcm_service.py already applies server-side.
    unawaited(_registerFcmToken());
    return AuthAuthenticated(user);
  }

  Future<void> _registerFcmToken() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token == null) return;
      await _repository.registerFcmToken(token);
    } catch (e) {
      if (kDebugMode) debugPrint('FCM token registration failed (non-fatal): $e');
    }
  }
}

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>(
  (ref) => AuthController(ref.watch(authRepositoryProvider)),
);
