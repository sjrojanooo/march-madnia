import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

class ChatBubble extends StatelessWidget {
  final String role;
  final String content;
  final bool isStreaming;

  const ChatBubble({
    super.key,
    required this.role,
    required this.content,
    this.isStreaming = false,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = role == 'user';
    return Align(
      alignment: isUser
          ? Alignment.centerRight
          : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(
          vertical: 4,
        ),
        padding: const EdgeInsets.all(12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context)
                  .size
                  .width *
              0.78,
        ),
        decoration: BoxDecoration(
          color: isUser
              ? Colors.orange.withOpacity(0.2)
              : Colors.grey.withOpacity(0.15),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(12),
            topRight: const Radius.circular(12),
            bottomLeft: Radius.circular(
              isUser ? 12 : 0,
            ),
            bottomRight: Radius.circular(
              isUser ? 0 : 12,
            ),
          ),
        ),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            if (isUser)
              Text(
                content,
                style: const TextStyle(
                  fontSize: 14,
                ),
              )
            else
              MarkdownBody(
                data: content,
                styleSheet:
                    MarkdownStyleSheet(
                  p: const TextStyle(
                    fontSize: 14,
                  ),
                ),
              ),
            if (isStreaming)
              Padding(
                padding:
                    const EdgeInsets.only(top: 4),
                child: SizedBox(
                  width: 12,
                  height: 12,
                  child:
                      CircularProgressIndicator(
                    strokeWidth: 1.5,
                    color: Colors.grey[500],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
