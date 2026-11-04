// lib/core/services/demo_backend.dart
// Faux backend en mémoire pour le mode démo (entrée sans compte ni serveur).
// Mêmes formats JSON que l'API réelle — les écrans ne voient aucune différence.
// Rien n'est persisté : tout est réinitialisé à la sortie du mode démo.

import 'dart:math';

class DemoBackend {
  static const patientId = 'demo';

  static final _rand = Random(42);
  static int _prochainId = 1;
  static List<Map<String, dynamic>> _mesures = [];
  static List<Map<String, dynamic>> _alertes = [];
  static Map<String, dynamic> _profilMedical = {};
  // Anti-spam : une alerte max par capteur toutes les 10 min (simulation = envoi / 30 s)
  static final Map<String, DateTime> _derniereAlerte = {};

  static void reinitialiser() {
    _prochainId = 1;
    _derniereAlerte.clear();
    _profilMedical = {
      'groupe_sanguin'      : 'O+',
      'antecedents'         : ['Appendicectomie (2015)'],
      'maladies_chroniques' : ['Hypertension artérielle'],
      'traitements'         : ['Amlodipine 5 mg — 1/jour'],
    };
    _genererHistorique();
    _genererAlertes();
  }

  static Future<void> _latence() =>
      Future.delayed(Duration(milliseconds: 150 + _rand.nextInt(250)));

  // ── Endpoints ─────────────────────────────────────────

  static Future<Map<String, dynamic>> monProfil() async {
    await _latence();
    return {
      'email'       : 'demo@stopmnt.bj',
      'patient_id'  : patientId,
      'nom'         : 'Démo',
      'prenom'      : 'Patient',
      'role'        : 'patient',
      'departement' : 'Atlantique',
    };
  }

  static Future<List<dynamic>> historique(int limite) async {
    await _latence();
    final tri = List<Map<String, dynamic>>.from(_mesures)
      ..sort((a, b) => (b['timestamp'] as String).compareTo(a['timestamp'] as String));
    return tri.take(limite).toList();
  }

  static Future<List<dynamic>> alertes() async {
    await _latence();
    return List<Map<String, dynamic>>.from(_alertes)
      ..sort((a, b) => (b['timestamp'] as String).compareTo(a['timestamp'] as String));
  }

  static Future<Map<String, dynamic>> profilMedical() async {
    await _latence();
    return Map<String, dynamic>.from(_profilMedical);
  }

  static Future<Map<String, dynamic>> sauvegarderProfilMedical(
      Map<String, dynamic> data) async {
    await _latence();
    _profilMedical = Map<String, dynamic>.from(data);
    return Map<String, dynamic>.from(_profilMedical);
  }

  static Future<Map<String, dynamic>> envoyerMesure(
      String capteur, Map<String, dynamic> mesures, DateTime quand) async {
    await _latence();
    final anomalie = _anomalie(mesures);
    final mesure   = _ajouterMesure(capteur, mesures, quand, anomalie: anomalie != null);

    Map<String, dynamic>? alerte;
    if (anomalie != null) {
      final derniere = _derniereAlerte[capteur];
      if (derniere == null || quand.difference(derniere).inMinutes >= 10) {
        _derniereAlerte[capteur] = quand;
        alerte = _ajouterAlerte(capteur, anomalie.$1, anomalie.$2, quand);
      }
    }
    return {...mesure, 'alerte': alerte};
  }

  // ── Seuils (approximation des règles serveur) ─────────

  static (String, String)? _anomalie(Map<String, dynamic> m) {
    double? v(String k) => (m[k] as num?)?.toDouble();
    final sys = v('systolique'), dia = v('diastolique');
    final glyc = v('glycemie'), spo2 = v('spo2'), fc = v('fc'), temp = v('temperature');

    if (sys != null && sys >= 180 || dia != null && dia >= 110) {
      return ('critique', 'Crise hypertensive : ${sys?.round()}/${dia?.round()} mmHg');
    }
    if (spo2 != null && spo2 < 90) {
      return ('critique', 'Désaturation sévère : SpO₂ ${spo2.round()} %');
    }
    if (glyc != null && glyc >= 2.0) {
      return ('critique', 'Hyperglycémie sévère : ${glyc.toStringAsFixed(2)} g/L');
    }
    if (sys != null && sys >= 140 || dia != null && dia >= 90) {
      return ('alerte', 'Tension élevée : ${sys?.round()}/${dia?.round()} mmHg');
    }
    if (glyc != null && glyc >= 1.26) {
      return ('alerte', 'Glycémie élevée : ${glyc.toStringAsFixed(2)} g/L');
    }
    if (spo2 != null && spo2 < 94) {
      return ('alerte', 'SpO₂ basse : ${spo2.round()} %');
    }
    if (fc != null && (fc > 120 || fc < 45)) {
      return ('alerte', 'Fréquence cardiaque anormale : ${fc.round()} bpm');
    }
    if (temp != null && temp >= 38) {
      return ('alerte', 'Fièvre : ${temp.toStringAsFixed(1)} °C');
    }
    return null;
  }

  // ── Génération des données initiales ──────────────────

  static Map<String, dynamic> _ajouterMesure(
    String capteur,
    Map<String, dynamic> mesures,
    DateTime quand, {
    bool anomalie = false,
    bool deferred = false,
  }) {
    final m = {
      'id'        : _prochainId++,
      'capteur'   : capteur,
      'timestamp' : quand.toUtc().toIso8601String(),
      'mesures'   : mesures,
      'anomalie'  : anomalie,
      'deferred'  : deferred,
    };
    _mesures.add(m);
    return m;
  }

  static Map<String, dynamic> _ajouterAlerte(
      String capteur, String niveau, String message, DateTime quand) {
    final a = {
      'id'          : _prochainId++,
      'patient_id'  : patientId,
      'departement' : 'Atlantique',
      'capteur'     : capteur,
      'niveau'      : niveau,
      'message'     : message,
      'timestamp'   : quand.toUtc().toIso8601String(),
      'acquittee'   : false,
    };
    _alertes.add(a);
    return a;
  }

  static double _bruit(double base, double amplitude) =>
      base + (_rand.nextDouble() * 2 - 1) * amplitude;

  static void _genererHistorique() {
    _mesures = [];
    final now = DateTime.now();

    for (var j = 13; j >= 0; j--) {
      final jour = DateTime(now.year, now.month, now.day).subtract(Duration(days: j));
      // Légère dérive : tension un peu plus haute en début de période
      final derive = j / 13 * 6;

      for (final h in [8, 19]) {
        final quand = jour.add(Duration(hours: h, minutes: _rand.nextInt(40)));
        if (quand.isAfter(now)) continue;
        final sys = _bruit(132 + derive, 8).round();
        final dia = _bruit(84 + derive / 2, 5).round();
        _ajouterMesure('tensiometre',
            {'systolique': sys, 'diastolique': dia, 'fc': _bruit(74, 6).round()},
            quand, anomalie: sys >= 140 || dia >= 90);
      }

      final matin = jour.add(Duration(hours: 7, minutes: _rand.nextInt(30)));
      if (!matin.isAfter(now)) {
        final glyc = double.parse(_bruit(1.08, 0.15).toStringAsFixed(2));
        _ajouterMesure('glucometre', {'glycemie': glyc}, matin, anomalie: glyc >= 1.26);
        _ajouterMesure('oxymetre',
            {'fc': _bruit(70, 6).round(), 'spo2': _bruit(97, 1.2).round()}, matin);
        if (j % 2 == 0) {
          _ajouterMesure('thermometre',
              {'temperature': double.parse(_bruit(36.8, 0.3).toStringAsFixed(1))}, matin);
        }
        if (j % 3 == 0) {
          _ajouterMesure('pese_personne',
              {'poids': double.parse(_bruit(78.5 - (13 - j) * 0.08, 0.3).toStringAsFixed(1))},
              matin);
        }
      }
    }
  }

  static void _genererAlertes() {
    _alertes = [];
    final now = DateTime.now();
    _ajouterAlerte('tensiometre', 'alerte',
        'Tension élevée : 148/93 mmHg', now.subtract(const Duration(days: 5, hours: 3)));
    _ajouterAlerte('glucometre', 'alerte',
        'Glycémie élevée : 1.34 g/L', now.subtract(const Duration(days: 2, hours: 11)));
    _ajouterAlerte('tensiometre', 'critique',
        'Crise hypertensive : 182/112 mmHg', now.subtract(const Duration(hours: 6)));
  }
}
