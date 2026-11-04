// lib/core/models/alerte.dart
class Alerte {
  final int      id;
  final String?  patientId;
  final String?  departement;
  final String   capteur;
  final String   niveau;
  final String   message;
  final DateTime timestamp;
  final bool     acquittee;

  const Alerte({
    required this.id,
    this.patientId,
    this.departement,
    required this.capteur,
    required this.niveau,
    required this.message,
    required this.timestamp,
    required this.acquittee,
  });

  factory Alerte.fromJson(Map<String, dynamic> json) => Alerte(
    id          : json['id']                       as int,
    patientId   : json['patient_id']               as String?,
    departement : json['departement']              as String?,
    capteur     : json['capteur']                  as String,
    niveau      : json['niveau']                   as String,
    message     : json['message']                  as String,
    timestamp   : DateTime.parse(json['timestamp'] as String),
    // acquittee peut être absent dans /mes-alertes
    acquittee   : json['acquittee']                as bool? ?? false,
  );

  bool get estCritique => niveau == 'critique';
}