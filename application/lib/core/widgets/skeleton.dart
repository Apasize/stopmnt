// lib/core/widgets/skeleton.dart
// Shimmer — lumière défilante sur les zones en attente de données
// Wrap le contenu skeleton dans Shimmer, remplace les données par ShimmerBlock

import 'package:flutter/material.dart';

// ── Lumière défilante ─────────────────────────────────────
// Applique un gradient blanc qui glisse de gauche à droite
// sur tout le sous-arbre enfant (synchronisé sur un seul controller)
class Shimmer extends StatefulWidget {
  final Widget child;
  const Shimmer({super.key, required this.child});

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync   : this,
      duration: const Duration(milliseconds: 1500),
    )..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      child    : widget.child,
      builder  : (context, child) => ShaderMask(
        blendMode     : BlendMode.srcATop,
        shaderCallback: (bounds) => LinearGradient(
          begin    : const Alignment(-1, 0),
          end      : const Alignment(1,  0),
          colors   : const [
            Colors.transparent,
            Color(0x66FFFFFF),
            Colors.transparent,
          ],
          stops    : const [0.0, 0.5, 1.0],
          transform: _SlidingGradient(slide: _ctrl.value),
        ).createShader(bounds),
        child: child!,
      ),
    );
  }
}

// Décale le gradient de -50% à +150% de la largeur en un cycle
class _SlidingGradient extends GradientTransform {
  const _SlidingGradient({required this.slide});
  final double slide;

  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) {
    return Matrix4.translationValues(
      bounds.width * (slide * 2 - 0.5), 0, 0,
    );
  }
}

// ── Bloc placeholder ──────────────────────────────────────
// Rectangle de remplissage — prend la couleur exacte du mode courant
// pour s'intégrer visuellement dans les cartes existantes
class ShimmerBlock extends StatelessWidget {
  final double? width;   // null = prend la contrainte du parent
  final double  height;
  final double  radius;
  const ShimmerBlock({
    super.key,
    this.width,
    required this.height,
    this.radius = 8,
  });

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width : width,
      height: height,
      decoration: BoxDecoration(
        color        : dark
            ? const Color(0xFF252B3E)   // légèrement au-dessus de darkSurface
            : const Color(0xFFDCE0EE),  // légèrement en-dessous de lightSurface
        borderRadius : BorderRadius.circular(radius),
      ),
    );
  }
}
