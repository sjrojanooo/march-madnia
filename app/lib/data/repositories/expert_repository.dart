import 'package:march_madness/core/models/expert_profile.dart';
import 'package:march_madness/data/services/api_service.dart';

class ExpertRepository {
  final ApiService _api;
  Map<String, ExpertProfile>? _cache;

  ExpertRepository(this._api);

  Future<Map<String, ExpertProfile>> getExperts({
    bool forceRefresh = false,
  }) async {
    if (_cache != null && !forceRefresh) {
      return _cache!;
    }

    final data = await _api.getExperts();
    final experts = <String, ExpertProfile>{};

    final rawExperts =
        data['experts'] as Map<String, dynamic>? ??
            data;
    for (final entry in rawExperts.entries) {
      if (entry.value is Map<String, dynamic>) {
        experts[entry.key] =
            ExpertProfile.fromJson(
          entry.key,
          entry.value as Map<String, dynamic>,
        );
      }
    }

    _cache = experts;
    return experts;
  }

  void clearCache() => _cache = null;
}
