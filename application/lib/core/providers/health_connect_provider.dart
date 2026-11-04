// lib/core/providers/health_connect_provider.dart
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:health/health.dart';
import '../services/api_service.dart';

class HealthConnectProvider extends ChangeNotifier {
  static final _health = Health();

  bool      _disponible    = false;
  bool      _autorise      = false;
  bool      _chargement    = false;
  bool      _hcNonInstalle = false;
  String?   _erreur;
  Timer?    _pollTimer;

  // ── Vitaux cardio-vasculaires ──────────────────────────
  double? _fc;
  double? _fcRepos;
  double? _vfc;
  double? _spo2;
  double? _systolique;
  double? _diastolique;
  double? _freqResp;
  double? _temperature;
  double? _glycemie;

  // ── Corps / composition ────────────────────────────────
  double? _poids;
  double? _taille;
  double? _graisseCorp;
  double? _masseMusc;
  double? _eauCorp;           // kg (BODY_WATER_MASS)

  // ── Activité physique ──────────────────────────────────
  int?    _pas;
  int?    _calories;
  int?    _caloriesActives;
  int?    _caloriesBasales;   // kcal (BASAL_ENERGY_BURNED)
  double? _distance;
  int?    _etages;
  double? _eau;               // L (apport hydrique journalier)

  // ── Sommeil ────────────────────────────────────────────
  double? _sommeil;           // h total
  double? _sommeilProfond;    // h (SLEEP_DEEP)
  double? _sommeilREM;        // h (SLEEP_REM)
  double? _sommeilLeger;      // h (SLEEP_LIGHT)

  DateTime? _derniereMaj;
  Map<String, String> _sourceParMetrique = {};
  int _nbMetriquesEnvoyes = 0;

  // ── Getters ────────────────────────────────────────────
  bool      get disponible     => _disponible;
  bool      get autorise       => _autorise;
  bool      get chargement     => _chargement;
  bool      get hcNonInstalle  => _hcNonInstalle;
  String?   get erreur         => _erreur;
  DateTime? get derniereMaj    => _derniereMaj;
  Map<String, String> get sourceParMetrique => Map.unmodifiable(_sourceParMetrique);

  double?   get fc             => _fc;
  double?   get fcRepos        => _fcRepos;
  double?   get vfc            => _vfc;
  double?   get spo2           => _spo2;
  double?   get systolique     => _systolique;
  double?   get diastolique    => _diastolique;
  double?   get freqResp       => _freqResp;
  double?   get temperature    => _temperature;
  double?   get glycemie       => _glycemie;

  double?   get poids          => _poids;
  double?   get taille         => _taille;
  double?   get graisseCorp    => _graisseCorp;
  double?   get masseMusc      => _masseMusc;
  double?   get eauCorp        => _eauCorp;
  double?   get imc            => (_poids != null && _taille != null && _taille! > 0)
      ? _poids! / (_taille! * _taille!)
      : null;

  int?      get pas            => _pas;
  int?      get calories       => _calories;
  int?      get caloriesActives=> _caloriesActives;
  int?      get caloriesBasales=> _caloriesBasales;
  double?   get distance       => _distance;
  int?      get etages         => _etages;
  double?   get eau            => _eau;

  double?   get sommeil        => _sommeil;
  double?   get sommeilProfond => _sommeilProfond;
  double?   get sommeilREM     => _sommeilREM;
  double?   get sommeilLeger   => _sommeilLeger;

  bool get aDonnees =>
      _fc != null || _fcRepos != null || _vfc != null || _spo2 != null || _systolique != null ||
      _glycemie != null || _freqResp != null || _temperature != null ||
      _poids != null || _graisseCorp != null || _eauCorp != null ||
      _pas != null || _calories != null || _caloriesActives != null ||
      _caloriesBasales != null || _masseMusc != null || _etages != null ||
      _distance != null || _eau != null || _sommeil != null ||
      _sommeilProfond != null || _sommeilREM != null || _sommeilLeger != null;

  int get nbMetriquesEnvoyes => _nbMetriquesEnvoyes;

  int get nbMetriques {
    int n = 0;
    if (_fc != null)             n++;
    if (_fcRepos != null)        n++;
    if (_vfc != null)            n++;
    if (_spo2 != null)           n++;
    if (_systolique != null)     n++;
    if (_diastolique != null)    n++;
    if (_freqResp != null)       n++;
    if (_temperature != null)    n++;
    if (_glycemie != null)       n++;
    if (_poids != null)          n++;
    if (_taille != null)         n++;
    if (_graisseCorp != null)    n++;
    if (_masseMusc != null)      n++;
    if (_eauCorp != null)        n++;
    if (_pas != null)            n++;
    if (_calories != null)       n++;
    if (_caloriesActives != null) n++;
    if (_caloriesBasales != null) n++;
    if (_distance != null)       n++;
    if (_etages != null)         n++;
    if (_eau != null)            n++;
    if (_sommeil != null)        n++;
    if (_sommeilProfond != null) n++;
    if (_sommeilREM != null)     n++;
    if (_sommeilLeger != null)   n++;
    return n;
  }

  // ── Types vitaux (fenêtre 24h) ─────────────────────────
  static const _typesVitaux = [
    HealthDataType.HEART_RATE,
    HealthDataType.RESTING_HEART_RATE,
    HealthDataType.HEART_RATE_VARIABILITY_RMSSD,   // RMSSD = VFC sur Android HC
    HealthDataType.BLOOD_OXYGEN,
    HealthDataType.BLOOD_PRESSURE_SYSTOLIC,
    HealthDataType.BLOOD_PRESSURE_DIASTOLIC,
    HealthDataType.RESPIRATORY_RATE,
    HealthDataType.BODY_TEMPERATURE,
    HealthDataType.BLOOD_GLUCOSE,
  ];

  // ── Types corps (fenêtre 30 jours) ─────────────────────
  static const _typesCorps = [
    HealthDataType.WEIGHT,
    HealthDataType.HEIGHT,
    HealthDataType.BODY_FAT_PERCENTAGE,
    HealthDataType.LEAN_BODY_MASS,
    HealthDataType.BODY_WATER_MASS,
  ];

  // ── Types activité journalière (depuis minuit) ─────────
  static const _typesActivite = [
    HealthDataType.STEPS,
    HealthDataType.TOTAL_CALORIES_BURNED,
    HealthDataType.ACTIVE_ENERGY_BURNED,
    HealthDataType.BASAL_ENERGY_BURNED,
    HealthDataType.DISTANCE_DELTA,
    HealthDataType.FLIGHTS_CLIMBED,
    HealthDataType.WATER,
  ];

  // ── Types sommeil (dernières 24h) ──────────────────────
  static const _typesSommeil = [
    HealthDataType.SLEEP_ASLEEP,
    HealthDataType.SLEEP_DEEP,
    HealthDataType.SLEEP_REM,
    HealthDataType.SLEEP_LIGHT,
  ];

  // Tous les types pour la demande de permission (non-const car spread de const lists)
  static List<HealthDataType> get _tousTypes => [
    ..._typesVitaux,
    ..._typesCorps,
    ..._typesActivite,
    ..._typesSommeil,
  ];

  HealthConnectProvider() {
    _verifierDisponibilite();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // Sur Android Health Connect, hasPermissions() pour les permissions READ
  // retourne systématiquement null/false (limitation de l'API Android —
  // un app ne peut pas interroger l'état de ses propres droits de lecture).
  // La seule vérification fiable : tenter un vrai accès et voir si ça passe.
  Future<bool> _autorisationEffective() async {
    try {
      final now = DateTime.now();
      await _health.getHealthDataFromTypes(
        startTime : now.subtract(const Duration(hours: 24)),
        endTime   : now,
        types     : [HealthDataType.STEPS],
      );
      debugPrint('[HC] _autorisationEffective → accordée');
      return true; // liste vide ou non = permission OK
    } catch (e) {
      debugPrint('[HC] _autorisationEffective → refusée: $e');
      return false;
    }
  }

  Future<void> _verifierDisponibilite() async {
    try {
      final status = await _health.getHealthConnectSdkStatus();
      debugPrint('[HC] SDK status: $status');
      if (status != HealthConnectSdkStatus.sdkAvailable) {
        _disponible    = false;
        _hcNonInstalle = true;
        debugPrint('[HC] SDK non disponible → hcNonInstalle=true');
        notifyListeners();
        return;
      }
      await _health.configure();
      _disponible = true;
      // Toujours demander les permissions pour capter les nouvelles entrées du manifest.
      // requestAuthorization ne montre le dialogue que pour les permissions manquantes.
      final types       = _tousTypes;
      final permissions = types.map((_) => HealthDataAccess.READ).toList();
      try {
        await _health.requestAuthorization(types, permissions: permissions);
      } catch (_) {}
      final deja = await _autorisationEffective();
      debugPrint('[HC] Autorisation effective au démarrage: $deja');
      if (deja) {
        _autorise = true;
        await charger();
        _demarrerPoll();
      }
    } catch (e) {
      debugPrint('[HC] _verifierDisponibilite error: $e');
      _disponible = false;
    }
    notifyListeners();
  }

  Future<bool> demanderPermissions() async {
    debugPrint('[HC] demanderPermissions() → disponible=$_disponible');
    if (!_disponible) return false;
    try {
      await _health.configure();
      final types       = _tousTypes;
      final permissions = types.map((_) => HealthDataAccess.READ).toList();
      debugPrint('[HC] requestAuthorization ${types.length} types');
      try {
        await _health.requestAuthorization(types, permissions: permissions);
      } catch (e) {
        // HC peut jeter si les permissions sont déjà accordées — on ignore
        debugPrint('[HC] requestAuthorization exception (ignorée): $e');
      }
      // Le return value de requestAuthorization est peu fiable sur HC :
      // on vérifie en tentant une vraie lecture.
      final ok = await _autorisationEffective();
      debugPrint('[HC] Autorisation après demande: $ok');
      _autorise = ok;
      _erreur   = ok ? null
          : 'Permissions refusées. Ouvrez Health Connect > Autorisations.';
      notifyListeners();
      if (ok) {
        await charger();
        _demarrerPoll();
      }
      return ok;
    } catch (e) {
      debugPrint('[HC] demanderPermissions error: $e');
      _erreur = 'Erreur lors de la demande de permissions';
      notifyListeners();
      return false;
    }
  }

  void _demarrerPoll() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(minutes: 5), (_) => charger());
  }

  void arreterPoll() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  /// Relance la lecture périodique après un logout → login (arreterPoll).
  void reprendrePoll() {
    if (!_autorise || _pollTimer != null) return;
    _demarrerPoll();
    charger();
  }

  // L'ordre renvoyé par Health Connect n'est pas garanti chronologique.
  static HealthDataPoint? _plusRecent(List<HealthDataPoint> data) {
    HealthDataPoint? res;
    for (final d in data) {
      if (res == null || d.dateTo.isAfter(res.dateTo)) res = d;
    }
    return res;
  }

  Future<void> charger() async {
    if (!_disponible || !_autorise || _chargement) return;
    _chargement = true;
    notifyListeners();

    try {
      final now      = DateTime.now();
      final debut24h = now.subtract(const Duration(hours: 24));
      final debut30j = now.subtract(const Duration(days: 30));
      final debutJour = DateTime(now.year, now.month, now.day);

      // ── Vitaux (24h) ─────────────────────────────────
      double? fc, fcRepos, vfc, spo2, sys, dias, freqResp, temp, glyc;
      DateTime? dateMaj;
      final sources = <String, String>{};

      for (final type in _typesVitaux) {
        try {
          final raw  = await _health.getHealthDataFromTypes(
            startTime: debut24h, endTime: now, types: [type],
          );
          final d = _plusRecent(_health.removeDuplicates(raw));
          if (d != null) {
            final val = (d.value as NumericHealthValue).numericValue.toDouble();
            debugPrint('[HC]   ${d.type.name}: $val (${d.sourceName})');
            switch (d.type) {
              case HealthDataType.HEART_RATE:                    fc      = val;
              case HealthDataType.RESTING_HEART_RATE:            fcRepos = val;
              case HealthDataType.HEART_RATE_VARIABILITY_RMSSD:  vfc     = val;
              case HealthDataType.BLOOD_OXYGEN:                  spo2    = val;
              case HealthDataType.BLOOD_PRESSURE_SYSTOLIC:       sys     = val;
              case HealthDataType.BLOOD_PRESSURE_DIASTOLIC:      dias    = val;
              case HealthDataType.RESPIRATORY_RATE:              freqResp= val;
              case HealthDataType.BODY_TEMPERATURE:              temp    = val;
              case HealthDataType.BLOOD_GLUCOSE:                 glyc    = val * 0.180;
              default: break;
            }
            final key = _typeKey(d.type);
            if (key != null && d.sourceName.isNotEmpty) sources[key] = d.sourceName;
            if (dateMaj == null || d.dateTo.isAfter(dateMaj)) dateMaj = d.dateTo;
          }
        } catch (e) {
          debugPrint('[HC]   ${type.name} ignoré: $e');
        }
      }

      // ── Corps (30 jours) ─────────────────────────────
      double? poids, taille, graisseCorp, masseMusc, eauCorp;

      for (final type in _typesCorps) {
        try {
          final raw  = await _health.getHealthDataFromTypes(
            startTime: debut30j, endTime: now, types: [type],
          );
          final d = _plusRecent(_health.removeDuplicates(raw));
          if (d != null) {
            final val = (d.value as NumericHealthValue).numericValue.toDouble();
            debugPrint('[HC]   ${d.type.name}: $val (${d.sourceName})');
            switch (d.type) {
              case HealthDataType.WEIGHT:              poids      = val;
              case HealthDataType.HEIGHT:              taille     = val;
              case HealthDataType.BODY_FAT_PERCENTAGE: graisseCorp= val;
              case HealthDataType.LEAN_BODY_MASS:      masseMusc  = val;
              case HealthDataType.BODY_WATER_MASS:     eauCorp    = val;
              default: break;
            }
            final key = _typeKey(d.type);
            if (key != null && d.sourceName.isNotEmpty) sources[key] = d.sourceName;
          }
        } catch (e) {
          debugPrint('[HC]   ${type.name} ignoré: $e');
        }
      }

      // ── Activité journalière (agrégation HC native) ──────
      // getHealthIntervalDataFromTypes → getIntervalData Android → AggregateGroupByDuration
      // Donne les mêmes totaux que l'UI Health Connect (agrège tous les contributeurs).
      // Un seul bucket = toute la journée → une seule valeur par type.
      int?    actPas, actCal, actCalAct, actCalBase, actEtages;
      double? actDist, actEau;
      final intervalJour = now.difference(debutJour).inSeconds.clamp(60, 86400);

      // Types supportés par l'agrégation HC native
      for (final type in const [
        HealthDataType.STEPS,
        HealthDataType.TOTAL_CALORIES_BURNED,
        HealthDataType.ACTIVE_ENERGY_BURNED,
        HealthDataType.DISTANCE_DELTA,
        HealthDataType.WATER,
      ]) {
        try {
          final data = await _health.getHealthIntervalDataFromTypes(
            types    : [type],
            startDate: debutJour,
            endDate  : now,
            interval : intervalJour,
          );
          if (data.isNotEmpty) {
            final d   = data.first; // Un seul bucket journalier
            final val = (d.value as NumericHealthValue).numericValue;
            debugPrint('[HC] AGG ${d.type.name}: $val (${d.sourceName})');
            switch (type) {
              case HealthDataType.STEPS:                 actPas    = val.toInt();
              case HealthDataType.TOTAL_CALORIES_BURNED: actCal    = val.toInt();
              case HealthDataType.ACTIVE_ENERGY_BURNED:  actCalAct = val.toInt();
              case HealthDataType.DISTANCE_DELTA:        actDist   = val.toDouble();
              case HealthDataType.WATER:                 actEau    = val.toDouble();
              default: break;
            }
            final key = _typeKey(type);
            if (key != null && d.sourceName.isNotEmpty) sources[key] = d.sourceName;
          }
        } catch (e) {
          debugPrint('[HC]   ${type.name} agrégation ignorée: $e');
        }
      }

      // Types NON supportés par l'agrégation — raw last entry
      for (final type in const [
        HealthDataType.BASAL_ENERGY_BURNED,
        HealthDataType.FLIGHTS_CLIMBED,
      ]) {
        try {
          final raw  = await _health.getHealthDataFromTypes(
            startTime: debutJour, endTime: now, types: [type],
          );
          final d = _plusRecent(_health.removeDuplicates(raw));
          if (d != null) {
            final val = (d.value as NumericHealthValue).numericValue;
            debugPrint('[HC]   ${d.type.name}: $val (${d.sourceName})');
            switch (type) {
              case HealthDataType.BASAL_ENERGY_BURNED: actCalBase = val.toInt();
              case HealthDataType.FLIGHTS_CLIMBED:     actEtages  = val.toInt();
              default: break;
            }
            final key = _typeKey(type);
            if (key != null && d.sourceName.isNotEmpty) sources[key] = d.sourceName;
          }
        } catch (e) {
          debugPrint('[HC]   ${type.name} ignoré: $e');
        }
      }

      // ── Sommeil (24h) — total + stades ───────────────
      double totalSommeilMin = 0, totalProfondMin = 0, totalREMMin = 0, totalLegerMin = 0;

      for (final type in _typesSommeil) {
        try {
          final raw  = await _health.getHealthDataFromTypes(
            startTime: debut24h, endTime: now, types: [type],
          );
          final data = _health.removeDuplicates(raw);
          for (final d in data) {
            final duree = d.dateTo.difference(d.dateFrom).inMinutes.toDouble();
            debugPrint('[HC]   ${d.type.name}: ${duree}min (${d.sourceName})');
            switch (d.type) {
              case HealthDataType.SLEEP_ASLEEP: totalSommeilMin += duree;
              case HealthDataType.SLEEP_DEEP:   totalProfondMin += duree;
              case HealthDataType.SLEEP_REM:    totalREMMin     += duree;
              case HealthDataType.SLEEP_LIGHT:  totalLegerMin   += duree;
              default: break;
            }
            if (d.sourceName.isNotEmpty) sources['sommeil'] = d.sourceName;
          }
        } catch (e) {
          debugPrint('[HC]   ${type.name} ignoré: $e');
        }
      }

      _fc              = fc;
      _fcRepos         = fcRepos;
      _vfc             = vfc;
      _spo2            = spo2;
      _systolique      = sys;
      _diastolique     = dias;
      _freqResp        = freqResp;
      _temperature     = temp;
      _glycemie        = glyc;
      _poids           = poids;
      _taille          = taille;
      _graisseCorp     = graisseCorp;
      _masseMusc       = masseMusc;
      _eauCorp         = eauCorp;
      _pas             = actPas;
      _calories        = actCal;
      _caloriesActives = actCalAct;
      _caloriesBasales = actCalBase;
      _distance        = actDist != null ? actDist / 1000 : null; // m → km
      _etages          = actEtages;
      _eau             = actEau;
      _sommeil         = totalSommeilMin > 0 ? totalSommeilMin / 60 : null;
      _sommeilProfond  = totalProfondMin > 0 ? totalProfondMin / 60 : null;
      _sommeilREM      = totalREMMin    > 0 ? totalREMMin    / 60 : null;
      _sommeilLeger    = totalLegerMin  > 0 ? totalLegerMin  / 60 : null;
      _derniereMaj        = dateMaj;
      _sourceParMetrique  = sources;
      _erreur             = null;

      debugPrint('[HC] résultat → fc=$_fc fcRepos=$_fcRepos vfc=$_vfc spo2=$_spo2 '
          'sys=$_systolique dias=$_diastolique resp=$_freqResp '
          'temp=$_temperature glyc=$_glycemie '
          'poids=$_poids taille=$_taille imc=${imc?.toStringAsFixed(2)} '
          'graisse=$_graisseCorp masseMusc=$_masseMusc eauCorp=$_eauCorp '
          'pas=$_pas cal=$_calories calAct=$_caloriesActives calBase=$_caloriesBasales '
          'dist=${_distance?.toStringAsFixed(2)}km etages=$_etages eau=${_eau?.toStringAsFixed(2)}L '
          'sommeil=$_sommeil h (profond=$_sommeilProfond REM=$_sommeilREM léger=$_sommeilLeger)');

      await _envoyerAuServeur();
    } catch (e) {
      _erreur = 'Impossible de lire Health Connect';
      debugPrint('[HC] charger() error: $e');
    }

    _chargement = false;
    notifyListeners();
  }

  // ── Déduplication des envois ─────────────────────────────
  // charger() tourne toutes les 5 min : sans filtre, les mêmes valeurs
  // (dernier poids, cumul de pas du jour…) seraient renvoyées à chaque fois
  // comme de nouvelles mesures. On n'envoie qu'une valeur qui a changé, et
  // les cumuls journaliers au plus une fois par heure.
  static const _cumulsJournaliers = {
    'pas', 'calories', 'calories_actives', 'calories_basales',
    'distance', 'etages', 'eau',
  };
  static const _intervalleCumuls = Duration(hours: 1);
  final Map<String, Object?>  _derniereValeur = {};
  final Map<String, DateTime> _dernierEnvoi   = {};

  Map<String, dynamic> _nouveautes(String capteur, Map<String, dynamic> toutes) {
    final now = DateTime.now();
    final res = <String, dynamic>{};
    toutes.forEach((k, v) {
      final cle = '$capteur.$k';
      if (_derniereValeur[cle] == v) return;
      final dernier = _dernierEnvoi[cle];
      if (_cumulsJournaliers.contains(k) && dernier != null &&
          now.difference(dernier) < _intervalleCumuls &&
          now.day == dernier.day) {
        return;
      }
      res[k] = v;
    });
    // Une tension s'envoie toujours par paire systolique/diastolique
    if (res.containsKey('systolique') || res.containsKey('diastolique')) {
      for (final k in const ['systolique', 'diastolique']) {
        if (toutes.containsKey(k)) res[k] = toutes[k];
      }
    }
    return res;
  }

  void _memoriserEnvoi(String capteur, Map<String, dynamic> mesures) {
    final now = DateTime.now();
    mesures.forEach((k, v) {
      _derniereValeur['$capteur.$k'] = v;
      _dernierEnvoi['$capteur.$k']   = now;
    });
  }

  /// À appeler au changement de compte : le nouveau patient doit recevoir
  /// les valeurs courantes même si elles ont déjà été envoyées pour l'ancien.
  void oublierEnvois() {
    _derniereValeur.clear();
    _dernierEnvoi.clear();
    _nbMetriquesEnvoyes = 0;
  }

  // Le serveur n'accepte que ['tensiometre', 'glucometre', 'balance'].
  // On répartit les données HC sur ces trois capteurs valides.
  Future<void> _envoyerAuServeur() async {
    if (!ApiService.sessionActive) return;
    // ── tensiometre : vitaux cardio-vasculaires ─────────────
    final mTensio = <String, dynamic>{};
    if (_fc != null)          mTensio['fc']          = _fc;
    if (_fcRepos != null)     mTensio['fc_repos']    = _fcRepos;
    if (_vfc != null)         mTensio['vfc']         = _vfc;
    if (_spo2 != null)        mTensio['spo2']        = _spo2;
    if (_systolique != null)  mTensio['systolique']  = _systolique;
    if (_diastolique != null) mTensio['diastolique'] = _diastolique;
    if (_freqResp != null)    mTensio['freq_resp']   = _freqResp;
    if (_temperature != null) mTensio['temperature'] = _temperature;

    // ── glucometre : glycémie ────────────────────────────────
    final mGlyco = <String, dynamic>{};
    if (_glycemie != null)    mGlyco['glycemie']     = _glycemie;

    // ── balance : composition corporelle + activité + sommeil
    final mBalance = <String, dynamic>{};
    if (_poids != null)           mBalance['poids']            = _poids;
    if (_taille != null)          mBalance['taille']           = _taille;
    if (imc != null)              mBalance['imc']              = imc;
    if (_graisseCorp != null)     mBalance['graisse_corp']     = _graisseCorp;
    if (_masseMusc != null)       mBalance['masse_musc']       = _masseMusc;
    if (_eauCorp != null)         mBalance['eau_corp']         = _eauCorp;
    if (_pas != null)             mBalance['pas']              = _pas;
    if (_calories != null)        mBalance['calories']         = _calories;
    if (_caloriesActives != null) mBalance['calories_actives'] = _caloriesActives;
    if (_caloriesBasales != null) mBalance['calories_basales'] = _caloriesBasales;
    if (_distance != null)        mBalance['distance']         = _distance;
    if (_etages != null)          mBalance['etages']           = _etages;
    if (_eau != null)             mBalance['eau']              = _eau;
    if (_sommeil != null)         mBalance['sommeil']          = _sommeil;
    if (_sommeilProfond != null)  mBalance['sommeil_profond']  = _sommeilProfond;
    if (_sommeilREM != null)      mBalance['sommeil_rem']      = _sommeilREM;
    if (_sommeilLeger != null)    mBalance['sommeil_leger']    = _sommeilLeger;

    int envoyes = 0;

    Future<void> envoyer(String capteur, Map<String, dynamic> toutes) async {
      final mesures = _nouveautes(capteur, toutes);
      if (mesures.isEmpty) return;
      try {
        final r = await ApiService.envoyerMesure(capteur: capteur, mesures: mesures);
        _memoriserEnvoi(capteur, mesures);
        if (r['differe'] != true) {
          envoyes += mesures.length;
          debugPrint('[HC] Envoi $capteur OK: ${mesures.keys.join(', ')}');
        } else {
          debugPrint('[HC] Envoi $capteur différé (hors-ligne)');
        }
      } catch (e) {
        debugPrint('[HC] Erreur envoi $capteur: $e');
      }
    }

    await envoyer('tensiometre', mTensio);
    await envoyer('glucometre',  mGlyco);
    await envoyer('balance',     mBalance);

    if (envoyes > 0) _nbMetriquesEnvoyes += envoyes;
  }

  Future<void> ouvrirHealthConnect() async {
    try { await _health.installHealthConnect(); } catch (_) {}
  }

  static String? _typeKey(HealthDataType type) => switch (type) {
    HealthDataType.HEART_RATE                   => 'fc',
    HealthDataType.RESTING_HEART_RATE           => 'fcRepos',
    HealthDataType.HEART_RATE_VARIABILITY_RMSSD => 'vfc',
    HealthDataType.BLOOD_OXYGEN                 => 'spo2',
    HealthDataType.BLOOD_PRESSURE_SYSTOLIC      => 'sys',
    HealthDataType.BLOOD_PRESSURE_DIASTOLIC     => 'dias',
    HealthDataType.RESPIRATORY_RATE             => 'freqResp',
    HealthDataType.BODY_TEMPERATURE             => 'temp',
    HealthDataType.BLOOD_GLUCOSE                => 'glyc',
    HealthDataType.WEIGHT                       => 'poids',
    HealthDataType.BODY_FAT_PERCENTAGE          => 'graisseCorp',
    HealthDataType.LEAN_BODY_MASS               => 'masseMusc',
    HealthDataType.BODY_WATER_MASS              => 'eauCorp',
    HealthDataType.STEPS                        => 'pas',
    HealthDataType.TOTAL_CALORIES_BURNED        => 'calories',
    HealthDataType.ACTIVE_ENERGY_BURNED         => 'calAct',
    HealthDataType.BASAL_ENERGY_BURNED          => 'calBase',
    HealthDataType.DISTANCE_DELTA               => 'distance',
    HealthDataType.FLIGHTS_CLIMBED              => 'etages',
    HealthDataType.WATER                        => 'eau',
    HealthDataType.SLEEP_ASLEEP                 => 'sommeil',
    HealthDataType.SLEEP_DEEP                   => 'sommeil',
    HealthDataType.SLEEP_REM                    => 'sommeil',
    HealthDataType.SLEEP_LIGHT                  => 'sommeil',
    _ => null,
  };

  void reinitialiser() {
    _fc = _fcRepos = _vfc = _spo2 = _systolique = _diastolique = null;
    _freqResp = _temperature = _glycemie = null;
    _poids = _taille = _graisseCorp = _masseMusc = _eauCorp = null;
    _pas = _calories = _caloriesActives = _caloriesBasales = _etages = null;
    _distance = _eau = _sommeil = _sommeilProfond = _sommeilREM = _sommeilLeger = null;
    _derniereMaj       = null;
    _sourceParMetrique = {};
    oublierEnvois();
    _autorise           = false;
    _pollTimer?.cancel();
    notifyListeners();
  }
}
