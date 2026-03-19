import 'package:flutter/material.dart';

class ExpertPickCell extends StatelessWidget {
  final String? pick;
  final String? modelPick;

  const ExpertPickCell({
    super.key,
    this.pick,
    this.modelPick,
  });

  @override
  Widget build(BuildContext context) {
    if (pick == null) {
      return const Text(
        '-',
        style: TextStyle(
          color: Colors.grey,
          fontSize: 11,
        ),
      );
    }

    final agrees = modelPick != null &&
        pick!.toLowerCase() ==
            modelPick!.toLowerCase();

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 6,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: agrees
            ? Colors.green.withOpacity(0.2)
            : Colors.red.withOpacity(0.2),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        pick!,
        style: TextStyle(
          color: agrees
              ? Colors.greenAccent
              : Colors.redAccent,
          fontSize: 11,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}
