// lib/core/models/patient.dart
// Modèle de données patient — correspond à la réponse de l'API

class Patient {
  final String patientId;
  final String email;
  final String? nom;
  final String? prenom;
  final String departement;
  final DateTime dateInscription;
  final bool actif;

  const Patient({
    required this.patientId,
    required this.email,
    this.nom,
    this.prenom,
    required this.departement,
    required this.dateInscription,
    required this.actif,
  });

  factory Patient.fromJson(Map<String, dynamic> json) => Patient(
    patientId       : json['patient_id'] as String,
    email           : json['email']      as String,
    nom             : json['nom']        as String?,
    prenom          : json['prenom']     as String?,
    departement     : json['departement'] as String,
    dateInscription : DateTime.parse(json['date_inscription'] as String),
    actif           : json['actif']      as bool? ?? true,
  );

  String get nomComplet {
    if (prenom != null && nom != null) return '$prenom $nom';
    return patientId;
  }

  String get initiales {
    if (prenom != null && nom != null) {
      return '${prenom![0]}${nom![0]}'.toUpperCase();
    }
    return patientId.substring(0, 2).toUpperCase();
  }
}