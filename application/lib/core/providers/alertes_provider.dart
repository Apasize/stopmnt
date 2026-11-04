// lib/core/providers/alertes_provider.dart
// Provider centralisé pour les alertes — une seule instance, persiste entre les onglets
// Polling toutes les 2 min + rafraîchissement immédiat sur réception FCM

import 'dart:async';
import 'package:flutter/foundation.dart';
import '../services/api_service.dart';
import '../models/alerte.dart';

class AlertesProvider extends ChangeNotifier {
  List<Alerte> _alertes          = [];
  List<Alerte> _nouvellesAlertes = [];
  Set<int>     _alertesVues      = {};
  bool         _loading          = false;
  Timer?       _pollTimer;

  List<Alerte> get alertes          => _alertes;
  List<Alerte> get nouvellesAlertes => _nouvellesAlertes;
  bool         get loading           => _loading;

  void demarrerPoll() {
    // Différé pour éviter notifyListeners() pendant le build (didChangeDependencies)
    Future.microtask(charger);
    _pollTimer ??= Timer.periodic(
      const Duration(minutes: 2),
      (_) => charger(),
    );
  }

  void arreterPoll() {
    _pollTimer?.cancel();
    _pollTimer         = null;
    _alertes           = [];
    _nouvellesAlertes  = [];
    _alertesVues       = {};
    _loading           = false;
    notifyListeners();
  }

  Future<void> charger() async {
    if (_loading) return;
    _loading = true;
    if (_alertes.isEmpty) notifyListeners();

    try {
      final data      = await ApiService.getMesAlertes();
      final nouvelles = data.map((j) => Alerte.fromJson(j)).toList();

      if (_alertesVues.isEmpty) {
        // Premier chargement — marquer tout vu sans bannière ni notification
        _alertesVues = nouvelles.map((a) => a.id).toSet();
        _alertes     = nouvelles;
      } else {
        final nonVues = nouvelles
            .where((a) => !_alertesVues.contains(a.id))
            .toList();
        _alertes = nouvelles;

        if (nonVues.isNotEmpty) {
          _nouvellesAlertes = nonVues;
          // Les notifications push sont gérées par FCM (worker → firebase).
          // Ici on met juste à jour la liste et la bannière in-app.
        }
      }
    } on TokenExpireException {
      _pollTimer?.cancel();
      _pollTimer = null;
    } catch (_) {
      // Réseau indisponible — conserver les données existantes
    }

    _loading = false;
    notifyListeners();
  }

  void marquerVues() {
    for (final a in _alertes) {
      _alertesVues.add(a.id);
    }
    _nouvellesAlertes = [];
    notifyListeners();
  }
}
