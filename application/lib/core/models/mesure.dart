// lib/core/models/mesure.dart

import 'dart:convert';

class Mesure {
  final int    id;
  final String capteur;
  final DateTime timestamp;
  final Map<String, dynamic> mesures;
  final bool anomalie;
  final bool deferred;

  const Mesure({
    required this.id,
    required this.capteur,
    required this.timestamp,
    required this.mesures,
    required this.anomalie,
    required this.deferred,
  });

  factory Mesure.fromJson(Map<String, dynamic> json) => Mesure(
    id        : json['id']        as int,
    capteur   : json['capteur']   as String,
    timestamp : DateTime.parse(json['timestamp'] as String),
    mesures   : json['mesures'] is String
        ? (jsonDecode(json['mesures'] as String) as Map<String, dynamic>? ?? {})
        : (json['mesures'] as Map<String, dynamic>? ?? {}),
    anomalie  : json['anomalie']  as bool? ?? false,
    deferred  : json['deferred']  as bool? ?? false,
  );

  // Résumé lisible des valeurs mesurées
  String get resume {
    return mesures.entries
        .map((e) => '${e.key}: ${e.value}')
        .join(' · ');
  }
}