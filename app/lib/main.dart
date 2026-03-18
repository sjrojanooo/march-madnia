import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:march_madness/core/config/app_config.dart';
import 'package:march_madness/data/repositories/bracket_repository.dart';
import 'package:march_madness/data/repositories/expert_repository.dart';
import 'package:march_madness/data/repositories/agent_repository.dart';
import 'package:march_madness/data/services/api_service.dart';
import 'package:march_madness/data/services/supabase_service.dart';
import 'package:march_madness/app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    anonKey: AppConfig.supabaseAnonKey,
  );

  final apiService = ApiService(
    baseUrl: AppConfig.apiBaseUrl,
  );
  runApp(
    MultiProvider(
      providers: [
        Provider<SupabaseService>(
          create: (_) => SupabaseService(),
        ),
        Provider<ApiService>.value(
          value: apiService,
        ),
        Provider<BracketRepository>(
          create: (_) =>
              BracketRepository(apiService),
        ),
        Provider<ExpertRepository>(
          create: (_) =>
              ExpertRepository(apiService),
        ),
        Provider<AgentRepository>(
          create: (_) =>
              AgentRepository(apiService),
        ),
      ],
      child: const MarchMadnessApp(),
    ),
  );
}
