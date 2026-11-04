// lib/features/profil/profil_screen.dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers/auth_provider.dart';
import '../../core/providers/ble_provider.dart';
import '../../core/providers/theme_provider.dart';
import '../../core/providers/profil_medical_provider.dart';
import '../../core/theme/app_theme.dart';

class ProfilScreen extends StatelessWidget {
  const ProfilScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth        = context.watch<AuthProvider>();
    final profil      = context.watch<ProfilMedicalProvider>();
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkBg       : AppColors.lightBg;
    final textColor   = dark ? AppColors.darkText      : AppColors.lightText;
    final mutedColor  = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final cardColor   = dark ? AppColors.darkSurface   : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder    : AppColors.lightBorder;

    final initiales = () {
      if (auth.prenom != null && auth.nom != null) {
        return '${auth.prenom![0]}${auth.nom![0]}'.toUpperCase();
      }
      return auth.email?.substring(0, 2).toUpperCase() ?? 'PA';
    }();

    final nomComplet = (auth.prenom != null && auth.nom != null)
        ? '${auth.prenom} ${auth.nom}'
        : auth.email ?? '';

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        title                    : const Text('Mon profil'),
        backgroundColor          : bgColor,
        automaticallyImplyLeading: false,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [

            // ── Avatar ──────────────────────────────────────
            Container(
              width: 88, height: 88,
              decoration: BoxDecoration(
                color : AppColors.blue.withValues(alpha: 0.12),
                shape : BoxShape.circle,
                border: Border.all(
                  color: AppColors.blue.withValues(alpha: 0.2), width: 2,
                ),
              ),
              child: Center(
                child: Text(
                  initiales,
                  style: const TextStyle(
                    fontSize: 30, fontWeight: FontWeight.w500,
                    color   : AppColors.blue,
                  ),
                ),
              ),
            ),

            const SizedBox(height: 14),

            Text(
              nomComplet,
              style: TextStyle(
                fontSize: 18, fontWeight: FontWeight.w500, color: textColor,
              ),
            ),

            const SizedBox(height: 6),

            Text(
              auth.email ?? '',
              style: TextStyle(fontSize: 13, color: mutedColor),
            ),

            const SizedBox(height: 8),

            if (auth.patientId != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                decoration: BoxDecoration(
                  color        : AppColors.blue.withValues(alpha: 0.08),
                  borderRadius : BorderRadius.circular(99),
                  border       : Border.all(color: AppColors.blue.withValues(alpha: 0.2)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.badge_outlined, color: AppColors.blue, size: 14),
                    const SizedBox(width: 5),
                    Text(
                      auth.patientId!,
                      style: const TextStyle(
                        fontSize: 12, color: AppColors.blue, fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),

            const SizedBox(height: 28),

            // ── Informations personnelles ────────────────────
            _Section(
              title   : 'Informations',
              children: [
                _InfoItem(icon: Icons.person_outline,           label: 'Prénom',
                  value: auth.prenom ?? '—',
                  textColor: textColor, mutedColor: mutedColor, cardColor: cardColor, borderColor: borderColor),
                _InfoItem(icon: Icons.person_outline,           label: 'Nom',
                  value: auth.nom ?? '—',
                  textColor: textColor, mutedColor: mutedColor, cardColor: cardColor, borderColor: borderColor),
                _InfoItem(icon: Icons.location_on_outlined,     label: 'Département',
                  value: auth.departement != null
                      ? auth.departement![0].toUpperCase() + auth.departement!.substring(1)
                      : '—',
                  textColor: textColor, mutedColor: mutedColor, cardColor: cardColor, borderColor: borderColor,
                  last: true),
              ],
            ),

            const SizedBox(height: 16),

            // ── Dossier médical ──────────────────────────────
            _DossierMedical(
              profil      : profil,
              textColor   : textColor,
              mutedColor  : mutedColor,
              cardColor   : cardColor,
              borderColor : borderColor,
            ),

            const SizedBox(height: 16),

            // ── Préférences ──────────────────────────────────
            _Section(
              title   : 'Préférences',
              children: [
                _ToggleItem(
                  icon      : dark ? Icons.light_mode_outlined : Icons.dark_mode_outlined,
                  label     : dark ? 'Mode clair' : 'Mode sombre',
                  value     : dark,
                  onChanged : (_) => context.read<ThemeProvider>().basculer(),
                  textColor : textColor, mutedColor: mutedColor,
                  cardColor : cardColor, borderColor: borderColor,
                  last      : true,
                ),
              ],
            ),

            const SizedBox(height: 28),

            // ── Déconnexion ──────────────────────────────────
            SizedBox(
              width: double.infinity, height: 52,
              child: OutlinedButton.icon(
                onPressed: () async {
                  final confirme = await showDialog<bool>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title  : const Text('Déconnexion'),
                      content: const Text('Voulez-vous vraiment vous déconnecter ?'),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(ctx, false),
                          child    : const Text('Annuler'),
                        ),
                        TextButton(
                          onPressed: () => Navigator.pop(ctx, true),
                          style    : TextButton.styleFrom(foregroundColor: AppColors.red),
                          child    : const Text('Déconnecter'),
                        ),
                      ],
                    ),
                  );
                  if (confirme == true && context.mounted) {
                    final ble    = context.read<BleProvider>();
                    final auth2  = context.read<AuthProvider>();
                    final router = GoRouter.of(context);
                    if (ble.simulation) ble.arreterSimulation();
                    if (ble.connecte)   await ble.deconnecter();
                    ble.effacerCapteurs();
                    await auth2.logout();
                    router.go('/login');
                  }
                },
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.red,
                  side           : BorderSide(color: AppColors.red.withValues(alpha: 0.4)),
                  shape          : RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                icon : const Icon(Icons.logout, size: 18),
                label: const Text(
                  'Se déconnecter',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
                ),
              ),
            ),

            const SizedBox(height: 20),

            Text(
              'STOP-MNT v1.0.0 · Bénin 2026',
              style: TextStyle(fontSize: 11, color: mutedColor),
            ),

            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}

// ── Dossier médical (lecture + bouton édition) ────────────
class _DossierMedical extends StatelessWidget {
  final ProfilMedicalProvider profil;
  final Color textColor, mutedColor, cardColor, borderColor;
  const _DossierMedical({
    required this.profil,
    required this.textColor, required this.mutedColor,
    required this.cardColor, required this.borderColor,
  });

  void _ouvrir(BuildContext context) {
    showModalBottomSheet(
      context             : context,
      isScrollControlled  : true,
      backgroundColor     : Colors.transparent,
      builder: (ctx) => _EditDossierSheet(
        profil      : profil,
        cardColor   : cardColor,
        borderColor : borderColor,
        textColor   : textColor,
        mutedColor  : mutedColor,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Row(
            children: [
              Text(
                'Dossier médical',
                style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w500,
                  color: mutedColor, letterSpacing: 0.3,
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => _ouvrir(context),
                child: Container(
                  padding   : const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color       : AppColors.blue.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(99),
                    border      : Border.all(color: AppColors.blue.withValues(alpha: 0.2)),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        profil.aDonnees ? Icons.edit_outlined : Icons.add,
                        color: AppColors.blue, size: 12,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        profil.aDonnees ? 'Modifier' : 'Compléter',
                        style: const TextStyle(
                          fontSize: 11, color: AppColors.blue, fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
        ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: profil.aDonnees
              ? _DossierRempli(
                  profil      : profil,
                  textColor   : textColor,
                  mutedColor  : mutedColor,
                  cardColor   : cardColor,
                  borderColor : borderColor,
                  onEditer    : () => _ouvrir(context),
                )
              : _DossierVide(
                  cardColor   : cardColor,
                  borderColor : borderColor,
                  mutedColor  : mutedColor,
                  onCompleter : () => _ouvrir(context),
                ),
        ),
      ],
    );
  }
}

class _DossierVide extends StatelessWidget {
  final Color   cardColor, borderColor, mutedColor;
  final VoidCallback onCompleter;
  const _DossierVide({
    required this.cardColor, required this.borderColor,
    required this.mutedColor, required this.onCompleter,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onCompleter,
      child: Container(
        width      : double.infinity,
        padding    : const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
        decoration : BoxDecoration(
          color : cardColor,
          border: Border.all(color: borderColor, width: 0.5),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          children: [
            Icon(Icons.medical_services_outlined, color: mutedColor, size: 28),
            const SizedBox(height: 8),
            Text(
              'Dossier médical non renseigné',
              style: TextStyle(fontSize: 13, color: mutedColor),
            ),
            const SizedBox(height: 4),
            Text(
              'Ajoutez groupe sanguin, antécédents, maladies chroniques et traitements.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, color: mutedColor.withValues(alpha: 0.7)),
            ),
          ],
        ),
      ),
    );
  }
}

class _DossierRempli extends StatelessWidget {
  final ProfilMedicalProvider profil;
  final Color      textColor, mutedColor, cardColor, borderColor;
  final VoidCallback onEditer;
  const _DossierRempli({
    required this.profil, required this.textColor,
    required this.mutedColor, required this.cardColor,
    required this.borderColor, required this.onEditer,
  });

  Widget _rangee({
    required IconData icon, required Color iconColor,
    required String label, required List<String> items,
    required bool last,
  }) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Container(
      padding   : const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color : cardColor,
        border: Border(
          left  : BorderSide(color: borderColor, width: 0.5),
          right : BorderSide(color: borderColor, width: 0.5),
          top   : BorderSide(color: borderColor, width: 0.5),
          bottom: last ? BorderSide(color: borderColor, width: 0.5) : BorderSide.none,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: iconColor),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: TextStyle(
                      fontSize: 11, color: mutedColor, fontWeight: FontWeight.w500,
                    )),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 6, runSpacing: 4,
                  children: [
                    for (final item in items.take(4))
                      _MiniChip(label: item, color: iconColor),
                    if (items.length > 4)
                      _MiniChip(
                        label: '+${items.length - 4} autres',
                        color: mutedColor,
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final gs = profil.groupeSanguin;
    final children = <Widget>[];

    // Groupe sanguin
    if (gs != null) {
      children.add(Container(
        padding   : const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: cardColor,
          border: Border(
            left : BorderSide(color: borderColor, width: 0.5),
            right: BorderSide(color: borderColor, width: 0.5),
            top  : BorderSide(color: borderColor, width: 0.5),
          ),
        ),
        child: Row(
          children: [
            const Icon(Icons.water_drop_outlined, size: 16, color: AppColors.red),
            const SizedBox(width: 12),
            Text('Groupe sanguin',
                style: TextStyle(fontSize: 13, color: textColor)),
            const Spacer(),
            Container(
              padding   : const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color       : AppColors.red.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(99),
                border      : Border.all(color: AppColors.red.withValues(alpha: 0.3)),
              ),
              child: Text(
                gs,
                style: const TextStyle(
                  fontSize: 13, color: AppColors.red, fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ));
    }

    final ant = profil.antecedents;
    final mal = profil.maladiesChroniques;
    final trt = profil.traitements;

    final sections = [
      if (ant.isNotEmpty) (Icons.history_outlined,      const Color(0xFF7C3AED), 'Antécédents', ant),
      if (mal.isNotEmpty) (Icons.coronavirus_outlined,  AppColors.amber,         'Maladies chroniques', mal),
      if (trt.isNotEmpty) (Icons.medication_outlined,   AppColors.blue,          'Traitements', trt),
    ];

    for (var i = 0; i < sections.length; i++) {
      final s = sections[i];
      children.add(_rangee(
        icon     : s.$1,
        iconColor: s.$2,
        label    : s.$3,
        items    : s.$4,
        last     : i == sections.length - 1 && gs == null || i == sections.length - 1,
      ));
    }

    if (gs != null && sections.isEmpty) {
      // Only blood type — close the border bottom
      children[0] = Container(
        padding   : const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color : cardColor,
          border: Border.all(color: borderColor, width: 0.5),
        ),
        child: (children[0] as Container).child,
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: Column(children: children),
    );
  }
}

class _MiniChip extends StatelessWidget {
  final String label;
  final Color  color;
  const _MiniChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding   : const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color       : color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(99),
        border      : Border.all(color: color.withValues(alpha: 0.25), width: 0.5),
      ),
      child: Text(label, style: TextStyle(fontSize: 11, color: color)),
    );
  }
}

// ── Feuille d'édition du dossier médical ──────────────────
class _EditDossierSheet extends StatefulWidget {
  final ProfilMedicalProvider profil;
  final Color cardColor, borderColor, textColor, mutedColor;
  const _EditDossierSheet({
    required this.profil,
    required this.cardColor, required this.borderColor,
    required this.textColor, required this.mutedColor,
  });

  @override
  State<_EditDossierSheet> createState() => _EditDossierSheetState();
}

class _EditDossierSheetState extends State<_EditDossierSheet> {
  String?      _groupeSanguin;
  List<String> _antecedents        = [];
  List<String> _maladiesChroniques = [];
  List<String> _traitements        = [];

  final _ctrlAnt = TextEditingController();
  final _ctrlMal = TextEditingController();
  final _ctrlTrt = TextEditingController();

  bool _sauvegarde = false;

  static const _groupes = ['A+', 'A−', 'B+', 'B−', 'O+', 'O−', 'AB+', 'AB−'];

  @override
  void initState() {
    super.initState();
    _groupeSanguin      = widget.profil.groupeSanguin;
    _antecedents        = List.from(widget.profil.antecedents);
    _maladiesChroniques = List.from(widget.profil.maladiesChroniques);
    _traitements        = List.from(widget.profil.traitements);
  }

  @override
  void dispose() {
    _ctrlAnt.dispose();
    _ctrlMal.dispose();
    _ctrlTrt.dispose();
    super.dispose();
  }

  Future<void> _sauvegarder() async {
    setState(() => _sauvegarde = true);
    await widget.profil.sauvegarder(
      groupeSanguin      : _groupeSanguin,
      antecedents        : _antecedents,
      maladiesChroniques : _maladiesChroniques,
      traitements        : _traitements,
    );
    if (mounted) Navigator.pop(context);
  }

  void _ajouter(List<String> liste, TextEditingController ctrl) {
    final v = ctrl.text.trim();
    if (v.isEmpty || liste.contains(v)) return;
    setState(() => liste.add(v));
    ctrl.clear();
  }

  void _retirer(List<String> liste, String item) {
    setState(() => liste.remove(item));
  }

  @override
  Widget build(BuildContext context) {
    final dark        = Theme.of(context).brightness == Brightness.dark;
    final bgColor     = dark ? AppColors.darkSurface : AppColors.lightSurface;
    final textColor   = widget.textColor;
    final mutedColor  = widget.mutedColor;
    final borderColor = widget.borderColor;

    return DraggableScrollableSheet(
      initialChildSize : 0.92,
      minChildSize     : 0.5,
      maxChildSize     : 0.97,
      builder: (ctx, scrollCtrl) => Container(
        decoration: BoxDecoration(
          color       : bgColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          children: [
            // Poignée
            const SizedBox(height: 12),
            Container(
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: mutedColor.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            // Titre + actions
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 16, 8),
              child: Row(
                children: [
                  Text('Dossier médical',
                      style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w600, color: textColor,
                      )),
                  const Spacer(),
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Annuler',
                        style: TextStyle(color: AppColors.red, fontSize: 13)),
                  ),
                  const SizedBox(width: 4),
                  FilledButton(
                    onPressed: _sauvegarde ? null : _sauvegarder,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.blue,
                      padding       : const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      shape         : RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    child: _sauvegarde
                        ? const SizedBox(
                            width: 14, height: 14,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                          )
                        : const Text('Sauvegarder',
                            style: TextStyle(fontSize: 13, color: Colors.white)),
                  ),
                ],
              ),
            ),
            Divider(color: borderColor, height: 1),
            // Formulaire
            Expanded(
              child: ListView(
                controller : scrollCtrl,
                padding    : const EdgeInsets.all(20),
                children   : [

                  // Groupe sanguin
                  _LabelSection(label: 'Groupe sanguin', mutedColor: mutedColor),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8, runSpacing: 8,
                    children: [
                      for (final g in _groupes)
                        GestureDetector(
                          onTap: () => setState(() {
                            _groupeSanguin = (_groupeSanguin == g) ? null : g;
                          }),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            decoration: BoxDecoration(
                              color       : _groupeSanguin == g
                                  ? AppColors.red.withValues(alpha: 0.12)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(10),
                              border      : Border.all(
                                color: _groupeSanguin == g
                                    ? AppColors.red
                                    : borderColor,
                                width: _groupeSanguin == g ? 1.5 : 0.5,
                              ),
                            ),
                            child: Text(
                              g,
                              style: TextStyle(
                                fontSize  : 14,
                                fontWeight: FontWeight.w600,
                                color     : _groupeSanguin == g ? AppColors.red : mutedColor,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),

                  const SizedBox(height: 24),

                  // Antécédents
                  _LabelSection(
                    label    : 'Antécédents médicaux',
                    mutedColor: mutedColor,
                    sousTitre: 'Ex : HTA familiale, diabète père, chirurgie cardiaque…',
                  ),
                  const SizedBox(height: 10),
                  _ChampAjout(
                    ctrl       : _ctrlAnt,
                    hint       : 'Ajouter un antécédent',
                    accentColor: const Color(0xFF7C3AED),
                    textColor  : textColor,
                    mutedColor : mutedColor,
                    borderColor: borderColor,
                    onAjouter  : () => _ajouter(_antecedents, _ctrlAnt),
                  ),
                  if (_antecedents.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _ChipsEdition(
                      items      : _antecedents,
                      accentColor: const Color(0xFF7C3AED),
                      onRetirer  : (item) => _retirer(_antecedents, item),
                    ),
                  ],

                  const SizedBox(height: 24),

                  // Maladies chroniques
                  _LabelSection(
                    label    : 'Maladies chroniques',
                    mutedColor: mutedColor,
                    sousTitre: 'Ex : Hypertension, diabète type 2, insuffisance rénale…',
                  ),
                  const SizedBox(height: 10),
                  _ChampAjout(
                    ctrl       : _ctrlMal,
                    hint       : 'Ajouter une maladie',
                    accentColor: AppColors.amber,
                    textColor  : textColor,
                    mutedColor : mutedColor,
                    borderColor: borderColor,
                    onAjouter  : () => _ajouter(_maladiesChroniques, _ctrlMal),
                  ),
                  if (_maladiesChroniques.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _ChipsEdition(
                      items      : _maladiesChroniques,
                      accentColor: AppColors.amber,
                      onRetirer  : (item) => _retirer(_maladiesChroniques, item),
                    ),
                  ],

                  const SizedBox(height: 24),

                  // Traitements
                  _LabelSection(
                    label    : 'Traitements en cours',
                    mutedColor: mutedColor,
                    sousTitre: 'Ex : Metformine 500mg, Lisinopril 5mg matin…',
                  ),
                  const SizedBox(height: 10),
                  _ChampAjout(
                    ctrl       : _ctrlTrt,
                    hint       : 'Ajouter un traitement',
                    accentColor: AppColors.blue,
                    textColor  : textColor,
                    mutedColor : mutedColor,
                    borderColor: borderColor,
                    onAjouter  : () => _ajouter(_traitements, _ctrlTrt),
                  ),
                  if (_traitements.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _ChipsEdition(
                      items      : _traitements,
                      accentColor: AppColors.blue,
                      onRetirer  : (item) => _retirer(_traitements, item),
                    ),
                  ],

                  SizedBox(height: MediaQuery.of(context).viewInsets.bottom + 32),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Widgets utilitaires de l'éditeur ─────────────────────

class _LabelSection extends StatelessWidget {
  final String label;
  final String? sousTitre;
  final Color  mutedColor;
  const _LabelSection({required this.label, required this.mutedColor, this.sousTitre});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w600,
              color: mutedColor.withValues(alpha: 0.85),
            )),
        if (sousTitre != null) ...[
          const SizedBox(height: 2),
          Text(sousTitre!,
              style: TextStyle(fontSize: 11, color: mutedColor.withValues(alpha: 0.6))),
        ],
      ],
    );
  }
}

class _ChampAjout extends StatelessWidget {
  final TextEditingController ctrl;
  final String    hint;
  final Color     accentColor, textColor, mutedColor, borderColor;
  final VoidCallback onAjouter;
  const _ChampAjout({
    required this.ctrl, required this.hint,
    required this.accentColor, required this.textColor,
    required this.mutedColor,  required this.borderColor,
    required this.onAjouter,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller  : ctrl,
            style       : TextStyle(fontSize: 13, color: textColor),
            textCapitalization: TextCapitalization.sentences,
            onSubmitted : (_) => onAjouter(),
            decoration  : InputDecoration(
              hintText      : hint,
              hintStyle     : TextStyle(fontSize: 12, color: mutedColor),
              isDense       : true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide  : BorderSide(color: borderColor),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide  : BorderSide(color: borderColor, width: 0.5),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide  : BorderSide(color: accentColor),
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        GestureDetector(
          onTap: onAjouter,
          child: Container(
            width : 40, height: 40,
            decoration: BoxDecoration(
              color       : accentColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
              border      : Border.all(color: accentColor.withValues(alpha: 0.3)),
            ),
            child: Icon(Icons.add, color: accentColor, size: 20),
          ),
        ),
      ],
    );
  }
}

class _ChipsEdition extends StatelessWidget {
  final List<String> items;
  final Color        accentColor;
  final void Function(String) onRetirer;
  const _ChipsEdition({
    required this.items, required this.accentColor, required this.onRetirer,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6, runSpacing: 6,
      children: [
        for (final item in items)
          Container(
            padding   : const EdgeInsets.fromLTRB(10, 5, 6, 5),
            decoration: BoxDecoration(
              color       : accentColor.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(99),
              border      : Border.all(color: accentColor.withValues(alpha: 0.3), width: 0.5),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(item, style: TextStyle(fontSize: 12, color: accentColor)),
                const SizedBox(width: 4),
                GestureDetector(
                  onTap: () => onRetirer(item),
                  child: Icon(Icons.close, size: 14, color: accentColor.withValues(alpha: 0.7)),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// ── Section ───────────────────────────────────────────────
class _Section extends StatelessWidget {
  final String       title;
  final List<Widget> children;
  const _Section({required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    final dark       = Theme.of(context).brightness == Brightness.dark;
    final mutedColor = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(
            title,
            style: TextStyle(
              fontSize: 12, fontWeight: FontWeight.w500,
              color: mutedColor, letterSpacing: 0.3,
            ),
          ),
        ),
        ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: Column(children: children),
        ),
      ],
    );
  }
}

// ── Item info ─────────────────────────────────────────────
class _InfoItem extends StatelessWidget {
  final IconData icon;
  final String   label, value;
  final Color    textColor, mutedColor, cardColor, borderColor;
  final bool     last;
  const _InfoItem({
    required this.icon, required this.label, required this.value,
    required this.textColor, required this.mutedColor,
    required this.cardColor, required this.borderColor,
    this.last = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding    : const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration : BoxDecoration(
        color : cardColor,
        border: Border(
          left  : BorderSide(color: borderColor, width: 0.5),
          right : BorderSide(color: borderColor, width: 0.5),
          top   : BorderSide(color: borderColor, width: 0.5),
          bottom: BorderSide(color: borderColor, width: 0.5),
        ),
      ),
      child: Row(
        children: [
          Icon(icon, size: 17, color: mutedColor),
          const SizedBox(width: 12),
          Text(label, style: TextStyle(fontSize: 13, color: textColor)),
          const Spacer(),
          Text(value,
              style: TextStyle(
                fontSize: 13, color: mutedColor, fontWeight: FontWeight.w500,
              )),
        ],
      ),
    );
  }
}

// ── Item toggle ───────────────────────────────────────────
class _ToggleItem extends StatelessWidget {
  final IconData           icon;
  final String             label;
  final bool               value;
  final ValueChanged<bool> onChanged;
  final Color              textColor, mutedColor, cardColor, borderColor;
  final bool               last;
  const _ToggleItem({
    required this.icon, required this.label, required this.value,
    required this.onChanged, required this.textColor,
    required this.mutedColor, required this.cardColor,
    required this.borderColor, this.last = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding    : const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration : BoxDecoration(
        color : cardColor,
        border: Border.all(color: borderColor, width: 0.5),
      ),
      child: Row(
        children: [
          Icon(icon, size: 17, color: mutedColor),
          const SizedBox(width: 12),
          Text(label, style: TextStyle(fontSize: 13, color: textColor)),
          const Spacer(),
          Switch(
            value           : value,
            onChanged       : onChanged,
            activeThumbColor: AppColors.blue,
          ),
        ],
      ),
    );
  }
}
