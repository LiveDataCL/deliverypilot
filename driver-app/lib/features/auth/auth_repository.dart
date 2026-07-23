// Same cross-library constraint as ApiClient's constructor -- see the note
// there.
// ignore_for_file: prefer_initializing_formals

import 'package:dio/dio.dart';

import '../../core/api_client.dart';
import '../../core/token_storage.dart';
import '../../models/user.dart';

class InvalidCredentialsException implements Exception {}

class AuthRepository {
  AuthRepository({required ApiClient apiClient, required TokenStorage tokenStorage})
      : _apiClient = apiClient,
        _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;

  Future<User> login(String email, String password) async {
    final Response response;
    try {
      response = await _apiClient.dio.post(
        '/api/v1/auth/login',
        data: {'email': email, 'password': password},
      );
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) throw InvalidCredentialsException();
      rethrow;
    }

    await _tokenStorage.write(
      AuthTokens(
        accessToken: response.data['access_token'] as String,
        refreshToken: response.data['refresh_token'] as String,
      ),
    );
    return fetchMe();
  }

  Future<User> fetchMe() async {
    final response = await _apiClient.dio.get('/api/v1/auth/me');
    return User.fromJson(response.data as Map<String, dynamic>);
  }

  /// Registers this device's FCM token against the authenticated user's own
  /// account (PATCH /api/v1/auth/me/fcm-token). Not yet called anywhere in
  /// the login flow -- there is no real device token to pass it until the
  /// Firebase project exists and firebase_messaging is wired in a follow-up.
  /// Left here, real and tested against the backend, so that follow-up is a
  /// caller, not a new code path.
  Future<void> registerFcmToken(String fcmToken) async {
    await _apiClient.dio.patch('/api/v1/auth/me/fcm-token', data: {'fcm_token': fcmToken});
  }

  Future<bool> hasStoredSession() async {
    return await _tokenStorage.read() != null;
  }

  Future<void> logout() async {
    await _tokenStorage.clear();
  }
}
