import 'package:flutter/material.dart';

/// Draws connector lines between bracket rounds.
/// Connects pairs of matchups on the left to a single matchup on the right
/// (or right-to-left for mirrored regions).
class BracketConnectorPainter extends CustomPainter {
  final int gamesInRound;
  final double matchupHeight;
  final double gapBetweenMatchups;
  final bool mirrored;

  BracketConnectorPainter({
    required this.gamesInRound,
    required this.matchupHeight,
    required this.gapBetweenMatchups,
    this.mirrored = false,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFBDBDBD)
      ..strokeWidth = 1.0
      ..style = PaintingStyle.stroke;

    final pairCount = gamesInRound ~/ 2;
    if (pairCount == 0 && gamesInRound == 1) {
      // Single game connecting to next round: just draw a horizontal line.
      final y = size.height / 2;
      if (mirrored) {
        canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
      } else {
        canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
      }
      return;
    }

    // Calculate spacing: each game takes matchupHeight + gapBetweenMatchups.
    final slotHeight = matchupHeight + gapBetweenMatchups;
    // The total height for this round's games:
    // gamesInRound * matchupHeight + (gamesInRound - 1) * gapBetweenMatchups
    // Center of game i = i * slotHeight + matchupHeight / 2

    for (int i = 0; i < pairCount; i++) {
      final topIdx = i * 2;
      final botIdx = i * 2 + 1;

      final topCenter = topIdx * slotHeight + matchupHeight / 2;
      final botCenter = botIdx * slotHeight + matchupHeight / 2;
      final midY = (topCenter + botCenter) / 2;

      if (mirrored) {
        // Lines go from right to left.
        // Horizontal from right edge to midpoint, vertical between pairs, then horizontal to left.
        final rightX = size.width;
        final leftX = 0.0;
        final midX = size.width / 2;

        // Top horizontal line
        canvas.drawLine(
          Offset(midX, topCenter),
          Offset(rightX, topCenter),
          paint,
        );
        // Bottom horizontal line
        canvas.drawLine(
          Offset(midX, botCenter),
          Offset(rightX, botCenter),
          paint,
        );
        // Vertical connecting line
        canvas.drawLine(
          Offset(midX, topCenter),
          Offset(midX, botCenter),
          paint,
        );
        // Horizontal to next round
        canvas.drawLine(
          Offset(leftX, midY),
          Offset(midX, midY),
          paint,
        );
      } else {
        // Lines go from left to right.
        final leftX = 0.0;
        final rightX = size.width;
        final midX = size.width / 2;

        // Top horizontal line
        canvas.drawLine(
          Offset(leftX, topCenter),
          Offset(midX, topCenter),
          paint,
        );
        // Bottom horizontal line
        canvas.drawLine(
          Offset(leftX, botCenter),
          Offset(midX, botCenter),
          paint,
        );
        // Vertical connecting line
        canvas.drawLine(
          Offset(midX, topCenter),
          Offset(midX, botCenter),
          paint,
        );
        // Horizontal to next round
        canvas.drawLine(
          Offset(midX, midY),
          Offset(rightX, midY),
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant BracketConnectorPainter old) =>
      gamesInRound != old.gamesInRound ||
      matchupHeight != old.matchupHeight ||
      gapBetweenMatchups != old.gapBetweenMatchups ||
      mirrored != old.mirrored;
}
