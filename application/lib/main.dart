// lib/main.dart
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'core/providers/auth_provider.dart';
import 'core/providers/theme_provider.dart';
import 'core/theme/app_theme.dart';
import 'core/router/app_router.dart';
import 'core/providers/ble_provider.dart';
import 'core/providers/alertes_provider.dart';
import 'core/providers/connectivite_provider.dart';
import 'core/providers/health_connect_provider.dart';
import 'core/providers/profil_medical_provider.dart';
import 'core/providers/source_donnees_sante_provider.dart';
import 'core/services/api_service.dart';
import 'core/services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp();
  await NotificationService.init();

  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()..verifierSession()),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider(create: (_) => BleProvider()),
        ChangeNotifierProvider(create: (_) => AlertesProvider()),
        ChangeNotifierProvider(create: (_) => ConnectiviteProvider()),
        ChangeNotifierProvider(create: (_) => HealthConnectProvider()),
        ChangeNotifierProxyProvider<AuthProvider, ProfilMedicalProvider>(
          create: (_) => ProfilMedicalProvider(),
          update: (_, auth, profil) {
            profil!.mettreAJourPatient(auth.connecte ? auth.patientId : null);
            return profil;
          },
        ),
        ChangeNotifierProxyProvider2<BleProvider, HealthConnectProvider,
            SourceDonneesSanteProvider>(
          create: (ctx) => SourceDonneesSanteProvider(
            ctx.read<BleProvider>(),
            ctx.read<HealthConnectProvider>(),
          ),
          update: (_, ble, hc, prev) => prev!,
        ),
      ],
      child: const StopMntApp(),
    ),
  );
}

class StopMntApp extends StatefulWidget {
  const StopMntApp({super.key});

  @override
  State<StopMntApp> createState() => _StopMntAppState();
}

class _StopMntAppState extends State<StopMntApp> {
  GoRouter? _router;

  @override
  void initState() {
    super.initState();
    // Traiter la route en attente (app tuée + tap sur notification)
    WidgetsBinding.instance.addPostFrameCallback((_) {
      NotificationService.processPendingRoute();
    });
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final authProvider  = context.watch<AuthProvider>();

    _router ??= AppRouter.router(authProvider);

    // Injecter le callback de navigation pour les notifications
    NotificationService.onNavigate = (route) {
      if (authProvider.connecte) _router?.go(route);
    };

    // Rafraîchir la liste des alertes dès réception d'un message FCM foreground
    NotificationService.onNouvelleAlerte = () {
      context.read<AlertesProvider>().charger();
    };

    // Signaler la joignabilité du serveur à chaque appel API
    final connectivite = context.read<ConnectiviteProvider>();
    ApiService.onConnectivite = connectivite.mettreAJour;

    // Au retour du réseau : pousser un profil médical modifié hors-ligne
    connectivite.onReconnexion = () {
      context.read<ProfilMedicalProvider>().synchroniser();
    };

    // N'importe quel 401 (provider, écran, file hors-ligne) → retour au login
    ApiService.onTokenExpire = authProvider.gererTokenExpire;

    authProvider.onLogout = () {
      final ble = context.read<BleProvider>();
      if (ble.simulation) ble.arreterSimulation();
      if (ble.connecte)   ble.deconnecter();
      ble.effacerCapteurs();
      context.read<AlertesProvider>().arreterPoll();
      context.read<HealthConnectProvider>()
        ..arreterPoll()
        ..oublierEnvois();
    };

    return MaterialApp.router(
      title          : 'STOP-MNT',
      debugShowCheckedModeBanner: false,
      themeMode      : themeProvider.mode,
      theme          : AppTheme.light(),
      darkTheme      : AppTheme.dark(),
      routerConfig   : _router!,
    );
  }
}
