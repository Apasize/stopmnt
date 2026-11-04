// lib/features/main_shell.dart
// Shell de navigation — bottom navigation bar
// Contient les 5 onglets de l'app

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../core/models/alerte.dart';
import '../core/providers/alertes_provider.dart';
import '../core/providers/auth_provider.dart';
import '../core/providers/connectivite_provider.dart';
import '../core/providers/health_connect_provider.dart';
import '../core/theme/app_theme.dart';
import '../core/widgets/alerte_banner.dart';

class MainShell extends StatefulWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  AlertesProvider?      _alertesProvider;
  final List<OverlayEntry> _bannerEntries = [];

  static const _routes = [
    '/dashboard', '/mesures', '/ble', '/alertes', '/profil'
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_alertesProvider == null) {
      _alertesProvider = context.read<AlertesProvider>();
      _alertesProvider!.addListener(_onAlertesChange);
      _alertesProvider!.demarrerPoll();
      // Différé : charger() notifie, interdit pendant didChangeDependencies
      final hc = context.read<HealthConnectProvider>();
      Future.microtask(hc.reprendrePoll);
    }
  }

  @override
  void dispose() {
    _alertesProvider?.removeListener(_onAlertesChange);
    _alertesProvider?.arreterPoll();
    for (final e in _bannerEntries) {
      try { e.remove(); } catch (_) {}
    }
    _bannerEntries.clear();
    super.dispose();
  }

  void _onAlertesChange() {
    final provider  = _alertesProvider;
    if (provider == null) return;
    final nouvelles = provider.nouvellesAlertes;
    if (nouvelles.isEmpty) return;
    // Capturer la liste avant de la vider
    final copies = List<Alerte>.from(nouvelles);
    provider.marquerVues();
    for (int i = 0; i < copies.length; i++) {
      Future.delayed(Duration(milliseconds: i * 600), () {
        if (mounted) _afficherBanner(copies[i]);
      });
    }
  }

  void _afficherBanner(Alerte alerte) {
    late OverlayEntry entry;

    void remove() {
      if (_bannerEntries.contains(entry)) {
        try { entry.remove(); } catch (_) {}
        _bannerEntries.remove(entry);
      }
    }

    entry = OverlayEntry(
      builder: (ctx) => Positioned(
        top: 0, left: 0, right: 0,
        child: Material(
          color: Colors.transparent,
          child: AlerteBanner(alerte: alerte, onDismiss: remove),
        ),
      ),
    );

    _bannerEntries.add(entry);
    Overlay.of(context).insert(entry);
  }

  int _indexCourant(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith('/dashboard')) return 0;
    if (location.startsWith('/mesures'))   return 1;
    if (location.startsWith('/ble'))       return 2;
    if (location.startsWith('/alertes'))   return 3;
    if (location.startsWith('/profil'))    return 4;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final index     = _indexCourant(context);
    final connectivite = context.watch<ConnectiviteProvider>();
    final joignable    = connectivite.joignable;
    final nbEnAttente  = connectivite.nbEnAttente;
    final modeDemo     = context.select<AuthProvider, bool>((a) => a.modeDemo);
    return Scaffold(
      body: widget.child,
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (modeDemo) const _BanniereDemo(),
          AnimatedSize(
            duration: const Duration(milliseconds: 250),
            curve   : Curves.easeInOut,
            child   : joignable && nbEnAttente == 0
                ? const SizedBox.shrink()
                : _BanniereServeur(joignable: joignable, nbEnAttente: nbEnAttente),
          ),
          NavigationBar(
        selectedIndex        : index,
        onDestinationSelected: (i) => context.go(_routes[i]),
        destinations         : const [
          NavigationDestination(
            icon        : Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label       : 'Accueil',
          ),
          NavigationDestination(
            icon        : Icon(Icons.monitor_heart_outlined),
            selectedIcon: Icon(Icons.monitor_heart),
            label       : 'Mesures',
          ),
          NavigationDestination(
            icon        : Icon(Icons.bluetooth_outlined),
            selectedIcon: Icon(Icons.bluetooth),
            label       : 'Capteurs',
          ),
          NavigationDestination(
            icon        : Icon(Icons.notifications_outlined),
            selectedIcon: Icon(Icons.notifications),
            label       : 'Alertes',
          ),
          NavigationDestination(
            icon        : Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label       : 'Profil',
          ),
        ],
      ),
        ],
      ),
    );
  }
}

class _BanniereDemo extends StatelessWidget {
  const _BanniereDemo();

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width  : double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 20),
      decoration: BoxDecoration(
        color : AppColors.blue.withValues(alpha: dark ? 0.12 : 0.08),
        border: const Border(top: BorderSide(color: AppColors.blue, width: 0.5)),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.science_outlined, size: 12, color: AppColors.blue),
          SizedBox(width: 6),
          Flexible(
            child: Text(
              'Mode démo — données fictives, hors serveur',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 11, color: AppColors.blue, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

class _BanniereServeur extends StatelessWidget {
  final bool joignable;
  final int  nbEnAttente;
  const _BanniereServeur({required this.joignable, required this.nbEnAttente});

  @override
  Widget build(BuildContext context) {
    final dark     = Theme.of(context).brightness == Brightness.dark;
    final enLigne  = joignable;
    final couleur  = enLigne ? AppColors.green : AppColors.amber;
    final icone    = enLigne ? Icons.cloud_done_outlined : Icons.cloud_off_outlined;

    String label;
    if (!enLigne) {
      label = nbEnAttente > 0
          ? 'Hors ligne — $nbEnAttente mesure${nbEnAttente > 1 ? 's' : ''} en attente'
          : 'Serveur inaccessible';
    } else {
      // En ligne mais queue en cours de vidage
      label = nbEnAttente > 0
          ? 'Reconnecté — envoi de $nbEnAttente mesure${nbEnAttente > 1 ? 's' : ''}…'
          : 'Serveur inaccessible';
    }

    return Container(
      width  : double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 20),
      decoration: BoxDecoration(
        color: couleur.withValues(alpha: dark ? 0.12 : 0.08),
        border: Border(
          top: BorderSide(color: couleur, width: 0.5),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icone, size: 12, color: couleur),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize  : 11,
              color     : couleur,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
