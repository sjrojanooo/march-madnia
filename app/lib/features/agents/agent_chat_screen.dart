import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/agent_message.dart';
import 'package:march_madness/data/repositories/agent_repository.dart';
import 'package:march_madness/features/agents/widgets/chat_bubble.dart';

class AgentChatScreen extends StatefulWidget {
  final String expertId;
  final String expertName;

  const AgentChatScreen({
    super.key,
    required this.expertId,
    required this.expertName,
  });

  @override
  State<AgentChatScreen> createState() =>
      _AgentChatScreenState();
}

class _AgentChatScreenState
    extends State<AgentChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _messages = <AgentMessage>[];
  StreamSubscription<String>? _subscription;
  bool _isStreaming = false;
  String _streamBuffer = '';

  @override
  void dispose() {
    _subscription?.cancel();
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty || _isStreaming) return;

    _controller.clear();

    setState(() {
      _messages.add(AgentMessage(
        role: 'user',
        content: text,
        timestamp: DateTime.now(),
      ));
      _isStreaming = true;
      _streamBuffer = '';
    });

    _scrollToBottom();

    final repo = context.read<AgentRepository>();
    final stream = repo.chat(
      widget.expertId,
      text,
      _messages
          .where((m) => m.role == 'user')
          .toList(),
    );

    _subscription = stream.listen(
      (chunk) {
        setState(() {
          _streamBuffer += chunk;
        });
        _scrollToBottom();
      },
      onDone: () {
        setState(() {
          if (_streamBuffer.isNotEmpty) {
            _messages.add(AgentMessage(
              role: 'assistant',
              content: _streamBuffer,
              timestamp: DateTime.now(),
            ));
          }
          _streamBuffer = '';
          _isStreaming = false;
        });
        _scrollToBottom();
      },
      onError: (Object error) {
        setState(() {
          _isStreaming = false;
          _streamBuffer = '';
        });
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(
            SnackBar(
              content: Text(
                'Error: $error',
              ),
              backgroundColor: Colors.red,
            ),
          );
        }
      },
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback(
      (_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController
                .position.maxScrollExtent,
            duration: const Duration(
              milliseconds: 200,
            ),
            curve: Curves.easeOut,
          );
        }
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.expertName),
      ),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty &&
                    !_isStreaming
                ? Center(
                    child: Text(
                      'Ask ${widget.expertName} '
                      'about their picks',
                      style: TextStyle(
                        color: Colors.grey[500],
                      ),
                    ),
                  )
                : ListView.builder(
                    controller:
                        _scrollController,
                    padding:
                        const EdgeInsets.all(12),
                    itemCount:
                        _messages.length +
                        (_isStreaming ? 1 : 0),
                    itemBuilder:
                        (context, index) {
                      if (index ==
                              _messages.length &&
                          _isStreaming) {
                        return ChatBubble(
                          role: 'assistant',
                          content:
                              _streamBuffer.isEmpty
                                  ? '...'
                                  : _streamBuffer,
                          isStreaming: true,
                        );
                      }
                      final msg =
                          _messages[index];
                      return ChatBubble(
                        role: msg.role,
                        content: msg.content,
                      );
                    },
                  ),
          ),
          _buildInput(),
        ],
      ),
    );
  }

  Widget _buildInput() {
    return Container(
      padding: const EdgeInsets.fromLTRB(
        12, 8, 12, 24,
      ),
      decoration: BoxDecoration(
        color: Theme.of(context)
            .colorScheme
            .surface,
        border: Border(
          top: BorderSide(
            color: Colors.grey[800]!,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              enabled: !_isStreaming,
              textInputAction:
                  TextInputAction.send,
              onSubmitted: (_) => _send(),
              decoration:
                  const InputDecoration(
                hintText: 'Ask a question...',
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 10,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            onPressed:
                _isStreaming ? null : _send,
            icon: _isStreaming
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child:
                        CircularProgressIndicator(
                      strokeWidth: 2,
                    ),
                  )
                : const Icon(Icons.send),
            color: Colors.orange,
          ),
        ],
      ),
    );
  }
}
