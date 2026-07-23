// Constructor params here can't be initializing formals (this._field):
// the fields are private, and callers constructing these classes live in
// other files/libraries that can't reference a private named parameter.
// ignore_for_file: prefer_initializing_formals

import 'package:dio/dio.dart';

import 'env.dart';
import 'token_storage.dart';

/// Thrown when a request 401s and there's no usable refresh token (or the
/// refresh itself fails) -- callers treat this as "log the user out", the
/// same terminal case dispatch-web's client.ts reaches by clearing storage
/// and re-throwing.
class SessionExpiredException implements Exception {}

/// dio client with the same refresh contract dispatch-web's api/client.ts
/// uses against the same backend: attach the access token to every request,
/// and on a single 401 retry once after refreshing -- concurrent 401s while
/// a refresh is already in flight await the same refresh future instead of
/// each firing their own POST /auth/refresh.
class ApiClient {
  // Can't use an initializing formal (this._tokenStorage) here: the field is
  // private, and callers constructing ApiClient live in other files/libraries
  // that can't reference a private named parameter.
  ApiClient({required TokenStorage tokenStorage, Dio? dio})
      : _tokenStorage = tokenStorage,
        _dio = dio ?? Dio(BaseOptions(baseUrl: Env.apiBaseUrl)) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final tokens = await _tokenStorage.read();
          if (tokens != null) {
            options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          final request = error.requestOptions;
          final alreadyRetried = request.extra['retried'] == true;
          if (error.response?.statusCode != 401 || alreadyRetried) {
            handler.next(error);
            return;
          }

          try {
            final newAccessToken = await _refreshAccessToken();
            request.extra['retried'] = true;
            request.headers['Authorization'] = 'Bearer $newAccessToken';
            final response = await _dio.fetch(request);
            handler.resolve(response);
          } catch (_) {
            await _tokenStorage.clear();
            handler.reject(DioException(requestOptions: request, error: SessionExpiredException()));
          }
        },
      ),
    );
  }

  final Dio _dio;
  final TokenStorage _tokenStorage;
  Future<String>? _refreshInFlight;

  Future<String> _refreshAccessToken() {
    return _refreshInFlight ??= _doRefresh().whenComplete(() => _refreshInFlight = null);
  }

  Future<String> _doRefresh() async {
    final tokens = await _tokenStorage.read();
    if (tokens == null) throw SessionExpiredException();

    final response = await Dio(BaseOptions(baseUrl: Env.apiBaseUrl)).post(
      '/api/v1/auth/refresh',
      data: {'refresh_token': tokens.refreshToken},
    );
    final newTokens = AuthTokens(
      accessToken: response.data['access_token'] as String,
      refreshToken: response.data['refresh_token'] as String,
    );
    await _tokenStorage.write(newTokens);
    return newTokens.accessToken;
  }

  Dio get dio => _dio;
}
