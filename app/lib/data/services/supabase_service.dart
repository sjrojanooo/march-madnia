import 'package:supabase_flutter/supabase_flutter.dart';

class SupabaseService {
  SupabaseClient? get _client {
    try {
      return Supabase.instance.client;
    } catch (_) {
      return null;
    }
  }

  bool get isInitialized => _client != null;

  // --- Auth ---

  User? get currentUser => _client?.auth.currentUser;

  bool get isLoggedIn => currentUser != null;

  String? get accessToken => _client?.auth.currentSession?.accessToken;

  Stream<AuthState> get authStateChanges =>
      _client?.auth.onAuthStateChange ?? const Stream.empty();

  Future<AuthResponse> signUp({
    required String email,
    required String password,
  }) async {
    final client = _client;
    if (client == null) throw Exception('Supabase not initialized');
    return client.auth.signUp(email: email, password: password);
  }

  Future<AuthResponse> signIn({
    required String email,
    required String password,
  }) async {
    final client = _client;
    if (client == null) throw Exception('Supabase not initialized');
    return client.auth.signInWithPassword(email: email, password: password);
  }

  Future<void> signOut() async {
    await _client?.auth.signOut();
  }

  // --- User Brackets ---

  Future<List<Map<String, dynamic>>> getUserBrackets() async {
    final client = _client;
    if (client == null) return [];
    final response = await client
        .from('user_brackets')
        .select()
        .order('created_at', ascending: false);
    return List<Map<String, dynamic>>.from(response);
  }

  Future<Map<String, dynamic>> createBracket({
    required Map<String, String> picks,
    String name = 'My Bracket',
  }) async {
    final client = _client;
    if (client == null) throw Exception('Supabase not initialized');
    final response = await client.from('user_brackets').insert({
      'user_id': currentUser!.id,
      'picks': picks,
      'name': name,
    }).select().single();
    return response;
  }

  Future<Map<String, dynamic>> updateBracket({
    required String bracketId,
    Map<String, String>? picks,
    String? name,
  }) async {
    final client = _client;
    if (client == null) throw Exception('Supabase not initialized');
    final updates = <String, dynamic>{
      'updated_at': DateTime.now().toIso8601String(),
    };
    if (picks != null) updates['picks'] = picks;
    if (name != null) updates['name'] = name;
    final response = await client
        .from('user_brackets')
        .update(updates)
        .eq('id', bracketId)
        .select()
        .single();
    return response;
  }

  Future<void> deleteBracket(String bracketId) async {
    final client = _client;
    if (client == null) throw Exception('Supabase not initialized');
    await client.from('user_brackets').delete().eq('id', bracketId);
  }

  // --- Chat History ---

  Future<List<Map<String, dynamic>>> getChatHistory(String expertId) async {
    final client = _client;
    if (client == null) return [];
    final response = await client
        .from('chat_history')
        .select()
        .eq('user_id', currentUser!.id)
        .eq('expert_id', expertId);
    if (response.isEmpty) return [];
    final messages = response.first['messages'];
    return List<Map<String, dynamic>>.from(messages ?? []);
  }

  Future<void> saveChatHistory({
    required String expertId,
    required List<Map<String, String>> messages,
  }) async {
    final client = _client;
    if (client == null) return;
    await client.from('chat_history').upsert({
      'user_id': currentUser!.id,
      'expert_id': expertId,
      'messages': messages,
      'updated_at': DateTime.now().toIso8601String(),
    }, onConflict: 'user_id,expert_id');
  }
}
