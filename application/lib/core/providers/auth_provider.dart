// lib/core/providers/auth_provider.dart
// Gestion de l'état d'authentification dans toute l'app
// Utilise Provider pour notifier les widgets du changement d'état

import 'dart:async';
import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';

class AuthProvider extends ChangeNotifier with WidgetsBindingObserver {
  static const _storage = FlutterSecureStorage();

  // État courant
  bool   _loading      = false;
  bool   _connecte     = false;
  bool _tokenExpire    = false;
  bool _modeDemo       = false;
  String? _patientId;
  String? _email;
  String? _nom;
  String? _prenom;
  String? _role;
  String? _departement;
  String? _erreur;
  Timer?  _tokenTimer;

  // Getters
  bool    get loading      => _loading;
  bool    get connecte     => _connecte;
  String? get patientId    => _patientId;
  bool    get tokenExpire  => _tokenExpire;
  bool    get modeDemo     => _modeDemo;
  String? get email        => _email;
  String? get nom          => _nom;
  String? get prenom       => _prenom;
  String? get role         => _role;
  String? get departement  => _departement;
  String? get erreur       => _erreur;

  VoidCallback? onLogout;

  AuthProvider() {
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _tokenTimer?.cancel();
    super.dispose();
  }

  // ── Cycle de vie de l'app — vérifier le token au retour au premier plan ──
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _connecte) {
      _verifierExpirationLocale();
    }
  }

  // ── Vérification locale du token JWT (sans appel réseau) ─────────────────
  Future<void> _verifierExpirationLocale() async {
    final token = await ApiService.getToken();
    if (token == null) return;
    final payload = _decoderJwt(token);
    final exp     = payload['exp'];
    if (exp == null) return;
    final expDate = DateTime.fromMillisecondsSinceEpoch(
      (exp as int) * 1000, isUtc: true,
    );
    if (DateTime.now().toUtc().isAfter(expDate)) {
      gererTokenExpire();
    }
  }

  // ── Timer périodique toutes les 5 min ────────────────────────────────────
  void _demarrerTimerToken() {
    _tokenTimer?.cancel();
    _tokenTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      if (_connecte) _verifierExpirationLocale();
      if (_connecte) ApiService.viderQueue();
    });
  }

  /// Vérifie si un token existe au démarrage de l'app.
  /// Serveur injoignable → session restaurée depuis le cache local tant que
  /// le JWT n'est pas expiré (le mode hors-ligne doit marcher dès le lancement).
  /// Seul un 401 du serveur ou un JWT expiré déconnecte.
  Future<void> verifierSession() async {
    final token = await ApiService.getToken();
    if (token == null) {
      _loading = false;
      notifyListeners();
      return;
    }

    try {
      final profil = await ApiService.getMonProfil();
      _appliquerProfil(profil);
      _connecte = true;
      await _sauvegarderUserData();
    } on TokenExpireException {
      _connecte = false;
    } catch (e) {
      debugPrint('[AUTH] Serveur injoignable au démarrage: $e');
      _connecte = !_jwtExpire(token) && await _restaurerUserData();
      if (!_connecte) await ApiService.clearToken();
    }

    if (_connecte) await _ouvrirSession();

    _loading = false;
    notifyListeners();
  }

  void _appliquerProfil(Map<String, dynamic> profil) {
    _email       = profil['email']       as String? ?? _email;
    _patientId   = profil['patient_id']  as String? ?? _patientId;
    _nom         = profil['nom']         as String?;
    _prenom      = profil['prenom']      as String?;
    _role        = profil['role']        as String? ?? _role;
    _departement = profil['departement'] as String? ?? _departement;
  }

  Future<void> _sauvegarderUserData() => _storage.write(
    key   : 'user_data',
    value : jsonEncode({
      'patient_id'  : _patientId,
      'email'       : _email,
      'nom'         : _nom,
      'prenom'      : _prenom,
      'role'        : _role,
      'departement' : _departement,
    }),
  );

  Future<bool> _restaurerUserData() async {
    try {
      final raw = await _storage.read(key: 'user_data');
      if (raw == null) return false;
      _appliquerProfil(jsonDecode(raw) as Map<String, dynamic>);
      return _patientId != null;
    } catch (_) {
      return false;
    }
  }

  // Tâches communes à toute ouverture de session (login, restauration, démo)
  Future<void> _ouvrirSession() async {
    await ApiService.definirPatient(_patientId);
    if (_modeDemo) return;
    _demarrerTimerToken();
    NotificationService.enregistrerToken();
    ApiService.viderQueue();
  }

  /// Entrée sans compte ni serveur — données fictives (DemoBackend).
  Future<void> entrerModeDemo() async {
    ApiService.activerModeDemo(true);
    _modeDemo    = true;
    _tokenExpire = false;
    _erreur      = null;
    _appliquerProfil(await ApiService.getMonProfil());
    _connecte    = true;
    await _ouvrirSession();
    notifyListeners();
  }

  /// Nom d'affichage — prénom si disponible, sinon partie avant @ de l'email
  String get nomAffichage {
    if (_prenom != null && _prenom!.isNotEmpty) return _prenom!;
    if (_nom    != null && _nom!.isNotEmpty)    return _nom!;
    return _email?.split('@').first ?? 'Patient';
  }

  /// Connexion avec email et mot de passe
  Future<bool> login(String email, String password) async {
    _loading = true;
    _erreur  = null;
    notifyListeners();

    try {
      final data = await ApiService.login(email, password);

      _tokenExpire = false;  // réinitialiser le flag à la reconnexion

      final payload = _decoderJwt(data['access_token'] as String);

      _patientId   = payload['patient_id']  as String?;
      _email       = payload['email']       as String?;
      _role        = payload['role']        as String?;
      _departement = payload['departement'] as String?;

      try {
        _appliquerProfil(await ApiService.getMonProfil());
      } catch (_) {}

      // Sans dispositif enrôlé, le serveur refuse les mesures du patient.
      if (_role == 'patient') {
        try {
          await ApiService.enrollDevice();
        } catch (e) {
          debugPrint('[AUTH] Enrôlement échoué : $e');
        }
      }

      _connecte = true;
      await _sauvegarderUserData();
      await _ouvrirSession();

      return true;

    } on ApiException catch (e) {
      _erreur = e.message;
      return false;
    } catch (_) {
      _erreur = 'Erreur de connexion. Vérifiez votre réseau.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _fermerSession();
    await ApiService.clearToken();
    await _storage.delete(key: 'user_data');
    notifyListeners();
  }

  void gererTokenExpire() {
    if (!_connecte || _modeDemo) return; // déjà traité (plusieurs 401 en vol)
    _fermerSession();
    _tokenExpire = true;
    ApiService.clearToken();
    notifyListeners();
  }

  void _fermerSession() {
    _tokenTimer?.cancel();
    _tokenTimer = null;
    onLogout?.call();
    if (_modeDemo) ApiService.activerModeDemo(false);
    ApiService.definirPatient(null);
    _modeDemo    = false;
    _connecte    = false;
    _email       = null;
    _patientId   = null;
    _nom         = null;
    _prenom      = null;
    _role        = null;
    _departement = null;
  }

  bool _jwtExpire(String token) {
    try {
      final exp = _decoderJwt(token)['exp'];
      if (exp is! int) return false;
      return DateTime.now().toUtc().isAfter(
        DateTime.fromMillisecondsSinceEpoch(exp * 1000, isUtc: true),
      );
    } catch (_) {
      return true;
    }
  }

  /// Décode le payload d'un token JWT sans vérifier la signature
  /// La vérification est faite côté serveur — ici on lit juste les claims
  Map<String, dynamic> _decoderJwt(String token) {
    final parts   = token.split('.');
    if (parts.length != 3) return {};
    final payload = parts[1];
    // Ajouter le padding Base64 si nécessaire
    final padded  = payload.padRight(
        payload.length + (4 - payload.length % 4) % 4, '='
    );
    final decoded = utf8.decode(base64Url.decode(padded));
    return jsonDecode(decoded) as Map<String, dynamic>;
  }
}

