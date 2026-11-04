// lib/core/services/api_service.dart
// Service HTTP sécurisé — utilise la CA STOP-MNT pour valider les certificats
// Le téléphone ne fait confiance qu'aux certificats signés par notre CA interne
// Confiance limitée à cette CA embarquée — aucune autre autorité n'est acceptée

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'demo_backend.dart';

class ApiService {
  // Adresse du serveur, à fixer au build : --dart-define=API_BASE_URL=https://<serveur>/api/v1
  static const String _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://localhost/api/v1',
  );
  static const _storage = FlutterSecureStorage();

  // Callback appelé avec true/false selon la joignabilité du serveur
  static void Function(bool)? onConnectivite;

  // Callback appelé quand le serveur répond 401 — l'app doit se déconnecter
  static VoidCallback? onTokenExpire;

  // ── Mode démo ─────────────────────────────────────────
  // Aucune requête réseau : toutes les réponses viennent de DemoBackend.
  static bool _modeDemo = false;
  static bool get modeDemo => _modeDemo;

  static void activerModeDemo(bool actif) {
    _modeDemo = actif;
    if (actif) DemoBackend.reinitialiser();
  }

  // ── File de mesures différées (hors-ligne) ────────────
  // Une file par patient : des mesures en attente ne doivent jamais partir
  // sous le token d'un autre compte.
  static const _cleQueueLegacy = 'mesures_diff_v1';
  static String _cleQueue(String patientId) => 'mesures_diff_v2_$patientId';

  static String? _patientId;
  static final List<Map<String, dynamic>> _queue = [];
  static Future<void>? _chargementQueue;
  static bool _vidageEnCours = false;
  static void Function(int)? onQueueChange;

  static int get nbEnAttente => _queue.length;

  /// Un patient (réel ou démo) est connecté — sinon inutile d'envoyer.
  static bool get sessionActive => _patientId != null;

  /// À appeler à chaque changement de compte (login, session restaurée,
  /// logout → null). Charge la file du patient, ou la vide en mémoire.
  static Future<void> definirPatient(String? patientId) {
    if (patientId == _patientId && _chargementQueue != null) {
      return _chargementQueue!;
    }
    _patientId = patientId;
    _queue.clear();
    onQueueChange?.call(0);
    if (patientId == null || _modeDemo) {
      _chargementQueue = Future.value();
      return _chargementQueue!;
    }
    return _chargementQueue = _chargerQueue(patientId);
  }

  static Future<void> _chargerQueue(String patientId) async {
    try {
      final raw = await _storage.read(key: _cleQueue(patientId));
      // Migration : l'ancienne file globale (v1) est rattachée au premier
      // patient qui se connecte, puis supprimée.
      final legacy = await _storage.read(key: _cleQueueLegacy);
      if (_patientId != patientId) return; // compte changé pendant la lecture
      if (raw != null) {
        _queue.addAll((jsonDecode(raw) as List).cast<Map<String, dynamic>>());
      }
      if (legacy != null) {
        _queue.addAll((jsonDecode(legacy) as List).cast<Map<String, dynamic>>());
        await _storage.delete(key: _cleQueueLegacy);
        await _sauvegarderQueue();
      }
    } catch (e) {
      debugPrint('[API] Lecture file hors-ligne échouée: $e');
    }
    onQueueChange?.call(_queue.length);
  }

  static Future<void> _sauvegarderQueue() async {
    final id = _patientId;
    if (id == null) return;
    try {
      await _storage.write(key: _cleQueue(id), value: jsonEncode(_queue));
    } catch (_) {}
  }

  static Future<bool> _ajouterQueue({
    required String capteur,
    required Map<String, dynamic> mesures,
    required String horodatage,
    required String mesureId,
  }) async {
    if (_patientId == null) return false;
    await _chargementQueue;
    _queue.add({
      'capteur'  : capteur,
      'mesures'  : mesures,
      'timestamp': horodatage,
      'mesure_id': mesureId,
    });
    await _sauvegarderQueue();
    onQueueChange?.call(_queue.length);
    return true;
  }

  /// Renvoie les mesures en attente du patient courant.
  /// Un élément n'est retiré que s'il est accepté (201) ou rejeté
  /// définitivement (4xx de validation). 401, 408, 429, 5xx et erreurs
  /// réseau → on s'arrête et on garde tout pour la prochaine tentative.
  static Future<void> viderQueue() async {
    if (_modeDemo || _vidageEnCours) return;
    final patient = _patientId;
    if (patient == null) return;
    _vidageEnCours = true;
    try {
      await _chargementQueue;
      final aEnvoyer = List<Map<String, dynamic>>.from(_queue);
      for (final item in aEnvoyer) {
        if (_patientId != patient) return; // déconnexion pendant le vidage
        final http.Response response;
        try {
          response = await _doPost('/mesures', {
            'capteur'        : item['capteur'],
            'timestamp_data' : item['timestamp'],
            'mesures'        : item['mesures'],
            'deferred'       : true,
            // Anciennes entrées de file : pas d'identifiant, le serveur les accepte.
            if (item['mesure_id'] != null) 'mesure_id': item['mesure_id'],
          });
        } catch (e) {
          debugPrint('[API] Vidage file interrompu: $e');
          break;
        }
        if (_patientId != patient) return;
        final code = response.statusCode;
        if (code == 200 || code == 201) {
          _queue.remove(item);
        } else if (code == 401) {
          _verifierStatut(response); // déclenche la déconnexion
          break;
        } else if (code == 408 || code == 429 || code >= 500) {
          break; // serveur temporairement indisponible
        } else {
          debugPrint('[API] Mesure différée rejetée ($code), abandonnée: '
              '${_parseError(response.body)}');
          _queue.remove(item);
        }
      }
      await _sauvegarderQueue();
      onQueueChange?.call(_queue.length);
    } catch (_) {
      // TokenExpireException du 401 — déjà signalée via onTokenExpire
    } finally {
      _vidageEnCours = false;
    }
  }

  // Client HTTP mis en cache — le contexte SSL est coûteux à recréer à chaque appel
  static http.Client? _cachedClient;

  static Future<http.Client> _client() async {
    if (_cachedClient != null) return _cachedClient!;
    final caData = await rootBundle.load('assets/certs/stopmnt_ca.crt');
    final ctx    = SecurityContext(withTrustedRoots: false);
    ctx.setTrustedCertificatesBytes(caData.buffer.asUint8List());
    final ioClient = HttpClient(context: ctx)
      ..badCertificateCallback = (cert, host, port) => false;
    _cachedClient = IOClient(ioClient);
    return _cachedClient!;
  }

  // ── Token JWT ─────────────────────────────────────────
  static Future<String?> getToken() => _storage.read(key: 'jwt_token');
  static Future<void> setToken(String token) =>
      _storage.write(key: 'jwt_token', value: token);
  static Future<void> clearToken() => _storage.delete(key: 'jwt_token');

  static Future<Map<String, String>> _headers({bool auth = true}) async {
    final headers = {'Content-Type': 'application/json'};
    if (auth) {
      final token = await getToken();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  static void _verifierStatut(http.Response response) {
    if (response.statusCode == 401) {
      clearToken();
      onTokenExpire?.call();
      throw const TokenExpireException();
    }
  }

  // ── Helpers réseau avec signalement de connectivité ───
  static Future<http.Response> _doGet(String path) async {
    try {
      final client   = await _client();
      final response = await client.get(
        Uri.parse('$_baseUrl$path'),
        headers: await _headers(),
      );
      onConnectivite?.call(true);
      return response;
    } on IOException {
      onConnectivite?.call(false);
      rethrow;
    }
  }

  static Future<http.Response> _doPost(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final client   = await _client();
      final response = await client.post(
        Uri.parse('$_baseUrl$path'),
        headers: await _headers(),
        body: jsonEncode(body),
      );
      onConnectivite?.call(true);
      return response;
    } on IOException {
      onConnectivite?.call(false);
      rethrow;
    }
  }

  static Future<http.Response> _doPut(
    String path,
    Map<String, dynamic> body,
  ) async {
    try {
      final client   = await _client();
      final response = await client.put(
        Uri.parse('$_baseUrl$path'),
        headers: await _headers(),
        body: jsonEncode(body),
      );
      onConnectivite?.call(true);
      return response;
    } on IOException {
      onConnectivite?.call(false);
      rethrow;
    }
  }

  // ── Authentification ──────────────────────────────────
  static Future<Map<String, dynamic>> login(
      String email, String password) async {
    try {
      final client   = await _client();
      final response = await client.post(
        Uri.parse('$_baseUrl/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        await setToken(data['access_token'] as String);
        return data;
      }
      throw ApiException(
        statusCode: response.statusCode,
        message   : _parseError(response.body),
      );
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException(statusCode: 0, message: 'Erreur réseau : $e');
    }
  }

  // Récupérer le profil du patient connecté
  static Future<Map<String, dynamic>> getMonProfil() async {
    if (_modeDemo) return DemoBackend.monProfil();
    final response = await _doGet('/auth/me');
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  // ── Token FCM — push notifications ───────────────────────
  static Future<void> enregistrerTokenFcm(String token) async {
    if (_modeDemo) return;
    try {
      final client = await _client();
      await client.post(
        Uri.parse('$_baseUrl/auth/device/fcm-token'),
        headers: await _headers(),
        body: jsonEncode({'fcm_token': token}),
      );
    } catch (_) {
      // Échec silencieux — réessayé au prochain démarrage
    }
  }

  // ── Enrôlement dispositif ─────────────────────────────
  static Future<Map<String, dynamic>> enrollDevice() async {
    if (_modeDemo) return {'statut': 'demo'};
    final response = await _doPost('/auth/device/enroll', {});
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  static String _nouvelIdMesure() {
    final r = Random.secure();
    return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }

  // ── Mesures discrètes ─────────────────────────────────
  // Retourne {'differe': true} si l'envoi a été mis en file hors-ligne.
  static Future<Map<String, dynamic>> envoyerMesure({
    required String capteur,
    required Map<String, dynamic> mesures,
    bool deferred = false,
  }) async {
    if (_modeDemo) {
      return DemoBackend.envoyerMesure(capteur, mesures, DateTime.now());
    }
    // Même identifiant et même heure si la mesure repart de la file : le serveur
    // reconnaît alors un renvoi après une réponse perdue.
    final horodatage = DateTime.now().toUtc().toIso8601String();
    final mesureId = _nouvelIdMesure();
    try {
      final response = await _doPost('/mesures', {
        'capteur'        : capteur,
        'timestamp_data' : horodatage,
        'mesures'        : mesures,
        'deferred'       : deferred,
        'mesure_id'      : mesureId,
      });
      _verifierStatut(response);
      if (response.statusCode == 201) {
        // Le serveur répond de nouveau : on en profite pour vider la file.
        if (_queue.isNotEmpty) unawaited(viderQueue());
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      throw ApiException(
        statusCode: response.statusCode,
        message   : _parseError(response.body),
      );
    } on IOException {
      if (await _ajouterQueue(capteur: capteur, mesures: mesures, horodatage: horodatage, mesureId: mesureId)) {
        return {'differe': true};
      }
      rethrow;
    }
  }

  // ── Historique mesures ────────────────────────────────
  static Future<List<dynamic>> getHistoriqueMesures({int limite = 20}) async {
    if (_modeDemo) return DemoBackend.historique(limite);
    final response = await _doGet('/mesures/historique?limite=$limite');
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  // ── Profil médical ────────────────────────────────────
  static Future<Map<String, dynamic>> getMonProfilMedical() async {
    if (_modeDemo) return DemoBackend.profilMedical();
    final response = await _doGet('/profil-medical/moi');
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  static Future<Map<String, dynamic>> sauvegarderProfilMedical(
      Map<String, dynamic> data) async {
    if (_modeDemo) return DemoBackend.sauvegarderProfilMedical(data);
    final response = await _doPut('/profil-medical/moi', data);
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  // ── Alertes patient ───────────────────────────────────
  static Future<List<dynamic>> getMesAlertes() async {
    if (_modeDemo) return DemoBackend.alertes();
    final response = await _doGet('/alertes/mes-alertes');
    _verifierStatut(response);
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    }
    throw ApiException(
      statusCode: response.statusCode,
      message   : _parseError(response.body),
    );
  }

  // ── Helper erreur ─────────────────────────────────────
  static String _parseError(String body) {
    debugPrint('[API] Error body: $body');
    try {
      final json   = jsonDecode(body) as Map<String, dynamic>;
      final detail = json['detail'];
      if (detail is String) return detail;
      // Pydantic v2 — detail est une liste d'erreurs de validation
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first as Map<String, dynamic>;
        return first['msg'] as String? ?? body;
      }
      return json['message'] as String? ?? json['error'] as String? ?? body;
    } catch (_) {
      return body.isNotEmpty ? body : 'Erreur réseau';
    }
  }
}

class ApiException implements Exception {
  final int    statusCode;
  final String message;
  const ApiException({required this.statusCode, required this.message});

  @override
  String toString() => 'ApiException($statusCode): $message';
}

// Ajoute cette classe à la fin du fichier
class TokenExpireException implements Exception {
  const TokenExpireException();
}


