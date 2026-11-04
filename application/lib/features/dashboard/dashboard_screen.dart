// lib/features/dashboard/dashboard_screen.dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers/auth_provider.dart';
import '../../core/providers/theme_provider.dart';
import '../../core/providers/ble_provider.dart';
import '../../core/providers/alertes_provider.dart';
import '../../core/providers/source_donnees_sante_provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/models/alerte.dart';
import '../../core/widgets/skeleton.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _dialogBleShown = false;

  // Panneau notifications
  void _afficherNotifications(BuildContext context, List<Alerte> alertes) {
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkSurface  : AppColors.lightSurface;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;

    showModalBottomSheet(
      context         : context,
      backgroundColor : bgColor,
      isScrollControlled: true, // important pour éviter l'overflow
      shape           : const RoundedRectangleBorder(
        borderRadius  : BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
            // Max 60% de la hauteur écran
            maxHeight: MediaQuery.of(context).size.height * 0.6,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 12),
              Container(
                width: 36, height: 4,
                decoration: BoxDecoration(
                  color        : mutedColor.withValues(alpha: 0.3),
                  borderRadius : BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Row(
                  children: [
                    Text('Notifications',
                        style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w500,
                          color: textColor,
                        )),
                    const Spacer(),
                    if (alertes.isNotEmpty)
                      Container(
                        padding    : const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3,
                        ),
                        decoration : BoxDecoration(
                          color        : AppColors.red.withValues(alpha: 0.1),
                          borderRadius : BorderRadius.circular(99),
                        ),
                        child: Text(
                          '${alertes.length}',
                          style: const TextStyle(
                            fontSize: 12, color: AppColors.red,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Flexible(
                child: alertes.isEmpty
                    ? Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.notifications_off_outlined,
                          color: mutedColor, size: 32),
                      const SizedBox(height: 8),
                      Text('Aucune notification',
                          style: TextStyle(
                            color: mutedColor, fontSize: 13,
                          )),
                    ],
                  ),
                )
                    : ListView.separated(
                  shrinkWrap      : true,
                  padding         : const EdgeInsets.symmetric(
                    horizontal: 16,
                  ),
                  itemCount       : alertes.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder     : (_, i) {
                    final a     = alertes[i];
                    final color = a.estCritique
                        ? AppColors.red
                        : AppColors.amber;
                    return Container(
                      padding    : const EdgeInsets.all(12),
                      decoration : BoxDecoration(
                        color        : color.withValues(alpha: 0.07),
                        borderRadius : BorderRadius.circular(12),
                        border       : Border.all(
                          color: color.withValues(alpha: 0.2), width: 0.5,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            a.estCritique
                                ? Icons.warning_amber_outlined
                                : Icons.info_outline,
                            color: color, size: 18,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment:
                              CrossAxisAlignment.start,
                              children: [
                                Text(a.message,
                                    style: TextStyle(
                                      fontSize  : 12,
                                      fontWeight: FontWeight.w500,
                                      color     : textColor,
                                    ),
                                    maxLines : 2,
                                    overflow : TextOverflow.ellipsis),
                                const SizedBox(height: 2),
                                Text(
                                  '${a.timestamp.toLocal().day.toString().padLeft(2,'0')}/'
                                      '${a.timestamp.toLocal().month.toString().padLeft(2,'0')} '
                                      '${a.timestamp.toLocal().hour.toString().padLeft(2,'0')}:'
                                      '${a.timestamp.toLocal().minute.toString().padLeft(2,'0')}',
                                  style: TextStyle(
                                    fontSize: 10, color: mutedColor,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      Navigator.pop(ctx);
                      context.go('/alertes');
                    },
                    style: OutlinedButton.styleFrom(
                      side : BorderSide(
                        color: AppColors.blue.withValues(alpha: 0.4),
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text('Voir toutes les alertes',
                        style: TextStyle(color: AppColors.blue)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth        = context.watch<AuthProvider>();
    final ble         = context.watch<BleProvider>();
    final src         = context.watch<SourceDonneesSanteProvider>();
    final alertesProv = context.watch<AlertesProvider>();
    final mesAlertes  = alertesProv.alertes;
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkBg       : AppColors.lightBg;
    final cardColor   = dark ? AppColors.darkSurface   : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder    : AppColors.lightBorder;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;

    // Dialogue BLE désactivé — une seule fois
    if (!ble.btActif && ble.erreur == 'bluetooth_desactive_pendant_session'
        && !_dialogBleShown) {
      _dialogBleShown = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            title  : const Row(children: [
              Icon(Icons.bluetooth_disabled, color: AppColors.amber),
              SizedBox(width: 8),
              Text('Bluetooth désactivé'),
            ]),
            content: const Text(
              'Le Bluetooth a été désactivé. '
                  'Réactivez-le pour continuer la surveillance médicale.',
            ),
            actions: [
              TextButton(
                onPressed : () {
                  Navigator.pop(ctx);
                  _dialogBleShown = false;
                },
                child: const Text('Ignorer'),
              ),
              FilledButton(
                onPressed : () async {
                  Navigator.pop(ctx);
                  _dialogBleShown = false;
                  await context.read<BleProvider>()
                      .demanderActivationBluetooth();
                },
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.blue,
                ),
                child: const Text('Réactiver'),
              ),
            ],
          ),
        ).then((_) => _dialogBleShown = false);
      });
    }

    // Réinitialiser le flag quand BLE est réactivé
    if (ble.btActif && _dialogBleShown) {
      _dialogBleShown = false;
    }

    return Scaffold(
      backgroundColor    : bgColor,
      // Supprimer le drawer automatique Material 3
      drawerEnableOpenDragGesture: false,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh : () => context.read<AlertesProvider>().charger(),
          color     : AppColors.blue,
          child     : CustomScrollView(
            slivers: [

              SliverAppBar(
                floating             : true,
                backgroundColor      : bgColor,
                automaticallyImplyLeading: false,
                title                : Column(
                  crossAxisAlignment : CrossAxisAlignment.start,
                  children           : [
                    Text('Bonjour,',
                        style: TextStyle(fontSize: 12, color: mutedColor)),
                    Text(
                      auth.nomAffichage,
                      style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.w500,
                        color: textColor,
                      ),
                    ),
                  ],
                ),
                actions: [
                  IconButton(
                    icon    : Icon(
                      dark
                          ? Icons.light_mode_outlined
                          : Icons.dark_mode_outlined,
                      color: mutedColor,
                    ),
                    onPressed: () => context.read<ThemeProvider>().basculer(),
                  ),
                  Stack(
                    children: [
                      IconButton(
                        icon      : Icon(Icons.notifications_outlined,
                            color: mutedColor),
                        onPressed : () => _afficherNotifications(context, mesAlertes),
                      ),
                      if (mesAlertes.isNotEmpty)
                        Positioned(
                          top: 8, right: 8,
                          child: Container(
                            width : 8, height: 8,
                            decoration: const BoxDecoration(
                              color: AppColors.red, shape: BoxShape.circle,
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              ),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([

                    _VitalsCard(
                      src         : src,
                      cardColor   : cardColor,
                      borderColor : borderColor,
                      textColor   : textColor,
                      mutedColor  : mutedColor,
                    ),

                    const SizedBox(height: 12),

                    GestureDetector(
                      onTap: () => context.go('/ble'),
                      child: _BleStatusCard(
                        src         : src,
                        cardColor   : cardColor,
                        borderColor : borderColor,
                        textColor   : textColor,
                        mutedColor  : mutedColor,
                      ),
                    ),

                    const SizedBox(height: 16),

                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Alertes récentes',
                            style: TextStyle(
                              fontSize: 15, fontWeight: FontWeight.w500,
                              color: textColor,
                            )),
                        TextButton(
                          onPressed : () => context.go('/alertes'),
                          child     : const Text('Voir tout',
                              style: TextStyle(
                                fontSize: 13, color: AppColors.blue,
                              )),
                        ),
                      ],
                    ),

                    const SizedBox(height: 4),

                    if (alertesProv.loading && mesAlertes.isEmpty)
                      _SkeletonDashAlertes(
                        cardColor  : cardColor,
                        borderColor: borderColor,
                      )
                    else if (mesAlertes.isEmpty)
                      _EmptyAlertes(
                        cardColor   : cardColor,
                        borderColor : borderColor,
                        mutedColor  : mutedColor,
                      )
                    else
                      ...mesAlertes.take(3).map((a) => _AlerteItem(
                        alerte      : a,
                        cardColor   : cardColor,
                        borderColor : borderColor,
                        textColor   : textColor,
                        mutedColor  : mutedColor,
                      )),

                    const SizedBox(height: 24),
                  ]),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Carte vitales dynamique ───────────────────────────────
class _VitalsCard extends StatelessWidget {
  final SourceDonneesSanteProvider src;
  final Color cardColor, borderColor, textColor, mutedColor;
  const _VitalsCard({
    required this.src,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  String _fmt(double v) {
    if (v == v.roundToDouble() || v.abs() >= 100) return v.round().toString();
    return v.toStringAsFixed(1);
  }

  // Rangées sémantiques — même logique que _CarteMedicale sur la page capteurs
  List<Widget> _rangees(DonneesSante d) {
    final result = <Widget>[];

    _VitalItem? mk(String label, double? value, String unit, Color color,
        [String Function(double)? statusFn]) {
      if (value == null || value == 0.0) return null;
      return _VitalItem(
        label: label, value: _fmt(value), unit: unit, color: color,
        status: statusFn?.call(value) ?? '',
        textColor: textColor, mutedColor: mutedColor,
      );
    }

    void ligne(List<_VitalItem?> candidats) {
      final visible = candidats.whereType<_VitalItem>().toList();
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

    // FC + SpO₂
    ligne([
      mk('Fréq. cardiaque', d.fc,   'bpm', AppColors.red,
          (v) => v > 100 ? 'Élevée' : v < 60 ? 'Faible' : 'Normal'),
      mk('SpO₂',            d.spo2, '%',   AppColors.blue,
          (v) => v < 94 ? 'Faible' : 'Normal'),
    ]);

    // FC repos + VFC
    ligne([
      mk('FC repos', d.fcRepos, 'bpm', const Color(0xFFE11D48),
          (v) => v > 100 ? 'Élevée' : v < 50 ? 'Faible' : 'Normal'),
      mk('VFC',      d.vfc,     'ms',  const Color(0xFF0D9488),
          (v) => v > 50 ? 'Excellent' : v < 30 ? 'Faible' : 'Normal'),
    ]);

    // Tension artérielle : sys + dias toujours ensemble
    ligne([
      mk('Systolique',  d.systolique,  'mmHg', const Color(0xFFEF4444),
          (v) => v > 140 ? 'Élevée' : v < 90 ? 'Faible' : 'Normal'),
      mk('Diastolique', d.diastolique, 'mmHg', const Color(0xFF3B82F6),
          (v) => v > 90 ? 'Élevée' : v < 60 ? 'Faible' : 'Normal'),
    ]);

    // Resp. + Temp. + Glycémie
    ligne([
      mk('Fréq. resp.',  d.freqResp,   '/min', const Color(0xFF0891B2),
          (v) => v > 20 ? 'Élevée' : v < 12 ? 'Faible' : 'Normal'),
      mk('Température',  d.temperature, '°C',  const Color(0xFF7C3AED),
          (v) => v >= 38 ? 'Fièvre' : v < 36 ? 'Faible' : 'Normal'),
      mk('Glycémie',     d.glycemie,   'g/L',  const Color(0xFFD97706),
          (v) => v > 1.1 ? 'Élevée' : v < 0.7 ? 'Faible' : 'Normal'),
    ]);

    // Poids + IMC
    ligne([
      mk('Poids', d.poids, 'kg',    const Color(0xFF6366F1)),
      mk('IMC',   d.imc,   'kg/m²', const Color(0xFF8B5CF6),
          (v) => v >= 30 ? 'Obésité' : v >= 25 ? 'Surpoids' : v < 18.5 ? 'Insuf.' : 'Normal'),
    ]);

    // Composition corporelle : graisse + muscle + eau corporelle
    ligne([
      mk('Graisse corp.', d.graisseCorp, '%',  const Color(0xFFF59E0B)),
      mk('Masse musc.',   d.masseMusc,   'kg', const Color(0xFF10B981)),
      mk('Eau corp.',     d.eauCorp,     'kg', const Color(0xFF0EA5E9)),
    ]);

    // Activité : pas + distance + étages
    ligne([
      mk('Pas du jour', d.pas?.toDouble(), 'pas', AppColors.green,
          (v) => v >= 10000 ? 'Objectif ✓' : 'En cours'),
      (d.distance != null && d.distance! > 0)
          ? _VitalItem(
              label    : 'Distance',
              value    : d.distance! < 1 ? '${(d.distance! * 1000).round()}' : _fmt(d.distance!),
              unit     : d.distance! < 1 ? 'm' : 'km',
              color    : const Color(0xFF0284C7),
              status   : '',
              textColor: textColor, mutedColor: mutedColor,
            )
          : null,
      mk('Étages', d.etages?.toDouble(), 'ét.', const Color(0xFF64748B)),
    ]);

    // Énergie : calories totales + actives + basales
    ligne([
      mk('Calories',     d.calories?.toDouble(),        'kcal', AppColors.amber),
      mk('Cal. actives', d.caloriesActives?.toDouble(), 'kcal', const Color(0xFFEA580C)),
      mk('Cal. base',    d.caloriesBasales?.toDouble(), 'kcal', const Color(0xFF78716C)),
    ]);

    // Hydratation
    ligne([
      mk('Hydrat.', d.eau, 'L', const Color(0xFF38BDF8),
          (v) => v < 1.5 ? 'Faible' : v >= 2.5 ? 'Optimal' : 'Correct'),
    ]);

    // Sommeil total
    ligne([
      mk('Sommeil', d.sommeil, 'h', const Color(0xFF4F46E5),
          (v) => v < 6 ? 'Insuffisant' : v > 9 ? 'Long' : 'Normal'),
    ]);

    // Stades du sommeil
    ligne([
      mk('Profond', d.sommeilProfond, 'h', const Color(0xFF312E81)),
      mk('REM',     d.sommeilREM,     'h', const Color(0xFF6D28D9)),
      mk('Léger',   d.sommeilLeger,   'h', const Color(0xFF7C3AED)),
    ]);

    return result;
  }

  @override
  Widget build(BuildContext context) {
    final d      = src.donnees;
    final source = src.sourceActive;

    final badgeCouleur = source == SourceActive.aucune  ? AppColors.amber
        : source == SourceActive.healthConnect ? AppColors.blue : AppColors.green;
    final badgeLabel = switch (source) {
      SourceActive.aucune       => 'Aucune source',
      SourceActive.simulation   => 'Simulation',
      SourceActive.healthConnect=> 'Health Connect',
      SourceActive.ble          => 'En direct',
    };

    final rangees = _rangees(d);

    return Container(
      padding    : const EdgeInsets.all(16),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(20),
        border       : Border.all(color: borderColor, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── En-tête ──
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Données vitales', style: TextStyle(
                fontSize: 13, fontWeight: FontWeight.w500, color: mutedColor)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color       : badgeCouleur.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(99),
                  border      : Border.all(color: badgeCouleur.withValues(alpha: 0.4)),
                ),
                child: Row(children: [
                  Container(width: 6, height: 6,
                    decoration: BoxDecoration(color: badgeCouleur, shape: BoxShape.circle)),
                  const SizedBox(width: 5),
                  Text(badgeLabel, style: TextStyle(
                    fontSize: 10, color: badgeCouleur, fontWeight: FontWeight.w500)),
                ]),
              ),
            ],
          ),

          const SizedBox(height: 14),

          // ── Contenu ──
          if (source == SourceActive.aucune) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color       : AppColors.amber.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
                border      : Border.all(color: AppColors.amber.withValues(alpha: 0.25), width: 0.5),
              ),
              child: Row(children: [
                const Icon(Icons.sensors_off_outlined, color: AppColors.amber, size: 16),
                const SizedBox(width: 8),
                Expanded(child: Text(
                  'Connectez un capteur BLE ou activez Health Connect pour voir vos données réelles.',
                  style: const TextStyle(fontSize: 11, color: AppColors.amber))),
              ]),
            ),
          ] else if (rangees.isEmpty) ...[
            Text('En attente de données…', style: TextStyle(fontSize: 12, color: mutedColor)),
          ] else ...[
            ...rangees,
          ],
        ],
      ),
    );
  }
}

class _VitalItem extends StatelessWidget {
  final String label, value, unit, status;
  final Color  color, textColor, mutedColor;
  const _VitalItem({
    required this.label, required this.value,
    required this.unit,  required this.color,
    required this.status,
    required this.textColor, required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding    : const EdgeInsets.all(12),
      decoration : BoxDecoration(
        color        : dark ? AppColors.darkBg : AppColors.lightBg,
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(
          color: dark ? AppColors.darkBorder : AppColors.lightBorder,
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 6, height: 6,
                decoration: BoxDecoration(
                  color: color,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 5),
              Expanded(
                child: Text(label,
                    style  : TextStyle(fontSize: 10, color: mutedColor),
                    overflow: TextOverflow.ellipsis),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              fontSize   : value.length > 5 ? 16 : 22,
              fontWeight : FontWeight.w500,
              color      : textColor,
            ),
          ),
          Text(status.isEmpty ? unit : '$unit · $status',
              style: TextStyle(fontSize: 10, color: mutedColor)),
        ],
      ),
    );
  }
}

class _BleStatusCard extends StatelessWidget {
  final SourceDonneesSanteProvider src;
  final Color cardColor, borderColor, textColor, mutedColor;
  const _BleStatusCard({
    required this.src,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    final ble      = src.ble;
    final hc       = src.hc;
    final source   = src.sourceActive;
    final bleActif = source == SourceActive.ble || source == SourceActive.simulation;
    final hcActif  = source == SourceActive.healthConnect;
    final actif    = bleActif || hcActif;
    final couleur  = actif ? AppColors.green : AppColors.blue;

    // Titre + sous-titre selon la source
    final String titre;
    final String sousTitre;
    final IconData icone;
    if (hcActif) {
      titre    = 'Health Connect';
      sousTitre= 'Données synchronisées automatiquement';
      icone    = Icons.favorite_outline;
    } else if (ble.simulation) {
      titre    = 'Simulation active';
      sousTitre= 'Capteur simulé STOP-MNT';
      icone    = Icons.bluetooth_connected;
    } else if (bleActif) {
      titre    = ble.dispositif?.platformName ?? 'Capteur connecté';
      sousTitre= 'Données reçues en direct';
      icone    = Icons.bluetooth_connected;
    } else {
      titre    = 'Aucun capteur connecté';
      sousTitre= 'Appuyez pour connecter un capteur';
      icone    = Icons.bluetooth;
    }

    // Texte de l'indicateur de synchronisation
    final String? syncTexte;
    final int?    syncCount;
    if (bleActif) {
      syncCount = ble.nbEnvoyes;
      syncTexte = syncCount == 0
          ? 'En attente du premier envoi…'
          : '$syncCount mesure${syncCount > 1 ? 's' : ''} '
            'envoyée${syncCount > 1 ? 's' : ''} vers le serveur';
    } else if (hcActif) {
      syncCount = hc.nbMetriquesEnvoyes;
      syncTexte = syncCount == 0
          ? 'En attente du premier envoi…'
          : '$syncCount donnée${syncCount > 1 ? 's' : ''} envoyée${syncCount > 1 ? 's' : ''} vers le serveur';
    } else {
      syncCount = null;
      syncTexte = null;
    }

    return Container(
      padding    : const EdgeInsets.all(14),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(16),
        border       : Border.all(
          color: actif
              ? AppColors.green.withValues(alpha: 0.3)
              : borderColor,
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Ligne principale ──────────────────────────────
          Row(
            children: [
              Container(
                width: 42, height: 42,
                decoration: BoxDecoration(
                  color        : couleur.withValues(alpha: 0.12),
                  borderRadius : BorderRadius.circular(12),
                ),
                child: Icon(icone, color: couleur, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      titre,
                      style: TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w500,
                        color: textColor,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(sousTitre, style: TextStyle(fontSize: 11, color: mutedColor)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: couleur, size: 18),
            ],
          ),

          // ── Indicateur de synchronisation ─────────────────
          if (syncTexte != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color        : AppColors.green.withValues(alpha: 0.07),
                borderRadius : BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  Icon(
                    hcActif
                        ? Icons.sync_outlined
                        : Icons.cloud_upload_outlined,
                    color: AppColors.green, size: 14,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      syncTexte,
                      style: TextStyle(
                        fontSize   : 11,
                        fontWeight : FontWeight.w500,
                        color      : (syncCount ?? 0) == 0 ? mutedColor : AppColors.green,
                      ),
                    ),
                  ),
                  if ((syncCount ?? 0) > 0)
                    Container(
                      width: 6, height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.green, shape: BoxShape.circle,
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

class _AlerteItem extends StatelessWidget {
  final Alerte alerte;
  final Color  cardColor, borderColor, textColor, mutedColor;
  const _AlerteItem({
    required this.alerte,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    final isCritique = alerte.estCritique;
    final iconColor  = isCritique ? AppColors.red : AppColors.amber;
    final bgColor    = isCritique
        ? AppColors.red.withValues(alpha: 0.08)
        : AppColors.amber.withValues(alpha: 0.08);
    return Container(
      margin     : const EdgeInsets.only(bottom: 8),
      padding    : const EdgeInsets.all(12),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(
          color : isCritique
              ? AppColors.red.withValues(alpha: 0.3)
              : borderColor,
          width : 0.5,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 34, height: 34,
            decoration: BoxDecoration(
              color: bgColor, borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(
              isCritique
                  ? Icons.warning_amber_outlined
                  : Icons.info_outline,
              color: iconColor, size: 17,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(alerte.message,
                    style: TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w500,
                      color: textColor,
                    ),
                    maxLines : 1,
                    overflow : TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Text(
                  '${alerte.capteur} · '
                      '${alerte.timestamp.toLocal().toString().substring(11, 16)}',
                  style: TextStyle(fontSize: 10, color: mutedColor),
                ),
              ],
            ),
          ),
          Container(
            padding    : const EdgeInsets.symmetric(
              horizontal: 8, vertical: 3,
            ),
            decoration : BoxDecoration(
              color        : bgColor,
              borderRadius : BorderRadius.circular(99),
            ),
            child: Text(alerte.niveau,
                style: TextStyle(
                  fontSize: 9, fontWeight: FontWeight.w500,
                  color: iconColor,
                )),
          ),
        ],
      ),
    );
  }
}

class _EmptyAlertes extends StatelessWidget {
  final Color cardColor, borderColor, mutedColor;
  const _EmptyAlertes({
    required this.cardColor, required this.borderColor,
    required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding    : const EdgeInsets.symmetric(vertical: 28),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(16),
        border       : Border.all(color: borderColor, width: 0.5),
      ),
      child: Column(
        children: [
          Icon(Icons.notifications_off_outlined, color: mutedColor, size: 28),
          const SizedBox(height: 8),
          Text('Aucune alerte active',
              style: TextStyle(fontSize: 13, color: mutedColor)),
        ],
      ),
    );
  }
}

// ── Skeleton alertes dashboard ────────────────────────────
// Reproduit exactement la structure de _AlerteItem, données remplacées par
// des ShimmerBlock — la lumière défile sur l'ensemble via un seul Shimmer

class _SkeletonDashAlertes extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonDashAlertes({
    required this.cardColor, required this.borderColor,
  });

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: Column(
        children: [
          _SkeletonAlertItem(cardColor: cardColor, borderColor: borderColor),
          _SkeletonAlertItem(cardColor: cardColor, borderColor: borderColor),
          _SkeletonAlertItem(cardColor: cardColor, borderColor: borderColor),
        ],
      ),
    );
  }
}

class _SkeletonAlertItem extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonAlertItem({required this.cardColor, required this.borderColor});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin     : const EdgeInsets.only(bottom: 8),
      padding    : const EdgeInsets.all(12),
      decoration : BoxDecoration(
        color        : cardColor,
        borderRadius : BorderRadius.circular(14),
        border       : Border.all(color: borderColor, width: 0.5),
      ),
      child: Row(
        children: [
          ShimmerBlock(width: 34, height: 34, radius: 10),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ShimmerBlock(height: 12),
                const SizedBox(height: 5),
                ShimmerBlock(width: 110, height: 9, radius: 5),
              ],
            ),
          ),
          const SizedBox(width: 8),
          ShimmerBlock(width: 44, height: 18, radius: 99),
        ],
      ),
    );
  }
}