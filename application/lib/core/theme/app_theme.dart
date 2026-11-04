// lib/core/theme/app_theme.dart
// Système de design STOP-MNT
// Définit les couleurs, typographie et composants pour les deux modes

import 'package:flutter/material.dart';

class AppColors {
  // ── Couleurs communes ─────────────────────────────────
  static const blue        = Color(0xFF378ADD);
  static const blueLight   = Color(0xFFB5D4F4);
  static const blueDark    = Color(0xFF185FA5);

  static const green       = Color(0xFF1D9E75);
  static const greenLight  = Color(0xFF9FE1CB);
  static const greenDark   = Color(0xFF0F6E56);

  static const red         = Color(0xFFE24B4A);
  static const redLight    = Color(0xFFF7C1C1);
  static const redDark     = Color(0xFFA32D2D);

  static const amber       = Color(0xFFEF9F27);
  static const amberLight  = Color(0xFFFAC775);
  static const amberDark   = Color(0xFFBA7517);

  // ── Mode sombre ───────────────────────────────────────
  static const darkBg        = Color(0xFF0F1117);
  static const darkSurface   = Color(0xFF1A1E2E);
  static const darkCard      = Color(0xFF1E2338);
  static const darkBorder    = Color(0xFF2A2F45);
  static const darkText      = Color(0xFFE8EAF0);
  static const darkTextMuted = Color(0xFF8B8FA8);
  static const darkTextHint  = Color(0xFF5F6480);

  // ── Mode clair ────────────────────────────────────────
  static const lightBg        = Color(0xFFF4F5F7);
  static const lightSurface   = Color(0xFFFFFFFF);
  static const lightCard      = Color(0xFFFFFFFF);
  static const lightBorder    = Color(0xFFE8EAF0);
  static const lightText      = Color(0xFF1A1E2E);
  static const lightTextMuted = Color(0xFF6B7080);
  static const lightTextHint  = Color(0xFF9CA3AF);
}

class AppTheme {

  // ── Thème clair ───────────────────────────────────────
  static ThemeData light() => ThemeData(
    useMaterial3      : true,
    brightness        : Brightness.light,
    scaffoldBackgroundColor : AppColors.lightBg,
    colorScheme       : ColorScheme.light(
      primary         : AppColors.blue,
      secondary       : AppColors.green,
      error           : AppColors.red,
      surface         : AppColors.lightSurface,
    ),
    cardTheme         : CardThemeData(
      color           : AppColors.lightCard,
      elevation       : 0,
      shape           : RoundedRectangleBorder(
        borderRadius  : BorderRadius.circular(16),
        side          : const BorderSide(color: AppColors.lightBorder, width: 0.5),
      ),
    ),
    appBarTheme       : const AppBarTheme(
      backgroundColor : AppColors.lightBg,
      elevation       : 0,
      scrolledUnderElevation: 0,
      foregroundColor : AppColors.lightText,
      titleTextStyle  : TextStyle(
        fontSize      : 17,
        fontWeight    : FontWeight.w500,
        color         : AppColors.lightText,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor     : AppColors.lightSurface,
      indicatorColor      : AppColors.blue.withValues(alpha: 0.12),
      labelTextStyle      : WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const TextStyle(fontSize: 10, color: AppColors.blue, fontWeight: FontWeight.w500);
        }
        return const TextStyle(fontSize: 10, color: AppColors.lightTextMuted);
      }),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled            : true,
      fillColor         : AppColors.lightBg,
      border            : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.lightBorder, width: 0.5),
      ),
      enabledBorder     : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.lightBorder, width: 0.5),
      ),
      focusedBorder     : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.blue, width: 1.5),
      ),
      contentPadding    : const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    textTheme           : _textTheme(AppColors.lightText, AppColors.lightTextMuted),
    fontFamily          : 'Inter',
  );

  // ── Thème sombre ──────────────────────────────────────
  static ThemeData dark() => ThemeData(
    useMaterial3      : true,
    brightness        : Brightness.dark,
    scaffoldBackgroundColor : AppColors.darkBg,
    colorScheme       : ColorScheme.dark(
      primary         : AppColors.blue,
      secondary       : AppColors.green,
      error           : AppColors.red,
      surface         : AppColors.darkSurface,
    ),
    cardTheme         : CardThemeData(
      color           : AppColors.darkSurface,
      elevation       : 0,
      shape           : RoundedRectangleBorder(
        borderRadius  : BorderRadius.circular(16),
        side          : const BorderSide(color: AppColors.darkBorder, width: 0.5),
      ),
    ),
    appBarTheme       : const AppBarTheme(
      backgroundColor : AppColors.darkBg,
      elevation       : 0,
      scrolledUnderElevation: 0,
      foregroundColor : AppColors.darkText,
      titleTextStyle  : TextStyle(
        fontSize      : 17,
        fontWeight    : FontWeight.w500,
        color         : AppColors.darkText,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor     : AppColors.darkSurface,
      indicatorColor      : AppColors.blue.withValues(alpha: 0.15),
      labelTextStyle      : WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const TextStyle(fontSize: 10, color: AppColors.blue, fontWeight: FontWeight.w500);
        }
        return const TextStyle(fontSize: 10, color: AppColors.darkTextMuted);
      }),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled            : true,
      fillColor         : AppColors.darkCard,
      border            : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.darkBorder, width: 0.5),
      ),
      enabledBorder     : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.darkBorder, width: 0.5),
      ),
      focusedBorder     : OutlineInputBorder(
        borderRadius    : BorderRadius.circular(12),
        borderSide      : const BorderSide(color: AppColors.blue, width: 1.5),
      ),
      contentPadding    : const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    textTheme           : _textTheme(AppColors.darkText, AppColors.darkTextMuted),
    fontFamily          : 'Inter',
  );

  // ── Typographie commune ───────────────────────────────
  static TextTheme _textTheme(Color primary, Color secondary) => TextTheme(
    displayLarge  : TextStyle(fontSize: 32, fontWeight: FontWeight.w600, color: primary),
    displayMedium : TextStyle(fontSize: 28, fontWeight: FontWeight.w600, color: primary),
    headlineLarge : TextStyle(fontSize: 22, fontWeight: FontWeight.w500, color: primary),
    headlineMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w500, color: primary),
    headlineSmall : TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: primary),
    titleLarge    : TextStyle(fontSize: 15, fontWeight: FontWeight.w500, color: primary),
    titleMedium   : TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: primary),
    titleSmall    : TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: primary),
    bodyLarge     : TextStyle(fontSize: 15, fontWeight: FontWeight.w400, color: primary),
    bodyMedium    : TextStyle(fontSize: 14, fontWeight: FontWeight.w400, color: secondary),
    bodySmall     : TextStyle(fontSize: 12, fontWeight: FontWeight.w400, color: secondary),
    labelLarge    : TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: primary),
    labelMedium   : TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: secondary),
    labelSmall    : TextStyle(fontSize: 10, fontWeight: FontWeight.w400, color: secondary),
  );
}