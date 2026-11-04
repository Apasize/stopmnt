import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:stopmnt_app/core/models/alerte.dart';
import 'package:stopmnt_app/core/models/mesure.dart';
import 'package:stopmnt_app/core/providers/profil_medical_provider.dart';
import 'package:stopmnt_app/core/services/api_service.dart';
import 'package:stopmnt_app/core/services/demo_backend.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    ApiService.activerModeDemo(true);
  });

  tearDown(() => ApiService.activerModeDemo(false));

  group('Mode démo — ApiService', () {
    test('historique et alertes au format de l\'API', () async {
      final hist = await ApiService.getHistoriqueMesures(limite: 100);
      expect(hist, isNotEmpty);
      final mesures = hist.map((j) => Mesure.fromJson(j)).toList();
      expect(mesures.map((m) => m.capteur).toSet(),
          containsAll(['tensiometre', 'glucometre', 'oxymetre']));

      final alertes = (await ApiService.getMesAlertes())
          .map((j) => Alerte.fromJson(j))
          .toList();
      expect(alertes.any((a) => a.estCritique), isTrue);
    });

    test('une mesure envoyée apparaît dans l\'historique', () async {
      final r = await ApiService.envoyerMesure(
        capteur: 'glucometre', mesures: {'glycemie': 0.95},
      );
      expect(r['differe'], isNot(true));
      final hist = await ApiService.getHistoriqueMesures(limite: 1);
      expect(Mesure.fromJson(hist.first).mesures['glycemie'], 0.95);
    });

    test('anomalie → alerte, sans spam sur envois rapprochés', () async {
      final avant = (await ApiService.getMesAlertes()).length;
      final r1 = await ApiService.envoyerMesure(
        capteur: 'tensiometre', mesures: {'systolique': 150, 'diastolique': 95},
      );
      final r2 = await ApiService.envoyerMesure(
        capteur: 'tensiometre', mesures: {'systolique': 152, 'diastolique': 96},
      );
      expect(r1['anomalie'], isTrue);
      expect(r1['alerte'], isNotNull);
      expect(r2['anomalie'], isTrue);
      expect(r2['alerte'], isNull);
      expect((await ApiService.getMesAlertes()).length, avant + 1);
    });
  });

  group('ProfilMedicalProvider', () {
    test('charge le profil du patient, vide tout à la déconnexion', () async {
      final p = ProfilMedicalProvider();
      var notifs = 0;
      p.addListener(() => notifs++);

      // Appelé pendant un build par le ProxyProvider : aucune notif synchrone
      p.mettreAJourPatient(DemoBackend.patientId);
      expect(notifs, 0);

      await Future<void>.delayed(const Duration(seconds: 1));
      expect(p.groupeSanguin, 'O+');
      expect(p.chargement, isFalse);

      p.mettreAJourPatient(null);
      expect(p.groupeSanguin, isNull);
    });

    test('sauvegarde synchronisée → plus rien en attente', () async {
      final p = ProfilMedicalProvider()..mettreAJourPatient(DemoBackend.patientId);
      await Future<void>.delayed(const Duration(seconds: 1));
      await p.sauvegarder(
        groupeSanguin: 'A-', antecedents: [], maladiesChroniques: ['Diabète type 2'],
        traitements: [],
      );
      expect(p.aSynchroniser, isFalse);
      expect((await DemoBackend.profilMedical())['groupe_sanguin'], 'A-');
    });
  });
}
