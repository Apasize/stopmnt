// lib/features/mesures/mesures_screen.dart

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../core/providers/auth_provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/services/api_service.dart';
import '../../core/models/mesure.dart';
import '../../core/widgets/skeleton.dart';

class MesuresScreen extends StatefulWidget {
  const MesuresScreen({super.key});

  @override
  State<MesuresScreen> createState() => _MesuresScreenState();
}

class _MesuresScreenState extends State<MesuresScreen>
    with SingleTickerProviderStateMixin {

  late TabController _tabs;
  List<Mesure> _historique = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _chargerHistorique();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _chargerHistorique() async {
    try {
      final data = await ApiService.getHistoriqueMesures(limite: 100);
      if (!mounted) return;
      setState(() {
        _historique = data.map((j) => Mesure.fromJson(j)).toList();
        _loading    = false;
      });
    }on TokenExpireException {
      // Token expiré — déconnecter et rediriger vers login
      if (mounted) {
        context.read<AuthProvider>().gererTokenExpire();
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final dark       = Theme.of(context).brightness == Brightness.dark;
    final bgColor    = dark ? AppColors.darkBg      : AppColors.lightBg;
    final textColor  = dark ? AppColors.darkText     : AppColors.lightText;
    final mutedColor = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final cardColor  = dark ? AppColors.darkSurface  : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder  : AppColors.lightBorder;

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        title: const Text('Mesures'),
        backgroundColor: bgColor,
        bottom: TabBar(
          controller  : _tabs,
          labelColor  : AppColors.blue,
          unselectedLabelColor: mutedColor,
          indicatorColor: AppColors.blue,
          indicatorSize: TabBarIndicatorSize.label,
          tabs: const [
            Tab(child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.add_circle_outline, size: 14),
                SizedBox(width: 5),
                Text('Saisie'),
              ],
            )),
            Tab(text: 'Tendances'),
            Tab(text: 'Historique'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          // ── Onglet 1 — Saisie ──
          _SaisieMesure(
            onMesureEnvoyee: () {
              _chargerHistorique();
              _tabs.animateTo(2);
            },
          ),
          // ── Onglet 2 — Tendances ──
          _loading
              ? _SkeletonHistorique(
            cardColor  : dark ? AppColors.darkSurface : AppColors.lightSurface,
            borderColor: dark ? AppColors.darkBorder  : AppColors.lightBorder,
          )
              : _Tendances(
            mesures    : _historique,
            mutedColor : mutedColor,
            textColor  : textColor,
            cardColor  : cardColor,
            borderColor: borderColor,
          ),
          // ── Onglet 3 — Historique ──
          _loading
              ? _SkeletonHistorique(
            cardColor  : dark ? AppColors.darkSurface : AppColors.lightSurface,
            borderColor: dark ? AppColors.darkBorder  : AppColors.lightBorder,
          )
              : _Historique(
            mesures     : _historique,
            mutedColor  : mutedColor,
            textColor   : textColor,
            cardColor   : cardColor,
            borderColor : borderColor,
            onRefresh   : _chargerHistorique,
          ),
        ],
      ),
    );
  }
}

// ── Formulaire de saisie ──────────────────────────────────
class _SaisieMesure extends StatefulWidget {
  final VoidCallback onMesureEnvoyee;
  const _SaisieMesure({required this.onMesureEnvoyee});

  @override
  State<_SaisieMesure> createState() => _SaisieMesureState();
}

class _SaisieMesureState extends State<_SaisieMesure> {
  String _capteur   = 'tensiometre';
  bool   _loading   = false;
  String? _message;
  bool   _succes    = false;

  // Tensiomètre
  final _sysCtrl  = TextEditingController();
  final _diasCtrl = TextEditingController();

  // Glucomètre
  final _glycCtrl = TextEditingController();

  // Oxymètre (saisie manuelle)
  final _fcManCtrl  = TextEditingController();
  final _spo2Ctrl   = TextEditingController();

  // Thermomètre
  final _tempCtrl = TextEditingController();

  // Pèse-personne
  final _poidsCtrl = TextEditingController();

  // Taille
  final _tailleCtrl = TextEditingController();

  @override
  void dispose() {
    _sysCtrl.dispose();
    _diasCtrl.dispose();
    _glycCtrl.dispose();
    _fcManCtrl.dispose();
    _spo2Ctrl.dispose();
    _tempCtrl.dispose();
    _poidsCtrl.dispose();
    _tailleCtrl.dispose();
    super.dispose();
  }

  Future<void> _envoyer() async {
    setState(() { _loading = true; _message = null; });

    try {
      Map<String, dynamic> mesures;

      if (_capteur == 'tensiometre') {
        final sys  = double.tryParse(_sysCtrl.text.trim());
        final dias = double.tryParse(_diasCtrl.text.trim());
        if (sys == null || dias == null || sys <= dias) {
          setState(() { _message = 'Valeurs invalides'; _loading = false; });
          return;
        }
        mesures = {'systolique': sys, 'diastolique': dias};
      } else if (_capteur == 'glucometre') {
        final glyc = double.tryParse(_glycCtrl.text.trim());
        if (glyc == null) {
          setState(() { _message = 'Valeur invalide'; _loading = false; });
          return;
        }
        mesures = {'glycemie': glyc};
      } else if (_capteur == 'oxymetre') {
        final fc   = double.tryParse(_fcManCtrl.text.trim());
        final spo2 = double.tryParse(_spo2Ctrl.text.trim());
        if (fc == null || spo2 == null) {
          setState(() { _message = 'Valeurs invalides'; _loading = false; });
          return;
        }
        mesures = {'fc': fc, 'spo2': spo2};
      } else if (_capteur == 'thermometre') {
        final temp = double.tryParse(_tempCtrl.text.trim());
        if (temp == null) {
          setState(() { _message = 'Valeur invalide'; _loading = false; });
          return;
        }
        mesures = {'temperature': temp};
      } else if (_capteur == 'pese_personne') {
        final poids = double.tryParse(_poidsCtrl.text.trim());
        if (poids == null) {
          setState(() { _message = 'Valeur invalide'; _loading = false; });
          return;
        }
        mesures = {'poids': poids};
      } else {
        final taille = double.tryParse(_tailleCtrl.text.trim());
        if (taille == null) {
          setState(() { _message = 'Valeur invalide'; _loading = false; });
          return;
        }
        mesures = {'taille': taille};
      }

      final result = await ApiService.envoyerMesure(
        capteur : _capteur,
        mesures : mesures,
      );

      final differe  = result['differe']  as bool? ?? false;
      final anomalie = result['anomalie'] as bool? ?? false;
      final alerte   = result['alerte']   as Map?;

      setState(() {
        _succes  = true;
        _loading = false;
        _message = differe
            ? 'Mesure enregistrée localement — sera envoyée à la reconnexion'
            : anomalie && alerte != null
                ? 'Anomalie détectée : ${alerte['message']}'
                : 'Mesure enregistrée avec succès';
        _sysCtrl.clear();   _diasCtrl.clear();
        _glycCtrl.clear();  _fcManCtrl.clear();
        _spo2Ctrl.clear();  _tempCtrl.clear();
        _poidsCtrl.clear(); _tailleCtrl.clear();
      });

      await Future.delayed(const Duration(seconds: 2));
      if (mounted) widget.onMesureEnvoyee();

    } on TokenExpireException {
      if (mounted) context.read<AuthProvider>().gererTokenExpire();
    } on ApiException catch (e) {
      setState(() {
        _message = e.message;
        _loading = false;
        _succes  = false;
      });
    } catch (_) {
      setState(() {
        _message = 'Serveur inaccessible. Vérifiez votre connexion réseau.';
        _loading = false;
        _succes  = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final dark       = Theme.of(context).brightness == Brightness.dark;
    final textColor  = dark ? AppColors.darkText     : AppColors.lightText;
    final mutedColor = dark ? AppColors.darkTextMuted : AppColors.lightTextMuted;
    final cardColor  = dark ? AppColors.darkSurface  : AppColors.lightSurface;
    final borderColor = dark ? AppColors.darkBorder  : AppColors.lightBorder;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          const SizedBox(height: 8),

          // ── Sélecteur capteur ──
          Text(
            'Type de mesure',
            style: TextStyle(
              fontSize   : 13,
              fontWeight : FontWeight.w500,
              color      : textColor,
            ),
          ),
          const SizedBox(height: 10),
          LayoutBuilder(
            builder: (_, c) {
              final w = (c.maxWidth - 20) / 3;
              return Wrap(
                spacing: 10, runSpacing: 10,
                children: [
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'Tension', unit: 'mmHg',
                    icon: Icons.favorite_outline,
                    selected: _capteur == 'tensiometre',
                    onTap: () => setState(() => _capteur = 'tensiometre'),
                    color: AppColors.red, cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'Glycémie', unit: 'g/L',
                    icon: Icons.water_drop_outlined,
                    selected: _capteur == 'glucometre',
                    onTap: () => setState(() => _capteur = 'glucometre'),
                    color: AppColors.amber, cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'SpO₂ / FC', unit: '% · bpm',
                    icon: Icons.air_outlined,
                    selected: _capteur == 'oxymetre',
                    onTap: () => setState(() => _capteur = 'oxymetre'),
                    color: AppColors.blue, cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'Température', unit: '°C',
                    icon: Icons.device_thermostat_outlined,
                    selected: _capteur == 'thermometre',
                    onTap: () => setState(() => _capteur = 'thermometre'),
                    color: Color(0xFF7C3AED), cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'Poids', unit: 'kg',
                    icon: Icons.monitor_weight_outlined,
                    selected: _capteur == 'pese_personne',
                    onTap: () => setState(() => _capteur = 'pese_personne'),
                    color: AppColors.green, cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                  SizedBox(width: w, child: _CapteurBtn(
                    label: 'Taille', unit: 'cm',
                    icon: Icons.height,
                    selected: _capteur == 'taille',
                    onTap: () => setState(() => _capteur = 'taille'),
                    color: Color(0xFF0891B2), cardColor: cardColor,
                    borderColor: borderColor, textColor: textColor,
                  )),
                ],
              );
            },
          ),

          const SizedBox(height: 24),

          // ── Champs selon le capteur ──
          if (_capteur == 'tensiometre') ...[
            Text('Tension artérielle', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: _ChampNumerique(
                  ctrl: _sysCtrl, label: 'Systolique',
                  unite: 'mmHg', hint: '120', mutedColor: mutedColor,
                )),
                const SizedBox(width: 12),
                Expanded(child: _ChampNumerique(
                  ctrl: _diasCtrl, label: 'Diastolique',
                  unite: 'mmHg', hint: '80', mutedColor: mutedColor,
                )),
              ],
            ),
            const SizedBox(height: 8),
            Text('Valeurs normales : 90-140 / 60-90 mmHg',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ] else if (_capteur == 'glucometre') ...[
            Text('Glycémie', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            _ChampNumerique(
              ctrl: _glycCtrl, label: 'Valeur',
              unite: 'g/L', hint: '1.0',
              mutedColor: mutedColor, decimal: true,
            ),
            const SizedBox(height: 8),
            Text('Valeur normale à jeun : 0.7–1.1 g/L',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ] else if (_capteur == 'oxymetre') ...[
            Text('Oxymètre de pouls', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: _ChampNumerique(
                  ctrl: _fcManCtrl, label: 'Fréq. cardiaque',
                  unite: 'bpm', hint: '72', mutedColor: mutedColor,
                )),
                const SizedBox(width: 12),
                Expanded(child: _ChampNumerique(
                  ctrl: _spo2Ctrl, label: 'Saturation O₂',
                  unite: '%', hint: '98', mutedColor: mutedColor,
                )),
              ],
            ),
            const SizedBox(height: 8),
            Text('Normales : FC 60-100 bpm · SpO₂ ≥ 95 %',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ] else if (_capteur == 'thermometre') ...[
            Text('Température corporelle', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            _ChampNumerique(
              ctrl: _tempCtrl, label: 'Température',
              unite: '°C', hint: '37.0',
              mutedColor: mutedColor, decimal: true,
            ),
            const SizedBox(height: 8),
            Text('Normale : 36.1–37.2 °C · Fièvre ≥ 38 °C',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ] else if (_capteur == 'pese_personne') ...[
            Text('Poids corporel', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            _ChampNumerique(
              ctrl: _poidsCtrl, label: 'Poids',
              unite: 'kg', hint: '70.0',
              mutedColor: mutedColor, decimal: true,
            ),
            const SizedBox(height: 8),
            Text('Pesez-vous de préférence le matin à jeun',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ] else ...[
            Text('Taille', style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w500, color: textColor,
            )),
            const SizedBox(height: 10),
            _ChampNumerique(
              ctrl: _tailleCtrl, label: 'Taille',
              unite: 'cm', hint: '170',
              mutedColor: mutedColor,
            ),
            const SizedBox(height: 8),
            Text('Saisie en centimètres — ex. 1 m 70 → 170 cm',
              style: TextStyle(fontSize: 11, color: mutedColor)),
          ],

          const SizedBox(height: 24),

          // ── Message retour ──
          if (_message != null)
            Container(
              padding    : const EdgeInsets.all(12),
              decoration : BoxDecoration(
                color        : _succes
                    ? AppColors.green.withValues(alpha: 0.1)
                    : AppColors.red.withValues(alpha: 0.1),
                borderRadius : BorderRadius.circular(12),
                border       : Border.all(
                  color : _succes
                      ? AppColors.green.withValues(alpha: 0.3)
                      : AppColors.red.withValues(alpha: 0.3),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    _succes ? Icons.check_circle_outline : Icons.error_outline,
                    color : _succes ? AppColors.green : AppColors.red,
                    size  : 16,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _message!,
                      style: TextStyle(
                        fontSize : 12,
                        color    : _succes ? AppColors.green : AppColors.red,
                      ),
                    ),
                  ),
                ],
              ),
            ),

          const SizedBox(height: 20),

          // ── Bouton envoyer ──
          SizedBox(
            width  : double.infinity,
            height : 52,
            child  : FilledButton.icon(
              onPressed : _loading ? null : _envoyer,
              style     : FilledButton.styleFrom(
                backgroundColor : AppColors.blue,
                shape           : RoundedRectangleBorder(
                  borderRadius  : BorderRadius.circular(14),
                ),
              ),
              icon  : _loading
                  ? const SizedBox(
                width: 18, height: 18,
                child: CircularProgressIndicator(
                  color: Colors.white, strokeWidth: 2,
                ),
              )
                  : const Icon(Icons.send_outlined, size: 18, color: Colors.white),
              label : Text(
                _loading ? 'Envoi en cours...' : 'Envoyer la mesure',
                style: const TextStyle(
                  fontSize   : 15,
                  fontWeight : FontWeight.w500,
                  color      : Colors.white,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Bouton sélection capteur ──────────────────────────────
class _CapteurBtn extends StatelessWidget {
  final String label, unit;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final Color color, cardColor, borderColor, textColor;

  const _CapteurBtn({
    required this.label, required this.unit, required this.icon,
    required this.selected, required this.onTap,
    required this.color, required this.cardColor,
    required this.borderColor, required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    final iconBg = selected ? color.withValues(alpha: 0.15) : color.withValues(alpha: 0.07);
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding   : const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color       : selected ? color.withValues(alpha: 0.08) : cardColor,
          borderRadius: BorderRadius.circular(14),
          border      : Border.all(
            color: selected ? color : borderColor,
            width: selected ? 1.5 : 0.5,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width : 38, height: 38,
              decoration: BoxDecoration(color: iconBg, shape: BoxShape.circle),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize  : 11,
                fontWeight: FontWeight.w600,
                color     : selected ? color : textColor,
                height    : 1.2,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              unit,
              style: TextStyle(
                fontSize: 10,
                color   : selected ? color.withValues(alpha: 0.75) : textColor.withValues(alpha: 0.4),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Champ numérique ───────────────────────────────────────
class _ChampNumerique extends StatelessWidget {
  final TextEditingController ctrl;
  final String label, unite, hint;
  final Color mutedColor;
  final bool decimal;

  const _ChampNumerique({
    required this.ctrl, required this.label,
    required this.unite, required this.hint,
    required this.mutedColor, this.decimal = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$label ($unite)',
          style: TextStyle(fontSize: 11, color: mutedColor),
        ),
        const SizedBox(height: 6),
        TextField(
          controller  : ctrl,
          keyboardType: TextInputType.numberWithOptions(decimal: decimal),
          inputFormatters: [
            FilteringTextInputFormatter.allow(
              decimal ? RegExp(r'^\d*\.?\d*') : RegExp(r'^\d*'),
            ),
          ],
          decoration: InputDecoration(
            hintText   : hint,
            suffixText : unite,
          ),
        ),
      ],
    );
  }
}

// ── Skeleton onglet historique ────────────────────────────
// Reproduit la structure exacte de chaque item mesure dans _Historique

class _SkeletonHistorique extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonHistorique({required this.cardColor, required this.borderColor});

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: ListView.separated(
        padding         : const EdgeInsets.all(16),
        itemCount       : 5,
        separatorBuilder: (_, _) => const SizedBox(height: 8),
        itemBuilder     : (_, _) => _SkeletonMesureItem(
          cardColor  : cardColor,
          borderColor: borderColor,
        ),
      ),
    );
  }
}

class _SkeletonMesureItem extends StatelessWidget {
  final Color cardColor, borderColor;
  const _SkeletonMesureItem({required this.cardColor, required this.borderColor});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding   : const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color       : cardColor,
        borderRadius: BorderRadius.circular(14),
        border      : Border.all(color: borderColor, width: 0.5),
      ),
      child: Row(
        children: [
          ShimmerBlock(width: 38, height: 38, radius: 10),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(children: [
                  ShimmerBlock(width: 105, height: 13, radius: 6),
                  const SizedBox(width: 8),
                  ShimmerBlock(width: 52, height: 16, radius: 99),
                ]),
                const SizedBox(height: 6),
                ShimmerBlock(width: 150, height: 10, radius: 5),
              ],
            ),
          ),
          const SizedBox(width: 12),
          ShimmerBlock(width: 32, height: 11, radius: 4),
        ],
      ),
    );
  }
}

// ── Historique des mesures ────────────────────────────────

enum _Periode { tout, aujourdhui, semaine, mois, date }

class _Historique extends StatefulWidget {
  final List<Mesure> mesures;
  final Color mutedColor, textColor, cardColor, borderColor;
  final Future<void> Function() onRefresh;

  const _Historique({
    required this.mesures, required this.mutedColor,
    required this.textColor, required this.cardColor,
    required this.borderColor, required this.onRefresh,
  });

  @override
  State<_Historique> createState() => _HistoriqueState();
}

class _HistoriqueState extends State<_Historique> {
  static const _pageSize = 10;
  _Periode  _periode     = _Periode.tout;
  DateTime? _dateChoisie;
  String?   _type;
  int       _visible     = _pageSize;

  bool get _filtrActif => _periode != _Periode.tout || _type != null;

  List<Mesure> get _filtrees {
    var list = widget.mesures;
    final now = DateTime.now();
    switch (_periode) {
      case _Periode.aujourdhui:
        list = list.where((m) {
          final d = m.timestamp.toLocal();
          return d.year == now.year && d.month == now.month && d.day == now.day;
        }).toList();
      case _Periode.semaine:
        final cutoff = now.subtract(const Duration(days: 7));
        list = list.where((m) => m.timestamp.isAfter(cutoff)).toList();
      case _Periode.mois:
        list = list.where((m) {
          final d = m.timestamp.toLocal();
          return d.year == now.year && d.month == now.month;
        }).toList();
      case _Periode.date:
        if (_dateChoisie != null) {
          list = list.where((m) {
            final d = m.timestamp.toLocal();
            return d.year == _dateChoisie!.year &&
                   d.month == _dateChoisie!.month &&
                   d.day   == _dateChoisie!.day;
          }).toList();
        }
      case _Periode.tout:
        break;
    }
    if (_type == '__anomalie__') return list.where((m) => m.anomalie).toList();
    if (_type != null) list = list.where((m) => m.capteur == _type).toList();
    return list;
  }

  static (Color, IconData, String) _meta(String capteur) => switch (capteur) {
    'tensiometre'   => (AppColors.red,          Icons.favorite_outline,          'Tensiomètre'),
    'glucometre'    => (AppColors.amber,         Icons.water_drop_outlined,       'Glucomètre'),
    'oxymetre'      => (AppColors.blue,          Icons.air_outlined,              'Oxymètre'),
    'thermometre'   => (const Color(0xFF7C3AED), Icons.device_thermostat_outlined,'Thermomètre'),
    'pese_personne' => (AppColors.green,         Icons.monitor_weight_outlined,   'Pèse-personne'),
    'taille'        => (const Color(0xFF0891B2), Icons.height,                    'Taille'),
    'simulateur'    => (const Color(0xFF6B7280), Icons.sensors_outlined,          'Simulateur'),
    _               => (AppColors.blue,          Icons.monitor_heart_outlined,    capteur),
  };

  @override
  void didUpdateWidget(_Historique old) {
    super.didUpdateWidget(old);
    if (old.mesures != widget.mesures) _visible = _pageSize;
  }

  void _ouvrirFiltres() {
    _Periode  periodeTemp = _periode;
    DateTime? dateTemp    = _dateChoisie;
    String?   typeTemp    = _type;

    showModalBottomSheet(
      context          : context,
      isScrollControlled: true,
      backgroundColor  : Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModal) {
          const types = [
            ('tensiometre',   'Tension',   AppColors.red),
            ('glucometre',    'Glycémie',  AppColors.amber),
            ('oxymetre',      'SpO₂ / FC', AppColors.blue),
            ('thermometre',   'Temp.',     Color(0xFF7C3AED)),
            ('pese_personne', 'Poids',     AppColors.green),
            ('taille',        'Taille',    Color(0xFF0891B2)),
            ('__anomalie__',  'Anomalies', AppColors.red),
          ];

          Widget periodeBtn(_Periode p, String lbl, IconData ic) {
            final sel = periodeTemp == p;
            return GestureDetector(
              onTap: () async {
                if (p == _Periode.date) {
                  final picked = await showDatePicker(
                    context    : ctx,
                    initialDate: dateTemp ?? DateTime.now(),
                    firstDate  : DateTime(2020),
                    lastDate   : DateTime.now(),
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
                    color: sel ? AppColors.blue : widget.borderColor,
                    width: sel ? 1.5 : 0.6,
                  ),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(ic, size: 15,
                      color: sel ? AppColors.blue : widget.mutedColor),
                  const SizedBox(width: 7),
                  Text(
                    p == _Periode.date && dateTemp != null
                        ? '${dateTemp!.day.toString().padLeft(2,'0')}/${dateTemp!.month.toString().padLeft(2,'0')}/${dateTemp!.year}'
                        : lbl,
                    style: TextStyle(
                      fontSize  : 12,
                      fontWeight: sel ? FontWeight.w600 : FontWeight.normal,
                      color     : sel ? AppColors.blue : widget.mutedColor,
                    ),
                  ),
                ]),
              ),
            );
          }

          final dark = Theme.of(ctx).brightness == Brightness.dark;
          final sheetBg = dark ? AppColors.darkSurface : Colors.white;

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
                // Handle
                Center(child: Container(
                  width: 36, height: 4,
                  decoration: BoxDecoration(
                    color       : widget.borderColor,
                    borderRadius: BorderRadius.circular(99),
                  ),
                )),
                const SizedBox(height: 18),
                Row(children: [
                  Text('Filtres', style: TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700,
                    color: widget.textColor,
                  )),
                  const Spacer(),
                  GestureDetector(
                    onTap: () {
                      setState(() { _periode = _Periode.tout; _dateChoisie = null; _type = null; _visible = _pageSize; });
                      Navigator.pop(ctx);
                    },
                    child: Text('Réinitialiser',
                        style: TextStyle(fontSize: 12, color: AppColors.blue)),
                  ),
                ]),
                const SizedBox(height: 20),

                // Période
                Text('Période', style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w600,
                    color: widget.mutedColor)),
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  periodeBtn(_Periode.tout,       'Tout',         Icons.all_inclusive_rounded),
                  periodeBtn(_Periode.aujourdhui,  "Aujourd'hui",  Icons.today_outlined),
                  periodeBtn(_Periode.semaine,     '7 derniers j', Icons.date_range_outlined),
                  periodeBtn(_Periode.mois,        'Ce mois',      Icons.calendar_month_outlined),
                  periodeBtn(_Periode.date,        'Date précise', Icons.event_outlined),
                ]),
                const SizedBox(height: 22),

                // Type
                Text('Type de mesure', style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w600,
                    color: widget.mutedColor)),
                const SizedBox(height: 10),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  GestureDetector(
                    onTap: () => setModal(() => typeTemp = null),
                    child: _SheetChip(label: 'Tout', selected: typeTemp == null,
                        color: AppColors.blue, border: widget.borderColor, muted: widget.mutedColor),
                  ),
                  ...types.map((t) => GestureDetector(
                    onTap: () => setModal(() => typeTemp = typeTemp == t.$1 ? null : t.$1),
                    child: _SheetChip(label: t.$2, selected: typeTemp == t.$1,
                        color: t.$3, border: widget.borderColor, muted: widget.mutedColor),
                  )),
                ]),
                const SizedBox(height: 24),

                // Appliquer
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: FilledButton(
                    onPressed: () {
                      setState(() {
                        _periode     = periodeTemp;
                        _dateChoisie = dateTemp;
                        _type        = typeTemp;
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

  @override
  Widget build(BuildContext context) {
    if (widget.mesures.isEmpty) {
      return Center(child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.monitor_heart_outlined, color: widget.mutedColor, size: 40),
          const SizedBox(height: 12),
          Text('Aucune mesure enregistrée',
              style: TextStyle(fontSize: 14, color: widget.mutedColor)),
        ],
      ));
    }

    final filtered = _filtrees;
    final shown    = filtered.take(_visible).toList();
    final hasMore  = _visible < filtered.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── En-tête ──
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 12, 8),
          child: Row(children: [
            Expanded(child: Text(
              '${filtered.length} mesure${filtered.length > 1 ? 's' : ''}',
              style: TextStyle(
                fontSize  : 13,
                fontWeight: FontWeight.w500,
                color     : widget.mutedColor,
              ),
            )),
            Stack(clipBehavior: Clip.none, children: [
              IconButton(
                onPressed: _ouvrirFiltres,
                icon: Icon(Icons.tune_rounded,
                    color: _filtrActif ? AppColors.blue : widget.mutedColor),
                tooltip: 'Filtrer',
              ),
              if (_filtrActif) Positioned(
                top: 8, right: 8,
                child: Container(
                  width: 8, height: 8,
                  decoration: const BoxDecoration(
                    color: AppColors.blue, shape: BoxShape.circle,
                  ),
                ),
              ),
            ]),
          ]),
        ),

        // ── Liste ──
        Expanded(
          child: filtered.isEmpty
              ? Center(child: Text('Aucun résultat pour ce filtre',
                  style: TextStyle(fontSize: 13, color: widget.mutedColor)))
              : RefreshIndicator(
                  onRefresh: widget.onRefresh,
                  color    : AppColors.blue,
                  child    : ListView.separated(
                    padding         : const EdgeInsets.fromLTRB(16, 0, 16, 24),
                    itemCount       : shown.length + (hasMore ? 1 : 0),
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder     : (_, i) {
                      if (i == shown.length) {
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: TextButton(
                            onPressed: () => setState(() => _visible += _pageSize),
                            child: Text(
                              'Voir plus · ${filtered.length - _visible} restantes',
                              style: const TextStyle(fontSize: 13, color: AppColors.blue),
                            ),
                          ),
                        );
                      }

                      final m = shown[i];
                      final (color, icon, label) = _meta(m.capteur);
                      final d = m.timestamp.toLocal();
                      final dateTxt =
                          '${d.day.toString().padLeft(2,'0')}/${d.month.toString().padLeft(2,'0')} '
                          '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';

                      return Container(
                        padding   : const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color       : widget.cardColor,
                          borderRadius: BorderRadius.circular(14),
                          border      : Border.all(
                            color: m.anomalie
                                ? AppColors.red.withValues(alpha: 0.4)
                                : widget.borderColor,
                            width: 0.5,
                          ),
                        ),
                        child: Row(children: [
                          Container(
                            width: 38, height: 38,
                            decoration: BoxDecoration(
                              color       : color.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Icon(icon, color: color, size: 18),
                          ),
                          const SizedBox(width: 12),
                          Expanded(child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(children: [
                                Text(label, style: TextStyle(
                                  fontSize: 13, fontWeight: FontWeight.w500,
                                  color: widget.textColor,
                                )),
                                if (m.anomalie) ...[
                                  const SizedBox(width: 6),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color       : AppColors.red.withValues(alpha: 0.1),
                                      borderRadius: BorderRadius.circular(99),
                                    ),
                                    child: const Text('Anomalie', style: TextStyle(
                                      fontSize: 9, color: AppColors.red,
                                      fontWeight: FontWeight.w500,
                                    )),
                                  ),
                                ],
                              ]),
                              const SizedBox(height: 3),
                              Text(m.resume, style: TextStyle(
                                  fontSize: 12, color: widget.mutedColor)),
                            ],
                          )),
                          Text(dateTxt, style: TextStyle(
                              fontSize: 11, color: widget.mutedColor)),
                        ]),
                      );
                    },
                  ),
                ),
        ),
      ],
    );
  }
}

// ── Chip dans le bottom sheet filtre ─────────────────────
class _SheetChip extends StatelessWidget {
  final String label;
  final bool selected;
  final Color color, border, muted;
  const _SheetChip({
    required this.label, required this.selected,
    required this.color, required this.border, required this.muted,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      padding : const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color       : selected ? color.withValues(alpha: 0.1) : Colors.transparent,
        borderRadius: BorderRadius.circular(99),
        border      : Border.all(color: selected ? color : border, width: selected ? 1.5 : 0.6),
      ),
      child: Text(label, style: TextStyle(
        fontSize  : 12,
        fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
        color     : selected ? color : muted,
      )),
    );
  }
}

// ── Tendances — configuration des métriques ───────────────

class _ChartOpt {
  final String id, label, capteur;
  final Color  chipColor;
  final List<_Serie> series;
  const _ChartOpt({
    required this.id, required this.label,
    required this.capteur, required this.chipColor,
    required this.series,
  });
}

class _Serie {
  final String field, label, unit;
  final Color  color;
  const _Serie({required this.field, required this.label, required this.unit, required this.color});
}

// ── Onglet tendances ──────────────────────────────────────

class _Tendances extends StatefulWidget {
  final List<Mesure> mesures;
  final Color mutedColor, textColor, cardColor, borderColor;
  const _Tendances({
    required this.mesures,
    required this.mutedColor, required this.textColor,
    required this.cardColor,  required this.borderColor,
  });

  @override
  State<_Tendances> createState() => _TendancesState();
}

class _TendancesState extends State<_Tendances> {

  static final _opts = <_ChartOpt>[
    _ChartOpt(id: 'tension', label: 'Tension', capteur: 'tensiometre', chipColor: AppColors.red,
      series: [
        _Serie(field: 'systolique',  label: 'Sys', unit: 'mmHg', color: AppColors.red),
        _Serie(field: 'diastolique', label: 'Dia', unit: 'mmHg', color: Color(0xFFF97316)),
      ]),
    _ChartOpt(id: 'glycemie', label: 'Glycémie', capteur: 'glucometre', chipColor: AppColors.amber,
      series: [_Serie(field: 'glycemie', label: 'Glycémie', unit: 'g/L', color: AppColors.amber)]),
    _ChartOpt(id: 'fc', label: 'Fréq. card.', capteur: 'oxymetre', chipColor: AppColors.blue,
      series: [_Serie(field: 'fc', label: 'FC', unit: 'bpm', color: AppColors.blue)]),
    _ChartOpt(id: 'spo2', label: 'SpO₂', capteur: 'oxymetre', chipColor: Color(0xFF0891B2),
      series: [_Serie(field: 'spo2', label: 'SpO₂', unit: '%', color: Color(0xFF0891B2))]),
    _ChartOpt(id: 'temp', label: 'Temp.', capteur: 'thermometre', chipColor: Color(0xFF7C3AED),
      series: [_Serie(field: 'temperature', label: 'Temp.', unit: '°C', color: Color(0xFF7C3AED))]),
    _ChartOpt(id: 'poids', label: 'Poids', capteur: 'pese_personne', chipColor: Color(0xFF6366F1),
      series: [_Serie(field: 'poids', label: 'Poids', unit: 'kg', color: Color(0xFF6366F1))]),
  ];

  static const _periodes = [
    (label: '24h', duration: Duration(hours: 24)),
    (label: '7j',  duration: Duration(days: 7)),
    (label: '14j', duration: Duration(days: 14)),
    (label: '30j', duration: Duration(days: 30)),
  ];

  String _optId    = 'tension';
  int    _periodeIdx = 1; // 7j par défaut

  _ChartOpt get _opt => _opts.firstWhere((o) => o.id == _optId);

  List<Mesure> get _donnees {
    final cutoff = DateTime.now().subtract(_periodes[_periodeIdx].duration);
    return widget.mesures
        // Filtre sur la présence du champ, pas sur le nom du capteur :
        // la FC arrive aussi via 'tensiometre' (simulation, Health Connect)
        // et le poids via 'balance' (Health Connect).
        .where((m) => m.timestamp.isAfter(cutoff) &&
            _opt.series.any((s) => m.mesures[s.field] is num))
        .toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
  }

  String _fmt(double v) =>
      v.abs() >= 10 ? v.round().toString() : v.toStringAsFixed(1);

  @override
  Widget build(BuildContext context) {
    final opt    = _opt;
    final data   = _donnees;
    final muted  = widget.mutedColor;
    final txt    = widget.textColor;
    final card   = widget.cardColor;
    final border = widget.borderColor;
    final dark   = Theme.of(context).brightness == Brightness.dark;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          // ── Sélecteur métrique — scroll horizontal ──
          SizedBox(
            height: 40,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount      : _opts.length,
              separatorBuilder: (context, index) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final o   = _opts[i];
                final sel = o.id == _optId;
                return GestureDetector(
                  onTap: () => setState(() => _optId = o.id),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 0),
                    decoration: BoxDecoration(
                      color       : sel ? o.chipColor.withValues(alpha: dark ? 0.18 : 0.1) : Colors.transparent,
                      borderRadius: BorderRadius.circular(99),
                      border      : Border.all(
                        color: sel ? o.chipColor : border,
                        width: sel ? 1.5 : 0.8,
                      ),
                    ),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Container(
                        width: 7, height: 7,
                        decoration: BoxDecoration(
                          color : sel ? o.chipColor : muted.withValues(alpha: 0.4),
                          shape : BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 7),
                      Text(o.label, style: TextStyle(
                        fontSize  : 13,
                        fontWeight: sel ? FontWeight.w600 : FontWeight.normal,
                        color     : sel ? o.chipColor : muted,
                      )),
                    ]),
                  ),
                );
              },
            ),
          ),

          const SizedBox(height: 16),

          // ── Carte graphique ──
          Container(
            padding   : const EdgeInsets.fromLTRB(16, 18, 12, 16),
            decoration: BoxDecoration(
              color       : card,
              borderRadius: BorderRadius.circular(20),
              border      : Border.all(color: border, width: 0.5),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [

                // Titre + période
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(opt.label,
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: txt)),
                          const SizedBox(height: 2),
                          Text(
                            opt.series.length == 1 ? opt.series.first.unit : opt.series.map((s) => s.unit).first,
                            style: TextStyle(fontSize: 12, color: muted),
                          ),
                        ],
                      ),
                    ),
                    // Segmented period control
                    Container(
                      decoration: BoxDecoration(
                        color       : border.withValues(alpha: 0.3),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: List.generate(_periodes.length, (i) {
                          final sel = _periodeIdx == i;
                          return GestureDetector(
                            onTap: () => setState(() => _periodeIdx = i),
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 180),
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                              decoration: BoxDecoration(
                                color       : sel ? (dark ? AppColors.darkSurface : Colors.white) : Colors.transparent,
                                borderRadius: BorderRadius.circular(7),
                                boxShadow   : sel ? [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 4, offset: const Offset(0, 1))] : null,
                              ),
                              child: Text(_periodes[i].label, style: TextStyle(
                                fontSize  : 11,
                                fontWeight: sel ? FontWeight.w600 : FontWeight.normal,
                                color     : sel ? txt : muted,
                              )),
                            ),
                          );
                        }),
                      ),
                    ),
                  ],
                ),

                // Dernière valeur
                if (data.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  _DerniereValeur(opt: opt, mesure: data.last, textColor: txt, mutedColor: muted),
                ],

                const SizedBox(height: 16),

                // Légende multi-série
                if (data.isNotEmpty && opt.series.length > 1) ...[
                  Row(children: opt.series.map((s) => Padding(
                    padding: const EdgeInsets.only(right: 18),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Container(width: 20, height: 2.5,
                          decoration: BoxDecoration(color: s.color, borderRadius: BorderRadius.circular(2))),
                      const SizedBox(width: 6),
                      Text(s.label, style: TextStyle(fontSize: 11, color: muted)),
                    ]),
                  )).toList()),
                  const SizedBox(height: 12),
                ],

                // Graphique
                SizedBox(
                  height: 230,
                  child: data.isEmpty
                      ? Center(child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.show_chart, color: muted, size: 40),
                            const SizedBox(height: 10),
                            Text(
                              'Aucune mesure sur ${_periodes[_periodeIdx].label}',
                              style: TextStyle(fontSize: 13, color: muted),
                            ),
                          ],
                        ))
                      : _TendancesChart(
                          opt       : opt,
                          mesures   : data,
                          muted     : muted,
                          border    : border,
                          isIntraday: _periodeIdx == 0,
                        ),
                ),
              ],
            ),
          ),

          // ── Stats min / moy / max ──
          if (data.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...opt.series.map((s) {
              final vals = data
                  .map((m) => m.mesures[s.field])
                  .whereType<num>()
                  .map((v) => v.toDouble())
                  .toList();
              if (vals.isEmpty) return const SizedBox.shrink();
              final minV = vals.reduce((a, b) => a < b ? a : b);
              final maxV = vals.reduce((a, b) => a > b ? a : b);
              final moy  = vals.reduce((a, b) => a + b) / vals.length;
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (opt.series.length > 1) ...[
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6, left: 2),
                        child: Row(children: [
                          Container(width: 10, height: 10,
                              decoration: BoxDecoration(color: s.color, shape: BoxShape.circle)),
                          const SizedBox(width: 6),
                          Text(s.label, style: TextStyle(fontSize: 12, color: muted, fontWeight: FontWeight.w500)),
                        ]),
                      ),
                    ],
                    Row(children: [
                      _StatTile(label: 'Minimum', value: _fmt(minV), unit: s.unit, color: AppColors.blue,   card: card, border: border, txt: txt, muted: muted),
                      const SizedBox(width: 8),
                      _StatTile(label: 'Moyenne', value: _fmt(moy),  unit: s.unit, color: s.color,          card: card, border: border, txt: txt, muted: muted),
                      const SizedBox(width: 8),
                      _StatTile(label: 'Maximum', value: _fmt(maxV), unit: s.unit, color: AppColors.red,    card: card, border: border, txt: txt, muted: muted),
                    ]),
                  ],
                ),
              );
            }),
          ],

          const SizedBox(height: 4),
          Text(
            '${data.length} mesure${data.length > 1 ? 's' : ''} · ${_periodes[_periodeIdx].label}',
            style: TextStyle(fontSize: 11, color: muted),
          ),
        ],
      ),
    );
  }
}

// ── Dernière valeur ───────────────────────────────────────

class _DerniereValeur extends StatelessWidget {
  final _ChartOpt opt;
  final Mesure    mesure;
  final Color     textColor, mutedColor;
  const _DerniereValeur({required this.opt, required this.mesure, required this.textColor, required this.mutedColor});

  @override
  Widget build(BuildContext context) {
    // Construire la chaîne valeur (ex: "124 / 82" pour tension, "1.3" pour glycémie)
    final parts = <String>[];
    for (final s in opt.series) {
      final v = mesure.mesures[s.field];
      if (v != null) {
        final n = (v as num).toDouble();
        parts.add(n.abs() >= 10 ? n.round().toString() : n.toStringAsFixed(1));
      }
    }
    if (parts.isEmpty) return const SizedBox.shrink();
    final d = mesure.timestamp.toLocal();
    final ts   = '${d.day.toString().padLeft(2,'0')}/${d.month.toString().padLeft(2,'0')} '
                 '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
    return Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Text(parts.join(' / '), style: TextStyle(
        fontSize  : 22,
        fontWeight: FontWeight.w700,
        color     : opt.chipColor,
        height    : 1,
      )),
      const Spacer(),
      Text(ts, style: TextStyle(fontSize: 11, color: mutedColor)),
    ]);
  }
}

// ── Tuile statistique ─────────────────────────────────────

class _StatTile extends StatelessWidget {
  final String label, value, unit;
  final Color  color, card, border, txt, muted;
  const _StatTile({
    required this.label, required this.value, required this.unit,
    required this.color, required this.card,  required this.border,
    required this.txt,   required this.muted,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding   : const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
        decoration: BoxDecoration(
          color       : card,
          borderRadius: BorderRadius.circular(14),
          border      : Border.all(color: border, width: 0.5),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: TextStyle(fontSize: 10, color: muted)),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: color, height: 1)),
          const SizedBox(height: 2),
          Text(unit,  style: TextStyle(fontSize: 10, color: muted)),
        ]),
      ),
    );
  }
}

// ── Graphique fl_chart ────────────────────────────────────

class _TendancesChart extends StatelessWidget {
  final _ChartOpt    opt;
  final List<Mesure> mesures;
  final Color        muted, border;
  final bool         isIntraday;
  const _TendancesChart({
    required this.opt, required this.mesures,
    required this.muted, required this.border,
    this.isIntraday = false,
  });

  @override
  Widget build(BuildContext context) {
    final multi    = opt.series.length > 1;
    final spotsMap = <String, List<FlSpot>>{};
    for (var i = 0; i < mesures.length; i++) {
      for (final s in opt.series) {
        final v = mesures[i].mesures[s.field];
        if (v != null) {
          spotsMap.putIfAbsent(s.field, () => []).add(
            FlSpot(i.toDouble(), (v as num).toDouble()),
          );
        }
      }
    }

    final allVals = spotsMap.values.expand((l) => l.map((s) => s.y)).toList();
    if (allVals.isEmpty) return const SizedBox.shrink();

    final minV = allVals.reduce((a, b) => a < b ? a : b);
    final maxV = allVals.reduce((a, b) => a > b ? a : b);
    final pad  = maxV == minV ? maxV * 0.08 + 5 : (maxV - minV) * 0.25;
    final yMin = (minV - pad).floorToDouble();
    final yMax = (maxV + pad).ceilToDouble();
    final n    = mesures.length;
    final xInterval = (n / 4).clamp(1.0, n.toDouble()).ceilToDouble();

    String xLabel(int i) {
      final d = mesures[i].timestamp.toLocal();
      if (isIntraday) {
        return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
      }
      return '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}';
    }

    return LineChart(
      LineChartData(
        minX: -0.5,
        maxX: (n - 1) + 0.5,
        minY: yMin,
        maxY: yMax,
        clipData: const FlClipData.all(),
        gridData: FlGridData(
          show             : true,
          drawVerticalLine : false,
          horizontalInterval: (yMax - yMin) / 4,
          getDrawingHorizontalLine: (_) => FlLine(
            color: border.withValues(alpha: 0.25), strokeWidth: 0.5,
            dashArray: [4, 6],
          ),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles  : const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles : AxisTitles(
            sideTitles: SideTitles(
              showTitles  : true,
              reservedSize: 38,
              interval    : (yMax - yMin) / 3,
              getTitlesWidget: (v, meta) {
                if (v == meta.min || v == meta.max) return const SizedBox.shrink();
                return Text(
                  v.round().toString(),
                  style: TextStyle(fontSize: 9, color: muted),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles  : true,
              reservedSize: 24,
              interval    : xInterval,
              getTitlesWidget: (v, _) {
                final i = v.round();
                if ((v - i).abs() > 0.01 || i < 0 || i >= n) return const SizedBox.shrink();
                return Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(xLabel(i), style: TextStyle(fontSize: 9, color: muted)),
                );
              },
            ),
          ),
        ),
        lineBarsData: opt.series.map((s) {
          final spots = spotsMap[s.field] ?? [];
          return LineChartBarData(
            spots          : spots,
            color          : s.color,
            barWidth       : 2,
            isCurved       : true,
            curveSmoothness: 0.5,
            preventCurveOverShooting: true,
            dotData: FlDotData(
              show: true,
              getDotPainter: (spot, p, bar, idx) {
                final i = spot.x.toInt();
                final anomaly = i < mesures.length && mesures[i].anomalie;
                if (anomaly) {
                  return FlDotCirclePainter(
                    radius     : 3,
                    color      : AppColors.red,
                    strokeColor: AppColors.red.withValues(alpha: 0.20),
                    strokeWidth: 2,
                  );
                }
                if (!isIntraday) {
                  return FlDotCirclePainter(
                    radius: 0, color: Colors.transparent,
                    strokeColor: Colors.transparent, strokeWidth: 0,
                  );
                }
                return FlDotCirclePainter(
                  radius     : 3,
                  color      : Colors.transparent,
                  strokeColor: bar.color ?? s.color,
                  strokeWidth: 1.5,
                );
              },
            ),
            belowBarData: multi
                ? BarAreaData(show: false)
                : BarAreaData(
                    show    : true,
                    gradient: LinearGradient(
                      begin : Alignment.topCenter,
                      end   : Alignment.bottomCenter,
                      stops : const [0.0, 0.4, 1.0],
                      colors: [
                        s.color.withValues(alpha: 0.18),
                        s.color.withValues(alpha: 0.05),
                        s.color.withValues(alpha: 0.0),
                      ],
                    ),
                  ),
          );
        }).toList(),
        lineTouchData: LineTouchData(
          handleBuiltInTouches: true,
          getTouchedSpotIndicator: (barData, spotIndexes) =>
              spotIndexes.map((i) => TouchedSpotIndicatorData(
                FlLine(
                  color      : barData.color?.withValues(alpha: 0.5) ?? Colors.white24,
                  strokeWidth: 1,
                ),
                FlDotData(getDotPainter: (spot, pct, bar, idx) => FlDotCirclePainter(
                  radius     : 2.5,
                  color      : bar.color ?? Colors.white,
                  strokeColor: Colors.white,
                  strokeWidth: 1.5,
                )),
              )).toList(),
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor    : (_) => const Color(0xFF1A2535),
            tooltipRoundedRadius: 12,
            tooltipPadding     : const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            getTooltipItems: (spots) => spots.map((s) {
              final serie = opt.series[s.barIndex];
              final i     = s.x.toInt();
              final d     = i < mesures.length ? mesures[i].timestamp.toLocal() : null;
              final ts    = d != null
                  ? '${d.day.toString().padLeft(2,'0')}/${d.month.toString().padLeft(2,'0')} '
                    '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}'
                  : '';
              final val = s.y % 1 == 0 ? s.y.round().toString() : s.y.toStringAsFixed(1);
              return LineTooltipItem(
                '$val ${serie.unit}',
                TextStyle(color: serie.color, fontSize: 13, fontWeight: FontWeight.w700),
                children: [TextSpan(
                  text: '\n$ts',
                  style: const TextStyle(color: Colors.white54, fontSize: 10, fontWeight: FontWeight.normal),
                )],
              );
            }).toList(),
          ),
        ),
      ),
    );
  }
}