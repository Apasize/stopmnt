// lib/features/alertes/alertes_screen.dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/alertes_provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/models/alerte.dart';
import '../../core/widgets/skeleton.dart';

enum _PeriodeAlerte { tout, aujourdhui, semaine, mois, date }

class AlertesScreen extends StatefulWidget {
  const AlertesScreen({super.key});

  @override
  State<AlertesScreen> createState() => _AlertesScreenState();
}

class _AlertesScreenState extends State<AlertesScreen> {
  static const _pageSize = 10;
  _PeriodeAlerte _periode     = _PeriodeAlerte.tout;
  DateTime?      _dateChoisie;
  String?        _niveau;   // null = tout, 'critique', 'alerte'
  int            _visible   = _pageSize;

  bool get _filtrActif =>
      _periode != _PeriodeAlerte.tout || _niveau != null;

  List<Alerte> _filtrer(List<Alerte> toutes) {
    var list = toutes;
    final now = DateTime.now();
    switch (_periode) {
      case _PeriodeAlerte.aujourdhui:
        list = list.where((a) {
          final d = a.timestamp.toLocal();
          return d.year == now.year && d.month == now.month && d.day == now.day;
        }).toList();
      case _PeriodeAlerte.semaine:
        final cutoff = now.subtract(const Duration(days: 7));
        list = list.where((a) => a.timestamp.isAfter(cutoff)).toList();
      case _PeriodeAlerte.mois:
        list = list.where((a) {
          final d = a.timestamp.toLocal();
          return d.year == now.year && d.month == now.month;
        }).toList();
      case _PeriodeAlerte.date:
        if (_dateChoisie != null) {
          list = list.where((a) {
            final d = a.timestamp.toLocal();
            return d.year == _dateChoisie!.year &&
                   d.month == _dateChoisie!.month &&
                   d.day   == _dateChoisie!.day;
          }).toList();
        }
      case _PeriodeAlerte.tout:
        break;
    }
    if (_niveau == 'critique') list = list.where((a) =>  a.estCritique).toList();
    if (_niveau == 'alerte')   list = list.where((a) => !a.estCritique).toList();
    return list;
  }

  void _ouvrirFiltres(BuildContext context, Color borderColor, Color textColor, Color mutedColor) {
    _PeriodeAlerte periodeTemp = _periode;
    DateTime?      dateTemp    = _dateChoisie;
    String?        niveauTemp  = _niveau;

    showModalBottomSheet(
      context           : context,
      isScrollControlled: true,
      backgroundColor   : Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModal) {
          final dark    = Theme.of(ctx).brightness == Brightness.dark;
          final sheetBg = dark ? AppColors.darkSurface : Colors.white;

          Widget periodeBtn(_PeriodeAlerte p, String lbl, IconData ic) {
            final sel = periodeTemp == p;
            return GestureDetector(
              onTap: () async {
                if (p == _PeriodeAlerte.date) {
                  final picked = await showDatePicker(
                    context  : ctx,
                    initialDate: dateTemp ?? DateTime.now(),
                    firstDate: DateTime(2020),
                    lastDate : DateTime.now(),
                  );
                  if (picked != null) setModal(() { periodeTemp = p; dateTemp = picked; });
                } else {
                  setModal(() { periodeTemp = p; dateTemp = null; });
                }
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 140),
                padding : const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                decoration: BoxDecoration(
                  color       : sel ? AppColors.blue.withValues(alpha: 0.1) : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  border      : Border.all(
                    color: sel ? AppColors.blue : borderColor, width: sel ? 1.5 : 0.6,
                  ),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(ic, size: 15, color: sel ? AppColors.blue : mutedColor),
                  const SizedBox(width: 7),
                  Text(
                    p == _PeriodeAlerte.date && dateTemp != null
                        ? '${dateTemp!.day.toString().padLeft(2,'0')}/${dateTemp!.month.toString().padLeft(2,'0')}/${dateTemp!.year}'
                        : lbl,
                    style: TextStyle(
                      fontSize  : 12,
                      fontWeight: sel ? FontWeight.w600 : FontWeight.normal,
                      color     : sel ? AppColors.blue : mutedColor,
                    ),
                  ),
                ]),
              ),
            );
          }

          Widget chip(String label, String? val, String? current, Color color, void Function(String?) onTap) {
            final sel = current == val;
            return GestureDetector(
              onTap: () => onTap(sel ? null : val),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 140),
                padding : const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: BoxDecoration(
                  color       : sel ? color.withValues(alpha: 0.1) : Colors.transparent,
                  borderRadius: BorderRadius.circular(99),
                  border      : Border.all(color: sel ? color : borderColor, width: sel ? 1.5 : 0.6),
                ),
                child: Text(label, style: TextStyle(
                  fontSize  : 12,
                  fontWeight: sel ? FontWeight.w600 : FontWeight.normal,
                  color     : sel ? color : mutedColor,
                )),
              ),
            );
          }

          return Container(
            decoration: BoxDecoration(
              color       : sheetBg,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
            ),
            padding: EdgeInsets.fromLTRB(
                20, 16, 20, MediaQuery.of(ctx).viewInsets.bottom + 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(child: Container(
                  width: 36, height: 4,
                  decoration: BoxDecoration(
                    color: borderColor, borderRadius: BorderRadius.circular(99),
                  ),
                )),
                const SizedBox(height: 18),
                Row(children: [
                  Text('Filtres', style: TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700, color: textColor,
                  )),
                  const Spacer(),
                  GestureDetector(
                    onTap: () {
                      setState(() {
                        _periode = _PeriodeAlerte.tout; _dateChoisie = null;
                        _niveau  = null; _visible = _pageSize;
                      });
                      Navigator.pop(ctx);
                    },
                    child: const Text('Réinitialiser',
                        style: TextStyle(fontSize: 12, color: AppColors.blue)),
                  ),
                ]),
                const SizedBox(height: 20),

                Text('Période', style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w600, color: mutedColor)),
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  periodeBtn(_PeriodeAlerte.tout,       'Tout',          Icons.all_inclusive_rounded),
                  periodeBtn(_PeriodeAlerte.aujourdhui,  "Aujourd'hui",   Icons.today_outlined),
                  periodeBtn(_PeriodeAlerte.semaine,     '7 derniers j',  Icons.date_range_outlined),
                  periodeBtn(_PeriodeAlerte.mois,        'Ce mois',       Icons.calendar_month_outlined),
                  periodeBtn(_PeriodeAlerte.date,        'Date précise',  Icons.event_outlined),
                ]),
                const SizedBox(height: 22),

                Text('Niveau', style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w600, color: mutedColor)),
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  chip('Tout',     null,        niveauTemp, AppColors.blue,  (v) => setModal(() => niveauTemp = v)),
                  chip('Critique', 'critique',  niveauTemp, AppColors.red,   (v) => setModal(() => niveauTemp = v)),
                  chip('Alerte',   'alerte',    niveauTemp, AppColors.amber, (v) => setModal(() => niveauTemp = v)),
                ]),
                const SizedBox(height: 22),

                const SizedBox(height: 24),

                SizedBox(
                  width: double.infinity, height: 48,
                  child: FilledButton(
                    onPressed: () {
                      setState(() {
                        _periode     = periodeTemp;
                        _dateChoisie = dateTemp;
                        _niveau      = niveauTemp;
                        _visible     = _pageSize;
                      });
                      Navigator.pop(ctx);
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.blue,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text('Appliquer',
                        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  void _afficherDetail(BuildContext context, Alerte alerte) {
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkSurface  : AppColors.lightSurface;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final borderColor = dark ? AppColors.darkBorder    : AppColors.lightBorder;
    final critique    = alerte.estCritique;
    final color       = critique ? AppColors.red : AppColors.amber;

    showModalBottomSheet(
      context            : context,
      backgroundColor    : bgColor,
      isScrollControlled : true,
      shape              : const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            // Poignée
            Center(
              child: Container(
                width: 36, height: 4,
                decoration: BoxDecoration(
                  color        : mutedColor.withValues(alpha: 0.3),
                  borderRadius : BorderRadius.circular(2),
                ),
              ),
            ),

            const SizedBox(height: 20),

            // En-tête
            Row(
              children: [
                Container(
                  width: 44, height: 44,
                  decoration: BoxDecoration(
                    color        : color.withValues(alpha: 0.1),
                    borderRadius : BorderRadius.circular(12),
                  ),
                  child: Icon(
                    critique
                        ? Icons.warning_amber_outlined
                        : Icons.info_outline,
                    color: color, size: 22,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        padding    : const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3,
                        ),
                        decoration : BoxDecoration(
                          color        : color.withValues(alpha: 0.1),
                          borderRadius : BorderRadius.circular(99),
                        ),
                        child: Text(
                          critique ? 'CRITIQUE' : 'ALERTE',
                          style: TextStyle(
                            fontSize     : 10,
                            fontWeight   : FontWeight.w600,
                            color        : color,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        alerte.message,
                        style: TextStyle(
                          fontSize  : 15,
                          fontWeight: FontWeight.w500,
                          color     : textColor,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Détails
            Container(
              padding    : const EdgeInsets.all(14),
              decoration : BoxDecoration(
                color        : dark ? AppColors.darkBg : AppColors.lightBg,
                borderRadius : BorderRadius.circular(14),
                border       : Border.all(color: borderColor, width: 0.5),
              ),
              child: Column(
                children: [
                  _DetailLigne(
                    label     : 'Capteur',
                    valeur    : alerte.capteur,
                    textColor : textColor,
                    mutedColor: mutedColor,
                  ),
                  Divider(color: borderColor, height: 20, thickness: 0.5),
                  _DetailLigne(
                    label     : 'Date',
                    valeur    : _formaterDateComplete(alerte.timestamp),
                    textColor : textColor,
                    mutedColor: mutedColor,
                  ),
                  Divider(color: borderColor, height: 20, thickness: 0.5),
                  _DetailLigne(
                    label     : 'Niveau',
                    valeur    : alerte.niveau,
                    textColor : textColor,
                    mutedColor: mutedColor,
                    couleurValeur: color,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Description contextuelle
            Container(
              padding    : const EdgeInsets.all(14),
              decoration : BoxDecoration(
                color        : color.withValues(alpha: 0.06),
                borderRadius : BorderRadius.circular(14),
                border       : Border.all(
                  color: color.withValues(alpha: 0.2), width: 0.5,
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.lightbulb_outline, color: color, size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _descriptionAlerte(alerte),
                      style: TextStyle(
                        fontSize: 12,
                        color   : color,
                        height  : 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formaterDateComplete(DateTime dt) {
    final local = dt.toLocal();
    const mois = [
      '', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
      'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
    ];
    return '${local.day} ${mois[local.month]} ${local.year} '
        'à ${local.hour.toString().padLeft(2,'0')}:'
        '${local.minute.toString().padLeft(2,'0')}';
  }

  String _descriptionAlerte(Alerte alerte) {
    final msg = alerte.message.toLowerCase();
    if (msg.contains('glycémie') || msg.contains('glycemie')) {
      if (alerte.estCritique) {
        return 'Votre glycémie est dangereusement élevée. '
            'Contactez immédiatement votre médecin ou rendez-vous '
            'aux urgences si vous ressentez des symptômes.';
      }
      return 'Votre glycémie est au-dessus des valeurs normales. '
          'Évitez les sucres rapides et consultez votre médecin.';
    }
    if (msg.contains('tension') || msg.contains('hta')) {
      if (alerte.estCritique) {
        return 'Votre tension artérielle est à un niveau critique. '
            'Reposez-vous immédiatement et contactez votre médecin '
            'sans délai.';
      }
      return 'Votre tension artérielle est élevée. '
          'Reposez-vous, évitez le sel et le stress. '
          'Consultez votre médecin si cela persiste.';
    }
    if (msg.contains('fc') || msg.contains('cardiaque') || msg.contains('pouls')) {
      return 'Votre fréquence cardiaque sort des valeurs normales. '
          'Reposez-vous et consultez votre médecin si la situation persiste.';
    }
    if (msg.contains('spo2') || msg.contains('oxygène')) {
      return 'Votre saturation en oxygène est basse. '
          'Respirez profondément et contactez un médecin si '
          'la valeur reste inférieure à 94%.';
    }
    return 'Une anomalie a été détectée sur vos données de santé. '
        'Consultez votre médecin pour plus d\'informations.';
  }

  @override
  Widget build(BuildContext context) {
    final alertesProv = context.watch<AlertesProvider>();
    final toutes      = alertesProv.alertes;
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkBg       : AppColors.lightBg;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final cardColor   = dark ? AppColors.darkSurface   : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder    : AppColors.lightBorder;

    final alertes    = _filtrer(toutes);
    final shown      = alertes.take(_visible).toList();
    final hasMore    = _visible < alertes.length;
    final nbCritiques = toutes.where((a) =>  a.estCritique).length;
    final nbAlertes   = toutes.where((a) => !a.estCritique).length;

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        title                    : const Text('Mes alertes'),
        backgroundColor          : bgColor,
        automaticallyImplyLeading: false,
        actions: [
          Stack(clipBehavior: Clip.none, children: [
            IconButton(
              onPressed: () => _ouvrirFiltres(context, borderColor, textColor, mutedColor),
              icon: Icon(Icons.tune_rounded,
                  color: _filtrActif ? AppColors.blue : mutedColor),
              tooltip: 'Filtrer',
            ),
            if (_filtrActif) Positioned(
              top: 8, right: 8,
              child: Container(
                width: 8, height: 8,
                decoration: const BoxDecoration(
                    color: AppColors.blue, shape: BoxShape.circle),
              ),
            ),
          ]),
          const SizedBox(width: 4),
        ],
      ),
      body: (alertesProv.loading && alertes.isEmpty)
          ? _SkeletonAlertes(cardColor: cardColor, borderColor: borderColor)
          : RefreshIndicator(
              onRefresh: () => context.read<AlertesProvider>().charger(),
              color    : AppColors.blue,
              child    : CustomScrollView(
                slivers: [
                  // ── Résumé ──
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 20, 16, 12),
                    sliver: SliverToBoxAdapter(
                      child: Row(children: [
                        Expanded(child: _ResumeBadge(
                          label: 'Critiques', count: nbCritiques,
                          color: AppColors.red,   icon: Icons.warning_amber_outlined,
                          actif: false, onTap: () {},
                        )),
                        const SizedBox(width: 10),
                        Expanded(child: _ResumeBadge(
                          label: 'Alertes', count: nbAlertes,
                          color: AppColors.amber, icon: Icons.info_outline,
                          actif: false, onTap: () {},
                        )),
                        const SizedBox(width: 10),
                        Expanded(child: _ResumeBadge(
                          label: 'Total', count: toutes.length,
                          color: AppColors.blue,  icon: Icons.notifications_outlined,
                          actif: false, onTap: () {},
                        )),
                      ]),
                    ),
                  ),

                  // ── Liste ──
                  alertes.isEmpty
                      ? SliverFillRemaining(
                          child: Center(child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.notifications_off_outlined,
                                  color: mutedColor, size: 48),
                              const SizedBox(height: 12),
                              Text(
                                _filtrActif ? 'Aucune alerte pour ce filtre' : 'Aucune alerte',
                                style: TextStyle(fontSize: 15, color: mutedColor),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                _filtrActif
                                    ? 'Modifiez ou réinitialisez le filtre'
                                    : 'Vos données sont dans les valeurs normales',
                                style: TextStyle(fontSize: 12, color: mutedColor),
                              ),
                            ],
                          )),
                        )
                      : SliverPadding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          sliver: SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (_, i) {
                                if (i == shown.length) {
                                  return Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 8),
                                    child: TextButton(
                                      onPressed: () => setState(() => _visible += _pageSize),
                                      child: Text(
                                        'Voir plus · ${alertes.length - _visible} restantes',
                                        style: const TextStyle(fontSize: 13, color: AppColors.blue),
                                      ),
                                    ),
                                  );
                                }
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: _AlerteCard(
                                    alerte     : shown[i],
                                    cardColor  : cardColor,
                                    borderColor: borderColor,
                                    textColor  : textColor,
                                    mutedColor : mutedColor,
                                    onTap      : () => _afficherDetail(context, shown[i]),
                                  ),
                                );
                              },
                              childCount: shown.length + (hasMore ? 1 : 0),
                            ),
                          ),
                        ),

                  const SliverPadding(padding: EdgeInsets.only(bottom: 24)),
                ],
              ),
            ),
    );
  }
}

// ── Skeleton page alertes ─────────────────────────────────
class _SkeletonAlertes extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonAlertes({required this.cardColor, required this.borderColor});

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            // ── Badges résumé ──
            Row(
              children: List.generate(3, (i) => Expanded(
                child: Container(
                  margin    : EdgeInsets.only(right: i < 2 ? 10 : 0),
                  padding   : const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color       : cardColor,
                    borderRadius: BorderRadius.circular(12),
                    border      : Border.all(color: borderColor, width: 0.5),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        ShimmerBlock(width: 14, height: 14, radius: 4),
                        const Spacer(),
                        ShimmerBlock(width: 28, height: 22, radius: 6),
                      ]),
                      const SizedBox(height: 5),
                      ShimmerBlock(width: 48, height: 10, radius: 5),
                    ],
                  ),
                ),
              )),
            ),

            const SizedBox(height: 16),

            // ── Cartes alertes ──
            ...List.generate(4, (_) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child  : _SkeletonAlerteCard(
                cardColor  : cardColor,
                borderColor: borderColor,
              ),
            )),
          ],
        ),
      ),
    );
  }
}

class _SkeletonAlerteCard extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonAlerteCard({required this.cardColor, required this.borderColor});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding   : const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color       : cardColor,
        borderRadius: BorderRadius.circular(16),
        border      : Border.all(color: borderColor, width: 0.5),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShimmerBlock(width: 38, height: 38, radius: 10),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(children: [
                  ShimmerBlock(width: 52, height: 18, radius: 99),
                  const Spacer(),
                  ShimmerBlock(width: 55, height: 10, radius: 4),
                ]),
                const SizedBox(height: 8),
                ShimmerBlock(height: 13),
                const SizedBox(height: 6),
                ShimmerBlock(width: 120, height: 10, radius: 4),
              ],
            ),
          ),
          const SizedBox(width: 6),
          ShimmerBlock(width: 16, height: 16, radius: 2),
        ],
      ),
    );
  }
}

// ── Badge résumé compact ──────────────────────────────────
class _ResumeBadge extends StatelessWidget {
  final String        label;
  final int           count;
  final Color         color;
  final IconData      icon;
  final bool          actif;
  final VoidCallback  onTap;
  const _ResumeBadge({
    required this.label,  required this.count,
    required this.color,  required this.icon,
    required this.actif,  required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration   : const Duration(milliseconds: 180),
        padding    : const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration : BoxDecoration(
          color        : actif ? color.withValues(alpha: 0.18) : color.withValues(alpha: 0.08),
          borderRadius : BorderRadius.circular(12),
          border       : Border.all(
            color: actif ? color : color.withValues(alpha: 0.2),
            width: actif ? 1.5 : 0.5,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 14),
                const Spacer(),
                Text(
                  '$count',
                  style: TextStyle(
                    fontSize  : 22,
                    fontWeight: FontWeight.w600,
                    color     : color,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize  : 11,
                    color     : color,
                    fontWeight: actif ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                if (actif) ...[
                  const Spacer(),
                  Icon(Icons.check_circle, color: color, size: 11),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── Carte alerte avec tap pour détail ─────────────────────
class _AlerteCard extends StatelessWidget {
  final Alerte       alerte;
  final Color        cardColor, borderColor, textColor, mutedColor;
  final VoidCallback onTap;
  const _AlerteCard({
    required this.alerte,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final critique = alerte.estCritique;
    final color    = critique ? AppColors.red : AppColors.amber;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding    : const EdgeInsets.all(14),
        decoration : BoxDecoration(
          color        : cardColor,
          borderRadius : BorderRadius.circular(16),
          border       : Border.all(
            color : critique
                ? AppColors.red.withValues(alpha: 0.3)
                : borderColor,
            width : 0.5,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            // Icône
            Container(
              width: 38, height: 38,
              decoration: BoxDecoration(
                color        : color.withValues(alpha: 0.1),
                borderRadius : BorderRadius.circular(10),
              ),
              child: Icon(
                critique
                    ? Icons.warning_amber_outlined
                    : Icons.info_outline,
                color: color, size: 18,
              ),
            ),

            const SizedBox(width: 12),

            // Contenu
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding    : const EdgeInsets.symmetric(
                          horizontal: 7, vertical: 2,
                        ),
                        decoration : BoxDecoration(
                          color        : color.withValues(alpha: 0.1),
                          borderRadius : BorderRadius.circular(99),
                        ),
                        child: Text(
                          critique ? 'CRITIQUE' : 'ALERTE',
                          style: TextStyle(
                            fontSize     : 9,
                            fontWeight   : FontWeight.w600,
                            color        : color,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        _formaterDate(alerte.timestamp),
                        style: TextStyle(fontSize: 10, color: mutedColor),
                      ),
                    ],
                  ),
                  const SizedBox(height: 5),
                  Text(
                    alerte.message,
                    style: TextStyle(
                      fontSize  : 13,
                      fontWeight: FontWeight.w500,
                      color     : textColor,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Capteur : ${alerte.capteur}',
                    style: TextStyle(fontSize: 11, color: mutedColor),
                  ),
                ],
              ),
            ),

            const SizedBox(width: 6),
            Icon(Icons.chevron_right, color: mutedColor, size: 16),
          ],
        ),
      ),
    );
  }

  String _formaterDate(DateTime dt) {
    final local = dt.toLocal();
    return '${local.day.toString().padLeft(2,'0')}/'
        '${local.month.toString().padLeft(2,'0')} '
        '${local.hour.toString().padLeft(2,'0')}:'
        '${local.minute.toString().padLeft(2,'0')}';
  }
}

// ── Ligne de détail ───────────────────────────────────────
class _DetailLigne extends StatelessWidget {
  final String  label, valeur;
  final Color   textColor, mutedColor;
  final Color?  couleurValeur;
  const _DetailLigne({
    required this.label, required this.valeur,
    required this.textColor, required this.mutedColor,
    this.couleurValeur,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(label,
            style: TextStyle(fontSize: 13, color: mutedColor)),
        const Spacer(),
        Text(
          valeur,
          style: TextStyle(
            fontSize  : 13,
            fontWeight: FontWeight.w500,
            color     : couleurValeur ?? textColor,
          ),
        ),
      ],
    );
  }
}
