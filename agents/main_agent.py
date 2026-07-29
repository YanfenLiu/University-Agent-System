from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class MainAgent:
    """Main orchestrator for task understanding, agent scheduling, and integration."""

    agent_name = "MainAgent"

    required_fields = {
        "task_id",
        "user_input",
        "task_type",
        "user_profile",
        "context",
        "input_data",
        "history",
        "required_output",
        "metadata",
    }

    allowed_agents = {"info_collect", "info_extract", "recommendation", "material"}

    sub_agent_specs = {
        "info_collect": ("agents.info_collect_agent", "InfoCollectAgent"),
        "info_extract": ("agents.info_extract_agent", "InfoExtractAgent"),
        "recommendation": ("agents.recommendation_agent", "RecommendationAgent"),
        "material": ("agents.material_agent", "MaterialAgent"),
    }

    reset_commands = {
        "重置",
        "重置所有",
        "全部重置",
        "重置对话",
        "重新开始",
        "清空会话",
        "清空对话",
        "清除对话",
        "忘记之前的信息",
    }

    valid_material_types = {
        "generic_personal_resume",
        "generic_application_form",
        "generic_project_report",
        "generic_ppt",
        "generic_team_description",
        "generic_budget",
        "generic_schedule",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.sub_agents = self._load_sub_agents()

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Only external interface of MainAgent."""
        task_id = self._get_task_id(input_data)

        try:
            validation_error = self.validate_input(input_data)
            if validation_error:
                return self._build_output(
                    task_id=task_id,
                    status="failed",
                    data={},
                    message="Input validation failed.",
                    error=validation_error,
                )

            return self.process(input_data)
        except Exception as exc:
            return self._build_output(
                task_id=task_id,
                status="failed",
                data={},
                message="MainAgent execution failed.",
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(input_data, dict):
            return {"message": "input_data must be a dict."}

        missing_fields = sorted(self.required_fields - set(input_data.keys()))
        if missing_fields:
            return {"message": "Missing required fields.", "fields": missing_fields}

        dict_fields = ["user_profile", "context", "input_data", "metadata"]
        invalid_dict_fields = [
            field for field in dict_fields if not isinstance(input_data.get(field), dict)
        ]
        if invalid_dict_fields:
            return {"message": "These fields must be dict.", "fields": invalid_dict_fields}

        if not isinstance(input_data.get("history"), list):
            return {"message": "history must be a list."}

        return None

    def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        task_id = self._get_task_id(input_data)
        planning = self.plan_task(input_data)
        selected_agents = planning.get("selected_agents", [])

        agent_results = []
        shared_context = dict(input_data.get("context", {}))
        shared_context["main_agent_plan"] = planning

        for agent_key in selected_agents:
            agent_input = self._build_agent_input(
                original_input=input_data,
                agent_key=agent_key,
                previous_results=agent_results,
                shared_context=shared_context,
            )
            result = self._call_sub_agent(agent_key, agent_input)
            agent_results.append(result)
            shared_context[f"{agent_key}_result"] = result.get("data", {})

        final_data = self.integrate_results(input_data, agent_results, planning)
        status = self._resolve_final_status(agent_results, planning)

        return self._build_output(
            task_id=task_id,
            status=status,
            data=final_data,
            message="MainAgent completed orchestration.",
            error=None if status in {"success", "partial", "need_input"} else final_data.get("errors"),
            next_action=final_data.get("next_action"),
            metadata={
                "selected_agents": selected_agents,
                "planning_source": planning.get("planning_source"),
                "agent_statuses": {
                    result.get("agent_name", "unknown"): result.get("status", "failed")
                    for result in agent_results
                },
            },
        )

    def new_conversation_state(self) -> dict[str, Any]:
        """Return the browser-safe dialogue state owned by MainAgent."""
        return {
            "version": 1,
            "intent": "",
            "input_role": "",
            "dialogue_action": "",
            "response_mode": "",
            "major": "",
            "grade": "",
            "interests": [],
            "skills": [],
            "skills_status": "unknown",
            "skill_gaps": [],
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
            "project_name": "",
            "material_type": "",
            "material_details": "",
            "material_generation_confirmed": False,
            "selected_recommendation": {},
            "recommendation_options": {},
            "last_recommendations": [],
            "last_result": {},
            "pending_action": "",
            "last_acknowledgement": "",
            "conversation_summary": "",
            "turns": [],
        }

    def run_conversation_turn(
        self,
        user_input: str,
        state_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Understand one web turn, update state, and dispatch only when ready.

        This is the single conversational entry point for web clients.  The
        browser stores the returned state transparently; all business decisions
        remain inside MainAgent.
        """
        text = str(user_input or "").strip()
        state = self._normalize_conversation_state(state_snapshot)

        if self._is_reset_command(text):
            return self._conversation_response(
                text=(
                    "已经为你重置全部信息，我们重新开始吧。\n\n"
                    "请先告诉我你的专业和年级。"
                ),
                state=self.new_conversation_state(),
                response_type="reset",
                reset=True,
            )
        if not text:
            return self._conversation_response(
                text="请输入你想咨询的内容。",
                state=state,
                response_type="need_input",
            )

        understanding = self.understand_conversation_turn(text, state)
        if not isinstance(understanding, dict):
            return self._conversation_response(
                text="当前AI理解服务暂时不可用，我已保留你的对话内容，请稍后重试。",
                state=state,
                response_type="error",
                success=False,
            )

        state = self._apply_conversation_understanding(state, text, understanding)
        action = str(state.get("dialogue_action") or "")

        if action == "reset_all":
            return self._conversation_response(
                text=(
                    "已经为你重置全部信息，我们重新开始吧。\n\n"
                    "请先告诉我你的专业和年级。"
                ),
                state=self.new_conversation_state(),
                response_type="reset",
                reset=True,
            )

        if state.get("last_result") and action in {
            "competition_detail",
            "compare_recommendations",
            "explain_recommendation_count",
        }:
            followup = self.handle_followup(text, state["last_result"], state)
            if followup:
                return self._conversation_response(
                    text=followup.get("data", {}).get(
                        "final_answer",
                        followup.get("message", ""),
                    ),
                    state=state,
                    response_type=followup.get("status", "success"),
                )

        if state.get("input_role") == "chat" or action == "chat":
            control = self.handle_conversation_control(text, state)
            if control:
                return self._conversation_response(
                    text=control.get("data", {}).get(
                        "final_answer",
                        control.get("message", ""),
                    ),
                    state=state,
                )

        intent = self._resolve_conversation_intent(state, understanding)
        state["intent"] = intent

        if intent == "material":
            return self._run_material_conversation(text, state, understanding)

        if intent in {"", "recommendation", "full_process", "collect"}:
            state["intent"] = "recommendation"
            question = self._next_recommendation_question(state)
            if question:
                fallback = self._with_acknowledgement(state, question)
                return self._conversation_response(
                    text=self._semantic_conversation_question(
                        understanding,
                        str(state.get("pending_action") or ""),
                        fallback,
                    ),
                    state=state,
                    response_type="need_input",
                )
            result = self.run(
                self._build_conversation_agent_input(
                    state,
                    text,
                    task_type="recommendation",
                )
            )
            return self._conversation_agent_response(
                state,
                result,
                prefix=self._conversation_profile_summary(state),
            )

        if intent == "extract":
            fallback = self._with_acknowledgement(
                state,
                "请把完整的竞赛通知粘贴过来，我会整理关键信息和报名要求。",
            )
            return self._conversation_response(
                text=fallback,
                state=state,
                response_type="need_input",
            )

        return self._conversation_response(
            text=(
                "我还没有完全理解你想继续推荐竞赛、了解某项详情，"
                "还是准备材料。请再具体说一点。"
            ),
            state=state,
            response_type="need_input",
        )

    def understand_conversation_turn(
        self,
        user_input: str,
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Interpret one natural-language turn into conservative state updates.

        The result supplements deterministic parsing. Invalid output or an unavailable
        model returns ``None`` so the conversation can continue locally.
        """
        text = str(user_input or "").strip()
        if not text or not self._is_llm_enabled():
            return None

        llm_config = self.config.get("llm", {}) if isinstance(self.config, dict) else {}
        api_key_env = llm_config.get("api_key_env", "DEEPSEEK_API_KEY")
        api_key = llm_config.get("api_key", "") or os.getenv(str(api_key_env), "")
        if not api_key:
            return None
        base_url = llm_config.get("base_url") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = llm_config.get("model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        state = conversation_state or {}
        state_summary = {
            key: state.get(key)
            for key in [
                "intent", "major", "grade", "skills", "skill_gaps", "competition_type",
                "competition_scope", "competition_level", "development_goals", "available_time_per_week",
                "team_preference", "project_name", "material_type",
                "conversation_summary", "dialogue_action", "recommendation_options",
                "pending_action",
            ]
        }
        state_summary["last_recommendations"] = [
            {
                "index": index,
                "title": item.get("title") or item.get("name") or "",
            }
            for index, item in enumerate(state.get("last_recommendations", [])[:5], 1)
            if isinstance(item, dict)
        ]
        schema = {
            "intent": "collect|extract|recommendation|material|full_process|empty",
            "input_role": (
                "user_profile|competition_notice|project_description|command|followup|chat"
            ),
            "dialogue_action": (
                "continue|profile_change|new_recommendation|expand_recommendations|explain_recommendation_count|"
                "compare_recommendations|competition_detail|change_preferences|generate_material|reset_all|chat"
            ),
            "response_mode": "run_agent|answer_from_context|ask_clarification",
            "recommendation_options": {
                "top_n": "integer 1-10 or null",
                "include_backup": "boolean or null",
                "relax_quality_gate": "boolean or null",
                "explanation_requested": "boolean",
            },
            "major": "string or empty",
            "grade": "大一|大二|大三|大四|研究生|empty",
            "skills_add": ["string"],
            "skills_remove": ["string explicitly negated by user"],
            "skills_status": "provided|no_preference|unknown",
            "competition_type": "string or empty",
            "competition_type_status": "provided|no_preference|unknown",
            "competition_scope": "major_aligned|cross_disciplinary|both|unknown",
            "excluded_competition_types": ["string"],
            "competition_level": "国际级|国家级|省级|校级|empty",
            "competition_level_status": "provided|no_preference|unknown",
            "preferred_levels": ["string"],
            "acceptable_levels": ["string"],
            "excluded_levels": ["string"],
            "development_goals": ["保研|考研|留学|就业|创业|兴趣提升"],
            "available_time_per_week": "number or null",
            "team_preference": "个人赛|团队赛|无偏好|empty",
            "project_name": "用户明确提到的竞赛或项目名称；未提及则empty",
            "selected_recommendation": {
                "index": "1-based integer or null",
                "title": "string or empty",
            },
            "material_type": (
                "generic_personal_resume|generic_application_form|generic_project_report|"
                "generic_ppt|generic_team_description|generic_budget|generic_schedule|empty"
            ),
            "corrected_fields": ["仅列出用户本轮明确纠正的字段名"],
            "acknowledgement": "不超过45字，自然承接用户的话，不提问",
            "reply_target": (
                "collect_major|collect_grade|collect_competition_type|collect_skills|"
                "collect_competition_level|collect_preferences|provide_material_project|empty"
            ),
            "reply_text": (
                "结合用户本轮表达自然承接，并只询问reply_target对应的一项信息；"
                "不超过120字，不编造竞赛、结果或用户经历"
            ),
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你负责理解大学生竞赛助手中的单轮用户表达。结合已有状态抽取本轮明确新增、修改、"
                        "否定、排除和无偏好信息。不要猜测未表达的专业、能力或目标；‘不会Python但会Java’"
                        "必须分别放入skills_remove和skills_add；‘除了数学建模都可以’必须放入排除项；"
                        "先判断input_role。粘贴的竞赛通知、公告、赛程、参赛要求属于competition_notice；"
                        "通知正文里的专业、学生、软件、人工智能等描述属于赛事内容，绝不能当成用户画像，"
                        "此时major、grade、skills_add、skills_remove和corrected_fields必须为空，"
                        "也不能输出profile_change。用户自己的项目介绍属于project_description。"
                        "‘没有硬性要求/没什么硬性要求/都可以’要结合当前追问字段标记no_preference，"
                        "只改那一个字段：追问级别就只标competition_level_status，追问技能就只标skills_status，"
                        "追问方向就只标competition_type_status；不要顺带清空或改写其它已填字段。"
                        "字段约定：某字段本轮未提及时输出空字符串或null，系统不会改旧值；"
                        "本轮明确提到则输出非空值，系统会覆盖规则草稿或旧值"
                        "（major、grade、competition_type、competition_level、team_preference均如此）。"
                        "区分专业与竞赛方向：‘人工智能专业’只能写入major，不能写入competition_type；"
                        "‘想参加数学建模方面的竞赛’才写入competition_type=数学建模。"
                        "用户说方向随便/不限方向/没什么方向要求时，competition_type_status用no_preference；"
                        "用户说没什么擅长/暂时没有特别擅长时，skills_status用no_preference。"
                        "用户说贴近本专业、接受跨学科、两者都行时，分别输出competition_scope为"
                        "major_aligned、cross_disciplinary、both；若同时没有具体主题，"
                        "competition_type_status可用no_preference；只有范围确认但未表达开放偏好时用unknown。"
                        "用户取消材料并要求重新推荐时intent必须是recommendation。已有intent在用户没有明确换任务时应保持。"
                        "如果用户明确给出与已有状态不同的专业或身份，dialogue_action必须是profile_change，"
                        "把major列入corrected_fields，并将新专业写入major。"
                        "如果用户修改已有偏好（级别/方向/年级/技能/参赛形式等，如‘改成’‘换成’‘不是X是Y’‘冲国赛’），"
                        "dialogue_action用change_preferences（改专业仍用profile_change），"
                        "把对应字段名写入corrected_fields，并输出新的非空字段值；不要只改acknowledgement。"
                        "还要判断本轮对话动作，而不是依赖固定措辞：用户认为结果少、要求更多、换一批或接受次优候选时，"
                        "dialogue_action用expand_recommendations，并给出合理的recommendation_options，"
                        "若已有上一轮推荐结果则response_mode用answer_from_context（由系统从缓存扩容，勿要求重跑）；"
                        "只询问为什么结果少时，"
                        "用explain_recommendation_count和answer_from_context；询问上一轮某项详情或比较时，不要当成新推荐。"
                        "用户表达要为刚才推荐的某项准备材料时，intent用material、dialogue_action用generate_material；"
                        "如果提到了推荐序号或名称，把它写入selected_recommendation。"
                        "材料类型必须归一化为material_type给定枚举；没有明确类型就输出empty，不要猜。"
                        "如果已有pending_action，优先把本轮短回答理解为对该追问的回答。"
                        "尤其当pending_action是collect_competition_type或collect_preferences时，"
                        "用户只回答‘人工智能’‘数学建模’‘算法’等方向名称，必须写入competition_type，"
                        "绝不能当成新专业或profile_change；只有用户明确说‘我是X专业’‘专业改成X’"
                        "‘其实学的是X’时才修改major。pending_action是collect_preferences时，"
                        "应一次理解用户对方向、技能和级别中任意一项或多项的回答；如果用户概括说"
                        "‘都可以’‘都不限’‘没有要求’，可以把仍未确定的方向、技能和级别都标为"
                        "no_preference，避免机械地逐项重复追问。"
                        "用户明确要求清空全部记忆、重置会话或重新开始时，dialogue_action用reset_all。"
                        "acknowledgement要像自然对话，优先使用‘明白了’‘了解’‘这样我就清楚了’，"
                        "不要使用‘已记录’‘字段’‘状态’等系统日志口吻。"
                        "同时根据已有状态和本轮新增信息，预测系统下一步唯一缺少的信息："
                        "依次检查专业、年级、竞赛方向、技能、竞赛级别；材料任务没有具体竞赛或项目时"
                        "使用provide_material_project。方向、技能、级别中同时缺少两项以上时，"
                        "reply_target使用collect_preferences并把它们自然地合并成一个简短问题；"
                        "不要像问卷一样逐字段确认。把对应动作写入reply_target，并在reply_text中"
                        "用自然、口语化、贴合上下文的语言承接，使用‘你’而不是‘您’，"
                        "不要说‘已更新你的专业/状态/字段’，也不要机械复述用户原话。"
                        "reply_text不能声称已经完成推荐、搜索或材料生成，不能编造竞赛名称、用户经历、"
                        "链接或事实；不需要追问时reply_target和reply_text均为空。只输出JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"已有状态：{json.dumps(state_summary, ensure_ascii=False)}\n"
                        f"本轮用户输入：{text}\n"
                        f"输出结构：{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 900,
        }
        request = urllib.request.Request(
            url=base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=int(llm_config.get("timeout", 30))) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            content = response_data["choices"][0]["message"]["content"]
            parsed = self._parse_json_object(content)
            return parsed if isinstance(parsed, dict) else None
        except (urllib.error.URLError, KeyError, IndexError, ValueError, json.JSONDecodeError, TimeoutError):
            return None

    def _normalize_conversation_state(self, value: Any) -> dict[str, Any]:
        state = self.new_conversation_state()
        if isinstance(value, dict):
            for key in state:
                if key in value:
                    state[key] = deepcopy(value[key])
        state["version"] = 1
        for key in (
            "interests",
            "skills",
            "skill_gaps",
            "excluded_competition_types",
            "preferred_levels",
            "acceptable_levels",
            "excluded_levels",
            "development_goals",
            "last_recommendations",
            "turns",
        ):
            if not isinstance(state.get(key), list):
                state[key] = []
        for key in ("last_result", "selected_recommendation", "recommendation_options"):
            if not isinstance(state.get(key), dict):
                state[key] = {}
        return state

    def _is_reset_command(self, message: str) -> bool:
        normalized = "".join(str(message or "").strip().split()).rstrip("。！!")
        return normalized in self.reset_commands

    def _apply_conversation_understanding(
        self,
        state_snapshot: dict[str, Any],
        message: str,
        understanding: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._normalize_conversation_state(state_snapshot)
        state["turns"] = [*state["turns"], message][-12:]
        state["last_acknowledgement"] = ""
        understanding = dict(understanding)

        # A short answer belongs to the question MainAgent just asked.  Guard
        # against the model treating a competition direction such as
        # "人工智能" as an academic-major correction.
        pending_before = str(state.get("pending_action") or "")
        proposed_major = str(understanding.get("major") or "").strip()
        explicit_identity_change = any(
            marker in message
            for marker in (
                "专业",
                "我是",
                "我学",
                "学的是",
                "改成",
                "其实是",
                "不是",
            )
        )
        if (
            pending_before in {"collect_competition_type", "collect_preferences"}
            and proposed_major
            and not explicit_identity_change
        ):
            if not str(understanding.get("competition_type") or "").strip():
                understanding["competition_type"] = proposed_major
                understanding["competition_type_status"] = "provided"
            understanding["major"] = ""
            understanding["corrected_fields"] = [
                item
                for item in understanding.get("corrected_fields", [])
                if str(item).strip() != "major"
            ]
            if understanding.get("dialogue_action") == "profile_change":
                understanding["dialogue_action"] = "continue"

        for key in ("input_role", "dialogue_action", "response_mode"):
            value = str(understanding.get(key) or "").strip()
            if value:
                state[key] = value

        acknowledgement = str(understanding.get("acknowledgement") or "").strip()
        if acknowledgement:
            state["last_acknowledgement"] = acknowledgement

        corrected_fields = {
            str(item).strip()
            for item in understanding.get("corrected_fields", [])
            if str(item).strip()
        }
        previous_profile = {
            key: deepcopy(state.get(key))
            for key in (
                "major",
                "grade",
                "skills",
                "competition_type",
                "competition_level",
                "team_preference",
            )
        }

        for key in (
            "major",
            "grade",
            "competition_type",
            "competition_scope",
            "competition_level",
            "team_preference",
            "project_name",
        ):
            value = understanding.get(key)
            if isinstance(value, str) and value.strip():
                state[key] = value.strip()

        for status_key in (
            "skills_status",
            "competition_type_status",
            "competition_level_status",
        ):
            value = str(understanding.get(status_key) or "").strip()
            # "unknown" means the field was not resolved in this turn; keep
            # an earlier explicit provided/no_preference decision.
            if value in {"provided", "no_preference"}:
                state[status_key] = value

        state["skills"] = self._append_conversation_values(
            state["skills"],
            understanding.get("skills_add", []),
        )
        removed_skills = {
            str(item).strip()
            for item in understanding.get("skills_remove", [])
            if str(item).strip()
        }
        if removed_skills:
            state["skills"] = [
                item for item in state["skills"] if item not in removed_skills
            ]
            state["skill_gaps"] = self._append_conversation_values(
                state["skill_gaps"],
                removed_skills,
            )
        if state["skills"]:
            state["skills_status"] = "provided"

        for source_key, target_key in (
            ("excluded_competition_types", "excluded_competition_types"),
            ("preferred_levels", "preferred_levels"),
            ("acceptable_levels", "acceptable_levels"),
            ("excluded_levels", "excluded_levels"),
            ("development_goals", "development_goals"),
        ):
            state[target_key] = self._append_conversation_values(
                state[target_key],
                understanding.get(source_key, []),
            )

        if state["competition_type"]:
            state["competition_type_status"] = "provided"
            state["interests"] = self._append_conversation_values(
                state["interests"],
                [state["competition_type"]],
            )
        if state["competition_level"]:
            state["competition_level_status"] = "provided"

        available_time = understanding.get("available_time_per_week")
        if isinstance(available_time, (int, float)) and available_time >= 0:
            state["available_time_per_week"] = available_time

        selected = understanding.get("selected_recommendation")
        if isinstance(selected, dict):
            selection = {
                "index": selected.get("index"),
                "title": str(selected.get("title") or "").strip(),
            }
            if selection["index"] is not None or selection["title"]:
                state["selected_recommendation"] = selection

        material_type = str(understanding.get("material_type") or "").strip()
        if material_type in self.valid_material_types:
            state["material_type"] = material_type

        options = understanding.get("recommendation_options")
        if isinstance(options, dict):
            state["recommendation_options"] = {
                key: value
                for key, value in options.items()
                if key in {
                    "top_n",
                    "include_backup",
                    "relax_quality_gate",
                    "explanation_requested",
                }
            }

        intent = str(understanding.get("intent") or "").strip()
        if intent:
            state["intent"] = intent
        elif state.get("input_role") == "user_profile" and not state.get("intent"):
            state["intent"] = "recommendation"
        if state.get("dialogue_action") == "generate_material":
            state["intent"] = "material"

        profile_changed = bool(
            corrected_fields
            & {
                "major",
                "grade",
                "skills",
                "competition_type",
                "competition_level",
                "team_preference",
            }
        ) or any(
            previous_profile[key] != state.get(key)
            for key in previous_profile
            if previous_profile[key] not in ("", [], None)
        )
        if profile_changed and state.get("dialogue_action") not in {
            "generate_material",
            "competition_detail",
            "compare_recommendations",
        }:
            state["last_recommendations"] = []
            state["last_result"] = {}
            state["selected_recommendation"] = {}
            state["project_name"] = ""
            state["material_type"] = ""

        state["conversation_summary"] = self._build_conversation_state_summary(state)
        return state

    def _resolve_conversation_intent(
        self,
        state: dict[str, Any],
        understanding: dict[str, Any],
    ) -> str:
        action = str(
            understanding.get("dialogue_action")
            or state.get("dialogue_action")
            or ""
        )
        if action == "generate_material":
            return "material"
        intent = str(
            understanding.get("intent") or state.get("intent") or ""
        ).strip()
        aliases = {
            "recommend": "recommendation",
            "generate_material": "material",
            "info_extract": "extract",
            "info_collect": "collect",
        }
        return aliases.get(intent, intent)

    def _next_recommendation_question(
        self,
        state: dict[str, Any],
    ) -> str | None:
        if not state.get("major"):
            state["pending_action"] = "collect_major"
            return "你现在学习什么专业？"
        if not state.get("grade"):
            state["pending_action"] = "collect_grade"
            return "你目前读大几，或者是在研究生阶段？"
        missing_preferences = [
            key
            for key, status_key in (
                ("direction", "competition_type_status"),
                ("skills", "skills_status"),
                ("level", "competition_level_status"),
            )
            if state.get(status_key) == "unknown"
        ]
        if len(missing_preferences) >= 2:
            state["pending_action"] = "collect_preferences"
            prompts = {
                "direction": "想尝试的方向（例如 AI、算法、建模或创新创业）",
                "skills": "目前会的技能、工具或做过的项目",
                "level": "对校级、省级、国家级或国际级有没有偏好",
            }
            details = "；".join(prompts[key] for key in missing_preferences)
            return (
                f"再简单说说这几项就可以开始推荐了：{details}。"
                "没有特别要求的部分直接说不限就行，不需要逐条回答。"
            )
        if state.get("competition_type_status") == "unknown":
            state["pending_action"] = "collect_competition_type"
            return (
                "你比较感兴趣的竞赛方向是什么？例如人工智能、算法、数学建模或创新创业；"
                "如果方向不限，也可以直接告诉我。"
            )
        if state.get("skills_status") == "unknown":
            state["pending_action"] = "collect_skills"
            return (
                "你目前有哪些比较熟悉的技能、工具或项目经历？"
                "没有特别擅长的也可以直接说明。"
            )
        if state.get("competition_level_status") == "unknown":
            state["pending_action"] = "collect_competition_level"
            return (
                "你更倾向校级、省级、国家级还是国际级？"
                "如果没有硬性要求也可以直接说明。"
            )
        state["pending_action"] = ""
        return None

    def _semantic_conversation_question(
        self,
        understanding: dict[str, Any],
        expected_target: str,
        fallback: str,
    ) -> str:
        """Use the LLM wording only when it matches MainAgent's decision."""
        target = str(understanding.get("reply_target") or "").strip()
        reply = str(understanding.get("reply_text") or "").strip()
        if (
            target == expected_target
            and reply
            and len(reply) <= 220
            and "```" not in reply
            and "http://" not in reply
            and "https://" not in reply
        ):
            return reply
        return fallback

    def _run_material_conversation(
        self,
        message: str,
        state: dict[str, Any],
        understanding: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            state.get("pending_action") == "collect_material_details"
            and state.get("material_type") in self.valid_material_types
        ):
            compact = re.sub(r"[\s，,。.!！?？]", "", message)
            if compact in {"生成", "直接生成", "先生成", "跳过", "暂不提供"}:
                state["material_generation_confirmed"] = True
            else:
                state["material_details"] = message

        recommendations = state.get("last_recommendations", [])
        if not recommendations and not state.get("project_name"):
            state["pending_action"] = "provide_material_project"
            fallback = self._with_acknowledgement(
                state,
                "我可以帮你准备材料。请先告诉我具体的竞赛或项目名称，"
                "或者先完成一次竞赛推荐。",
            )
            return self._conversation_response(
                text=self._semantic_conversation_question(
                    understanding,
                    "provide_material_project",
                    fallback,
                ),
                state=state,
                response_type="need_input",
            )

        selected = self._resolve_conversation_selection(state, understanding)
        if recommendations and not selected:
            state["pending_action"] = "select_material_competition"
            choices = "\n".join(
                f"{index}. {item.get('title') or item.get('name') or '未命名竞赛'}"
                for index, item in enumerate(recommendations[:5], 1)
            )
            return self._conversation_response(
                text=self._with_acknowledgement(
                    state,
                    f"你想为哪一个竞赛准备材料？回复序号或名称即可：\n\n{choices}",
                ),
                state=state,
                response_type="need_input",
            )

        if selected:
            selected_index = recommendations.index(selected) + 1
            selected_title = str(
                selected.get("title") or selected.get("name") or ""
            )
            state["selected_recommendation"] = {
                "index": selected_index,
                "title": selected_title,
            }
            state["project_name"] = selected_title

        if state.get("material_type") not in self.valid_material_types:
            state["pending_action"] = "select_material_type"
            return self._conversation_response(
                text=self._with_acknowledgement(
                    state,
                    "想准备哪种材料？可以选择申报书、项目计划书、个人简历、"
                    "PPT提纲、团队介绍、预算或进度安排。",
                ),
                state=state,
                response_type="need_input",
            )

        state["pending_action"] = ""
        result = self.run(
            self._build_conversation_agent_input(
                state,
                message,
                task_type="material",
            )
        )
        if str(result.get("status") or "") == "need_input":
            state["pending_action"] = "collect_material_details"
        else:
            state["pending_action"] = ""
        return self._conversation_agent_response(state, result)

    def _resolve_conversation_selection(
        self,
        state: dict[str, Any],
        understanding: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = state.get("last_recommendations", [])
        selection = understanding.get("selected_recommendation")
        if not isinstance(selection, dict):
            selection = state.get("selected_recommendation", {})
        try:
            index = int(selection.get("index"))
        except (TypeError, ValueError):
            index = 0
        if 1 <= index <= len(rows):
            return rows[index - 1]
        title = str(selection.get("title") or "").strip()
        if title:
            for row in rows:
                candidate = str(
                    row.get("title") or row.get("name") or ""
                ).strip()
                if candidate and (
                    candidate == title or candidate in title or title in candidate
                ):
                    return row
        return None

    def _build_conversation_agent_input(
        self,
        state_snapshot: dict[str, Any],
        message: str,
        *,
        task_type: str,
    ) -> dict[str, Any]:
        state = self._normalize_conversation_state(state_snapshot)
        profile = {
            "major": state["major"],
            "grade": state["grade"],
            "education_level": (
                "研究生" if state["grade"] == "研究生" else "本科"
            ),
            "interests": state["interests"],
            "skills": state["skills"],
            "skill_gaps": state["skill_gaps"],
            "competition_level": state["competition_level"],
            "development_goals": state["development_goals"],
            "available_time_per_week": state["available_time_per_week"],
            "team_preference": state["team_preference"],
        }
        payload: dict[str, Any] = {
            "data_source": "web",
            "preferences": {
                "preferred_levels": state["preferred_levels"],
                "acceptable_levels": state["acceptable_levels"],
                "excluded_levels": state["excluded_levels"],
                "excluded_competition_types": state[
                    "excluded_competition_types"
                ],
                "competition_scope": state["competition_scope"],
            },
        }
        if task_type == "recommendation":
            # A synchronous web request must not wait for every registered
            # crawler to fill a missing source.  InfoCollectAgent still uses
            # the shared Supabase cache/semantic search, while the primary
            # source keeps the request bounded.  Other collection entry points
            # retain their existing all-source behavior.
            info_config = (
                self.config.get("info_collect", {})
                if isinstance(self.config, dict)
                else {}
            )
            configured_sources = info_config.get(
                "conversation_sources",
                ["saikr"],
            )
            sources = [
                str(item).strip()
                for item in configured_sources
                if str(item).strip()
            ] if isinstance(configured_sources, list) else []
            payload["sources"] = sources or ["saikr"]
            payload["max_results"] = int(
                info_config.get("max_results", 10)
            )
        if state["competition_type"]:
            payload["keywords"] = [state["competition_type"]]
        if task_type == "recommendation" and state["recommendation_options"]:
            payload["recommendation_rules"] = state["recommendation_options"]
        if task_type == "material":
            selected = self._resolve_conversation_selection(state, {})
            payload["material_type"] = state["material_type"]
            if selected:
                name = (
                    selected.get("title")
                    or selected.get("name")
                    or state["project_name"]
                )
                payload["project_info"] = {
                    **selected,
                    "project_name": name,
                    "title": name,
                }
                selected_background = (
                    selected.get("summary")
                    or selected.get("reason")
                )
                if selected_background:
                    payload["project_info"]["background"] = selected_background
                payload["competition_info"] = {
                    **selected,
                    "competition_name": name,
                }
            elif state["project_name"]:
                payload["project_info"] = {
                    "project_name": state["project_name"],
                    "title": state["project_name"],
                }
                details = str(state.get("material_details") or "").strip()
                if details:
                    payload["project_info"].update({
                        "summary": details,
                        "background": details,
                    })
                elif state.get("material_generation_confirmed"):
                    payload["project_info"]["background"] = (
                        "用户明确要求先生成可编辑草稿；未知事实必须标记为“待补充”，不得编造。"
                    )
                    payload["requirements"] = {
                        "missing_information_policy": (
                            "未知的项目、团队、数据和指导教师信息必须使用“待补充”占位符，"
                            "不得虚构姓名、数据、机构、论文或成果。"
                        )
                    }

        return {
            "task_id": f"web_chat_{uuid4().hex[:8]}",
            "user_input": message,
            "task_type": task_type,
            "user_profile": profile,
            "context": {
                "conversation_summary": state["conversation_summary"],
                "recent_turns": state["turns"][-6:],
            },
            "input_data": payload,
            "history": [],
            "required_output": "markdown",
            "metadata": {
                "source": "main_agent_conversation",
                "ui_version": "4.0",
            },
        }

    def _conversation_agent_response(
        self,
        state: dict[str, Any],
        result: dict[str, Any],
        *,
        prefix: str = "",
    ) -> dict[str, Any]:
        state["last_result"] = result if isinstance(result, dict) else {}
        recommendations = self._conversation_recommendations(result)
        if recommendations:
            state["last_recommendations"] = recommendations
        text = self._conversation_result_text(result)
        if prefix:
            text = f"{prefix}\n\n{text}"
        status = str(result.get("status") or "failed")
        response_type = "result" if recommendations else "agent"
        if status in {"failed", "skipped"}:
            response_type = "error"
        elif status == "need_input":
            response_type = "need_input"
        return self._conversation_response(
            text=text,
            state=state,
            response_type=response_type,
            success=status in {"success", "partial"},
            recommendations=recommendations,
            files=self._conversation_files(result),
        )

    def _conversation_recommendations(
        self,
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []
        data = result.get("data", {})
        agent_results = data.get("agent_results", []) if isinstance(data, dict) else []
        for item in agent_results:
            rows = item.get("data", {}).get("recommendations", [])
            if isinstance(rows, list) and rows:
                return [row for row in rows if isinstance(row, dict)]
        return []

    def _conversation_files(self, result: dict[str, Any]) -> list[str]:
        files: list[str] = []
        if not isinstance(result, dict):
            return files
        for item in result.get("data", {}).get("agent_results", []):
            for value in item.get("data", {}).get("_saved_files", []) or []:
                path = str(value or "").strip()
                if path:
                    files.append(path)
        return files

    def _conversation_result_text(self, result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return "处理失败，请稍后重试。"
        data = result.get("data", {})
        text = data.get("final_answer") if isinstance(data, dict) else ""
        if str(text or "").strip():
            return str(text).strip()

        # ``message`` is an internal orchestration/debug field and may contain
        # values such as "MainAgent completed orchestration.".  It must never
        # be exposed as the assistant's user-facing answer.
        status = str(result.get("status") or "failed").strip().lower()
        if status == "need_input":
            return "还需要补充一些信息后才能继续，请根据当前提示完善相关内容。"
        if status == "partial":
            return "这次只完成了部分处理，你可以补充更多信息后再继续。"
        if status in {"failed", "skipped"}:
            return "这次处理没有成功，请稍后重试。"
        return "这一步已经处理完成。"

    def _conversation_profile_summary(self, state: dict[str, Any]) -> str:
        direction = state["competition_type"] or "方向不限"
        skills = (
            "、".join(state["skills"])
            if state["skills"]
            else "暂无特别擅长"
        )
        level = state["competition_level"] or "级别不限"
        return (
            f"明白了。我会按照**{state['major']}、{state['grade']}**，"
            f"竞赛方向为**{direction}**、技能情况为**{skills}**、"
            f"偏好**{level}**来进行推荐。"
        )

    def _with_acknowledgement(
        self,
        state: dict[str, Any],
        text: str,
    ) -> str:
        acknowledgement = str(
            state.get("last_acknowledgement") or ""
        ).strip()
        return f"{acknowledgement}\n\n{text}" if acknowledgement else text

    def _append_conversation_values(
        self,
        existing: list[Any],
        values: Any,
    ) -> list[str]:
        result = [
            str(item).strip()
            for item in existing
            if str(item).strip()
        ]
        iterable = values if isinstance(values, (list, tuple, set)) else []
        for item in iterable:
            value = str(item).strip()
            if value and value not in result:
                result.append(value)
        return result

    def _build_conversation_state_summary(
        self,
        state: dict[str, Any],
    ) -> str:
        parts = []
        for label, key in (
            ("专业", "major"),
            ("年级", "grade"),
            ("方向", "competition_type"),
            ("级别", "competition_level"),
            ("材料", "material_type"),
        ):
            value = state.get(key)
            if value:
                parts.append(f"{label}:{value}")
        if state.get("skills"):
            parts.append(f"技能:{'、'.join(state['skills'])}")
        return "；".join(parts)

    def _conversation_response(
        self,
        *,
        text: str,
        state: dict[str, Any],
        response_type: str = "agent",
        success: bool = True,
        recommendations: list[dict[str, Any]] | None = None,
        files: list[str] | None = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        return {
            "success": success,
            "response": {
                "text": str(text or ""),
                "type": response_type,
                "files": files or [],
                "recommendations": recommendations or [],
            },
            "state_snapshot": self._normalize_conversation_state(state),
            "metadata": {
                "status": "success" if success else "error",
                "reset": reset,
            },
        }

    def handle_followup(
        self,
        user_input: str,
        previous_result: dict[str, Any],
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Handle a conversational follow-up against a previous recommendation result.

        Returning ``None`` means the message is not a supported follow-up and should
        continue through the normal task-planning flow.
        """
        state = conversation_state or {}
        if self._is_result_status_request(user_input):
            answer = self._build_previous_result_status_answer(previous_result)
            if answer:
                return self._build_output(
                    task_id=self._get_task_id(previous_result),
                    status="need_input",
                    data={"final_answer": answer},
                    message="MainAgent explained why no recommendation result was produced.",
                    next_action="adjust_search_constraints",
                    metadata={
                        "followup_type": "result_status",
                        "agents_dispatched": [],
                    },
                )
        if (
            state.get("intent") in {"material", "full_process"}
            and not state.get("project_name")
        ):
            # The UI is waiting for the user to select which recommendation
            # should be passed to MaterialAgent. Ordinals belong to that flow.
            return None
        if self._is_comparison_request(user_input):
            recommendations = self._recommendations_from_result(previous_result)
            if len(recommendations) < 2:
                return None
            answer = self._build_comparison_answer(recommendations, user_input, state)
            return self._build_output(
                task_id=self._get_task_id(previous_result),
                status="success",
                data={"final_answer": answer, "compared_competitions": recommendations[:3]},
                message="MainAgent compared previous recommendations.",
                metadata={"followup_type": "competition_comparison", "generation_source": "deterministic"},
            )
        if not self._is_competition_detail_request(user_input):
            return None

        recommendations = self._recommendations_from_result(previous_result)
        if not recommendations:
            return self._build_output(
                task_id=self._get_task_id(previous_result),
                status="need_input",
                data={"final_answer": "我还没有拿到可供展开的推荐结果。你可以先告诉我想找哪类竞赛，我会从推荐开始帮你梳理。"},
                message="No previous recommendation is available.",
                next_action="Run a recommendation task first.",
                metadata={"followup_type": "competition_detail"},
            )

        selected = self._select_recommendation_for_detail(
            recommendations,
            user_input,
            preferred_title=str(state.get("project_name", "")),
        )
        if selected is None:
            choices = "；".join(
                f"{index}. {item.get('title', '未命名竞赛')}"
                for index, item in enumerate(recommendations, 1)
            )
            return self._build_output(
                task_id=self._get_task_id(previous_result),
                status="need_input",
                data={"final_answer": f"我知道你在接着问上一轮推荐，不过还不能确定你指的是哪一个。回复序号或名称就行：{choices}"},
                message="A recommendation reference needs clarification.",
                next_action="ask_user",
                metadata={"followup_type": "competition_reference_clarification"},
            )
        fallback = self._build_competition_detail_fallback(selected, user_input)
        generated = {"content": "", "error": None}
        if not self._is_direct_field_question(user_input):
            generated = self._call_detail_llm(user_input, selected)
        answer = generated.get("content") or fallback
        source_url = str(selected.get("source_url", "")).strip()
        if source_url:
            answer += f"\n\n[打开竞赛原始网页]({source_url})"
        else:
            answer += "\n\n> 当前采集结果没有提供可验证的原始网页链接。"
        answer += "\n\n> 请以主办方或竞赛官网的最新通知为准。"

        return self._build_output(
            task_id=self._get_task_id(previous_result),
            status="success",
            data={"final_answer": answer, "selected_competition": selected},
            message="MainAgent completed conversational follow-up.",
            metadata={
                "followup_type": "competition_detail",
                "generation_source": "llm" if generated.get("content") else "fallback",
                "generation_error": generated.get("error"),
            },
        )

    def handle_conversation_control(
        self,
        user_input: str,
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Handle greetings and clearly out-of-scope messages without dispatching agents."""
        text = str(user_input or "").strip()
        state = conversation_state or {}
        if not text:
            return None

        normalized = re.sub(r"[\s，,。.!！?？]", "", text).lower()
        if normalized in {"你好", "您好", "在吗", "hello", "hi", "嗨"}:
            answer = (
                "你好，我在。你可以直接说说现在遇到的问题：想找适合自己的竞赛、"
                "看懂一份竞赛通知，或者准备报名材料都可以。"
            )
            control_type = "greeting"
        elif normalized in {"谢谢", "感谢", "辛苦了", "多谢", "谢谢你"}:
            answer = "不客气。如果你还想比较几个竞赛，或者要继续准备报名材料，直接接着说就好。"
            control_type = "acknowledgement"
        elif self._is_clearly_out_of_scope(text, state):
            answer = (
                "这个方向我暂时帮得不够专业。我更擅长大学生科研与竞赛相关的事情，"
                "比如找竞赛、整理通知、做匹配推荐和准备申报材料。"
                "如果你愿意，可以直接告诉我你的专业和想参加的竞赛方向，我们从这里开始。"
            )
            control_type = "out_of_scope"
        else:
            return None

        return self._build_output(
            task_id="conversation_control",
            status="success",
            data={"final_answer": answer},
            message="MainAgent handled conversational control.",
            metadata={"followup_type": control_type, "agents_dispatched": []},
        )

    def _is_clearly_out_of_scope(self, text: str, state: dict[str, Any]) -> bool:
        domain_words = [
            "竞赛", "比赛", "项目", "科研", "通知", "报名", "申报", "材料", "资料",
            "简历", "计划书", "PPT", "推荐", "提取", "收集", "专业", "年级", "技能",
        ]
        if any(word in text for word in domain_words):
            return False
        correction_words = ["不是", "改成", "更正", "应该是", "选第", "第一个", "第二个", "第三个"]
        if any(word in text for word in correction_words):
            return False
        expected_short_answers = [
            "大一", "大二", "大三", "大四", "研究生", "校级", "省级", "国家级", "国际级",
            "Python", "Java", "C++", "人工智能", "算法", "数学建模", "创新创业",
        ]
        if any(word.lower() in text.lower() for word in expected_short_answers):
            return False
        explicit_off_topic = [
            "天气", "股票", "彩票", "做饭", "菜谱", "电影", "电视剧", "游戏攻略",
            "旅游攻略", "星座", "看病", "诊断疾病", "政治新闻", "写诗", "写小说",
        ]
        if any(word in text for word in explicit_off_topic):
            return True
        return not state.get("intent") and len(text) > 4

    def _is_competition_detail_request(self, message: str) -> bool:
        text = str(message or "").strip()
        return any(keyword in text for keyword in [
            "详细了解", "详细介绍", "具体介绍", "竞赛详情", "项目详情",
            "展开说说", "详细说说", "第一个", "第二个", "第三个",
            "什么时候", "截止", "报名", "组队", "团队", "主办方", "含金量",
            "难度", "适合我", "这个比赛", "这个竞赛", "它",
        ])

    @staticmethod
    def _is_result_status_request(message: str) -> bool:
        text = re.sub(r"[\s，,。.!！?？]", "", str(message or ""))
        return text in {
            "结果呢", "结果在哪里", "怎么没有结果", "为什么没有结果",
            "推荐结果呢", "没有推荐吗", "怎么没推荐",
            "什么信息", "缺什么信息", "还需要什么", "需要补充什么",
        }

    def _build_previous_result_status_answer(
        self, previous_result: dict[str, Any]
    ) -> str | None:
        agent_results = previous_result.get("data", {}).get("agent_results", [])
        if not isinstance(agent_results, list):
            return None
        if self._recommendations_from_result(previous_result):
            return None

        actionable = self._build_actionable_issue_answer(agent_results)
        if actionable:
            return actionable

        collected_count = None
        failed_messages = []
        for result in agent_results:
            data = result.get("data", {}) if isinstance(result, dict) else {}
            if result.get("agent_name") == "info_collect_agent":
                raw_items = data.get("raw_items")
                if isinstance(raw_items, list):
                    collected_count = len(raw_items)
            if result.get("status") in {"failed", "need_input", "skipped"}:
                message = str(result.get("message") or "").strip()
                if message:
                    failed_messages.append(message)

        if collected_count == 0:
            return (
                "这轮没有生成可展示的推荐结果。采集阶段没有找到符合当前专业方向和级别条件的"
                "有效竞赛，后续提取与评分因此无法继续。你可以放宽竞赛级别，或者告诉我是否接受"
                "与本专业相关的交叉方向，我会基于新条件重新查找。"
            )
        if failed_messages:
            return (
                "这轮没有生成可展示的推荐结果，原因是候选信息在采集或整理阶段没有满足推荐所需的"
                "完整条件。你的个人信息已经保留，可以调整方向或级别后重新查找。"
            )
        return None

    @staticmethod
    def _is_comparison_request(message: str) -> bool:
        text = str(message or "").strip()
        return any(keyword in text for keyword in [
            "对比", "比较", "哪个更", "哪一个更", "前两个", "这几个",
        ])

    @staticmethod
    def _is_direct_field_question(message: str) -> bool:
        text = str(message or "").strip()
        return any(keyword in text for keyword in ["什么时候", "截止", "报名时间", "组队", "团队", "主办方"])

    def _recommendations_from_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        for agent_result in result.get("data", {}).get("agent_results", []):
            recommendations = agent_result.get("data", {}).get("recommendations")
            if isinstance(recommendations, list) and recommendations:
                return [item for item in recommendations if isinstance(item, dict)]
        return []

    def _select_recommendation_for_detail(
        self,
        recommendations: list[dict[str, Any]],
        message: str,
        preferred_title: str = "",
    ) -> dict[str, Any] | None:
        ordinal_map = {
            "第一个": 0, "第一项": 0, "第1个": 0,
            "第二个": 1, "第二项": 1, "第2个": 1,
            "第三个": 2, "第三项": 2, "第3个": 2,
        }
        for marker, index in ordinal_map.items():
            if marker in message and index < len(recommendations):
                return recommendations[index]

        if preferred_title:
            for recommendation in recommendations:
                if str(recommendation.get("title", "")) == preferred_title:
                    return recommendation

        query = str(message or "").strip()
        for phrase in [
            "我想", "详细了解", "详细介绍", "具体介绍", "竞赛详情", "项目详情",
            "展开说说", "详细说说", "一下", "这个", "竞赛", "项目",
        ]:
            query = query.replace(phrase, "")
        query = query.strip(" ，。！？：:、“”'\"")
        if query:
            tokens = re.findall(r"[A-Za-z0-9+]+|[\u4e00-\u9fff]{2,}", query)
            for recommendation in recommendations:
                title = str(recommendation.get("title", ""))
                if query in title or any(token in title for token in tokens):
                    return recommendation
        if len(recommendations) == 1:
            return recommendations[0]
        return None

    def _build_competition_detail_fallback(self, selected: dict[str, Any], user_input: str = "") -> str:
        title = str(selected.get("title") or "未命名项目")
        text = str(user_input or "")
        if any(keyword in text for keyword in ["什么时候", "截止", "报名时间"]):
            deadline = str(selected.get("deadline") or "").strip()
            if deadline and deadline.lower() != "unknown":
                return f"**{title}** 当前记录的报名截止时间是 **{deadline}**。时间可能调整，提交前最好再到官网确认一次。"
            return f"目前的数据里没有 **{title}** 的可靠报名截止时间。我不想替你猜，建议打开原始页面核实最新通知。"
        if any(keyword in text for keyword in ["组队", "团队"]):
            requirements = selected.get("requirements", {}) if isinstance(selected.get("requirements"), dict) else {}
            team_requirement = str(requirements.get("team_requirement") or selected.get("team_requirement") or "").strip()
            if team_requirement and team_requirement.lower() != "unknown":
                return f"**{title}** 当前记录的组队要求是：{team_requirement}。"
            return f"目前的数据里没有明确写出 **{title}** 是否需要组队。这个条件会影响报名，建议以官网通知为准。"
        lines = [f"### {title}"]
        fields = [
            ("", selected.get("summary")),
            ("主办方", selected.get("organizer")),
            ("截止日期", selected.get("deadline")),
            ("适合你的原因", selected.get("reason")),
            ("注意事项", selected.get("risk")),
        ]
        for label, value in fields:
            value = str(value or "").strip()
            if not value or value.lower() == "unknown":
                continue
            lines.append(value if not label else f"- **{label}：** {value}")
        return "\n\n".join(lines)

    def _build_comparison_answer(
        self,
        recommendations: list[dict[str, Any]],
        user_input: str,
        state: dict[str, Any],
    ) -> str:
        selected = recommendations[:2]
        goal = "保研" if "保研" in user_input or "保研" in state.get("development_goals", []) else "你的当前需求"
        lines = [f"可以，我先按**{goal}**来比较前两个候选："]
        for index, item in enumerate(selected, 1):
            title = str(item.get("title") or f"候选 {index}")
            score = item.get("match_score")
            reason = str(item.get("reason") or item.get("summary") or "现有数据没有给出完整推荐理由").strip()
            deadline = str(item.get("deadline") or "待核实").strip()
            score_text = f"，匹配分 {score}" if score not in {None, ""} else ""
            lines.append(f"{index}. **{title}**{score_text}；截止时间：{deadline}；{reason}")
        lines.append("如果以保研为目标，还需要结合你所在学校的竞赛认定目录判断，当前数据不能直接证明某项比赛一定能获得加分。")
        return "\n\n".join(lines)

    def _call_detail_llm(
        self,
        user_input: str,
        selected: dict[str, Any],
    ) -> dict[str, Any]:
        llm_config = self.config.get("llm", {}) if isinstance(self.config, dict) else {}
        api_key_env = llm_config.get("api_key_env", "DEEPSEEK_API_KEY")
        api_key = llm_config.get("api_key", "") or os.getenv(str(api_key_env), "")
        if not api_key:
            return {"content": "", "error": f"Missing API key in {api_key_env}."}

        base_url = llm_config.get("base_url") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = llm_config.get("model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        source_data = {
            key: selected.get(key, "")
            for key in ["title", "summary", "deadline", "organizer", "type", "reason", "risk", "source_url"]
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是大学生竞赛顾问。严格回答用户实际提出的问题，只能使用竞赛数据中明确存在的事实。"
                        "数据没有提供的内容必须直接说‘当前信息未提供’，禁止根据常见竞赛经验推测参赛人群、"
                        "语言、赛制、奖项、题库、培训、就业或升学价值。先给直接结论，再简要说明依据，"
                        "最后列出确实需要官网核实的事项。回答控制在400字以内。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"用户问题：{user_input}\n竞赛数据：{json.dumps(source_data, ensure_ascii=False)}",
                },
            ],
            "temperature": 0.0,
            "max_tokens": 650,
        }
        request = urllib.request.Request(
            url=base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=int(llm_config.get("timeout", 30))) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            content = str(response_data["choices"][0]["message"]["content"] or "").strip()
            return {"content": content, "error": None}
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
            return {"content": "", "error": {"type": exc.__class__.__name__, "message": str(exc)}}

    def plan_task(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Use an optional LLM planner, then fall back to deterministic rules."""
        fallback_agents = self.select_agents(input_data)
        fallback_plan = self._build_rule_plan(input_data, fallback_agents)

        # Explicit task types come from the UI/API contract. Their dependency
        # chain must be determined by the data that is actually present, not
        # replaced by a free-form LLM plan that may request unavailable inputs.
        task_type = str(input_data.get("task_type", "")).lower()
        explicit_task_types = {
            "collect", "info_collect", "data_collect",
            "extract", "info_extract",
            "recommend", "recommendation",
            "material", "generate_material",
            "full_process", "application_assistant", "mvp_demo",
        }
        if task_type in explicit_task_types:
            return fallback_plan

        if not self._is_llm_enabled():
            return fallback_plan

        llm_plan = self._call_llm_planner(input_data)
        if not llm_plan.get("ok"):
            fallback_plan["planning_error"] = llm_plan.get("error")
            return fallback_plan

        normalized_plan = self._normalize_planning_result(llm_plan.get("data", {}))
        if not normalized_plan.get("selected_agents") and not normalized_plan.get("need_user_input"):
            fallback_plan["planning_error"] = {"message": "LLM returned no usable selected_agents."}
            return fallback_plan

        normalized_plan["planning_source"] = "llm"
        return normalized_plan

    def select_agents(self, input_data: dict[str, Any]) -> list[str]:
        """Deterministic fallback scheduler."""
        task_type = str(input_data.get("task_type", "")).lower()
        user_input = str(input_data.get("user_input", "")).lower()
        payload = input_data.get("input_data", {})

        if task_type in {"collect", "info_collect", "data_collect"}:
            return ["info_collect"]
        if task_type in {"extract", "info_extract"}:
            return ["info_extract"]
        if task_type in {"recommend", "recommendation"}:
            if payload.get("structured_items") or payload.get("projects"):
                return ["recommendation"]
            if self._has_raw_text_input(payload):
                return ["info_extract", "recommendation"]
            return ["info_collect", "info_extract", "recommendation"]
        if task_type in {"material", "generate_material"}:
            if payload.get("project_info") or payload.get("structured_items") or payload.get("projects"):
                return ["material"]
            if self._has_raw_text_input(payload):
                return ["info_extract", "material"]
            return ["material"]
        if task_type in {"full_process", "application_assistant", "mvp_demo"}:
            return self._select_full_process_agents(payload)

        selected = []
        if any(keyword in user_input for keyword in ["notice", "extract", "field", "deadline"]):
            selected.append("info_extract")
        if any(keyword in user_input for keyword in ["recommend", "match", "project", "competition"]):
            selected.extend(["info_collect", "recommendation"])
        if any(keyword in user_input for keyword in ["material", "application", "statement", "plan"]):
            selected.append("material")

        # Chinese keywords are encoded as unicode escapes to avoid source encoding issues.
        chinese_rules = [
            (["\u901a\u77e5", "\u62bd\u53d6", "\u5b57\u6bb5"], "info_extract"),
            (["\u63a8\u8350", "\u5339\u914d", "\u9879\u76ee", "\u7ade\u8d5b"], "recommendation"),
            (["\u6750\u6599", "\u7533\u8bf7", "\u6587\u4e66", "\u8ba1\u5212"], "material"),
        ]
        for keywords, agent_key in chinese_rules:
            if any(keyword in user_input for keyword in keywords):
                if agent_key == "recommendation":
                    selected.extend(["info_collect", "recommendation"])
                else:
                    selected.append(agent_key)

        return self._deduplicate(selected) or self._select_full_process_agents(payload)

    def integrate_results(
        self,
        input_data: dict[str, Any],
        agent_results: list[dict[str, Any]],
        planning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        planning = planning or {}
        successful_data = {
            result.get("agent_name", f"agent_{index}"): result.get("data", {})
            for index, result in enumerate(agent_results)
            if result.get("status") in {"success", "partial"}
        }
        errors = [
            {
                "agent_name": result.get("agent_name", "unknown"),
                "status": result.get("status", "failed"),
                "error": result.get("error"),
                "message": result.get("message", ""),
            }
            for result in agent_results
            if result.get("status") in {"failed", "skipped"}
        ]

        return {
            "task_summary": {
                "task_type": input_data.get("task_type"),
                "user_input": input_data.get("user_input"),
            },
            "planning": planning,
            "agent_results": agent_results,
            "integrated_data": successful_data,
            "errors": errors,
            "final_answer": self._build_final_answer(agent_results, planning),
            "next_action": planning.get("suggested_next_action") or self._suggest_next_action(errors),
        }

    def _call_llm_planner(self, input_data: dict[str, Any]) -> dict[str, Any]:
        llm_config = self.config.get("llm", {}) if isinstance(self.config, dict) else {}
        api_key_env = llm_config.get("api_key_env", os.getenv("SAIZHITONG_LLM_API_KEY_ENV", "DEEPSEEK_API_KEY"))
        api_key = llm_config.get("api_key", "")
        if not api_key and isinstance(api_key_env, str) and api_key_env.startswith("sk-"):
            api_key = api_key_env
        if not api_key:
            api_key = os.getenv(str(api_key_env), "")
        if not api_key:
            return {"ok": False, "error": {"message": f"Missing API key in {api_key_env}."}}

        base_url = llm_config.get("base_url") or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
        model = llm_config.get("model") or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-chat")
        timeout = int(llm_config.get("timeout", 30))
        url = base_url.rstrip("/") + "/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._build_planner_system_prompt()},
                {"role": "user", "content": self._build_planner_user_prompt(input_data)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            content = response_data["choices"][0]["message"]["content"]
            return {"ok": True, "data": self._parse_json_object(content)}
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
            return {"ok": False, "error": {"type": exc.__class__.__name__, "message": str(exc)}}

    def _is_llm_enabled(self) -> bool:
        llm_config = self.config.get("llm", {}) if isinstance(self.config, dict) else {}
        configured = bool(llm_config.get("enabled", False))
        env_enabled = os.getenv("SAIZHITONG_LLM_ENABLED", "").lower() in {"1", "true", "yes"}
        deepseek_key_exists = bool(os.getenv("DEEPSEEK_API_KEY", ""))
        gemini_key_exists = bool(os.getenv("GEMINI_API_KEY", ""))
        return configured or env_enabled or deepseek_key_exists or gemini_key_exists

    def _build_planner_system_prompt(self) -> str:
        return """
You are the Main Agent of a multi-agent system named SaiZhiTong.
The system helps university students find suitable research projects, competitions, and application opportunities, then assists with recommendation and application materials.

Your responsibility is not to complete the whole task yourself.
Your responsibility is to understand the user request, decide which sub agents should be called, and define what each sub agent should do.

Available sub agents:
1. info_collect: collects project or competition information from local data, web data, uploaded files, or APIs.
2. info_extract: extracts structured fields from unstructured text, such as title, deadline, requirements, materials, links, organizer, category.
3. recommendation: matches projects with the user profile and provides ranking, scoring, reasons, or Top-N results.
4. material: generates application checklist, application reason, project introduction, personal statement draft, research plan, timeline, or preparation suggestions.

Return valid JSON only. Do not output markdown. Do not explain outside JSON.

Required JSON schema:
{
  "task_type": "",
  "selected_agents": [],
  "reason": "",
  "agent_tasks": {
    "info_collect": "",
    "info_extract": "",
    "recommendation": "",
    "material": ""
  },
  "missing_information": [],
  "need_user_input": false,
  "suggested_next_action": ""
}

Task type must be one of: info_collect, info_extract, recommendation, material, full_process, qa, unknown.
Only use these agent names: info_collect, info_extract, recommendation, material.
If the user wants project recommendation from raw sources, select info_collect, info_extract, and recommendation.
If the user wants recommendation and application materials from raw sources, select info_collect, info_extract, recommendation, and material.
If the user provides notice text and asks to extract fields, select info_extract.
If the user provides notice text and wants recommendation, select info_extract and recommendation.
If the user wants complete application assistance, select info_collect, recommendation, material, and include info_extract only when notice text exists.
If the user only wants materials based on known project information, select material.
If no agent is needed, selected_agents must be empty.
""".strip()

    def _build_planner_user_prompt(self, input_data: dict[str, Any]) -> str:
        planner_input = {
            "task_id": input_data.get("task_id"),
            "user_input": input_data.get("user_input"),
            "task_type": input_data.get("task_type"),
            "user_profile": input_data.get("user_profile"),
            "context": input_data.get("context"),
            "input_data": input_data.get("input_data"),
            "history": input_data.get("history"),
            "required_output": input_data.get("required_output"),
            "metadata": input_data.get("metadata"),
        }
        return "Analyze this standard input and return the planning JSON:\n" + json.dumps(
            planner_input,
            ensure_ascii=False,
            indent=2,
        )

    def _parse_json_object(self, value: str) -> dict[str, Any]:
        value = value.strip()
        if value.startswith("```"):
            value = value.strip("`")
            if value.lower().startswith("json"):
                value = value[4:].strip()
        start = value.find("{")
        end = value.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise json.JSONDecodeError("No JSON object found", value, 0)
        return json.loads(value[start : end + 1])

    def _normalize_planning_result(self, plan: dict[str, Any]) -> dict[str, Any]:
        selected_agents = self._deduplicate(
            [agent for agent in plan.get("selected_agents", []) if agent in self.allowed_agents]
        )
        agent_tasks = plan.get("agent_tasks", {})
        if not isinstance(agent_tasks, dict):
            agent_tasks = {}

        return {
            "task_type": str(plan.get("task_type", "unknown")),
            "selected_agents": selected_agents,
            "reason": str(plan.get("reason", "")),
            "agent_tasks": {
                "info_collect": str(agent_tasks.get("info_collect", "")),
                "info_extract": str(agent_tasks.get("info_extract", "")),
                "recommendation": str(agent_tasks.get("recommendation", "")),
                "material": str(agent_tasks.get("material", "")),
            },
            "missing_information": plan.get("missing_information", []) if isinstance(plan.get("missing_information", []), list) else [],
            "need_user_input": bool(plan.get("need_user_input", False)),
            "suggested_next_action": str(plan.get("suggested_next_action", "")),
        }

    def _build_rule_plan(self, input_data: dict[str, Any], selected_agents: list[str]) -> dict[str, Any]:
        return {
            "task_type": input_data.get("task_type") or "unknown",
            "selected_agents": selected_agents,
            "reason": "Rule-based fallback planning was used.",
            "agent_tasks": {
                "info_collect": "Collect project or competition information." if "info_collect" in selected_agents else "",
                "info_extract": "Extract structured fields from notice or raw text." if "info_extract" in selected_agents else "",
                "recommendation": "Match projects with user profile and rank results." if "recommendation" in selected_agents else "",
                "material": "Generate application checklist and draft materials." if "material" in selected_agents else "",
            },
            "missing_information": [],
            "need_user_input": False,
            "suggested_next_action": "Run selected agents in order and integrate their outputs.",
            "planning_source": "rule",
        }

    def _load_sub_agents(self) -> dict[str, Any]:
        loaded_agents = {}
        for agent_key, (module_name, class_name) in self.sub_agent_specs.items():
            try:
                module = import_module(module_name)
                agent_class = getattr(module, class_name)
                loaded_agents[agent_key] = agent_class(self.config)
            except Exception as exc:
                loaded_agents[agent_key] = {
                    "load_error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                        "module": module_name,
                        "class": class_name,
                    }
                }
        return loaded_agents

    def _call_sub_agent(self, agent_key: str, agent_input: dict[str, Any]) -> dict[str, Any]:
        agent = self.sub_agents.get(agent_key)
        task_id = self._get_task_id(agent_input)

        if isinstance(agent, dict) and "load_error" in agent:
            return self._build_output(
                task_id=task_id,
                agent_name=self.sub_agent_specs[agent_key][1],
                status="skipped",
                data={},
                message=f"{agent_key} is not ready and was skipped.",
                error=agent["load_error"],
            )

        try:
            result = agent.run(agent_input)
            return self._normalize_agent_output(agent_key, task_id, result)
        except Exception as exc:
            return self._build_output(
                task_id=task_id,
                agent_name=self.sub_agent_specs[agent_key][1],
                status="failed",
                data={},
                message=f"{agent_key} execution failed.",
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def _build_agent_input(
        self,
        original_input: dict[str, Any],
        agent_key: str,
        previous_results: list[dict[str, Any]],
        shared_context: dict[str, Any],
    ) -> dict[str, Any]:
        agent_input = dict(original_input)
        agent_input["context"] = shared_context
        agent_input["metadata"] = {
            **original_input.get("metadata", {}),
            "called_by": self.agent_name,
            "target_agent": agent_key,
            "previous_agent_count": len(previous_results),
        }
        agent_input["history"] = [
            *original_input.get("history", []),
            {"role": self.agent_name, "event": f"dispatch_to_{agent_key}"},
        ]
        if agent_key == "info_collect":
            agent_input["input_data"] = self._adapt_info_collect_input(original_input)
        elif agent_key == "info_extract":
            agent_input["input_data"] = self._adapt_info_extract_input(
                original_input, shared_context
            )
        elif agent_key == "recommendation":
            agent_input["input_data"] = self._adapt_recommendation_input(
                original_input, shared_context
            )
        elif agent_key == "material":
            agent_input["input_data"] = self._adapt_material_input(
                original_input, shared_context
            )
        return agent_input

    def _adapt_info_collect_input(self, original_input: dict[str, Any]) -> dict[str, Any]:
        """Map the web form fields to InfoCollectAgent without changing its API."""
        payload = dict(original_input.get("input_data", {}))
        if payload.get("sources"):
            return payload

        data_source = str(payload.get("data_source", "")).lower()
        sources = []

        # 网页采集：默认爬取所有已注册的 web 数据源
        if data_source in {"web", "mixed", ""}:
            from .info_collect.registry import SourceRegistry
            sources = SourceRegistry.list_all()
        if data_source in {"upload", "mixed"} and payload.get("file_paths"):
            sources.append("local_file")

        if sources:
            payload["sources"] = sources
                # keywords 按用户输入为准，不自动填充
        # 空 keywords 在 Crawler._match() 中会匹配全部条目
        if "keywords" not in payload:
            # 用 user_profile.interests 构建关键词，而非整段用户输入
            profile_keywords = self._collection_keywords_from_profile(
                original_input.get("user_profile", {})
            )
            if profile_keywords:
                payload["keywords"] = profile_keywords
            else:
                user_input = str(original_input.get("user_input", "")).strip()
                if user_input and user_input not in ("都可以", "随便", "不限", "", "全部", "所有"):
                    payload["keywords"] = [user_input]
        return payload

    @staticmethod
    def _collection_keywords_from_profile(profile: dict[str, Any]) -> list[str]:
        """Use durable profile facts for collection; never use the latest chat reply."""
        if not isinstance(profile, dict):
            return []

        keywords = [
            str(value).strip()
            for value in profile.get("interests", [])
            if str(value).strip()
        ]
        major = str(profile.get("major") or "").strip()
        if major:
            keywords.append(major)
            normalized = major.removesuffix("专业")
            for suffix in ("科学与技术", "工程", "学"):
                if normalized.endswith(suffix) and len(normalized) > len(suffix):
                    normalized = normalized[: -len(suffix)]
                    break
            if len(normalized) >= 2:
                keywords.append(normalized)

        return list(dict.fromkeys(keywords))

    def _adapt_info_extract_input(
        self,
        original_input: dict[str, Any],
        shared_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Provide raw items from collection results or pasted notice text."""
        payload = dict(original_input.get("input_data", {}))
        if payload.get("raw_items"):
            return payload

        collect_result = shared_context.get("info_collect_result", {})
        if isinstance(collect_result, dict) and collect_result.get("raw_items"):
            payload["raw_items"] = collect_result["raw_items"]
            return payload

        raw_text = (
            payload.get("notification_text")
            or payload.get("raw_text")
            or payload.get("raw_project_text")
        )
        if raw_text:
            payload["raw_items"] = [{
                "title": "",
                "url": payload.get("source_url", ""),
                "source": payload.get("data_source", "user_input"),
                "raw_text": str(raw_text),
                "publish_date": "",
                "collected_at": "",
            }]
            return payload

        projects = payload.get("projects")
        if isinstance(projects, list):
            raw_items = []
            for project in projects:
                if isinstance(project, dict):
                    item = dict(project)
                    item.setdefault("raw_text", json.dumps(project, ensure_ascii=False))
                    raw_items.append(item)
            if raw_items:
                payload["raw_items"] = raw_items
        return payload

    def _adapt_recommendation_input(
        self,
        original_input: dict[str, Any],
        shared_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Provide structured items produced by InfoExtractAgent."""
        payload = dict(original_input.get("input_data", {}))
        if payload.get("structured_items"):
            return payload

        extract_result = shared_context.get("info_extract_result", {})
        if isinstance(extract_result, dict) and extract_result.get("structured_items"):
            payload["structured_items"] = extract_result["structured_items"]
            return payload

        projects = payload.get("projects")
        if isinstance(projects, list) and projects:
            payload["structured_items"] = projects
        return payload

    def _adapt_material_input(
        self,
        original_input: dict[str, Any],
        shared_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build MaterialAgent input from explicit or recommended project data."""
        payload = dict(original_input.get("input_data", {}))
        payload.setdefault("user_profile", original_input.get("user_profile", {}))

        project_info = payload.get("project_info")
        if isinstance(project_info, dict) and project_info:
            project_info = dict(project_info)
            project_info.setdefault(
                "project_name",
                project_info.get("title") or project_info.get("name", ""),
            )
            payload["project_info"] = project_info
            return payload

        structured_items = payload.get("structured_items")
        if not isinstance(structured_items, list) or not structured_items:
            extract_result = shared_context.get("info_extract_result", {})
            structured_items = (
                extract_result.get("structured_items", [])
                if isinstance(extract_result, dict)
                else []
            )

        selected_title = ""
        recommendation_result = shared_context.get("recommendation_result", {})
        if isinstance(recommendation_result, dict):
            recommendations = recommendation_result.get("recommendations", [])
            if recommendations:
                selected_title = str(recommendations[0].get("title", ""))

        selected = None
        for item in structured_items or []:
            if isinstance(item, dict) and (
                not selected_title or str(item.get("title", "")) == selected_title
            ):
                selected = dict(item)
                break

        if selected is None:
            projects = payload.get("projects", [])
            if isinstance(projects, list) and projects and isinstance(projects[0], dict):
                selected = dict(projects[0])

        if selected is not None:
            title = selected.get("project_name") or selected.get("title") or selected_title
            selected["project_name"] = str(title or "")
            payload["project_info"] = selected
            payload.setdefault("competition_info", {
                "competition_name": str(selected.get("title", "")),
                "competition_type": str(selected.get("type", "")),
                "deadline": str(selected.get("deadline", "")),
                "organizer": str(selected.get("organizer", "")),
            })
        return payload

    def _normalize_agent_output(self, agent_key: str, task_id: str, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return self._build_output(
                task_id=task_id,
                agent_name=self.sub_agent_specs[agent_key][1],
                status="failed",
                data={},
                message="Sub agent returned invalid output type.",
                error={"message": "Agent output must be a dict."},
            )

        output = self._build_output(
            task_id=result.get("task_id", task_id),
            agent_name=result.get("agent_name", self.sub_agent_specs[agent_key][1]),
            status=result.get("status", "success"),
            data=result.get("data", {}),
            message=result.get("message", ""),
            error=result.get("error"),
            next_action=result.get("next_action"),
            metadata=result.get("metadata", {}),
        )

        if output["status"] not in {"success", "failed", "partial", "need_input", "skipped"}:
            output["status"] = "partial"
            output["metadata"]["normalization_warning"] = "Unknown status was converted to partial."

        return output

    def _select_full_process_agents(self, payload: dict[str, Any]) -> list[str]:
        if payload.get("structured_items") or payload.get("projects"):
            selected = ["recommendation", "material"]
        elif self._has_raw_text_input(payload):
            selected = ["info_extract", "recommendation", "material"]
        else:
            selected = ["info_collect", "info_extract", "recommendation", "material"]
        return selected

    @staticmethod
    def _has_raw_text_input(payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("notification_text")
            or payload.get("raw_text")
            or payload.get("raw_project_text")
            or payload.get("raw_items")
        )

    def _build_final_answer(self, agent_results: list[dict[str, Any]], planning: dict[str, Any] | None = None) -> str:
        planning = planning or {}
        if planning.get("need_user_input"):
            missing = [
                str(item).strip()
                for item in planning.get("missing_information", [])
                if str(item).strip()
            ]
            if missing:
                return f"还缺少这些信息：{'、'.join(missing)}。补充后我就可以继续。"
            return "当前任务还缺少明确输入，请告诉我具体要找的竞赛方向或要处理的材料。"

        if not agent_results:
            return "我还没能确定下一步怎么处理。你可以换一种说法，告诉我想找竞赛、整理通知，还是准备材料。"

        statuses = [result.get("status", "failed") for result in agent_results]
        actionable_issue = self._build_actionable_issue_answer(agent_results)
        if actionable_issue and any(
            status in {"failed", "need_input", "skipped"} for status in statuses
        ):
            return actionable_issue
        recommendations = self._recommendations_from_agent_results(agent_results)
        collected_count = self._collected_item_count(agent_results)
        if not recommendations and collected_count == 0:
            return (
                "这轮没有找到符合当前专业方向和竞赛级别的有效候选，因此暂时没有推荐结果。"
                "你可以放宽级别，或者允许本专业相关的交叉方向，我再重新查找。"
            )
        if recommendations and any(status == "success" for status in statuses):
            names = "、".join(
                r.get("title", "")
                for r in recommendations[:3]
                if isinstance(r, dict) and r.get("title")
            )
            if all(status == "success" for status in statuses):
                return f"已为你推荐以下竞赛：{names}。你可以继续问我其中某个竞赛的详情，或者选择一个项目准备报名材料。"
            return f"已为你推荐以下竞赛：{names}。部分竞赛的详细信息可能不够完整，建议以官网通知为准。"
        if all(status == "success" for status in statuses):
            return "已经处理完成。你可以继续问我其中某个竞赛的详情，或者选择一个项目准备报名材料。"
        if any(status == "success" for status in statuses):
            return "我已经整理出一部分结果，不过还有少量信息没有完整获取。建议你先查看现有内容，我会把需要核实的地方保留下来。"
        if any(status == "need_input" for status in statuses):
            return "当前缺少可供处理的具体数据，请补充竞赛通知、候选项目或明确的材料内容。"
        return "这次处理没有顺利完成，可能是数据源或模型服务暂时不可用。你可以稍后重试，我会保留已经提供的条件。"

    @staticmethod
    def _build_actionable_issue_answer(
        agent_results: list[dict[str, Any]],
    ) -> str | None:
        """Explain whether the missing input belongs to the user or the data pipeline."""
        issue_texts = []
        for result in agent_results:
            if result.get("status") not in {"failed", "need_input", "skipped"}:
                continue
            error = result.get("error") or {}
            issue_texts.append(str(result.get("message") or ""))
            if isinstance(error, dict):
                issue_texts.extend([
                    str(error.get("message") or ""),
                    str(error.get("error_message") or ""),
                    str(error.get("suggestion") or ""),
                ])
        issue_text = " ".join(issue_texts).lower()

        for result in agent_results:
            if (
                result.get("agent_name") == "material_agent"
                and result.get("status") == "need_input"
            ):
                message = str(result.get("message") or "").strip()
                if message:
                    return message

        if "row-level security" in issue_text or "42501" in issue_text:
            return (
                "你的专业、年级和竞赛方向已经足够，不需要继续补充个人信息。"
                "这次没有生成推荐，是因为竞赛数据库的写入权限被 Supabase RLS 策略拦截，"
                "需要先修复数据库权限后再重新查询。"
            )
        if "structured_items" in issue_text or "结构化项目数据" in issue_text:
            return (
                "你的个人信息已经足够。当前缺少的是可供评分的竞赛候选数据，"
                "不是你的专业、年级或技能；请先恢复竞赛数据采集，或提供一份具体竞赛通知后再推荐。"
            )
        if "user_profile" in issue_text or "用户画像" in issue_text:
            return "还缺少你的专业和年级；告诉我这两项后，我就可以继续筛选竞赛。"
        return None

    @staticmethod
    def _recommendations_from_agent_results(
        agent_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for result in agent_results:
            recommendations = result.get("data", {}).get("recommendations")
            if isinstance(recommendations, list) and recommendations:
                return recommendations
        return []

    @staticmethod
    def _collected_item_count(
        agent_results: list[dict[str, Any]],
    ) -> int | None:
        for result in agent_results:
            if result.get("agent_name") != "info_collect_agent":
                continue
            raw_items = result.get("data", {}).get("raw_items")
            if isinstance(raw_items, list):
                return len(raw_items)
        return None

    def _resolve_final_status(self, agent_results: list[dict[str, Any]], planning: dict[str, Any] | None = None) -> str:
        planning = planning or {}
        if planning.get("need_user_input"):
            return "need_input"
        if not agent_results:
            return "success" if not planning.get("selected_agents") else "failed"

        statuses = {result.get("status") for result in agent_results}
        if statuses <= {"success"}:
            return "success"
        if "success" in statuses or "partial" in statuses:
            return "partial"
        if "need_input" in statuses:
            return "need_input"
        return "failed"

    def _suggest_next_action(self, errors: list[dict[str, Any]]) -> str | None:
        if not errors:
            return None
        return "Check skipped or failed sub agents, then rerun the same standard input."

    def _deduplicate(self, items: list[str]) -> list[str]:
        seen = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _get_task_id(self, input_data: Any) -> str:
        if isinstance(input_data, dict) and input_data.get("task_id"):
            return str(input_data["task_id"])
        return "unknown_task"

    def _build_output(
        self,
        task_id: str,
        status: str,
        data: dict[str, Any],
        message: str,
        error: Any = None,
        next_action: Any = None,
        metadata: dict[str, Any] | None = None,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "agent_name": agent_name or self.agent_name,
            "status": status,
            "data": data,
            "message": message,
            "error": error,
            "next_action": next_action,
            "metadata": metadata or {},
        }


if __name__ == "__main__":
    demo_input = {
        "task_id": "demo_task_001",
        "user_input": "Please recommend suitable research competitions and generate an application checklist.",
        "task_type": "full_process",
        "user_profile": {
            "major": "computer science",
            "grade": "junior",
            "interests": ["AI", "data analysis"],
        },
        "context": {},
        "input_data": {},
        "history": [],
        "required_output": "markdown",
        "metadata": {"source": "main_agent_demo"},
    }

    agent = MainAgent(config={})
    print(json.dumps(agent.run(demo_input), ensure_ascii=False, indent=2))




