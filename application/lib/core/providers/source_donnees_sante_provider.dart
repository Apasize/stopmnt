// lib/core/providers/source_donnees_sante_provider.dart
// Agrégateur de données de santé — priorité BLE > Health Connect > rien.
// Les écrans UI lisent uniquement ce provider ; ils ignorent d'où viennent les données.

import 'package:flutter/foundation.dart';
import 'ble_provider.dart';
import 'health_connect_provider.dart';
import '../models/donnees_sante.dart';

export '../models/donnees_sante.dart';

class SourceDonneesSanteProvider extends ChangeNotifier {
  final BleProvider           _ble;
  final HealthConnectProvider _hc;

  SourceDonneesSanteProvider(this._ble, this._hc) {
    _ble.addListener(_maj);
    _hc.addListener(_maj);
  }

  @override
  void dispose() {
    _ble.removeListener(_maj);
    _hc.removeListener(_maj);
    super.dispose();
  }

  void _maj() => notifyListeners();

  // ── Source active ───────────────────────────────────────
  SourceActive get sourceActive {
    if (_ble.simulation) return SourceActive.simulation;
    if (_ble.connecte)   return SourceActive.ble;
    if (_hc.autorise) return SourceActive.healthConnect;
    return SourceActive.aucune;
  }

  bool get estActif => sourceActive != SourceActive.aucune;

  // ── Données unifiées ────────────────────────────────────
  DonneesSante get donnees {
    switch (sourceActive) {
      case SourceActive.ble:
      case SourceActive.simulation:
        return DonneesSante(
          fc              : _ble.fc,
          fcRepos         : _ble.fcRepos,
          vfc             : _ble.vfc,
          spo2            : _ble.spo2,
          batterie        : _ble.batterie,
          pas             : _ble.pas,
          caloriesActives : _ble.caloriesActives,
          distance        : _ble.distance,
          systolique      : _ble.systolique,
          diastolique     : _ble.diastolique,
          temperature     : _ble.temperature,
          glycemie        : _ble.glycemie,
          freqResp        : _ble.freqResp,
          source          : sourceActive,
        );
      case SourceActive.healthConnect:
        return DonneesSante(
          fc               : _hc.fc,
          fcRepos          : _hc.fcRepos,
          vfc              : _hc.vfc,
          spo2             : _hc.spo2,
          systolique       : _hc.systolique,
          diastolique      : _hc.diastolique,
          freqResp         : _hc.freqResp,
          temperature      : _hc.temperature,
          glycemie         : _hc.glycemie,
          poids            : _hc.poids,
          taille           : _hc.taille,
          imc              : _hc.imc,
          graisseCorp      : _hc.graisseCorp,
          masseMusc        : _hc.masseMusc,
          eauCorp          : _hc.eauCorp,
          pas              : _hc.pas,
          calories         : _hc.calories,
          caloriesActives  : _hc.caloriesActives,
          caloriesBasales  : _hc.caloriesBasales,
          distance         : _hc.distance,
          etages           : _hc.etages,
          eau              : _hc.eau,
          sommeil          : _hc.sommeil,
          sommeilProfond   : _hc.sommeilProfond,
          sommeilREM       : _hc.sommeilREM,
          sommeilLeger     : _hc.sommeilLeger,
          source           : SourceActive.healthConnect,
        );
      case SourceActive.aucune:
        return const DonneesSante();
    }
  }

  // ── Passthrough BLE pour la gestion de la connexion ────
  // Les écrans qui affichent boutons de scan / connexion
  // lisent directement BleProvider — pas ce provider.
  BleProvider           get ble => _ble;
  HealthConnectProvider get hc  => _hc;
}
