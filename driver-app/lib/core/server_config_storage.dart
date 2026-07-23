import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Backend base URL, persisted the same way the token pair is (Keystore-
/// backed secure storage, not SharedPreferences) and editable at runtime
/// from ServerConfigScreen -- there is no compile-time default, because this
/// dev machine's LAN IP changes across reconnects and the same screen has to
/// double as the switch to Railway production later.
class ServerConfigStorage {
  ServerConfigStorage({FlutterSecureStorage? storage}) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _baseUrlKey = 'dp_base_url';

  Future<String?> read() => _storage.read(key: _baseUrlKey);

  Future<void> write(String baseUrl) => _storage.write(key: _baseUrlKey, value: baseUrl);

  Future<void> clear() => _storage.delete(key: _baseUrlKey);
}
