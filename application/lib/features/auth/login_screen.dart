// lib/features/auth/login_screen.dart
// Écran de connexion patient
// Email + mot de passe → token JWT stocké localement

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers/auth_provider.dart';
import '../../core/providers/ble_provider.dart';
import '../../core/theme/app_theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl  = TextEditingController();
  final _passCtrl   = TextEditingController();
  bool  _showPass   = false;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final auth = context.read<AuthProvider>();
    final ok   = await auth.login(
      _emailCtrl.text.trim(),
      _passCtrl.text.trim(),
    );
    if (ok && mounted) context.go('/dashboard');
  }

  // Mode démo : pas de compte ni de serveur, données fictives + capteurs simulés
  Future<void> _entrerDemo() async {
    final auth = context.read<AuthProvider>();
    final ble  = context.read<BleProvider>();
    await auth.entrerModeDemo();
    if (!ble.simulation) ble.demarrerSimulation();
    if (mounted) context.go('/dashboard');
  }

  @override
  Widget build(BuildContext context) {
    final auth   = context.watch<AuthProvider>();
    final dark   = Theme.of(context).brightness == Brightness.dark;
    final bgColor = dark ? AppColors.darkBg : AppColors.lightBg;

    return Scaffold(
      backgroundColor: bgColor,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              const SizedBox(height: 32),

              // ── Logo ──
              Container(
                width: 52, height: 52,
                decoration: BoxDecoration(
                  color        : AppColors.blue,
                  borderRadius : BorderRadius.circular(16),
                ),
                child: const Icon(Icons.monitor_heart, color: Colors.white, size: 28),
              ),

              const SizedBox(height: 24),

              // ── Titre ──
              Text(
                'STOP-MNT',
                style: Theme.of(context).textTheme.headlineLarge,
              ),
              const SizedBox(height: 6),
              Text(
                'Surveillance des maladies non transmissibles',
                style: Theme.of(context).textTheme.bodyMedium,
              ),

              const SizedBox(height: 40),

              // ── Session expirée ──
              if (auth.tokenExpire) ...[
                Container(
                  padding    : const EdgeInsets.all(12),
                  decoration : BoxDecoration(
                    color        : AppColors.amber.withValues(alpha: 0.1),
                    borderRadius : BorderRadius.circular(12),
                    border       : Border.all(color: AppColors.amber.withValues(alpha: 0.3)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.timer_off_outlined, color: AppColors.amber, size: 16),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Votre session a expiré. Reconnectez-vous.',
                          style: TextStyle(color: AppColors.amber, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // ── Erreur ──
              if (auth.erreur != null) ...[
                Container(
                  padding      : const EdgeInsets.all(12),
                  decoration   : BoxDecoration(
                    color        : AppColors.red.withValues(alpha: 0.1),
                    borderRadius : BorderRadius.circular(12),
                    border       : Border.all(color: AppColors.red.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: AppColors.red, size: 16),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          auth.erreur!,
                          style: const TextStyle(color: AppColors.red, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // ── Email ──
              Text(
                'Email',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              TextField(
                controller   : _emailCtrl,
                keyboardType : TextInputType.emailAddress,
                autocorrect  : false,
                style        : Theme.of(context).textTheme.bodyLarge,
                decoration   : const InputDecoration(
                  hintText      : 'patient@stopmnt.bj',
                  prefixIcon    : Icon(Icons.mail_outline, size: 18),
                ),
              ),

              const SizedBox(height: 16),

              // ── Mot de passe ──
              Text(
                'Mot de passe',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              TextField(
                controller   : _passCtrl,
                obscureText  : !_showPass,
                style        : Theme.of(context).textTheme.bodyLarge,
                onSubmitted  : (_) => _login(),
                decoration   : InputDecoration(
                  hintText    : '••••••••',
                  prefixIcon  : const Icon(Icons.lock_outline, size: 18),
                  suffixIcon  : IconButton(
                    icon      : Icon(
                      _showPass ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                      size: 18,
                    ),
                    onPressed : () => setState(() => _showPass = !_showPass),
                  ),
                ),
              ),

              const SizedBox(height: 32),

              // ── Bouton connexion ──
              SizedBox(
                width  : double.infinity,
                height : 52,
                child  : FilledButton(
                  onPressed : auth.loading ? null : _login,
                  style     : FilledButton.styleFrom(
                    backgroundColor : AppColors.blue,
                    shape           : RoundedRectangleBorder(
                      borderRadius  : BorderRadius.circular(14),
                    ),
                  ),
                  child : auth.loading
                      ? const SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(
                      color      : Colors.white,
                      strokeWidth: 2,
                    ),
                  )
                      : const Text(
                    'Se connecter',
                    style: TextStyle(
                      fontSize   : 15,
                      fontWeight : FontWeight.w500,
                      color      : Colors.white,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 12),

              // ── Mode démo ──
              SizedBox(
                width  : double.infinity,
                height : 48,
                child  : OutlinedButton.icon(
                  onPressed : auth.loading ? null : _entrerDemo,
                  icon      : const Icon(Icons.science_outlined, size: 18),
                  label     : const Text('Essayer sans compte (mode démo)'),
                  style     : OutlinedButton.styleFrom(
                    foregroundColor : AppColors.blue,
                    side            : BorderSide(color: AppColors.blue.withValues(alpha: 0.4)),
                    shape           : RoundedRectangleBorder(
                      borderRadius  : BorderRadius.circular(14),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 32),

              // ── Mention projet ──
              Center(
                child: Text(
                  'Bénin · Projet STOP-MNT © 2026',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}