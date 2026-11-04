// lib/features/ble/qr_scanner_screen.dart
// Scan du QR code de la montre pour extraire le token d'appairage.
// Retourne le token (String) via Navigator.pop ou null si annulé.

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../core/theme/app_theme.dart';

class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({super.key});

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> {
  final MobileScannerController _ctrl = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  bool _traite = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_traite) return;
    final raw = capture.barcodes.firstOrNull?.rawValue;
    if (raw == null || raw.isEmpty) return;

    // Extraire le token : on accepte soit un nombre pur (48218648),
    // soit une URL/deeplink contenant le token en paramètre ou en chemin.
    final token = _extraireToken(raw);
    if (token == null) return;

    _traite = true;
    _ctrl.stop();
    Navigator.of(context).pop(token);
  }

  // Extrait un token de 4 à 10 chiffres depuis un contenu QR quelconque.
  // Cas 1 : QR = "48218648" (nombre brut)
  // Cas 2 : QR = "https://xxx?token=48218648" ou "/pair/48218648"
  static String? _extraireToken(String raw) {
    final trimmed = raw.trim();

    // Nombre brut pur
    if (RegExp(r'^\d{4,10}$').hasMatch(trimmed)) return trimmed;

    // Hex pur 8 chars (AABBCCDD)
    if (RegExp(r'^[0-9a-fA-F]{8}$').hasMatch(trimmed)) return trimmed;

    // Chercher un nombre de 6-10 chiffres dans la chaîne
    final match = RegExp(r'\d{6,10}').firstMatch(trimmed);
    if (match != null) return match.group(0);

    return null;
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Scanner le QR de la montre'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(null),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.flash_on_outlined),
            tooltip: 'Lampe torche',
            onPressed: () => _ctrl.toggleTorch(),
          ),
        ],
      ),
      body: Stack(
        children: [
          MobileScanner(
            controller: _ctrl,
            onDetect  : _onDetect,
          ),
          // Viseur central
          Center(
            child: Container(
              width : 220,
              height: 220,
              decoration: BoxDecoration(
                border: Border.all(color: AppColors.blue, width: 2.5),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
          ),
          // Instruction bas
          Positioned(
            bottom: 48,
            left  : 0,
            right : 0,
            child : Container(
              margin : const EdgeInsets.symmetric(horizontal: 32),
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 20),
              decoration: BoxDecoration(
                color       : Colors.black.withValues(alpha: 0.65),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                'Pointez sur le QR code affiché dans\nles réglages de la montre ou l\'app Oraimo Health',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color    : dark ? AppColors.darkText : Colors.white,
                  fontSize : 13,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
