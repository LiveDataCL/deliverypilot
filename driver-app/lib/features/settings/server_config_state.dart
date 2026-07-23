import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/server_config_storage.dart';
import '../../core/token_storage.dart';

final serverConfigStorageProvider = Provider((ref) => ServerConfigStorage());

sealed class ServerConfigState {
  const ServerConfigState();
}

class ServerConfigUnknown extends ServerConfigState {
  const ServerConfigUnknown();
}

class ServerConfigUnset extends ServerConfigState {
  const ServerConfigUnset();
}

class ServerConfigSet extends ServerConfigState {
  const ServerConfigSet(this.baseUrl);
  final String baseUrl;
}

class ServerConfigController extends StateNotifier<ServerConfigState> {
  ServerConfigController(this._storage, this._tokenStorage) : super(const ServerConfigUnknown()) {
    _bootstrap();
  }

  final ServerConfigStorage _storage;
  final TokenStorage _tokenStorage;

  Future<void> _bootstrap() async {
    final url = await _storage.read();
    state = url == null ? const ServerConfigUnset() : ServerConfigSet(url);
  }

  Future<void> save(String rawUrl) async {
    final normalized = _normalize(rawUrl);
    final previous = await _storage.read();
    await _storage.write(normalized);

    // An access/refresh token is only meaningful against the backend that
    // signed it (JWT_SECRET, business_id, user_id are all backend-specific)
    // -- pointing the app at a different server makes any stored session
    // stale, so clear it here rather than let it surface as a confusing
    // 401 on the next request.
    if (previous != null && previous != normalized) {
      await _tokenStorage.clear();
    }

    state = ServerConfigSet(normalized);
  }

  static String _normalize(String input) {
    var url = input.trim();
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    return url;
  }
}

final serverConfigProvider = StateNotifierProvider<ServerConfigController, ServerConfigState>(
  (ref) => ServerConfigController(ref.watch(serverConfigStorageProvider), ref.watch(tokenStorageProvider)),
);
