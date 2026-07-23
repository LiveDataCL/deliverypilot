import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'token_storage.dart';

/// Shared by auth_state.dart and settings/server_config_state.dart -- lives
/// here instead of either of those files so neither has to import the other
/// just to reach this one provider.
final tokenStorageProvider = Provider((ref) => TokenStorage());
