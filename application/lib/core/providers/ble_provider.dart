// lib/core/providers/ble_provider.dart
// Gestion BLE persistante — survit aux changements d'onglets
// Scan automatique, mémoire capteurs, gestion Bluetooth on/off, cycle de vie

import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:permission_handler/permission_handler.dart';
import '../services/api_service.dart';

enum ModeBle { reel, simulation }

enum ProtocoleDetecte { aucun, gattStandard, daFit, hiLink, inconnu }
enum NiveauSignal { excellent, bon, faible, tresFaible }

class CapteurDetecte {
  final BluetoothDevice device;
  int                   rssi;
  DateTime              dernierVu;
  bool                  connecte;

  CapteurDetecte({
    required this.device,
    required this.rssi,
    required this.dernierVu,
    this.connecte = false,
  });

  String get nom => device.platformName.isNotEmpty
      ? device.platformName
      : 'Inconnu (${device.remoteId.toString().substring(0, 8)})';

  NiveauSignal get niveauSignal {
    if (rssi >= -60) return NiveauSignal.excellent;
    if (rssi >= -75) return NiveauSignal.bon;
    if (rssi >= -90) return NiveauSignal.faible;
    return NiveauSignal.tresFaible;
  }

  String get labelSignal {
    switch (niveauSignal) {
      case NiveauSignal.excellent  : return 'Excellent';
      case NiveauSignal.bon        : return 'Bon';
      case NiveauSignal.faible     : return 'Faible';
      case NiveauSignal.tresFaible : return 'Très faible';
    }
  }

  int get barresSignal {
    switch (niveauSignal) {
      case NiveauSignal.excellent  : return 4;
      case NiveauSignal.bon        : return 3;
      case NiveauSignal.faible     : return 2;
      case NiveauSignal.tresFaible : return 1;
    }
  }
}

class BleProvider extends ChangeNotifier with WidgetsBindingObserver {
  ModeBle _mode = ModeBle.reel;

  final Map<String, CapteurDetecte> _capteursVus = {};

  bool             _scanning    = false;
  bool             _connecte    = false;
  bool             _simulation  = false;
  bool             _btActif     = true;
  BluetoothDevice? _dispositif;
  String?          _erreur;

  double?       _fc;
  double?       _fcRepos;
  double?       _vfc;
  double?       _spo2;
  int?          _batterie;
  int?          _pas;
  double?       _systolique;
  double?       _diastolique;
  double?       _temperature;
  double?       _glycemie;
  double?       _freqResp;
  double?       _distance;       // km, grandit avec les pas
  int?          _caloriesActives; // kcal actives
  bool               _donneesCachees  = false;
  int                _nbEnvoyes       = 0;
  ProtocoleDetecte   _protocole       = ProtocoleDetecte.aucun;
  List<String>       _servicesDetectes = [];
  final List<PaquetBrutBle> _paquetsBruts = [];

  // Caractéristique d'écriture Da Fit (33F1) — envoi de commandes
  BluetoothCharacteristic? _daFitEcriture;

  // HiLink LPv2 (Huawei) — FE01 écriture, FE02 notify
  BluetoothCharacteristic? _hiLinkEcriture;

  // Token d'appairage (depuis QR code de la montre)
  String? _tokenAppairage;

  int     _cyclesScan = 0;
  static const int      _cyclesRapides  = 3;
  static const Duration _pauseRapide    = Duration(seconds: 2);
  static const Duration _pauseReconnect = Duration(seconds: 10);
  static const Duration _pauseLente     = Duration(seconds: 30);
  Timer?  _scanTimer;

  String? _dernierCapteurId;
  bool    _autoReconnectPending = false;
  static const _storage = FlutterSecureStorage();

  Timer?  _simTimer;
  Timer?  _envoyerTimer;     // envoi simulation
  Timer?  _envoyerTimerBle;  // envoi BLE réel
  int     _nbEnvoyesBle = 0;
  final   _rand = Random();

  StreamSubscription?       _scanSub;
  StreamSubscription?       _connexionSub;
  StreamSubscription?       _btStateSub;
  final List<StreamSubscription> _notifySubs = [];

  ModeBle                   get mode                  => _mode;
  bool                      get scanning              => _scanning;
  bool                      get connecte              => _connecte;
  bool                      get simulation            => _simulation;
  bool                      get btActif               => _btActif;
  BluetoothDevice?          get dispositif            => _dispositif;
  String?                   get erreur                => _erreur;
  double?                   get fc                    => _fc;
  double?                   get fcRepos               => _fcRepos;
  double?                   get vfc                   => _vfc;
  double?                   get spo2                  => _spo2;
  double?                   get distance              => _distance;
  int?                      get caloriesActives       => _caloriesActives;
  int                       get nbEnvoyes             => _simulation ? _nbEnvoyes : _nbEnvoyesBle;
  bool                      get estActif              => _connecte || _simulation;

  // Protocole détecté après connexion
  ProtocoleDetecte          get protocole             => _protocole;
  // On maîtrise uniquement les profils SIG standard
  bool                      get maitrise              => _protocole == ProtocoleDetecte.gattStandard;
  // Connecté mais protocole hors contrôle natif
  bool                      get nonMaitrise           => _connecte &&
                                                         _protocole != ProtocoleDetecte.aucun &&
                                                         _protocole != ProtocoleDetecte.gattStandard;
  // Données santé disponibles (standard ou DaFit décodé)
  bool                      get donneesDisponibles    => _protocole == ProtocoleDetecte.gattStandard ||
                                                         _protocole == ProtocoleDetecte.daFit;
  // DaFit identifié mais token absent
  bool                      get necessiteConfiguration => _protocole == ProtocoleDetecte.daFit &&
                                                          _tokenAppairage == null;

  List<String>              get servicesDetectes      => _servicesDetectes;
  int?                      get batterie              => _batterie;
  int?                      get pas                   => _pas;
  double?                   get systolique            => _systolique;
  double?                   get diastolique           => _diastolique;
  double?                   get temperature           => _temperature;
  double?                   get glycemie              => _glycemie;
  double?                   get freqResp              => _freqResp;
  bool                      get donneesCachees        => _donneesCachees;
  String?                   get dernierCapteurId      => _dernierCapteurId;
  List<PaquetBrutBle>       get paquetsBruts          => List.unmodifiable(_paquetsBruts);
  String?                   get tokenAppairage        => _tokenAppairage;
  List<CapteurDetecte>      get capteurs              =>
      _capteursVus.values.toList()
        ..sort((a, b) => b.rssi.compareTo(a.rssi));

  BleProvider() {
    WidgetsBinding.instance.addObserver(this);
    _ecouterEtatBluetooth();
    _chargerDernierCapteur();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _scanSub?.cancel();
    _connexionSub?.cancel();
    _btStateSub?.cancel();
    _scanTimer?.cancel();
    _simTimer?.cancel();
    _envoyerTimer?.cancel();
    _envoyerTimerBle?.cancel();
    FlutterBluePlus.stopScan();
    super.dispose();
  }

  // ── Cycle de vie app — pause scan en arrière-plan ────────
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      // Arrêter le scan pour économiser la batterie
      if (_scanning) {
        _scanTimer?.cancel();
        FlutterBluePlus.stopScan();
        _scanning = false;
        notifyListeners();
      }
    } else if (state == AppLifecycleState.resumed) {
      // Relancer le scan au retour au premier plan si pas connecté
      if (!estActif && _btActif) {
        Future.delayed(const Duration(seconds: 1), demarrerScanAuto);
      }
    }
  }

  void _ecouterEtatBluetooth() {
    _btStateSub = FlutterBluePlus.adapterState.listen((state) {
      _btActif = state == BluetoothAdapterState.on;

      if (_btActif) {
        _erreur = null;
        if (!estActif) {
          Future.delayed(const Duration(seconds: 1), demarrerScanAuto);
        }
      } else {
        // BT désactivé — déconnecter le capteur physique si nécessaire
        if (_connecte) {
          // Marquer l'erreur pour que DashboardScreen affiche le dialogue
          _erreur     = 'bluetooth_desactive_pendant_session';
          _dispositif = null;
          _connecte   = false;
          _fc = _spo2 = null;
        }
      }

      notifyListeners();
    });
  }

  Future<bool> _demanderPermissions() async {
    final statuts = await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
    ].request();
    return statuts.values.every((s) => s.isGranted);
  }

  // ── Activer le Bluetooth ──────────────────────────────────
  // Sur Android 12+, FlutterBluePlus.turnOn() est bloqué par le système.
  // On redirige vers les paramètres Bluetooth.
  Future<bool> demanderActivationBluetooth() async {
    try {
      await FlutterBluePlus.turnOn();
      await Future.delayed(const Duration(seconds: 2));
      final state = await FlutterBluePlus.adapterState.first;
      return state == BluetoothAdapterState.on;
    } catch (_) {
      // Sur Android 12+, ouvrir les paramètres système à la place
      await openAppSettings();
      return false;
    }
  }

  Future<void> demarrerScanAuto() async {
    if (_scanning || estActif) return;

    final ok = await _demanderPermissions();
    if (!ok) {
      _erreur = 'permissions_refusees';
      notifyListeners();
      return;
    }

    if (!_btActif) return;

    _cyclesScan = 0;
    await _lancerUnScan();
  }

  Future<void> _lancerUnScan() async {
    if (_scanning || estActif) return;

    _scanning = true;
    _erreur   = null;
    notifyListeners();

    _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        if (r.device.platformName.isEmpty) continue;
        final id = r.device.remoteId.toString();

        if (_dernierCapteurId != null &&
            id == _dernierCapteurId &&
            !_connecte && !_simulation && !_autoReconnectPending) {
          _autoReconnectPending = true;
          Future.microtask(() async {
            if (!_connecte && !_simulation) await connecter(r.device);
            _autoReconnectPending = false;
            // Si la connexion a échoué, relancer le scan — sans ce rappel
            // la boucle s'arrête car le planificateur vérifie _autoReconnectPending
            // au moment où le scan se termine (avant que connecter() ait fini).
            if (!estActif && _btActif) {
              _scanTimer?.cancel();
              _scanTimer = Timer(_pauseRapide, () {
                if (!estActif && _btActif) _lancerUnScan();
              });
            }
          });
        }

        if (_capteursVus.containsKey(id)) {
          _capteursVus[id]!.rssi      = r.rssi;
          _capteursVus[id]!.dernierVu = DateTime.now();
        } else {
          _capteursVus[id] = CapteurDetecte(
            device    : r.device,
            rssi      : r.rssi,
            dernierVu : DateTime.now(),
          );
        }
        notifyListeners();
      }
    });

    await FlutterBluePlus.startScan(timeout: const Duration(seconds: 10));

    _scanning = false;
    _cyclesScan++;
    notifyListeners();

    if (!estActif && !_autoReconnectPending) {
      // Rapide si cycles initiaux, reconnexion active si capteur connu, lent sinon
      final pause = _cyclesScan <= _cyclesRapides
          ? _pauseRapide
          : (_dernierCapteurId != null ? _pauseReconnect : _pauseLente);
      _scanTimer?.cancel();
      _scanTimer = Timer(pause, () {
        if (!estActif && _btActif) _lancerUnScan();
      });
    }
  }

  Future<void> scanner() async {
    if (!_btActif) return;
    _cyclesScan = 0;
    await _lancerUnScan();
  }

  void arreterScan() {
    FlutterBluePlus.stopScan();
    _scanTimer?.cancel();
    _scanning = false;
    notifyListeners();
  }

  Future<void> _chargerDernierCapteur() async {
    final id = await _storage.read(key: 'ble_dernier_capteur');
    if (id != null) _dernierCapteurId = id;
  }

  Future<void> _sauvegarderCapteur(String id) async {
    _dernierCapteurId = id;
    await _storage.write(key: 'ble_dernier_capteur', value: id);
  }

  // Charge le token propre à cet appareil (clé = mac address).
  // Appelé juste après la connexion physique, avant _lireServices.
  Future<void> _chargerTokenPourDevice(String deviceId) async {
    _tokenAppairage = await _storage.read(key: 'ble_token_$deviceId');
  }

  Future<void> sauvegarderToken(String token) async {
    if (_dispositif == null) return;
    final deviceId = _dispositif!.remoteId.toString();
    final t = token.trim();
    _tokenAppairage = t.isEmpty ? null : t;
    if (_tokenAppairage != null) {
      await _storage.write(key: 'ble_token_$deviceId', value: _tokenAppairage!);
    } else {
      await _storage.delete(key: 'ble_token_$deviceId');
    }
    // Reconnexion automatique pour appliquer le token immédiatement
    if (_connecte && _tokenAppairage != null) {
      await reconnecter();
    } else {
      notifyListeners();
    }
  }

  Future<void> reconnecter() async {
    final device = _dispositif;
    if (device == null) return;
    await _deconnecterPhysique(oublierCapteur: false);
    notifyListeners();
    await Future.delayed(const Duration(milliseconds: 800));
    await connecter(device);
  }

  void effacerCapteurs() {
    _capteursVus.clear();
    _dernierCapteurId = null;
    _storage.delete(key: 'ble_dernier_capteur');
    notifyListeners();
  }

  Future<void> connecter(BluetoothDevice device) async {
    // Déjà connecté à ce même dispositif — rien à faire
    if (_connecte && _dispositif?.remoteId == device.remoteId) return;

    // Connecté à un autre dispositif — déconnecter d'abord
    if (_connecte && _dispositif != null) {
      await _deconnecterPhysique(oublierCapteur: false);
    }

    arreterScan();
    _erreur = null;
    _scanning = true;
    notifyListeners();

    try {
      await device.connect(
        timeout    : const Duration(seconds: 15),
        autoConnect: false,
      );

      _dispositif = device;
      _connecte   = true;
      _scanning   = false;

      final id = device.remoteId.toString();
      if (_capteursVus.containsKey(id)) {
        _capteursVus[id]!.connecte = true;
      }
      await _sauvegarderCapteur(id);
      // Charger le token propre à cet appareil avant l'init Da Fit
      await _chargerTokenPourDevice(id);

      notifyListeners();
      _ecouterDeconnexion(device);

      if (_mode == ModeBle.reel) {
        await _lireServices(device);
      }

    } catch (e) {
      _scanning = false;
      _erreur   = _traduireErreur(e.toString());
      notifyListeners();
    }
  }

  void _ecouterDeconnexion(BluetoothDevice device) {
    _connexionSub?.cancel();
    _connexionSub = device.connectionState.listen((state) {
      if (state == BluetoothConnectionState.disconnected) {
        final id = device.remoteId.toString();
        if (_capteursVus.containsKey(id)) {
          _capteursVus[id]!.connecte = false;
        }
        // Nettoyer abonnements et timer devenus invalides
        for (final s in _notifySubs) { s.cancel(); }
        _notifySubs.clear();
        _envoyerTimerBle?.cancel();
        _envoyerTimerBle = null;
        _daFitEcriture  = null;
        _hiLinkEcriture = null;
        _protocole      = ProtocoleDetecte.aucun;

        _dispositif = null;
        _connecte   = false;
        // Conserver FC/SpO2/pas pour affichage cached pendant la reconnexion
        if (_fc != null || _spo2 != null || _pas != null) {
          _donneesCachees = true;
        }

        // Déconnexion inattendue (pas initiée par l'utilisateur) :
        // relancer le scan immédiatement avec intervalles rapides.
        if (_dernierCapteurId != null && _btActif && !_simulation) {
          _cyclesScan = 0;
          _scanTimer?.cancel();
          _scanTimer = Timer(const Duration(seconds: 3), () {
            if (!estActif && _btActif) _lancerUnScan();
          });
        }

        notifyListeners();
      }
    });
  }

  // ── Lecture services GATT ─────────────────────────────────
  Future<void> _lireServices(BluetoothDevice device) async {
    _servicesDetectes = [];
    _protocole        = ProtocoleDetecte.aucun;
    _paquetsBruts.clear();

    try {
      final services = await device.discoverServices();
      bool standardSanteTrouve = false;
      bool hiLinkDetecte       = false;

      debugPrint('[STOPMNT] === SERVICES GATT ===');

      for (final service in services) {
        final sUuid = service.serviceUuid.toString().toLowerCase();
        _servicesDetectes.add(sUuid);

        debugPrint('[STOPMNT] Service: $sUuid');
        for (final c in service.characteristics) {
          final cUuid  = c.characteristicUuid.toString().toLowerCase();
          final props  = [
            if (c.properties.read)           'R',
            if (c.properties.write)          'W',
            if (c.properties.writeWithoutResponse) 'Wwr',
            if (c.properties.notify)         'N',
            if (c.properties.indicate)       'I',
          ].join('/');
          debugPrint('[STOPMNT]   char: $cUuid [$props]');

          // ── Profils santé standard ──────────────────────
          if (sUuid.contains('180d')) {
            standardSanteTrouve = true;
            if (c.properties.notify || c.properties.indicate) {
              await c.setNotifyValue(true);
              c.onValueReceived.listen((value) {
                if (value.length > 1) {
                  _fc = value[1].toDouble();
                  notifyListeners();
                }
              });
            }
          }
          if (sUuid.contains('1810')) {
            standardSanteTrouve = true;
            if (c.properties.indicate) {
              await c.setNotifyValue(true);
              c.onValueReceived.listen((value) {
                if (value.length >= 5) {
                  final sys  = value[1] | (value[2] << 8);
                  final dias = value[3] | (value[4] << 8);
                  debugPrint('[STOPMNT] Tension: $sys/$dias mmHg');
                  notifyListeners();
                }
              });
            }
          }
          if (sUuid.contains('1822')) {
            standardSanteTrouve = true;
            if (c.properties.notify || c.properties.indicate) {
              await c.setNotifyValue(true);
              c.onValueReceived.listen((value) {
                if (value.length > 1) {
                  _spo2 = value[1].toDouble();
                  notifyListeners();
                }
              });
            }
          }

          // ── Batterie (180F / 2a19) ──────────────────────
          if (sUuid.contains('180f') && cUuid.contains('2a19')) {
            try {
              final val = await c.read();
              debugPrint('[STOPMNT] Batterie raw: $val');
              // Certaines montres retournent 100 par défaut avant sync companion
              // On marque null plutôt que 100 pour éviter une fausse valeur
              if (val.isNotEmpty && val[0] < 100) {
                _batterie = val[0].clamp(0, 100);
                notifyListeners();
              }
            } catch (e) {
              debugPrint('[STOPMNT] Batterie read error: $e');
            }
            if (c.properties.notify) {
              await c.setNotifyValue(true);
              c.onValueReceived.listen((val) {
                debugPrint('[STOPMNT] Batterie notify: $val');
                if (val.isNotEmpty && val[0] < 100) {
                  _batterie = val[0].clamp(0, 100);
                  notifyListeners();
                }
              });
            }
          }

          // ── Da Fit / VeryFitPro (55FF, 56FF, 60FF, 61FF) ──
          // Capturer toutes les write + notify dans ces services
          if (sUuid.contains('55ff') || sUuid.contains('56ff') ||
              sUuid.contains('60ff') || sUuid.contains('61ff')) {
            // Préférer explicitement 33F1 (canal commandes Da Fit standard)
            if (c.properties.write || c.properties.writeWithoutResponse) {
              if (_daFitEcriture == null || cUuid.contains('33f1')) {
                _daFitEcriture = c;
                debugPrint('[STOPMNT] DaFit écriture: $cUuid (33f1=${cUuid.contains('33f1')})');
              }
            }
            if (c.properties.notify || c.properties.indicate) {
              try {
                await c.setNotifyValue(true);
                // UUID court (4 chars) ou long (36 chars) — gérer les deux formes
                final shortChr = cUuid.length <= 4
                    ? cUuid.toUpperCase()
                    : cUuid.substring(4, 8).toUpperCase();
                final shortSvc = sUuid.contains('55ff') ? '55FF'
                    : sUuid.contains('56ff') ? '56FF'
                    : sUuid.contains('60ff') ? '60FF'
                    : '61FF';
                final label = '$shortSvc/$shortChr';
                final sub = c.onValueReceived.listen((value) {
                  if (value.isEmpty) return;
                  final hex = value
                      .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
                      .join(' ');
                  debugPrint('[STOPMNT] RX $label : $hex');
                  // Tenter décodage
                  final sante = _decoderDaFit(value);
                  if (sante != null) {
                    if (sante.fc   != null) { _fc   = sante.fc;   _donneesCachees = false; }
                    if (sante.spo2 != null) { _spo2 = sante.spo2; _donneesCachees = false; }
                  }
                  // Tenter batterie depuis Da Fit
                  final batt = _extraireBatterieDaFit(value);
                  if (batt != null) _batterie = batt;

                  if (_paquetsBruts.length >= 30) _paquetsBruts.removeAt(0);
                  _paquetsBruts.add(PaquetBrutBle(
                    service        : label,
                    caracteristique: shortChr,
                    octets         : List<int>.from(value),
                    horodatage     : DateTime.now(),
                  ));
                  notifyListeners();
                });
                _notifySubs.add(sub);
              } catch (e) {
                debugPrint('[STOPMNT] setNotify error $cUuid: $e');
              }
            }
          }
          // ── Huawei HiLink LPv2 (FE86) ──────────────────────
          if (sUuid.contains('fe86')) {
            if (!hiLinkDetecte) {
              hiLinkDetecte = true;
              debugPrint('[STOPMNT] === HiLink LPv2 (FE86) détecté ===');
            }
            if (c.properties.write || c.properties.writeWithoutResponse) {
              _hiLinkEcriture = c;
              debugPrint('[STOPMNT] HiLink écriture: $cUuid');
            }
            if (c.properties.notify || c.properties.indicate) {
              try {
                await c.setNotifyValue(true);
                final shortChr = cUuid.length <= 4
                    ? cUuid.toUpperCase()
                    : cUuid.substring(4, 8).toUpperCase();
                final sub = c.onValueReceived.listen((value) {
                  if (value.isEmpty) return;
                  final hex = value
                      .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
                      .join(' ');
                  debugPrint('[STOPMNT] HiLink RX FE86/$shortChr : $hex');
                  _decoderHiLink(value);
                  if (_paquetsBruts.length >= 50) _paquetsBruts.removeAt(0);
                  _paquetsBruts.add(PaquetBrutBle(
                    service        : 'FE86',
                    caracteristique: shortChr,
                    octets         : List<int>.from(value),
                    horodatage     : DateTime.now(),
                  ));
                  notifyListeners();
                });
                _notifySubs.add(sub);
                debugPrint('[STOPMNT] HiLink notify activé: $cUuid');
              } catch (e) {
                debugPrint('[STOPMNT] HiLink setNotify error $cUuid: $e');
              }
            }
          }
        }
      }

      debugPrint('[STOPMNT] DaFit write char: ${_daFitEcriture?.characteristicUuid}');
      debugPrint('[STOPMNT] HiLink write char: ${_hiLinkEcriture?.characteristicUuid}');
      debugPrint('[STOPMNT] Standard santé: $standardSanteTrouve');

      if (standardSanteTrouve) {
        _protocole = ProtocoleDetecte.gattStandard;
      } else if (_daFitEcriture != null) {
        _protocole = ProtocoleDetecte.daFit;
      } else if (hiLinkDetecte) {
        _protocole = ProtocoleDetecte.hiLink;
      } else if (_servicesDetectes.isNotEmpty) {
        _protocole = ProtocoleDetecte.inconnu;
      }

      debugPrint('[STOPMNT] Protocole détecté: $_protocole');
    } catch (e) {
      debugPrint('[STOPMNT] Erreur services GATT: $e');
    }

    notifyListeners();

    if (_protocole == ProtocoleDetecte.hiLink) {
      await Future.delayed(const Duration(milliseconds: 600));
      await _initHiLink();
    } else if (_protocole == ProtocoleDetecte.daFit) {
      await Future.delayed(const Duration(milliseconds: 600));
      await _initDaFit();
    }
  }

  // Séquence d'initialisation Da Fit — envoyée après la découverte des services
  Future<void> _initDaFit() async {
    if (_daFitEcriture == null) {
      debugPrint('[STOPMNT] Pas de canal écriture — init skipped');
      return;
    }
    debugPrint('[STOPMNT] Init Da Fit (token=${_tokenAppairage ?? 'absent'})');

    // ── Bind/auth avec le token d'appairage ──────────────
    if (_tokenAppairage != null && _tokenAppairage!.isNotEmpty) {
      final bytes = _parseBytesToken(_tokenAppairage!);
      if (bytes != null) {
        debugPrint('[STOPMNT] Bind cmd 0x24 : ${bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ')}');
        await envoyerCommandeDaFit([0x24, 0x04, ...bytes]);
        await Future.delayed(const Duration(milliseconds: 500));
      }
    }

    // ── Sync heure (RTC usine = 2023-01-01) ──────────────
    // La montre stocke un timestamp dans chaque paquet de mesure.
    // Sans sync, elle rapporte 2023 ; certaines montres désactivent
    // le suivi continu si l'heure n'est pas réglée.
    await _syncHeure();
    await Future.delayed(const Duration(milliseconds: 400));

    // Sync état appareil
    await envoyerCommandeDaFit([0x71, 0x00]);
    await Future.delayed(const Duration(milliseconds: 400));
    // Demande infos appareil (battery + steps)
    await envoyerCommandeDaFit([0x08, 0x00]);
    await Future.delayed(const Duration(milliseconds: 400));
    // Demande FC temps réel
    await demanderFcDaFit();

    // Démarrer l'envoi périodique des mesures BLE réelles au serveur
    _envoyerTimerBle?.cancel();
    _envoyerTimerBle = Timer.periodic(const Duration(seconds: 30), (_) async {
      if (!_connecte || (_fc == null && _spo2 == null)) return;
      try {
        final mesures = <String, dynamic>{};
        if (_fc   != null) mesures['fc']   = _fc!.round();
        if (_spo2 != null) mesures['spo2'] = _spo2!.round();
        if (_pas  != null) mesures['pas']  = _pas;
        final r = await ApiService.envoyerMesure(
          capteur: _dispositif?.platformName ?? 'smartwatch',
          mesures: mesures,
        );
        if (r['differe'] != true) _nbEnvoyesBle++;
        notifyListeners();
      } catch (e) {
        debugPrint('[STOPMNT] Erreur envoi BLE : $e');
      }
    });
  }

  // ── Huawei HiLink LPv2 ───────────────────────────────────────────────────

  /// Probe initial après connexion à une Band 10 (FE86).
  /// Envoie un Link Layer Request LPv2 (svc=0x0001, cmd=0x0001) pour déclencher
  /// la réponse de la montre et observer le handshake en clair dans logcat.
  Future<void> _initHiLink() async {
    debugPrint('[STOPMNT] === Init HiLink LPv2 ===');
    if (_hiLinkEcriture == null) {
      debugPrint('[STOPMNT] HiLink: pas de char écriture, probe skipped');
      return;
    }
    // LPv2 Link Layer Request minimaliste
    // Format : [5A magic] [00 type=request] [seq LE 2B] [payLen LE 2B] [flags]
    //          [svcId LE 2B] [cmdId LE 2B] [payload TLV...]
    // TLV payload : tag=0x0001 len=0x0002 val=0x0002 (protocol version = 2)
    final pkt = <int>[
      0x5A, 0x00,       // magic + type request
      0x00, 0x00,       // sequence number
      0x06, 0x00,       // payload length = 6
      0x00,             // flags
      0x01, 0x00,       // service ID 0x0001
      0x01, 0x00,       // command ID 0x0001
      0x01, 0x00,       // TLV tag  = 0x0001 (protocol version)
      0x02, 0x00,       // TLV len  = 2
      0x02, 0x00,       // TLV val  = 2 (LPv2)
    ];
    final hex = pkt.map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase()).join(' ');
    debugPrint('[STOPMNT] HiLink TX probe : $hex');
    try {
      final wwr = _hiLinkEcriture!.properties.writeWithoutResponse;
      await _hiLinkEcriture!.write(pkt, withoutResponse: wwr);
      debugPrint('[STOPMNT] HiLink TX ok (withoutResponse=$wwr)');
    } catch (e) {
      debugPrint('[STOPMNT] HiLink TX error : $e');
    }
  }

  /// Décode un paquet reçu sur FE02 et logge au maximum pour analyse.
  void _decoderHiLink(List<int> octets) {
    // JSON en clair — seulement si le premier octet est bien '{' (0x7B)
    if (octets.isNotEmpty && octets[0] == 0x7B) {
      try { debugPrint('[STOPMNT] HiLink JSON  : ${String.fromCharCodes(octets)}'); } catch (_) {}
      return;
    }

    if (octets.length < 11 || octets[0] != 0x5A) {
      debugPrint('[STOPMNT] HiLink UNKNWN: len=${octets.length} first=0x${octets[0].toRadixString(16)}');
      return;
    }

    final type      = octets[1];
    final seqNum    = octets[2] | (octets[3] << 8);
    final payLen    = octets[4] | (octets[5] << 8);
    final flags     = octets[6];
    final serviceId = octets[7] | (octets[8] << 8);
    final commandId = octets[9] | (octets[10] << 8);
    debugPrint(
      '[STOPMNT] HiLink PKT  : type=0x${type.toRadixString(16).padLeft(2,'0')}'
      ' seq=$seqNum'
      ' svc=0x${serviceId.toRadixString(16).padLeft(4,'0')}'
      ' cmd=0x${commandId.toRadixString(16).padLeft(4,'0')}'
      ' payLen=$payLen flags=0x${flags.toRadixString(16)}',
    );
    if (octets.length > 11) {
      final payload = octets.sublist(11);
      final hex = payload
          .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
          .join(' ');
      debugPrint('[STOPMNT] HiLink PYLD  : $hex');
      // Device info — extrait MAC + clé
      if (serviceId == 0x0401 && commandId == 0x0102) {
        _logInfoAppareilHiLink(payload);
      }
    }
  }

  /// Extrait MAC et clé device depuis le payload TLV de la réponse 0x0401/0x0102.
  void _logInfoAppareilHiLink(List<int> payload) {
    // Clé device : bloc de 64 octets ASCII [0-9A-Fa-f] précédé du tag len=0x40
    for (int i = 0; i + 65 <= payload.length; i++) {
      if (payload[i] == 0x40) {
        final slice = payload.sublist(i + 1, i + 65);
        if (slice.every((b) =>
            (b >= 0x30 && b <= 0x39) ||
            (b >= 0x41 && b <= 0x46) ||
            (b >= 0x61 && b <= 0x66))) {
          try { debugPrint('[STOPMNT] HiLink DEV KEY : ${String.fromCharCodes(slice)}'); } catch (_) {}
          break;
        }
      }
    }
    // MAC : motif "xx:xx:xx:xx:xx:xx" (17 chars, séparateur 0x3A)
    for (int i = 0; i + 17 <= payload.length; i++) {
      if (payload[i + 2]  == 0x3A && payload[i + 5]  == 0x3A &&
          payload[i + 8]  == 0x3A && payload[i + 11] == 0x3A &&
          payload[i + 14] == 0x3A) {
        try { debugPrint('[STOPMNT] HiLink DEV MAC : ${String.fromCharCodes(payload.sublist(i, i + 17))}'); } catch (_) {}
        break;
      }
    }
  }

  // Synchronise l'horloge RTC de la montre avec l'heure du téléphone.
  // Format Da Fit : [0x22, 0x06, year_hi, year_lo, month, day, hour, min, sec]
  Future<void> _syncHeure() async {
    final now = DateTime.now();
    final yearHi = (now.year >> 8) & 0xFF;
    final yearLo =  now.year       & 0xFF;
    debugPrint('[STOPMNT] Sync heure: ${now.year}-${now.month.toString().padLeft(2,'0')}-${now.day.toString().padLeft(2,'0')} '
        '${now.hour.toString().padLeft(2,'0')}:${now.minute.toString().padLeft(2,'0')}');
    await envoyerCommandeDaFit([
      0x22, 0x06,
      yearHi, yearLo,
      now.month, now.day,
      now.hour, now.minute, now.second,
    ]);
  }

  // Parse un token string en 4 octets BE.
  // Supporte : "48218648" (décimal), "0x48218648" (hex), "48 21 86 48" (hex espacé).
  static List<int>? _parseBytesToken(String token) {
    try {
      final s = token.trim().replaceAll('0x', '').replaceAll('0X', '');
      // Hex espacé : "48 21 86 48"
      if (s.contains(' ')) {
        final parts = s.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
        if (parts.length == 4) {
          return parts.map((p) => int.parse(p, radix: 16)).toList();
        }
      }
      // 8 chiffres hex sans espace
      if (s.length == 8) {
        // Vérifier si tous les chars sont [0-9a-fA-F]
        if (RegExp(r'^[0-9a-fA-F]+$').hasMatch(s)) {
          return List.generate(4, (i) => int.parse(s.substring(i * 2, i * 2 + 2), radix: 16));
        }
      }
      // Décimal
      final v = int.parse(s);
      return [(v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF];
    } catch (_) {
      return null;
    }
  }

  // ── Commandes Da Fit ─────────────────────────────────────
  // Envoie une commande brute à la caractéristique 33F1.
  // La montre répond sur 33F2 (capturé dans _paquetsBruts).
  Future<void> envoyerCommandeDaFit(List<int> octets) async {
    if (_daFitEcriture == null) {
      debugPrint('[STOPMNT] TX: pas de canal écriture');
      return;
    }
    final hex = octets
        .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
        .join(' ');
    debugPrint('[STOPMNT] TX: $hex');
    try {
      // Préférer writeWithoutResponse (fire-and-forget) si disponible
      final wwr = _daFitEcriture!.properties.writeWithoutResponse;
      await _daFitEcriture!.write(octets, withoutResponse: wwr);
    } catch (e) {
      debugPrint('[STOPMNT] TX error: $e');
    }
  }

  Future<void> demanderFcDaFit() => envoyerCommandeDaFit([0x69, 0x01, 0x01]);

  // ── Décodeur Da Fit / VeryFitPro — Oraimo Watch 2R ──────
  // Protocole rétro-ingénié depuis captures BLE réelles.
  //
  // Protocole confirmé :
  //   E5 11 00 XX      → FC temps réel 1 Hz, XX bpm (flux continu)
  //   F7 03 [ts6] XX   → FC ponctuelle, byte[8] = bpm (flèche bas sur watch)
  //   F7 04 [ts6] XX   → FC pic/haute, byte[8] = bpm (flèche haut sur watch) — PAS SpO2
  //   34 11            → déclenchement mesure SpO2 (pas de valeur)
  //   34 00 00 XX      → SpO2 = XX% (ex: 62h = 98%)
  //   34 00 FF FF      → SpO2 mesure échouée / terminée
  //   A2 XX            → batterie = XX%
  _DonneesProto? _decoderDaFit(List<int> octets) {
    if (octets.isEmpty) return null;
    final type = octets[0];

    // Type 0xE5 — FC temps réel 1 Hz (flux continu pendant mesure active)
    // Format : [E5, 11, 00, XX] où XX = bpm (00 = pas encore de lecture)
    if (type == 0xE5 && octets.length >= 4 &&
        octets[1] == 0x11 && octets[2] == 0x00) {
      final fc = octets[3];
      if (fc > 30 && fc < 250) {
        debugPrint('[STOPMNT] FC temps réel (0xE5): $fc bpm');
        return _DonneesProto(fc: fc.toDouble());
      }
      return null;
    }

    // Type 0xF7 — paquet de mesure timestampé Oraimo Watch 2R
    // Format : [F7, sous-type, year_hi, year_lo, mois, jour, heure, min, valeur]
    // 0x03 = FC courante (flèche bas), 0x04 = FC pic (flèche haut) — les deux sont des bpm
    if (type == 0xF7 && octets.length >= 9) {
      final subType = octets[1];
      final valeur  = octets[8];
      if ((subType == 0x03 || subType == 0x04) && valeur > 30 && valeur < 250) {
        final label = subType == 0x03 ? 'FC courante' : 'FC pic';
        debugPrint('[STOPMNT] $label (0xF7/$subType): $valeur bpm');
        // Les deux sous-types sont des FC — on stocke dans _fc
        return _DonneesProto(fc: valeur.toDouble());
      }
      return null;
    }

    // Type 0xB1 — pas temps réel (cumul depuis début de l'heure courante, ~1 s)
    // IMPORTANT : B1 repart à 0 à chaque nouvelle heure — on n'écrase _pas
    // que si la valeur augmente, pour éviter la régression au changement d'heure
    // ou après une reconnexion avant que 58 FB (total journalier) n'arrive.
    if (type == 0xB1 && octets.length >= 9) {
      final pas = octets[7] | (octets[8] << 8);
      if (pas > 0 && (_pas == null || pas > _pas!)) {
        debugPrint('[STOPMNT] Pas temps réel (0xB1): $pas');
        _pas = pas;
        _donneesCachees = false;
      }
      return null;
    }

    // Type 0x58 FB — résumé activité journalière (service 56FF/34F2)
    // Total du jour depuis minuit — source autoritaire, écrase toujours B1.
    if (type == 0x58 && octets.length >= 20 && octets[1] == 0xFB) {
      final pas = octets[18] | (octets[19] << 8);
      if (pas > 0) {
        debugPrint('[STOPMNT] Pas résumé activité (0x58 FB): $pas');
        _pas = pas;
        _donneesCachees = false;
      }
      return null;
    }

    // Type 0x34 — SpO2
    // [34, FA, ...]       → historique SpO2 post-mesure (premier non-FF en sens inverse)
    // [34, 11]            → mesure SpO2 déclenchée (pas de valeur)
    // [34, 00, 00, XX]    → SpO2 = XX% temps réel
    // [34, 00, FF, FF]    → mesure échouée / terminée
    if (type == 0x34) {
      if (octets.length >= 9 && octets[1] == 0xFA) {
        for (int i = octets.length - 1; i >= 8; i--) {
          final v = octets[i];
          if (v != 0xFF && v > 50 && v <= 100) {
            debugPrint('[STOPMNT] SpO2 historique (0x34 FA): $v%');
            return _DonneesProto(spo2: v.toDouble());
          }
        }
        return null;
      }
      if (octets.length >= 2 && octets[1] == 0x11) {
        debugPrint('[STOPMNT] SpO2 mesure déclenchée (0x34 11)');
        return null;
      }
      if (octets.length >= 4 &&
          octets[1] == 0x00 && octets[2] == 0x00 && octets[3] != 0xFF) {
        final spo2 = octets[3];
        if (spo2 > 50 && spo2 <= 100) {
          debugPrint('[STOPMNT] SpO2 (0x34): $spo2%');
          return _DonneesProto(spo2: spo2.toDouble());
        }
      }
      if (octets.length >= 4 && octets[1] == 0x00 &&
          octets[2] == 0xFF && octets[3] == 0xFF) {
        debugPrint('[STOPMNT] SpO2 mesure échouée (0x34 00 FF FF)');
      }
      return null;
    }

    return null;
  }

  /// Déconnexion physique propre — met à jour tous les états locaux.
  /// [oublierCapteur] : true lors d'une action explicite de l'utilisateur,
  ///                    false lors d'un remplacement par un autre capteur.
  Future<void> _deconnecterPhysique({bool oublierCapteur = false}) async {
    if (_dispositif == null) return;

    final id = _dispositif!.remoteId.toString();

    if (oublierCapteur) {
      _dernierCapteurId = null;
      await _storage.delete(key: 'ble_dernier_capteur');
    }

    _connexionSub?.cancel();
    _connexionSub = null;
    for (final s in _notifySubs) { s.cancel(); }
    _notifySubs.clear();

    try { await _dispositif!.disconnect(); } catch (_) {}

    if (_capteursVus.containsKey(id)) {
      _capteursVus[id]!.connecte = false;
    }
    _envoyerTimerBle?.cancel();
    _envoyerTimerBle = null;
    _nbEnvoyesBle    = 0;
    _dispositif      = null;
    _connecte        = false;
    _tokenAppairage = null;
    if (oublierCapteur) {
      _fc = _spo2 = null;
      _batterie       = null;
      _pas            = null;
      _donneesCachees = false;
    }
    _protocole        = ProtocoleDetecte.aucun;
    _servicesDetectes = [];
    _paquetsBruts.clear();
    _daFitEcriture         = null;
    _hiLinkEcriture        = null;
  }

  /// Arrêt explicite par l'utilisateur — pas de reconnexion automatique.
  Future<void> deconnecter() async {
    await _deconnecterPhysique(oublierCapteur: true);
    notifyListeners();
  }

  Future<void> demarrerSimulation() async {
    if (_connecte && _dispositif != null) {
      await _deconnecterPhysique(oublierCapteur: true);
    }
    arreterScan();
    _simulation  = true;
    _mode        = ModeBle.simulation;
    _erreur      = null;
    _nbEnvoyes   = 0;
    _fc          = 72;
    _fcRepos     = 62;
    _vfc         = 42;
    _spo2        = 98;
    _systolique  = 120;
    _diastolique = 80;
    _temperature = 36.8;
    _glycemie    = 1.10;
    _freqResp    = 16;
    notifyListeners();

    _simTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      _fc          = (_fc!          + (_rand.nextDouble() * 4    - 2    )).clamp(50,  115);
      _spo2        = (_spo2!        + (_rand.nextDouble() * 0.6  - 0.3  )).clamp(94,  100);
      _freqResp    = (_freqResp!    + (_rand.nextDouble() * 0.6  - 0.3  )).clamp(10,   30);
      _systolique  = (_systolique!  + (_rand.nextDouble() * 2    - 1    )).clamp(90,  145);
      _diastolique = (_diastolique! + (_rand.nextDouble() * 1.5  - 0.75 )).clamp(55,   95);
      _temperature = (_temperature! + (_rand.nextDouble() * 0.1  - 0.05 )).clamp(35.8, 38.5);
      _glycemie    = (_glycemie!    + (_rand.nextDouble() * 0.08 - 0.04 )).clamp(0.7,   2.5);
      // FC repos et VFC bougent très lentement (toutes les 5 s env.)
      if (_rand.nextInt(5) == 0) {
        _fcRepos = (_fcRepos! + (_rand.nextDouble() * 2 - 1)).clamp(45, 85);
        _vfc     = (_vfc!     + (_rand.nextDouble() * 4 - 2)).clamp(15, 90);
      }
      notifyListeners();
    });

    _envoyerTimer = Timer.periodic(const Duration(seconds: 30), (_) async {
      var envoyes = 0;
      try {
        // Tensiomètre : pression artérielle + FC
        if (_systolique != null && _diastolique != null) {
          final r = await ApiService.envoyerMesure(
            capteur: 'tensiometre',
            mesures: {
              'systolique' : _systolique!.round(),
              'diastolique': _diastolique!.round(),
              if (_fc != null) 'fc': _fc!.round(),
            },
          );
          if (r['differe'] != true) envoyes++;
        }
        // Glucomètre : glycémie
        if (_glycemie != null) {
          final r = await ApiService.envoyerMesure(
            capteur: 'glucometre',
            mesures: {'glycemie': _glycemie},
          );
          if (r['differe'] != true) envoyes++;
        }
        _nbEnvoyes += envoyes;
        notifyListeners();
      } catch (e) {
        debugPrint('Erreur envoi simulation : $e');
      }
    });
  }

  void arreterSimulation() {
    _simTimer?.cancel();
    _envoyerTimer?.cancel();
    _simulation = false;
    _mode       = ModeBle.reel;
    _fc = _fcRepos = _vfc = _spo2 = null;
    _pas = _batterie = _caloriesActives = null;
    _systolique = _diastolique = _temperature = _glycemie = _freqResp = null;
    _distance = null;
    _nbEnvoyes  = 0;
    notifyListeners();
  }

  String _traduireErreur(String erreur) {
    if (erreur.contains('133')) {
      return 'Erreur Android (133) — Désactivez et réactivez le Bluetooth puis réessayez.';
    }
    if (erreur.contains('timeout') || erreur.contains('timed out')) {
      return 'Délai dépassé — Le capteur ne répond pas. Vérifiez qu\'il est allumé et proche.';
    }
    if (erreur.contains('8') || erreur.contains('disconnected')) {
      return 'Connexion interrompue — Le capteur s\'est déconnecté.';
    }
    if (erreur.contains('6')) {
      return 'Hors de portée — Rapprochez-vous du capteur.';
    }
    if (erreur.contains('permission')) {
      return 'Permission refusée — Autorisez le Bluetooth dans les paramètres.';
    }
    return 'Erreur de connexion — Réessayez dans quelques secondes.';
  }

  // Tente d'extraire la batterie depuis un paquet Da Fit.
  // Sera affiné une fois les vrais paquets analysés.
  int? _extraireBatterieDaFit(List<int> octets) {
    if (octets.isEmpty) return null;
    final type = octets[0];
    // Type 0xA2 — batterie Oraimo Watch 2R
    // Format : [A2, level, status] ex: A2 1A 01 → 26%
    if (type == 0xA2 && octets.length >= 2) {
      final v = octets[1];
      if (v > 0 && v <= 100) {
        debugPrint('[STOPMNT] Batterie Da Fit (0xA2): $v%');
        return v;
      }
    }
    // Formats alternatifs (autres variantes Da Fit)
    if (type == 0x71 && octets.length >= 3) {
      final v = octets[2];
      if (v > 0 && v < 100) return v;
    }
    if (type == 0x91 && octets.length >= 4) {
      final v = octets[3];
      if (v > 0 && v < 100) return v;
    }
    return null;
  }
}

// ── Structures de données internes ───────────────────────

class _DonneesProto {
  final double? fc;
  final double? spo2;
  const _DonneesProto({this.fc, this.spo2});
}

class PaquetBrutBle {
  final String    service;
  final String    caracteristique;
  final List<int> octets;
  final DateTime  horodatage;
  const PaquetBrutBle({
    required this.service,
    required this.caracteristique,
    required this.octets,
    required this.horodatage,
  });

  // Représentation hex pour l'affichage diagnostic
  String get hex => octets
      .map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase())
      .join(' ');
}
