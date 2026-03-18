import 'package:march_madness/core/models/agent_info.dart';
import 'package:march_madness/core/models/agent_message.dart';
import 'package:march_madness/core/models/bracket_rating.dart';
import 'package:march_madness/data/services/api_service.dart';

class AgentRepository {
  final ApiService _api;

  AgentRepository(this._api);

  Future<List<AgentInfo>> getAgents() async {
    final data = await _api.getAgents();
    return data
        .map(
          (e) => AgentInfo.fromJson(
            e as Map<String, dynamic>,
          ),
        )
        .toList();
  }

  Stream<String> chat(
    String expertId,
    String message,
    List<AgentMessage> history,
  ) {
    return _api.chatWithAgent(
      expertId,
      message,
      history,
    );
  }

  Future<BracketRating> rateBracket(
    String expertId,
    Map<String, String> bracket,
  ) async {
    final data = await _api.rateBracket(
      expertId,
      bracket,
    );
    return BracketRating.fromJson(data);
  }
}
