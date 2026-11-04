import 'package:flutter/foundation.dart';
import '../services/api_service.dart';

class ConnectiviteProvider extends ChangeNotifier {
  bool _joignable   = true;
  int  _nbEnAttente = 0;

  bool get joignable   => _joignable;
  int  get nbEnAttente => _nbEnAttente;

  // Appelé au retour du réseau (après la file de mesures) — ex. profil médical
  VoidCallback? onReconnexion;

  ConnectiviteProvider() {
    _nbEnAttente = ApiService.nbEnAttente;
    ApiService.onQueueChange = (n) {
      if (_nbEnAttente == n) return;
      _nbEnAttente = n;
      notifyListeners();
    };
  }

  void mettreAJour(bool joignable) {
    if (_joignable == joignable) return;
    _joignable = joignable;
    notifyListeners();
    if (joignable) {
      ApiService.viderQueue();
      onReconnexion?.call();
    }
  }
}
