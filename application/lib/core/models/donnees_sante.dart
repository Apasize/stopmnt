// lib/core/models/donnees_sante.dart
// Mesures de santé unifiées — indépendantes de la source (BLE, Health Connect, simulation).

enum SourceActive { aucune, ble, healthConnect, simulation }

class DonneesSante {
  // ── Vitaux cardio-vasculaires ──────────────────────────
  final double? fc;           // bpm
  final double? fcRepos;      // bpm
  final double? vfc;          // ms (variabilité FC, SDNN)
  final double? spo2;         // %
  final double? systolique;   // mmHg
  final double? diastolique;  // mmHg
  final double? freqResp;     // /min
  final double? temperature;  // °C
  final double? glycemie;     // g/L

  // ── Corps / composition ────────────────────────────────
  final double? poids;        // kg
  final double? taille;       // m
  final double? imc;          // kg/m²
  final double? graisseCorp;  // %
  final double? masseMusc;    // kg (lean body mass)
  final double? eauCorp;      // kg (BODY_WATER_MASS)

  // ── Activité physique ──────────────────────────────────
  final int?    pas;
  final int?    calories;         // kcal totales
  final int?    caloriesActives;  // kcal actives
  final int?    caloriesBasales;  // kcal (BASAL_ENERGY_BURNED)
  final double? distance;         // km
  final int?    etages;
  final double? eau;              // L (apport hydrique journalier)

  // ── Sommeil ────────────────────────────────────────────
  final double? sommeil;          // h total (SLEEP_ASLEEP)
  final double? sommeilProfond;   // h (SLEEP_DEEP)
  final double? sommeilREM;       // h (SLEEP_REM)
  final double? sommeilLeger;     // h (SLEEP_LIGHT)

  // ── Appareil ──────────────────────────────────────────
  final int?    batterie;

  final SourceActive source;

  const DonneesSante({
    this.fc,
    this.fcRepos,
    this.vfc,
    this.spo2,
    this.systolique,
    this.diastolique,
    this.freqResp,
    this.temperature,
    this.glycemie,
    this.poids,
    this.taille,
    this.imc,
    this.graisseCorp,
    this.masseMusc,
    this.eauCorp,
    this.pas,
    this.calories,
    this.caloriesActives,
    this.caloriesBasales,
    this.distance,
    this.etages,
    this.eau,
    this.sommeil,
    this.sommeilProfond,
    this.sommeilREM,
    this.sommeilLeger,
    this.batterie,
    this.source = SourceActive.aucune,
  });

  bool get disponible =>
      fc != null || fcRepos != null || vfc != null ||
      spo2 != null || systolique != null || freqResp != null ||
      temperature != null || glycemie != null ||
      poids != null || imc != null || graisseCorp != null || eauCorp != null ||
      masseMusc != null ||
      pas != null || calories != null || caloriesActives != null ||
      caloriesBasales != null || distance != null || etages != null || eau != null ||
      sommeil != null || sommeilProfond != null || sommeilREM != null ||
      sommeilLeger != null;

  String get labelSource {
    switch (source) {
      case SourceActive.ble          : return 'BLE';
      case SourceActive.healthConnect: return 'Health Connect';
      case SourceActive.simulation   : return 'Simulation';
      case SourceActive.aucune       : return 'Aucune source';
    }
  }
}
