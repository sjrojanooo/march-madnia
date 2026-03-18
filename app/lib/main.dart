import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/config/app_config.dart';
import 'package:march_madness/data/repositories/bracket_repository.dart';
import 'package:march_madness/data/repositories/expert_repository.dart';
import 'package:march_madness/data/repositories/agent_repository.dart';
import 'package:march_madness/data/services/api_service.dart';
import 'package:march_madness/app.dart';

void main() {
  final apiService = ApiService(
    baseUrl: AppConfig.apiBaseUrl,
  );
  runApp(
    MultiProvider(
      providers: [
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
