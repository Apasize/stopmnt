// lib/features/ble/ble_screen.dart

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../core/providers/ble_provider.dart';
import '../../core/providers/health_connect_provider.dart';
import '../../core/providers/source_donnees_sante_provider.dart';
import '../../core/theme/app_theme.dart';
import 'qr_scanner_screen.dart';

// Convertit l'identifiant source HC en nom d'app lisible.
// Retourne null si inconnu (package non référencé) → rien n'est affiché.
String? _nomApp(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  const map = <String, String?>{
    'com.fitbit.FitbitMobile'              : 'Fitbit',
    'com.google.android.apps.fitness'      : 'Google Fit',
    'com.samsung.android.shealth'          : 'Samsung Health',
    'com.samsung.health'                   : 'Samsung Health',
    'com.huawei.health'                    : 'Huawei Santé',
    'com.xiaomi.hm.health'                 : 'Mi Fitness',
    'nl.appyhapps.healthsync'              : 'Health Sync',
    'com.garmin.android.apps.connectmobile': 'Garmin Connect',
    'com.polar.androidapp'                 : 'Polar Flow',
    'com.strava'                           : 'Strava',
    'com.withings.healthmate'              : 'Withings',
    'com.runtastic.android'                : 'Runtastic',
    'com.adidas.running'                   : 'adidas Running',
    'com.nike.nikeplus.gps'                : 'Nike Run Club',
    'com.underarmour.record'               : 'MapMyFitness',
    'android'                              : null,
  };
  if (map.containsKey(raw)) return map[raw];
  if (raw.contains('.')) return null;
  return raw.length <= 20 ? raw : null;
}

class BleScreen extends StatefulWidget {
  const BleScreen({super.key});

  @override
  State<BleScreen> createState() => _BleScreenState();
}

class _BleScreenState extends State<BleScreen> {

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ble = context.read<BleProvider>();
      if (!ble.estActif && !ble.scanning && ble.capteurs.isEmpty) {
        ble.demarrerScanAuto();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final ble  = context.watch<BleProvider>();
    final hc   = context.watch<HealthConnectProvider>();
    final src  = context.watch<SourceDonneesSanteProvider>();
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkBg       : AppColors.lightBg;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final cardColor   = dark ? AppColors.darkSurface   : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder    : AppColors.lightBorder;

    // BLE est la source active (connecté, simulation ou reconnexion en cours)
    final bleSource = ble.estActif || ble.donneesCachees;
    // Invitation à activer HC (BLE inactif, HC disponible mais non autorisé)
    final hcInvite  = !bleSource && hc.disponible && !hc.hcNonInstalle && !hc.autorise;

    Future<void> activerHC() async {
      final ok = await hc.demanderPermissions();
      if (!ok) await hc.ouvrirHealthConnect();
    }

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        title           : const Text('Capteurs BLE'),
        backgroundColor : bgColor,
        automaticallyImplyLeading: false,
        actions: [
          if (ble.capteurs.isNotEmpty && !ble.estActif)
            IconButton(
              icon      : Icon(Icons.clear_all, color: mutedColor),
              onPressed : ble.effacerCapteurs,
              tooltip   : 'Effacer la liste',
            ),
          if (ble.estActif)
            TextButton(
              onPressed : ble.simulation ? ble.arreterSimulation : ble.deconnecter,
              child: const Text(
                'Arrêter',
                style: TextStyle(color: AppColors.red, fontSize: 13),
              ),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            // ── Bluetooth désactivé ─────────────────────────
            if (!ble.btActif) ...[
              _AlerteBluetooth(onActiver: ble.demanderActivationBluetooth),
              const SizedBox(height: 4),
            ],

            // ── Carte médicale dynamique (BLE / simulation / HC) ─
            if (src.estActif || ble.donneesCachees) ...[
              _CarteMedicale(
                nomSource      : src.sourceActive == SourceActive.healthConnect
                    ? 'Health Connect'
                    : ble.simulation
                        ? 'Capteur simulé STOP-MNT'
                        : ble.donneesCachees
                            ? (ble.capteurs
                                    .where((c) => c.device.remoteId.toString() == ble.dernierCapteurId)
                                    .firstOrNull?.nom ?? 'Capteur')
                            : (ble.dispositif?.platformName ?? 'Capteur connecté'),
                donnees        : src.donnees,
                simulation     : ble.simulation,
                donneesCachees : ble.donneesCachees,
                nbEnvoyes      : ble.nbEnvoyes,
                nbEnvoyesHC    : src.sourceActive == SourceActive.healthConnect ? hc.nbMetriquesEnvoyes : 0,
                derniereMajHC  : src.sourceActive == SourceActive.healthConnect ? hc.derniereMaj   : null,
                chargementHC   : src.sourceActive == SourceActive.healthConnect && hc.chargement,
                onActualiserHC : src.sourceActive == SourceActive.healthConnect ? hc.charger       : null,
                onDesactiverHC : src.sourceActive == SourceActive.healthConnect ? hc.reinitialiser : null,
                sourcesHC      : src.sourceActive == SourceActive.healthConnect ? hc.sourceParMetrique : const {},
                cardColor      : cardColor,
                borderColor    : borderColor,
                textColor      : textColor,
                mutedColor     : mutedColor,
              ),
              // Carte protocole propriétaire (HiLink / DaFit) si BLE connecté
              if ((src.estActif || ble.donneesCachees) && src.sourceActive != SourceActive.healthConnect && ble.nonMaitrise) ...[
                const SizedBox(height: 10),
                _CarteProprietaire(
                  nomAppareil       : ble.dispositif?.platformName ?? 'Inconnu',
                  servicesDetectes  : ble.servicesDetectes,
                  paquetsBruts      : ble.paquetsBruts,
                  batterie          : ble.batterie,
                  protocole         : ble.protocole,
                  tokenSauvegarde   : ble.tokenAppairage,
                  onSauvegarderToken: ble.sauvegarderToken,
                  cardColor         : cardColor,
                  borderColor       : borderColor,
                  textColor         : textColor,
                  mutedColor        : mutedColor,
                ),
              ],
              const SizedBox(height: 20),
            ],

            // ── Erreur BLE ──────────────────────────────────
            if (ble.erreur != null &&
                ble.erreur != 'bluetooth_desactive_pendant_session' &&
                !ble.estActif) ...[
              _CarteErreur(message: ble.erreur!),
              const SizedBox(height: 16),
            ],

            // ── Actions BLE ─────────────────────────────────
            if (!ble.estActif) ...[
              SizedBox(
                width : double.infinity,
                height: 52,
                child : FilledButton.icon(
                  onPressed: ble.btActif
                      ? (ble.scanning ? ble.arreterScan : ble.scanner)
                      : null,
                  style: FilledButton.styleFrom(
                    backgroundColor: ble.scanning ? AppColors.amber : AppColors.blue,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                  icon : ble.scanning
                      ? const SizedBox(
                          width: 16, height: 16,
                          child: CircularProgressIndicator(
                            color: Colors.white, strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.bluetooth_searching, color: Colors.white, size: 18),
                  label: Text(
                    ble.scanning ? 'Scan en cours...' : 'Scanner les capteurs',
                    style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w500, color: Colors.white,
                    ),
                  ),
                ),
              ),
              if (!ble.connecte) ...[
                const SizedBox(height: 8),
                SizedBox(
                  width : double.infinity,
                  height: 44,
                  child : OutlinedButton.icon(
                    onPressed: ble.demarrerSimulation,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.green,
                      side : BorderSide(color: AppColors.green.withValues(alpha: 0.4)),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    icon : const Icon(Icons.play_circle_outline, size: 16),
                    label: const Text(
                      'Tester en simulation',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
              ],

              // Invitation Health Connect (sous les boutons BLE)
              if (hcInvite) ...[
                const SizedBox(height: 12),
                _InviteHC(
                  chargement  : hc.chargement,
                  onActiver   : activerHC,
                  mutedColor  : mutedColor,
                  cardColor   : cardColor,
                  borderColor : borderColor,
                  textColor   : textColor,
                ),
              ],
            ],

            const SizedBox(height: 20),

            // ── Liste des capteurs détectés ─────────────────
            if (ble.capteurs.isNotEmpty) ...[
              Row(
                children: [
                  Text(
                    '${ble.capteurs.length} capteur${ble.capteurs.length > 1 ? 's' : ''} en mémoire',
                    style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
                    ),
                  ),
                  const SizedBox(width: 8),
                  if (ble.scanning)
                    const SizedBox(
                      width: 12, height: 12,
                      child: CircularProgressIndicator(
                        color: AppColors.blue, strokeWidth: 1.5,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              ...ble.capteurs.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: _CapteurItem(
                  capteur     : c,
                  onTap       : ble.estActif ? null : () => ble.connecter(c.device),
                  cardColor   : cardColor,
                  borderColor : borderColor,
                  textColor   : textColor,
                  mutedColor  : mutedColor,
                ),
              )),
            ],

            // ── État vide ───────────────────────────────────
            if (ble.capteurs.isEmpty && !ble.estActif)
              Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 32),
                  child: Column(
                    children: [
                      Icon(Icons.bluetooth_searching, color: mutedColor, size: 48),
                      const SizedBox(height: 12),
                      Text(
                        ble.scanning ? 'Recherche en cours...' : 'Aucun capteur détecté',
                        style: TextStyle(fontSize: 14, color: mutedColor),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Activez le Bluetooth et approchez\nvos capteurs du téléphone',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 12, color: mutedColor),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ── Alerte Bluetooth désactivé ────────────────────────────
class _AlerteBluetooth extends StatelessWidget {
  final VoidCallback onActiver;
  const _AlerteBluetooth({required this.onActiver});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin     : const EdgeInsets.only(bottom: 16),
      padding    : const EdgeInsets.all(14),
      decoration : BoxDecoration(
        color        : AppColors.amber.withValues(alpha: 0.1),
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(color: AppColors.amber.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.bluetooth_disabled, color: AppColors.amber, size: 20),
          const SizedBox(width: 10),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Bluetooth désactivé',
                  style: TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.amber,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Activez le Bluetooth pour détecter vos capteurs.',
                  style: TextStyle(fontSize: 11, color: AppColors.amber),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed : onActiver,
            style     : TextButton.styleFrom(
              foregroundColor: AppColors.amber,
              padding        : const EdgeInsets.symmetric(horizontal: 10),
            ),
            child: const Text('Activer', style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }
}

// ── Carte erreur ──────────────────────────────────────────
class _CarteErreur extends StatelessWidget {
  final String message;
  const _CarteErreur({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding    : const EdgeInsets.all(12),
      decoration : BoxDecoration(
        color        : AppColors.red.withValues(alpha: 0.1),
        borderRadius : BorderRadius.circular(12),
        border       : Border.all(color: AppColors.red.withValues(alpha: 0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 1),
            child  : Icon(Icons.error_outline, color: AppColors.red, size: 16),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(color: AppColors.red, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Carte médicale dynamique ──────────────────────────────
// Affiche tous les champs non-null de DonneesSante en grille adaptative.
class _CarteMedicale extends StatelessWidget {
  final String       nomSource;
  final DonneesSante donnees;
  final bool         simulation;
  final bool         donneesCachees;
  final int          nbEnvoyes;
  final int          nbEnvoyesHC;
  final DateTime?    derniereMajHC;
  final bool         chargementHC;
  final Future<void> Function()? onActualiserHC;
  final VoidCallback?            onDesactiverHC;
  final Map<String, String>      sourcesHC;
  final Color        cardColor, borderColor, textColor, mutedColor;

  const _CarteMedicale({
    required this.nomSource,
    required this.donnees,
    required this.simulation,
    this.donneesCachees = false,
    required this.nbEnvoyes,
    this.nbEnvoyesHC = 0,
    this.derniereMajHC,
    this.chargementHC = false,
    this.onActualiserHC,
    this.onDesactiverHC,
    this.sourcesHC = const {},
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  bool get _estHC => donnees.source == SourceActive.healthConnect;

  String _labelMajHC() {
    if (derniereMajHC == null) return 'Données disponibles';
    final diff = DateTime.now().difference(derniereMajHC!);
    if (diff.inMinutes < 1)  return 'À l\'instant';
    if (diff.inMinutes < 60) return 'Il y a ${diff.inMinutes} min';
    if (diff.inHours < 24)   return 'Il y a ${diff.inHours}h';
    return 'Il y a ${diff.inDays}j';
  }

  Color get _dotColor {
    if (_estHC)         return AppColors.blue;
    if (donneesCachees) return Colors.orange;
    return AppColors.green;
  }

  // Rangées sémantiques : les métriques liées restent sur la même ligne.
  List<Widget> _rangees() {
    final d      = donnees;
    final s      = sourcesHC;
    final muted  = mutedColor;
    final txt    = textColor;
    final att    = donneesCachees;
    final result = <Widget>[];

    // Retourne null si valeur absente ou nulle (pas d'intérêt à afficher 0)
    _Metrique? m(String label, double? value, String unite, Color color, {String? srcKey}) {
      if (value == null || value == 0.0) return null;
      return _Metrique(
        label: label, value: value, unite: unite, color: color,
        mutedColor: muted, textColor: txt, attenue: att,
        sourceNom: _nomApp(srcKey != null ? s[srcKey] : null),
      );
    }

    void ligne(List<_Metrique?> candidats) {
      final visible = candidats.whereType<_Metrique>().toList();
      if (visible.isEmpty) return;
      if (result.isNotEmpty) result.add(const SizedBox(height: 8));
      final cells = <Widget>[];
      for (var i = 0; i < visible.length; i++) {
        if (i > 0) cells.add(const SizedBox(width: 8));
        cells.add(Expanded(child: visible[i]));
      }
      result.add(IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: cells),
      ));
    }

    ligne([m('FC',   d.fc,   'bpm', AppColors.red,  srcKey: 'fc'),
           m('SpO₂', d.spo2, '%',   AppColors.blue, srcKey: 'spo2')]);

    ligne([m('FC repos', d.fcRepos, 'bpm', const Color(0xFFE11D48), srcKey: 'fcRepos'),
           m('VFC',      d.vfc,     'ms',  const Color(0xFF0D9488), srcKey: 'vfc')]);

    ligne([m('Systolique',  d.systolique,  'mmHg', const Color(0xFFEF4444), srcKey: 'sys'),
           m('Diastolique', d.diastolique, 'mmHg', const Color(0xFF3B82F6), srcKey: 'dias')]);

    ligne([m('Resp.',    d.freqResp,    '/min', const Color(0xFF0891B2), srcKey: 'freqResp'),
           m('Temp.',    d.temperature, '°C',   const Color(0xFF7C3AED), srcKey: 'temp'),
           m('Glycémie', d.glycemie,    'g/L',  const Color(0xFFD97706), srcKey: 'glyc')]);

    ligne([m('Poids', d.poids, 'kg',    const Color(0xFF6366F1), srcKey: 'poids'),
           m('IMC',   d.imc,   'kg/m²', const Color(0xFF8B5CF6), srcKey: 'poids')]);

    ligne([m('Graisse',  d.graisseCorp, '%',  const Color(0xFFF59E0B), srcKey: 'graisseCorp'),
           m('Musc.',    d.masseMusc,   'kg', const Color(0xFF10B981), srcKey: 'masseMusc'),
           m('Eau corp.',d.eauCorp,     'kg', const Color(0xFF0EA5E9), srcKey: 'eauCorp')]);

    // Distance : si < 1 km, convertir en mètres
    final distVal = d.distance != null
        ? (d.distance! < 1 ? d.distance! * 1000 : d.distance!)
        : null;
    final distUnit = (d.distance != null && d.distance! < 1) ? 'm' : 'km';
    ligne([m('Pas',      d.pas?.toDouble(),        'pas', AppColors.green,         srcKey: 'pas'),
           m('Distance', distVal,                   distUnit, const Color(0xFF0284C7), srcKey: 'distance'),
           m('Étages',   d.etages?.toDouble(),      'ét.', const Color(0xFF64748B), srcKey: 'etages')]);

    ligne([m('Calories',  d.calories?.toDouble(),        'kcal', AppColors.amber,         srcKey: 'calories'),
           m('Cal. act.', d.caloriesActives?.toDouble(), 'kcal', const Color(0xFFEA580C), srcKey: 'calAct'),
           m('Cal. base', d.caloriesBasales?.toDouble(), 'kcal', const Color(0xFF78716C), srcKey: 'calBase')]);

    ligne([m('Hydrat.', d.eau,     'L', const Color(0xFF38BDF8), srcKey: 'eau')]);
    ligne([m('Sommeil', d.sommeil, 'h', const Color(0xFF4F46E5), srcKey: 'sommeil')]);

    ligne([m('Profond', d.sommeilProfond, 'h', const Color(0xFF312E81), srcKey: 'sommeil'),
           m('REM',     d.sommeilREM,     'h', const Color(0xFF6D28D9), srcKey: 'sommeil'),
           m('Léger',   d.sommeilLeger,   'h', const Color(0xFF7C3AED), srcKey: 'sommeil')]);

    return result;
  }

  @override
  Widget build(BuildContext context) {
    final d       = donnees;
    final muted   = mutedColor;
    final rangees = _rangees();

    return Container(
      padding    : const EdgeInsets.all(16),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(20),
        border       : Border.all(color: _dotColor.withValues(alpha: 0.4), width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── En-tête ─────────────────────────────────────
          Row(
            children: [
              if (donneesCachees)
                const SizedBox(width: 8, height: 8,
                  child: CircularProgressIndicator(strokeWidth: 1.5, color: Colors.orange))
              else
                Container(width: 8, height: 8,
                  decoration: BoxDecoration(color: _dotColor, shape: BoxShape.circle)),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(nomSource, style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w500, color: textColor)),
                    if (donneesCachees)
                      const Text('Synchronisation en cours…',
                          style: TextStyle(fontSize: 10, color: Colors.orange))
                    else if (_estHC)
                      Text(_labelMajHC(),
                          style: TextStyle(fontSize: 10, color: muted)),
                  ],
                ),
              ),
              // Batterie (BLE uniquement)
              if (d.batterie != null) ...[
                Icon(
                  d.batterie! > 50 ? Icons.battery_full
                      : d.batterie! > 20 ? Icons.battery_3_bar : Icons.battery_1_bar,
                  color: d.batterie! > 20 ? AppColors.green : AppColors.red,
                  size: 14,
                ),
                const SizedBox(width: 2),
                Text('${d.batterie}%',
                  style: TextStyle(fontSize: 10,
                    color: d.batterie! > 20 ? AppColors.green : AppColors.red)),
                const SizedBox(width: 6),
              ],
              // Compteur envois (BLE/simulation)
              if (!_estHC && (simulation || nbEnvoyes > 0))
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.green.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(99),
                  ),
                  child: Text(
                    nbEnvoyes == 0
                        ? 'En attente…'
                        : '$nbEnvoyes envoyé${nbEnvoyes > 1 ? 's' : ''}',
                    style: const TextStyle(
                      fontSize: 10, color: AppColors.green, fontWeight: FontWeight.w500)),
                ),
              // HC : actualiser + désactiver
              if (_estHC) ...[
                IconButton(
                  onPressed: (chargementHC || onActualiserHC == null) ? null : onActualiserHC,
                  icon: chargementHC
                      ? const SizedBox(width: 16, height: 16,
                          child: CircularProgressIndicator(color: AppColors.blue, strokeWidth: 1.5))
                      : Icon(Icons.refresh, color: muted, size: 18),
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.all(6),
                  constraints: const BoxConstraints(),
                ),
                IconButton(
                  onPressed: onDesactiverHC,
                  icon: Icon(Icons.close, color: muted, size: 18),
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.all(6),
                  constraints: const BoxConstraints(),
                  tooltip: 'Désactiver Health Connect',
                ),
              ],
            ],
          ),

          // ── Contenu ──
          if (rangees.isEmpty) ...[
            const SizedBox(height: 12),
            Text('En attente de données…', style: TextStyle(fontSize: 12, color: mutedColor)),
          ] else ...[
            const SizedBox(height: 14),
            ...rangees,
          ],

          // ── Compteur envois HC (bas de section) ──────────
          if (_estHC) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: nbEnvoyesHC > 0
                    ? AppColors.green.withValues(alpha: 0.07)
                    : AppColors.blue.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  Icon(
                    nbEnvoyesHC > 0 ? Icons.cloud_done_outlined : Icons.cloud_upload_outlined,
                    size: 13,
                    color: nbEnvoyesHC > 0 ? AppColors.green : AppColors.blue,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    nbEnvoyesHC == 0
                        ? 'En attente du premier envoi vers le serveur…'
                        : '$nbEnvoyesHC donnée${nbEnvoyesHC > 1 ? 's' : ''} envoyée${nbEnvoyesHC > 1 ? 's' : ''} vers le serveur',
                    style: TextStyle(
                      fontSize  : 11,
                      fontWeight: FontWeight.w500,
                      color     : nbEnvoyesHC > 0 ? AppColors.green : AppColors.blue,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ── Invitation Health Connect (compact) ───────────────────
// Affichée sous les actions BLE quand HC est disponible mais non autorisé.
class _InviteHC extends StatelessWidget {
  final bool       chargement;
  final Future<void> Function() onActiver;
  final Color      cardColor, borderColor, textColor, mutedColor;

  const _InviteHC({
    required this.chargement, required this.onActiver,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding    : const EdgeInsets.all(14),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(color: borderColor, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(
              color        : AppColors.blue.withValues(alpha: 0.08),
              borderRadius : BorderRadius.circular(10),
            ),
            child: const Icon(Icons.favorite_border, color: AppColors.blue, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Health Connect',
                    style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
                    )),
                const SizedBox(height: 2),
                Text(
                  'Lit FC, SpO₂ et pas depuis vos apps santé (Huawei Health, Samsung Health…)',
                  style: TextStyle(fontSize: 11, color: mutedColor),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: chargement ? null : onActiver,
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.blue,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            child: chargement
                ? const SizedBox(
                    width: 14, height: 14,
                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                  )
                : const Text('Activer', style: TextStyle(fontSize: 12, color: Colors.white)),
          ),
        ],
      ),
    );
  }
}

class _Metrique extends StatelessWidget {
  final String  label, unite;
  final double? value;
  final bool    attenue;
  final Color   color, mutedColor, textColor;
  final String? sourceNom;
  const _Metrique({
    required this.label, required this.unite, this.value,
    this.attenue = false,
    required this.color, required this.mutedColor, required this.textColor,
    this.sourceNom,
  });

  String _formatValeur(double v) {
    if (v == v.roundToDouble() || v.abs() >= 100) return v.round().toString();
    return v.toStringAsFixed(1);
  }

  @override
  Widget build(BuildContext context) {
    final dark       = Theme.of(context).brightness == Brightness.dark;
    final valueColor = attenue ? textColor.withValues(alpha: 0.45) : textColor;
    return Container(
      padding    : const EdgeInsets.fromLTRB(10, 10, 10, 10),
      decoration : BoxDecoration(
        color        : dark ? AppColors.darkBg : AppColors.lightBg,
        borderRadius : BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 5, height: 5,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 4),
              Expanded(
                child: Text(label,
                  style: TextStyle(fontSize: 10, color: mutedColor),
                  overflow: TextOverflow.ellipsis),
              ),
            ],
          ),
          const SizedBox(height: 5),
          Text(
            value != null ? _formatValeur(value!) : '—',
            style: TextStyle(
              fontSize: 18, fontWeight: FontWeight.w600, color: valueColor,
            ),
          ),
          Text(unite, style: TextStyle(fontSize: 9, color: mutedColor)),
          if (sourceNom != null) ...[
            const SizedBox(height: 2),
            Text(
              sourceNom!,
              style: TextStyle(fontSize: 9, color: mutedColor.withValues(alpha: 0.65)),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

// ── Item capteur dans la liste ────────────────────────────
class _CapteurItem extends StatelessWidget {
  final CapteurDetecte capteur;
  final VoidCallback?  onTap;
  final Color          cardColor, borderColor, textColor, mutedColor;

  const _CapteurItem({
    required this.capteur, this.onTap,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    final connecte    = capteur.connecte;
    final couleur     = connecte ? AppColors.green : AppColors.blue;
    final secondsDiff = DateTime.now().difference(capteur.dernierVu).inSeconds;
    final recence     = secondsDiff < 15 ? 'En direct'
        : secondsDiff < 60 ? 'Il y a ${secondsDiff}s'
        : 'Il y a ${(secondsDiff / 60).round()} min';

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding    : const EdgeInsets.all(14),
        decoration : BoxDecoration(
          color        : connecte ? AppColors.green.withValues(alpha: 0.05) : cardColor,
          borderRadius : BorderRadius.circular(14),
          border       : Border.all(
            color: connecte ? AppColors.green.withValues(alpha: 0.4) : borderColor,
            width: 0.5,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 42, height: 42,
              decoration: BoxDecoration(
                color        : couleur.withValues(alpha: 0.1),
                borderRadius : BorderRadius.circular(12),
              ),
              child: Icon(
                connecte ? Icons.bluetooth_connected : Icons.bluetooth,
                color: couleur, size: 20,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          capteur.nom,
                          style: TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (connecte) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color       : AppColors.green.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(99),
                          ),
                          child: const Text(
                            'Connecté',
                            style: TextStyle(
                              fontSize: 9, fontWeight: FontWeight.w600, color: AppColors.green,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Text(
                        capteur.device.remoteId.toString().substring(0, 11),
                        style: TextStyle(fontSize: 10, color: mutedColor),
                      ),
                      const SizedBox(width: 6),
                      Text('·', style: TextStyle(color: mutedColor)),
                      const SizedBox(width: 6),
                      Text(recence, style: TextStyle(fontSize: 10, color: mutedColor)),
                    ],
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                _BarresSignal(
                  barres : capteur.barresSignal,
                  couleur: connecte ? AppColors.green : _couleurSignal(capteur),
                ),
                const SizedBox(height: 3),
                Text(
                  capteur.labelSignal,
                  style: TextStyle(
                    fontSize: 10, fontWeight: FontWeight.w500,
                    color: _couleurSignal(capteur),
                  ),
                ),
                Text('${capteur.rssi} dBm',
                    style: TextStyle(fontSize: 9, color: mutedColor)),
              ],
            ),
            if (!connecte) ...[
              const SizedBox(width: 8),
              Icon(Icons.chevron_right, color: mutedColor, size: 16),
            ],
          ],
        ),
      ),
    );
  }

  Color _couleurSignal(CapteurDetecte c) {
    switch (c.niveauSignal) {
      case NiveauSignal.excellent  : return AppColors.green;
      case NiveauSignal.bon        : return AppColors.green;
      case NiveauSignal.faible     : return AppColors.amber;
      case NiveauSignal.tresFaible : return AppColors.red;
    }
  }
}

// ── Carte protocole propriétaire ─────────────────────────
class _CarteProprietaire extends StatefulWidget {
  final String              nomAppareil;
  final List<String>        servicesDetectes;
  final List<PaquetBrutBle> paquetsBruts;
  final int?                batterie;
  final ProtocoleDetecte    protocole;
  final String?             tokenSauvegarde;
  final Future<void> Function(String) onSauvegarderToken;
  final Color               cardColor, borderColor, textColor, mutedColor;

  const _CarteProprietaire({
    required this.nomAppareil,
    required this.servicesDetectes,
    required this.paquetsBruts,
    required this.batterie,
    this.protocole = ProtocoleDetecte.inconnu,
    this.tokenSauvegarde,
    required this.onSauvegarderToken,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  State<_CarteProprietaire> createState() => _CarteProprietaireState();
}

class _CarteProprietaireState extends State<_CarteProprietaire> {
  bool _detailsOuverts      = false;
  bool _paquetsOuverts      = false;
  bool _saisieManuelleOuverte = false;
  final TextEditingController _tokenCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tokenCtrl.text = widget.tokenSauvegarde ?? '';
  }

  @override
  void dispose() {
    _tokenCtrl.dispose();
    super.dispose();
  }

  Future<void> _scanner() async {
    final nav       = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final valeur = await nav.push<String>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => const QrScannerScreen(),
      ),
    );
    if (valeur != null && mounted) {
      _tokenCtrl.text = valeur;
      await widget.onSauvegarderToken(valeur);
      if (mounted) {
        messenger.showSnackBar(
          const SnackBar(
            content        : Text('Montre configurée — reconnexion en cours…'),
            duration       : Duration(seconds: 3),
            backgroundColor: AppColors.green,
          ),
        );
      }
    }
  }

  Future<void> _validerManuel() async {
    if (_tokenCtrl.text.trim().isEmpty) return;
    final messenger = ScaffoldMessenger.of(context);
    await widget.onSauvegarderToken(_tokenCtrl.text);
    if (mounted) {
      setState(() => _saisieManuelleOuverte = false);
      messenger.showSnackBar(
        const SnackBar(
          content        : Text('Montre configurée — reconnexion en cours…'),
          duration       : Duration(seconds: 3),
          backgroundColor: AppColors.green,
        ),
      );
    }
  }

  static const _nomsServices = {
    '1800' : 'Generic Access',
    '1801' : 'Generic Attribute',
    '180f' : 'Battery Service',
    '1812' : 'HID (Media Control)',
    '55ff' : 'Da Fit — data',
    '56ff' : 'Da Fit — cmd',
    '60ff' : 'Propriétaire',
    '61ff' : 'Propriétaire',
    'fe86' : 'HiLink LPv2 (Huawei)',
  };

  String _labelService(String uuid) {
    final cleaned = uuid.toLowerCase().replaceAll('-', '');
    if (cleaned.startsWith('0000') &&
        cleaned.endsWith('00001000800000805f9b34fb')) {
      final court = cleaned.substring(4, 8);
      return _nomsServices[court] ?? '0x${court.toUpperCase()}';
    }
    if (uuid.length == 4) {
      return _nomsServices[uuid.toLowerCase()] ?? '0x${uuid.toUpperCase()}';
    }
    final prefix = uuid.length >= 8
        ? uuid.substring(0, 8).toLowerCase()
        : uuid.toLowerCase();
    return _nomsServices[prefix] ?? uuid.substring(0, 8).toUpperCase();
  }

  Color _couleurService(String uuid) {
    final u = uuid.toLowerCase();
    if (u.contains('180f')) return AppColors.green;
    if (u.contains('1812')) return AppColors.blue;
    if (u.contains('55ff') || u.contains('56ff')) return AppColors.amber;
    if (u.contains('1800') || u.contains('1801')) return AppColors.blue;
    if (u.contains('fe86')) return AppColors.amber;
    return AppColors.red;
  }

  @override
  Widget build(BuildContext context) {
    final hasPaquets  = widget.paquetsBruts.isNotEmpty;
    final estHiLink   = widget.protocole == ProtocoleDetecte.hiLink;
    final estDaFit    = widget.protocole == ProtocoleDetecte.daFit;

    return Container(
      padding    : const EdgeInsets.all(14),
      decoration : BoxDecoration(
        color        : AppColors.amber.withValues(alpha: 0.07),
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(
          color: AppColors.amber.withValues(alpha: 0.35), width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          // ── En-tête ────────────────────────────────────────
          Row(
            children: [
              Icon(
                widget.tokenSauvegarde != null
                    ? Icons.check_circle_outline
                    : Icons.settings_outlined,
                color: widget.tokenSauvegarde != null
                    ? AppColors.green : AppColors.amber,
                size: 16,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.nomAppareil,
                      style: TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600, color: widget.textColor,
                      ),
                    ),
                    Text(
                      switch (widget.protocole) {
                        ProtocoleDetecte.hiLink  => 'HiLink LPv2 — données chiffrées',
                        ProtocoleDetecte.inconnu => 'Protocole non identifié',
                        ProtocoleDetecte.daFit   => widget.tokenSauvegarde != null
                            ? 'Da Fit — configuré'
                            : 'Da Fit — configuration requise',
                        _ => 'Protocole propriétaire',
                      },
                      style: TextStyle(
                        fontSize: 10,
                        color: estDaFit && widget.tokenSauvegarde != null
                            ? AppColors.green.withValues(alpha: 0.8)
                            : AppColors.amber.withValues(alpha: 0.8),
                      ),
                    ),
                  ],
                ),
              ),
              if (widget.batterie != null) ...[
                Icon(
                  widget.batterie! > 50 ? Icons.battery_full
                      : widget.batterie! > 20 ? Icons.battery_3_bar
                      : Icons.battery_1_bar,
                  color: widget.batterie! > 20 ? AppColors.green : AppColors.red,
                  size: 16,
                ),
                const SizedBox(width: 3),
                Text(
                  '${widget.batterie}%',
                  style: TextStyle(
                    fontSize: 11, fontWeight: FontWeight.w500,
                    color: widget.batterie! > 20 ? AppColors.green : AppColors.red,
                  ),
                ),
                const SizedBox(width: 8),
              ],
              GestureDetector(
                onTap: () => setState(() => _detailsOuverts = !_detailsOuverts),
                child: Icon(
                  _detailsOuverts ? Icons.expand_less : Icons.expand_more,
                  color: widget.mutedColor, size: 18,
                ),
              ),
            ],
          ),

          // ── Limitation HiLink — saisie manuelle ────────────
          if (estHiLink) ...[
            const SizedBox(height: 12),
            Container(
              padding    : const EdgeInsets.all(12),
              decoration : BoxDecoration(
                color        : AppColors.amber.withValues(alpha: 0.07),
                borderRadius : BorderRadius.circular(10),
                border       : Border.all(
                  color: AppColors.amber.withValues(alpha: 0.3), width: 0.5,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.lock_outline, color: AppColors.amber, size: 14),
                      const SizedBox(width: 6),
                      const Expanded(
                        child: Text(
                          'Données non lisibles en temps réel',
                          style: TextStyle(
                            fontSize: 12, fontWeight: FontWeight.w600,
                            color: AppColors.amber,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Huawei chiffre ses données BLE et Huawei Health ne les '
                    'partage pas avec les autres apps. Consultez vos résultats '
                    'dans Huawei Health, puis saisissez-les ici.',
                    style: TextStyle(fontSize: 11, color: widget.mutedColor),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => context.go('/mesures'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.amber,
                        side: BorderSide(
                            color: AppColors.amber.withValues(alpha: 0.5)),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8)),
                      ),
                      icon: const Icon(Icons.edit_outlined, size: 14),
                      label: const Text(
                        'Saisir une mesure manuellement',
                        style: TextStyle(fontSize: 12),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // ── Config QR Da Fit ────────────────────────────────
          if (estDaFit) ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _scanner,
                style: OutlinedButton.styleFrom(
                  foregroundColor: widget.tokenSauvegarde != null
                      ? AppColors.green : AppColors.blue,
                  side: BorderSide(
                    color: widget.tokenSauvegarde != null
                        ? AppColors.green.withValues(alpha: 0.5)
                        : AppColors.blue.withValues(alpha: 0.5),
                  ),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
                icon : const Icon(Icons.qr_code_scanner, size: 16),
                label: Text(
                  widget.tokenSauvegarde != null
                      ? 'Reconfigurer (nouveau QR)'
                      : 'Scanner le QR pour activer la montre',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ),
            const SizedBox(height: 4),
            GestureDetector(
              onTap: () =>
                  setState(() => _saisieManuelleOuverte = !_saisieManuelleOuverte),
              child: Text(
                _saisieManuelleOuverte ? 'Masquer' : 'Saisir manuellement',
                style: TextStyle(
                  fontSize: 10, color: widget.mutedColor,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
            if (_saisieManuelleOuverte) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller  : _tokenCtrl,
                      style       : TextStyle(fontSize: 12, color: widget.textColor),
                      keyboardType: TextInputType.text,
                      decoration  : InputDecoration(
                        hintText      : 'Code affiché sur la montre',
                        hintStyle     : TextStyle(fontSize: 11, color: widget.mutedColor),
                        isDense       : true,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 8),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                              color: AppColors.blue.withValues(alpha: 0.4)),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                              color: AppColors.blue.withValues(alpha: 0.25)),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(color: AppColors.blue),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  FilledButton(
                    onPressed: _validerManuel,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.blue,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text('OK',
                        style: TextStyle(
                            fontSize: 12, color: Colors.white,
                            fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
            ],
          ],

          // ── Services détectés (détails) ─────────────────────
          if (_detailsOuverts) ...[
            const SizedBox(height: 12),
            Text(
              'Services (${widget.servicesDetectes.length})',
              style: TextStyle(
                fontSize: 10, fontWeight: FontWeight.w600, color: widget.mutedColor,
              ),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6, runSpacing: 6,
              children: widget.servicesDetectes.map((uuid) {
                final label   = _labelService(uuid);
                final couleur = _couleurService(uuid);
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color       : couleur.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(6),
                    border      : Border.all(
                        color: couleur.withValues(alpha: 0.25), width: 0.5),
                  ),
                  child: Text(label,
                      style: TextStyle(
                        fontSize: 10, color: couleur,
                        fontWeight: FontWeight.w500,
                      )),
                );
              }).toList(),
            ),

            // ── Paquets bruts ─────────────────────────────────
            const SizedBox(height: 12),
            GestureDetector(
              onTap: () => setState(() => _paquetsOuverts = !_paquetsOuverts),
              child: Row(
                children: [
                  Text(
                    'Paquets bruts${hasPaquets ? ' (${widget.paquetsBruts.length})' : ' — en attente'}',
                    style: TextStyle(
                      fontSize: 10, fontWeight: FontWeight.w600,
                      color: hasPaquets ? AppColors.amber : widget.mutedColor,
                    ),
                  ),
                  const SizedBox(width: 4),
                  if (hasPaquets)
                    Icon(
                      _paquetsOuverts ? Icons.expand_less : Icons.expand_more,
                      color: AppColors.amber, size: 14,
                    ),
                ],
              ),
            ),
            if (_paquetsOuverts && hasPaquets) ...[
              const SizedBox(height: 6),
              ...widget.paquetsBruts.reversed.take(5).map((p) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 5, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppColors.amber.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(p.service,
                          style: const TextStyle(
                            fontSize: 9, color: AppColors.amber,
                            fontWeight: FontWeight.w600,
                          )),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(p.hex,
                          style: TextStyle(
                            fontSize: 9, color: widget.textColor,
                            fontFamily: 'monospace',
                          )),
                    ),
                    Text(
                      '${p.horodatage.hour.toString().padLeft(2,'0')}:'
                      '${p.horodatage.minute.toString().padLeft(2,'0')}:'
                      '${p.horodatage.second.toString().padLeft(2,'0')}',
                      style: TextStyle(fontSize: 8, color: widget.mutedColor),
                    ),
                  ],
                ),
              )),
              const SizedBox(height: 4),
              Text(
                'Portez la montre et bougez pour générer des paquets.',
                style: TextStyle(fontSize: 10, color: widget.mutedColor),
              ),
            ],
          ],

        ],
      ),
    );
  }
}

// ── Barres de signal visuelles ────────────────────────────
class _BarresSignal extends StatelessWidget {
  final int   barres;
  final Color couleur;
  const _BarresSignal({required this.barres, required this.couleur});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: List.generate(4, (i) {
        final active  = i < barres;
        final hauteur = 6.0 + (i * 3.0);
        return Container(
          width : 4,
          height: hauteur,
          margin: const EdgeInsets.only(left: 2),
          decoration: BoxDecoration(
            color        : active ? couleur : couleur.withValues(alpha: 0.2),
            borderRadius : BorderRadius.circular(1),
          ),
        );
      }),
    );
  }
}
