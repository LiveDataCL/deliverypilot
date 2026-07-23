/// Backend base URL, injected at build/run time via --dart-define, e.g.:
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.50:8000
///
/// Never hardcode a LAN IP here: the emulator's loopback alias
/// (10.0.2.2) and a physical device's view of the dev machine's LAN IP
/// are different addresses, and both change across networks/machines.
class Env {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
}
