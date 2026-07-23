import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'server_config_state.dart';

class ServerConfigScreen extends ConsumerStatefulWidget {
  const ServerConfigScreen({super.key});

  @override
  ConsumerState<ServerConfigScreen> createState() => _ServerConfigScreenState();
}

class _ServerConfigScreenState extends ConsumerState<ServerConfigScreen> {
  final _formKey = GlobalKey<FormState>();
  final _urlController = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final state = ref.read(serverConfigProvider);
    if (state is ServerConfigSet) {
      _urlController.text = state.baseUrl;
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  String? _validateUrl(String? value) {
    final url = value?.trim() ?? '';
    if (url.isEmpty) return 'Ingresa la URL del servidor';
    final uri = Uri.tryParse(url);
    // http:// only, deliberately: this stack has no TLS anywhere yet (local
    // dev backend included), so https:// silently produces a TLS handshake
    // against a plain-HTTP port -- the server can't parse it (shows up as
    // "Invalid HTTP request received" in its logs) and the app previously
    // surfaced this as an opaque, undiagnosable login failure. Revisit if a
    // real deployment ever serves this over TLS.
    if (uri == null || !uri.isAbsolute || uri.scheme != 'http') {
      return 'Debe ser una URL http:// válida (https:// no es compatible por ahora)';
    }
    return null;
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    await ref.read(serverConfigProvider.notifier).save(_urlController.text);
    if (mounted) {
      setState(() => _saving = false);
      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Configurar servidor')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 360),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Ingresa la IP local del servidor backend en la red de '
                    'desarrollo (ej. http://192.168.1.50:8000). Por ahora '
                    'solo se admite http:// -- este stack todavía no sirve '
                    'nada por https.',
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'URL del servidor',
                      hintText: 'http://192.168.1.50:8000',
                    ),
                    validator: _validateUrl,
                    onFieldSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _saving ? null : _submit,
                    child: _saving
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Guardar'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
