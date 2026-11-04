// lib/core/services/notification_service.dart
// Notifications push (FCM) + notifications locales (flutter_local_notifications)
// Gère les 3 états : app ouverte, en arrière-plan, fermée

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'api_service.dart';

// Handler background — doit être une fonction top-level (pas dans une classe)
// FCM appelle cette fonction dans un isolate séparé quand l'app est en arrière-plan
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Les messages avec champ "notification" sont affichés automatiquement par FCM.
  // Rien à faire ici sauf pour les messages data-only (sans notification).
}

class NotificationService {
  static final _messaging          = FirebaseMessaging.instance;
  static final _localNotifications = FlutterLocalNotificationsPlugin();

  static String? _pendingRoute;
  static String? _fcmToken;

  // Injecté par main.dart
  static void Function(String route)? onNavigate;
  // Appelé à la réception d'un message FCM foreground pour rafraîchir la liste
  static VoidCallback? onNouvelleAlerte;

  static const _channelId          = 'stopmnt_alertes';
  static const _channelNom         = 'Alertes médicales STOP-MNT';
  static const _channelDescription = 'Alertes sur vos données de santé';

  static Future<void> init() async {
    // Enregistrer le handler background
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

    // Tout ce qui touche FCM/Play Services est dans un try/catch global —
    // un appareil sans Play Services ne doit pas empêcher le démarrage de l'app.
    try {
      // Demander la permission de notifier (Android 13+ / iOS)
      await _messaging.requestPermission(
        alert      : true,
        badge      : true,
        sound      : true,
        provisional: false,
      );

      // Message reçu quand l'app est au premier plan → afficher une notif locale
      FirebaseMessaging.onMessage.listen(_afficherDepuisMessage);

      // L'utilisateur a tapé la notif FCM depuis l'arrière-plan
      FirebaseMessaging.onMessageOpenedApp.listen((_) {
        onNavigate?.call('/alertes');
      });

      // L'utilisateur a tapé la notif FCM depuis l'app fermée
      final initial = await _messaging.getInitialMessage();
      if (initial != null) _pendingRoute = '/alertes';

      // getToken() lève SERVICE_NOT_AVAILABLE sur appareil sans Play Services
      try {
        _fcmToken = await _messaging.getToken();
      } catch (_) {}

      // Mettre à jour si Firebase régénère le token
      _messaging.onTokenRefresh.listen((t) { _fcmToken = t; });
    } catch (_) {}

    // Créer le canal de notification Android 8+ (local_notifications — pas FCM)
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(
          const AndroidNotificationChannel(
            _channelId,
            _channelNom,
            description : _channelDescription,
            importance  : Importance.high,
          ),
        );

    // Initialiser flutter_local_notifications
    await _localNotifications.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
      onDidReceiveNotificationResponse: (details) {
        onNavigate?.call('/alertes');
      },
    );
  }

  /// À appeler après un login ou verifierSession() réussi.
  static Future<void> enregistrerToken() async {
    if (_fcmToken != null) await ApiService.enregistrerTokenFcm(_fcmToken!);
  }

  // Appeler après que le router est prêt (dans le premier postFrameCallback)
  static void processPendingRoute() {
    if (_pendingRoute != null) {
      final route = _pendingRoute!;
      _pendingRoute = null;
      onNavigate?.call(route);
    }
  }

  // Afficher depuis un message FCM reçu en foreground
  static Future<void> _afficherDepuisMessage(RemoteMessage message) async {
    final notif = message.notification;
    if (notif == null) return;
    final critique = message.data['niveau'] == 'critique';
    await _afficher(
      id      : message.hashCode,
      titre   : notif.title ?? 'STOP-MNT',
      corps   : notif.body  ?? '',
      critique: critique,
    );
    // Rafraîchir immédiatement la liste des alertes dans l'app
    onNouvelleAlerte?.call();
  }

  // Afficher depuis le polling (AlertesProvider a détecté une nouvelle alerte)
  static Future<void> afficherAlerteLocale({
    required int    id,
    required String message,
    required bool   critique,
  }) =>
      _afficher(
        id      : id,
        titre   : critique
            ? 'Alerte critique — STOP-MNT'
            : 'Nouvelle alerte — STOP-MNT',
        corps   : message,
        critique: critique,
      );

  static Future<void> _afficher({
    required int    id,
    required String titre,
    required String corps,
    required bool   critique,
  }) async {
    await _localNotifications.show(
      id,
      titre,
      corps,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelNom,
          channelDescription : _channelDescription,
          importance         : Importance.high,
          priority           : Priority.high,
          icon               : '@mipmap/ic_launcher',
          color              : critique
              ? const Color(0xFFEF4444)
              : const Color(0xFFF59E0B),
        ),
      ),
    );
  }
}
