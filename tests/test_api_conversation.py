from __future__ import annotations

from agents.main_agent import MainAgent
import api


def _agent() -> MainAgent:
    agent = object.__new__(MainAgent)
    agent.config = {}
    agent.sub_agents = {}
    return agent


def _understanding(**overrides):
    value = {
        "intent": "",
        "input_role": "user_profile",
        "dialogue_action": "continue",
        "response_mode": "ask_clarification",
        "recommendation_options": {},
        "major": "",
        "grade": "",
        "skills_add": [],
        "skills_remove": [],
        "skills_status": "unknown",
        "competition_type": "",
        "competition_type_status": "unknown",
        "competition_scope": "unknown",
        "excluded_competition_types": [],
        "competition_level": "",
        "competition_level_status": "unknown",
        "preferred_levels": [],
        "acceptable_levels": [],
        "excluded_levels": [],
        "development_goals": [],
        "available_time_per_week": None,
        "team_preference": "",
        "selected_recommendation": {},
        "material_type": "",
        "corrected_fields": [],
        "acknowledgement": "明白了",
        "reply_target": "",
        "reply_text": "",
    }
    value.update(overrides)
    return value


def _recommendation_result():
    recommendation = {
        "title": "人工智能挑战赛",
        "summary": "面向高校学生的人工智能应用竞赛",
        "source_url": "https://example.com",
    }
    return {
        "status": "success",
        "message": "ok",
        "data": {
            "final_answer": "推荐完成。",
            "agent_results": [
                {
                    "agent_name": "RecommendationAgent",
                    "status": "success",
                    "data": {"recommendations": [recommendation]},
                }
            ],
        },
    }


def test_llm_unavailable_is_explicit_and_preserves_state(monkeypatch):
    agent = _agent()
    state = agent.new_conversation_state()
    state["major"] = "人工智能"
    monkeypatch.setattr(agent, "understand_conversation_turn", lambda *_: None)

    result = agent.run_conversation_turn("帮我推荐比赛", state)

    assert result["success"] is False
    assert "AI理解服务暂时不可用" in result["response"]["text"]
    assert result["state_snapshot"]["major"] == "人工智能"


def test_reset_all_does_not_call_llm(monkeypatch):
    agent = _agent()
    state = agent.new_conversation_state()
    state["major"] = "软件工程"

    def fail_if_called(*_):
        raise AssertionError("reset must not call LLM")

    monkeypatch.setattr(agent, "understand_conversation_turn", fail_if_called)
    result = agent.run_conversation_turn("重置所有", state)

    assert result["metadata"]["reset"] is True
    assert result["response"]["type"] == "reset"
    assert result["state_snapshot"]["major"] == ""


def test_short_reset_aliases_do_not_call_llm(monkeypatch):
    agent = _agent()

    def fail_if_called(*_):
        raise AssertionError("reset must not call LLM")

    monkeypatch.setattr(agent, "understand_conversation_turn", fail_if_called)
    for command in ("重置", "重置对话", "清除对话"):
        state = agent.new_conversation_state()
        state["major"] = "软件工程"
        result = agent.run_conversation_turn(command, state)

        assert result["metadata"]["reset"] is True
        assert result["response"]["type"] == "reset"
        assert result["state_snapshot"]["major"] == ""


def test_internal_orchestration_message_is_not_exposed():
    agent = _agent()
    text = agent._conversation_result_text(
        {
            "status": "need_input",
            "message": "MainAgent completed orchestration.",
            "data": {},
        }
    )

    assert "MainAgent completed orchestration" not in text
    assert "补充" in text


def test_profile_collection_groups_preferences_and_fills_remaining(monkeypatch):
    agent = _agent()
    turns = iter(
        [
            _understanding(
                intent="recommendation",
                major="计算机科学与技术",
                grade="大二",
            ),
            _understanding(
                intent="recommendation",
                competition_type_status="no_preference",
            ),
            _understanding(
                intent="recommendation",
                skills_status="no_preference",
            ),
            _understanding(
                intent="recommendation",
                competition_level_status="no_preference",
            ),
        ]
    )
    monkeypatch.setattr(
        agent,
        "understand_conversation_turn",
        lambda *_: next(turns),
    )
    captured = {}

    def fake_run(payload):
        captured.update(payload)
        return _recommendation_result()

    monkeypatch.setattr(agent, "run", fake_run)

    first = agent.run_conversation_turn("我是计算机专业大二", {})
    assert "方向" in first["response"]["text"]
    assert "技能" in first["response"]["text"]
    assert "级" in first["response"]["text"]
    assert first["state_snapshot"]["pending_action"] == "collect_preferences"

    second = agent.run_conversation_turn("方向都可以", first["state_snapshot"])
    assert "技能" in second["response"]["text"]

    third = agent.run_conversation_turn(
        "暂时没有特别擅长",
        second["state_snapshot"],
    )
    assert "校级" in third["response"]["text"]

    fourth = agent.run_conversation_turn(
        "级别不限",
        third["state_snapshot"],
    )
    assert fourth["response"]["type"] == "result"
    assert captured["task_type"] == "recommendation"
    assert captured["task_type"] != "full_process"
    assert captured["input_data"]["sources"] == ["saikr"]
    assert captured["input_data"]["max_results"] == 10
    assert (
        fourth["state_snapshot"]["last_recommendations"][0]["title"]
        == "人工智能挑战赛"
    )


def test_matching_semantic_question_is_used(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(
        agent,
        "understand_conversation_turn",
        lambda *_: _understanding(
            intent="recommendation",
            major="人工智能",
            grade="大二",
            reply_target="collect_preferences",
            reply_text=(
                "AI 相关竞赛选择很多。你可以一起说说想尝试的方向、"
                "会用的工具或项目经历，以及对竞赛级别有没有偏好。"
            ),
        ),
    )

    result = agent.run_conversation_turn("我是人工智能专业大二学生", {})

    assert "项目经历" in result["response"]["text"]
    assert result["state_snapshot"]["pending_action"] == "collect_preferences"


def test_mismatched_semantic_question_falls_back_to_safe_template(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(
        agent,
        "understand_conversation_turn",
        lambda *_: _understanding(
            intent="recommendation",
            major="人工智能",
            grade="大二",
            reply_target="collect_skills",
            reply_text="我已经替你推荐好了三个比赛。",
        ),
    )

    result = agent.run_conversation_turn("我是人工智能专业大二学生", {})

    assert "方向" in result["response"]["text"]
    assert "推荐好了" not in result["response"]["text"]


def test_short_direction_answer_does_not_overwrite_major():
    agent = _agent()
    state = agent.new_conversation_state()
    state.update(
        {
            "major": "计算机科学与技术",
            "grade": "大二",
            "pending_action": "collect_preferences",
        }
    )

    updated = agent._apply_conversation_understanding(
        state,
        "人工智能",
        _understanding(
            intent="recommendation",
            dialogue_action="profile_change",
            major="人工智能",
            corrected_fields=["major"],
        ),
    )

    assert updated["major"] == "计算机科学与技术"
    assert updated["competition_type"] == "人工智能"
    assert updated["competition_type_status"] == "provided"


def test_material_flow_selects_project_then_type(monkeypatch):
    agent = _agent()
    state = agent.new_conversation_state()
    state.update(
        {
            "major": "人工智能",
            "grade": "大二",
            "intent": "recommendation",
            "last_recommendations": [
                {"title": "人工智能挑战赛", "summary": "AI应用"},
                {"title": "数学建模竞赛", "summary": "建模"},
            ],
        }
    )
    turns = iter(
        [
            _understanding(
                intent="material",
                input_role="command",
                dialogue_action="generate_material",
            ),
            _understanding(
                intent="material",
                input_role="followup",
                dialogue_action="generate_material",
                selected_recommendation={"index": 2, "title": ""},
            ),
            _understanding(
                intent="material",
                input_role="followup",
                dialogue_action="generate_material",
                selected_recommendation={"index": 2, "title": ""},
                material_type="generic_application_form",
            ),
        ]
    )
    monkeypatch.setattr(
        agent,
        "understand_conversation_turn",
        lambda *_: next(turns),
    )
    captured = {}

    def fake_run(payload):
        captured.update(payload)
        return {
            "status": "success",
            "message": "材料完成",
            "data": {"final_answer": "申报书已生成。", "agent_results": []},
        }

    monkeypatch.setattr(agent, "run", fake_run)

    first = agent.run_conversation_turn("帮我准备相关材料", state)
    assert "哪一个竞赛" in first["response"]["text"]

    second = agent.run_conversation_turn("第二个", first["state_snapshot"])
    assert "哪种材料" in second["response"]["text"]
    assert second["state_snapshot"]["project_name"] == "数学建模竞赛"

    third = agent.run_conversation_turn("生成申报书", second["state_snapshot"])
    assert third["response"]["text"] == "申报书已生成。"
    assert captured["task_type"] == "material"
    assert captured["input_data"]["project_info"]["title"] == "数学建模竞赛"


def test_direct_material_does_not_invent_project_background():
    agent = _agent()
    state = agent.new_conversation_state()
    state.update({
        "project_name": "麟创杯数学建模竞赛",
        "material_type": "generic_project_report",
    })

    payload = agent._build_conversation_agent_input(
        state,
        "项目计划书",
        task_type="material",
    )

    project_info = payload["input_data"]["project_info"]
    assert project_info["project_name"] == "麟创杯数学建模竞赛"
    assert "background" not in project_info


def test_material_need_input_is_shown_and_next_details_are_forwarded(monkeypatch):
    agent = _agent()
    state = agent.new_conversation_state()
    state.update({
        "intent": "material",
        "project_name": "麟创杯数学建模竞赛",
        "material_type": "generic_project_report",
    })
    monkeypatch.setattr(
        agent,
        "understand_conversation_turn",
        lambda *_: _understanding(
            intent="material",
            input_role="followup",
            dialogue_action="generate_material",
            material_type="generic_project_report",
        ),
    )
    calls = []

    def fake_run(payload):
        calls.append(payload)
        if len(calls) == 1:
            return {
                "status": "need_input",
                "message": "MainAgent completed orchestration.",
                "data": {
                    "final_answer": "请补充项目简介、技术方案和创新点。",
                    "agent_results": [{
                        "agent_name": "material_agent",
                        "status": "need_input",
                        "message": "请补充项目简介、技术方案和创新点。",
                        "data": {},
                    }],
                },
            }
        return {
            "status": "success",
            "message": "MainAgent completed orchestration.",
            "data": {"final_answer": "项目计划书已生成。", "agent_results": []},
        }

    monkeypatch.setattr(agent, "run", fake_run)

    first = agent.run_conversation_turn("项目计划书", state)
    assert first["response"]["type"] == "need_input"
    assert "项目简介" in first["response"]["text"]
    assert first["state_snapshot"]["pending_action"] == "collect_material_details"

    details = "项目用于优化校园交通，采用时空预测模型，创新点是多目标动态调度。"
    second = agent.run_conversation_turn(details, first["state_snapshot"])
    assert second["response"]["text"] == "项目计划书已生成。"
    project_info = calls[1]["input_data"]["project_info"]
    assert project_info["summary"] == details
    assert project_info["background"] == details


def test_profile_change_invalidates_old_recommendations():
    agent = _agent()
    state = agent.new_conversation_state()
    state.update(
        {
            "major": "计算机科学与技术",
            "grade": "大二",
            "last_recommendations": [{"title": "旧推荐"}],
            "last_result": _recommendation_result(),
        }
    )

    updated = agent._apply_conversation_understanding(
        state,
        "我其实是人工智能专业",
        _understanding(
            intent="recommendation",
            dialogue_action="profile_change",
            major="人工智能",
            corrected_fields=["major"],
        ),
    )

    assert updated["major"] == "人工智能"
    assert updated["last_recommendations"] == []
    assert updated["last_result"] == {}


def test_api_is_a_thin_main_agent_adapter(monkeypatch):
    captured = {}

    class FakeMainAgent:
        def __init__(self, config):
            captured["config"] = config

        def run_conversation_turn(self, text, state):
            captured["text"] = text
            captured["state"] = state
            return {
                "success": True,
                "response": {
                    "text": "下一问",
                    "type": "need_input",
                    "files": [],
                    "recommendations": [],
                },
                "state_snapshot": {"major": "人工智能"},
                "metadata": {"status": "success", "reset": False},
            }

    monkeypatch.setattr(api, "MainAgent", FakeMainAgent)
    monkeypatch.setattr(api, "load_config", lambda: {"llm": {"enabled": True}})
    request = api.AgentRunRequest(
        user_input="我是人工智能专业",
        state_snapshot={"grade": "大二"},
    )

    response = api.run_agent(request)

    assert captured["text"] == "我是人工智能专业"
    assert captured["state"] == {"grade": "大二"}
    assert response.state_snapshot == {"major": "人工智能"}
