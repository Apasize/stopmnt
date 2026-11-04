// lib/core/providers/theme_provider.dart
// Gestion du thème clair/sombre
// Persiste la préférence dans le stockage sécurisé

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ThemeProvider extends ChangeNotifier {
  static const _storage = FlutterSecureStorage();
  ThemeMode _mode = ThemeMode.system;

  ThemeMode get mode => _mode;
  bool get isDark => _mode == ThemeMode.dark;

  ThemeProvider() {
    _charger();
  }

  Future<void> _charger() async {
    final val = await _storage.read(key: 'theme_mode');
    if (val == 'dark')  _mode = ThemeMode.dark;
    if (val == 'light') _mode = ThemeMode.light;
    notifyListeners();
  }

  Future<void> basculer() async {
    _mode = _mode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    await _storage.write(
      key   : 'theme_mode',
      value : _mode == ThemeMode.dark ? 'dark' : 'light',
    );
    notifyListeners();
  }
}