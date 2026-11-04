// lib/core/widgets/alerte_banner.dart
// Bannière in-app pour les nouvelles alertes critiques/importantes
// Slide depuis le haut, auto-dismiss après 5s, tap pour fermer

import 'package:flutter/material.dart';
import '../models/alerte.dart';
import '../theme/app_theme.dart';

class AlerteBanner extends StatefulWidget {
  final Alerte        alerte;
  final VoidCallback  onDismiss;
  const AlerteBanner({super.key, required this.alerte, required this.onDismiss});

  @override
  State<AlerteBanner> createState() => _AlerteBannerState();
}

class _AlerteBannerState extends State<AlerteBanner>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<Offset>   _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync   : this,
      duration: const Duration(milliseconds: 280),
    );
    _slide = Tween<Offset>(
      begin: const Offset(0, -1),
      end  : Offset.zero,
    ).animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOut));

    _ctrl.forward();

    // Auto-dismiss après 5 secondes
    Future.delayed(const Duration(seconds: 5), () {
      if (mounted) _dismiss();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _dismiss() async {
    if (!mounted) return;
    await _ctrl.reverse();
    widget.onDismiss();
  }

  @override
  Widget build(BuildContext context) {
    final critique = widget.alerte.estCritique;
    final color    = critique ? AppColors.red : AppColors.amber;

    return SlideTransition(
      position: _slide,
      child: SafeArea(
        child: GestureDetector(
          onTap: _dismiss,
          child: Container(
            margin    : const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            padding   : const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color       : color,
              borderRadius: BorderRadius.circular(14),
              boxShadow   : [
                BoxShadow(
                  color      : color.withValues(alpha: 0.35),
                  blurRadius : 14,
                  offset     : const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              children: [
                Icon(
                  critique
                      ? Icons.warning_amber_outlined
                      : Icons.info_outline,
                  color: Colors.white,
                  size : 20,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize      : MainAxisSize.min,
                    children: [
                      Text(
                        critique ? 'Alerte critique' : 'Alerte',
                        style: const TextStyle(
                          fontSize    : 10,
                          fontWeight  : FontWeight.w600,
                          color       : Colors.white,
                          letterSpacing: 0.4,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.alerte.message,
                        style: const TextStyle(
                          fontSize  : 13,
                          fontWeight: FontWeight.w500,
                          color     : Colors.white,
                        ),
                        maxLines : 2,
                        overflow : TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Icon(Icons.close,
                    color: Colors.white.withValues(alpha: 0.75), size: 16),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
