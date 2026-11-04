// lib/core/providers/profil_medical_provider.dart
// Dossier médical — source de vérité : API backend (par patient via JWT).
// Cache local FlutterSecureStorage pour le mode hors-ligne, clé par patientId.
// Une modification faite hors-ligne est marquée « à synchroniser » et poussée
// au serveur avant toute relecture — elle n'est jamais écrasée par l'API.

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../services/api_service.dart';

class ProfilMedicalProvider extends ChangeNotifier {
  static const _storage = FlutterSecureStorage();

  String?       _patientId;
  String?       _groupeSanguin;
  List<String>  _antecedents        = [];
  List<String>  _maladiesChroniques = [];
  List<String>  _traitements        = [];
  bool          _chargement         = false;
  bool          _aSynchroniser      = false;
  String?       _erreur;
  // Incrémenté à chaque changement de patient : une réponse arrivée après
  // un changement de compte est ignorée.
  int           _generation         = 0;

  String?      get groupeSanguin      => _groupeSanguin;
  List<String> get antecedents        => List.unmodifiable(_antecedents);
  List<String> get maladiesChroniques => List.unmodifiable(_maladiesChroniques);
  List<String> get traitements        => List.unmodifiable(_traitements);
  bool         get chargement         => _chargement;
  bool         get aSynchroniser      => _aSynchroniser;
  String?      get erreur             => _erreur;

  bool get aDonnees =>
      _groupeSanguin != null ||
      _antecedents.isNotEmpty ||
      _maladiesChroniques.isNotEmpty ||
      _traitements.isNotEmpty;

  String? get _cleCache =>
      _patientId != null ? 'profil_medical_v2_$_patientId' : null;

  Map<String, dynamic> get _json => {
    'groupe_sanguin'      : _groupeSanguin,
    'antecedents'         : _antecedents,
    'maladies_chroniques' : _maladiesChroniques,
    'traitements'         : _traitements,
  };

  void _appliquer(Map<String, dynamic> data) {
    _groupeSanguin      = data['groupe_sanguin'] as String?;
    _antecedents        = (data['antecedents']         as List?)?.cast<String>() ?? [];
    _maladiesChroniques = (data['maladies_chroniques'] as List?)?.cast<String>() ?? [];
    _traitements        = (data['traitements']         as List?)?.cast<String>() ?? [];
  }

  // Appelé par ChangeNotifierProxyProvider.update, donc pendant un build :
  // aucune notification synchrone ici, tout est différé.
  void mettreAJourPatient(String? patientId) {
    if (patientId == _patientId) return;
    _patientId = patientId;
    _generation++;
    _groupeSanguin      = null;
    _antecedents        = [];
    _maladiesChroniques = [];
    _traitements        = [];
    _erreur             = null;
    _aSynchroniser      = false;
    _chargement         = false;
    scheduleMicrotask(() {
      notifyListeners();
      if (patientId != null) charger();
    });
  }

  Future<void> charger() async {
    if (_patientId == null || _chargement) return;
    final gen = _generation;
    _chargement = true;
    notifyListeners();

    // 1. Le cache d'abord : affichage immédiat + détection d'une sauvegarde
    //    hors-ligne non encore synchronisée.
    await _chargerCache();
    if (gen != _generation) return;
    notifyListeners();

    // 2. Modification locale en attente → la pousser au lieu de l'écraser.
    if (_aSynchroniser) {
      await _pousser(gen);
    } else {
      try {
        final data = await ApiService.getMonProfilMedical();
        if (gen != _generation) return;
        _appliquer(data);
        _erreur = null;
        debugPrint('[PROFIL] Chargé depuis API pour $_patientId');
        await _sauvegarderCache();
      } catch (e) {
        debugPrint('[PROFIL] API indisponible, cache conservé: $e');
      }
    }

    if (gen != _generation) return;
    _chargement = false;
    notifyListeners();
  }

  /// Pousse une sauvegarde hors-ligne en attente (appelé au retour réseau).
  Future<void> synchroniser() async {
    if (_patientId == null || !_aSynchroniser || _chargement) return;
    final gen = _generation;
    await _pousser(gen);
    if (gen == _generation) notifyListeners();
  }

  Future<void> sauvegarder({
    required String? groupeSanguin,
    required List<String> antecedents,
    required List<String> maladiesChroniques,
    required List<String> traitements,
  }) async {
    if (_patientId == null) return;
    final gen = _generation;

    _groupeSanguin      = groupeSanguin;
    _antecedents        = List.from(antecedents);
    _maladiesChroniques = List.from(maladiesChroniques);
    _traitements        = List.from(traitements);
    _aSynchroniser      = true;
    _erreur             = null;
    notifyListeners();

    // Cache écrit avant l'appel réseau : rien n'est perdu si l'app est tuée.
    await _sauvegarderCache();
    await _pousser(gen);
    if (gen == _generation) notifyListeners();
  }

  Future<void> _pousser(int gen) async {
    try {
      await ApiService.sauvegarderProfilMedical(_json);
      if (gen != _generation) return;
      _aSynchroniser = false;
      _erreur        = null;
      debugPrint('[PROFIL] Synchronisé sur API pour $_patientId');
    } catch (e) {
      if (gen != _generation) return;
      _erreur = 'Sauvegarde hors-ligne — sera synchronisée à la reconnexion';
      debugPrint('[PROFIL] Sauvegarde API échouée, reste en attente: $e');
    }
    await _sauvegarderCache();
  }

  Future<void> _sauvegarderCache() async {
    final cle = _cleCache;
    if (cle == null) return;
    try {
      await _storage.write(
        key  : cle,
        value: jsonEncode({..._json, 'a_synchroniser': _aSynchroniser}),
      );
    } catch (e) {
      debugPrint('[PROFIL] Erreur cache: $e');
    }
  }

  Future<void> _chargerCache() async {
    final cle = _cleCache;
    if (cle == null) return;
    try {
      final raw = await _storage.read(key: cle);
      if (raw == null || cle != _cleCache) return;
      final json = jsonDecode(raw) as Map<String, dynamic>;
      _appliquer(json);
      _aSynchroniser = json['a_synchroniser'] as bool? ?? false;
      debugPrint('[PROFIL] Chargé depuis cache pour $_patientId '
          '(à synchroniser: $_aSynchroniser)');
    } catch (e) {
      debugPrint('[PROFIL] Erreur lecture cache: $e');
    }
  }
}
