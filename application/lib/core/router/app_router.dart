// lib/core/router/app_router.dart
// Navigation de l'app — go_router
// Redirige vers login si non connecté

import 'package:go_router/go_router.dart';
import '../../core/providers/auth_provider.dart';
import '../../features/auth/login_screen.dart';
import '../../features/main_shell.dart';
import '../../features/dashboard/dashboard_screen.dart';
import '../../features/mesures/mesures_screen.dart';
import '../../features/ble/ble_screen.dart';
import '../../features/alertes/alertes_screen.dart';
import '../../features/profil/profil_screen.dart';

class AppRouter {
  static GoRouter router(AuthProvider auth) => GoRouter(
    initialLocation: '/dashboard',
    redirect: (context, state) {
      final connecte = auth.connecte;
      final login    = state.matchedLocation == '/login';
      if (!connecte && !login) return '/login';
      if (connecte  &&  login) return '/dashboard';
      return null;
    },
    refreshListenable: auth,
    routes: [
      // Login — pas de shell
      GoRoute(
        path    : '/login',
        builder : (ctx, _) => const LoginScreen(),
      ),

      // Shell — navigation bottom tab
      ShellRoute(
        builder: (ctx, state, child) => MainShell(child: child),
        routes: [
          GoRoute(path: '/dashboard', builder: (ctx, _) => const DashboardScreen()),
          GoRoute(path: '/mesures',   builder: (ctx, _) => const MesuresScreen()),
          GoRoute(path: '/ble',       builder: (ctx, _) => const BleScreen()),
          GoRoute(path: '/alertes',   builder: (ctx, _) => const AlertesScreen()),
          GoRoute(path: '/profil',    builder: (ctx, _) => const ProfilScreen()),
        ],
      ),
    ],
  );
}