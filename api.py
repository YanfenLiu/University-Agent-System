"""API 服务层：为前端 third-web 提供 RESTful API 接口。

用法
----
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import re
import uuid
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.main_agent import MainAgent

# ---------------------------------------------------------------------------
# 临时诊断日志
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[DIAG] %(asctime)s %(message)s")
logger = logging.getLogger("api_diagnosis")

# ---------------------------------------------------------------------------
# 项目路径与配置加载
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config() -> dict:
    """加载 YAML 配置，失败时返回空 dict。"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# 请求 / 响应数据模型
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    """前端 POST /api/agent/run 请求体。"""
    user_input: str = ""
    task_type: str = "full_process"
    user_profile: dict[str, Any] = {}
    context: dict[str, Any] = {}
    input_data: dict[str, Any] = {}
    history: list[dict[str, str]] = []


class AgentRunResponse(BaseModel):
    """返回给前端的统一响应结构。"""
    success: bool
    response: dict[str, Any]


MATERIAL_KEYWORDS = (
    "材料", "申报书", "申请书", "报名表", "计划书", "商业计划书",
    "路演稿", "答辩稿", "简历", "项目书",
)


def _resolve_api_task_type(
    requested_task_type: str,
    user_text: str,
    understanding: dict[str, Any] | None,
) -> str:
    """Resolve a concrete task instead of running ``full_process`` every turn."""
    understood_intent = str((understanding or {}).get("intent") or "").strip().lower()
    if understood_intent in {"material", "generate_material"}:
        return "material"
    if understood_intent in {"recommendation", "recommend"}:
        return "recommendation"
    if understood_intent in {"collect", "info_collect"}:
        return "info_collect"
    if understood_intent in {"extract", "info_extract"}:
        return "info_extract"

    text = str(user_text or "").strip()
    if any(keyword in text for keyword in MATERIAL_KEYWORDS):
        return "material"

    requested = str(requested_task_type or "").strip().lower()
    # The current Pages client historically sent full_process for every turn.
    # Recommendation is the safe default; material generation must be explicit.
    if requested in {"", "full_process", "application_assistant", "mvp_demo"}:
        return "recommendation"
    return requested


def _context_recommendations(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = context.get("last_recommendations", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _select_context_recommendation(
    user_text: str,
    recommendations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Select a prior recommendation by ordinal or title."""
    if not recommendations:
        return None
    text = str(user_text or "").strip()
    ordinal_map = {
        "第一个": 0, "第一项": 0, "1": 0,
        "第二个": 1, "第二项": 1, "2": 1,
        "第三个": 2, "第三项": 2, "3": 2,
    }
    for marker, index in ordinal_map.items():
        if marker in text and index < len(recommendations):
            return recommendations[index]
    for row in recommendations:
        title = str(row.get("title") or row.get("name") or "").strip()
        if title and title in text:
            return row
    return None


def _material_project_info(row: dict[str, Any]) -> dict[str, Any]:
    """Map the Pages recommendation shape to MaterialAgent project_info."""
    return {
        **row,
        "title": row.get("title") or row.get("name") or "未命名竞赛",
        "summary": row.get("summary") or row.get("description") or "",
        "source_url": row.get("source_url") or row.get("officialUrl") or "",
    }


def _need_material_selection(
    recommendations: list[dict[str, Any]],
) -> AgentRunResponse:
    if recommendations:
        choices = "\n".join(
            f"{index}. {row.get('title') or row.get('name') or '未命名竞赛'}"
            for index, row in enumerate(recommendations[:5], 1)
        )
        text = (
            "可以生成，但需要先确定你要为哪一个竞赛准备材料。"
            "请回复序号或竞赛名称：\n\n"
            f"{choices}"
        )
    else:
        text = (
            "可以生成材料。请先告诉我具体的竞赛或项目名称，"
            "并提供已有的通知、申报要求或项目简介。"
        )
    return AgentRunResponse(
        success=False,
        response={
            "text": text,
            "type": "need_input",
            "files": [],
            "recommendations": recommendations[:5],
        },
    )


# ---------------------------------------------------------------------------
# 构建 MainAgent.run() 标准输入
# ---------------------------------------------------------------------------


def build_minimal_input(
    user_input: str,
    task_type: str,
    user_profile: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    input_data: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """构建标准输入，兼容 MainAgent.run() 的所有必填字段。

    优先使用前端传递的已有状态，保持对话连续。
    """
    return {
        "task_id": f"api_task_{uuid.uuid4().hex[:8]}",
        "user_input": (user_input or "").strip(),
        "task_type": (task_type or "full_process").strip(),
        "user_profile": user_profile or {},
        "context": context or {},
        "input_data": input_data or {},
        "history": history or [],
        "required_output": "markdown",
        "metadata": {"source": "api", "ui_version": "2.0"},
    }


# ---------------------------------------------------------------------------
# FastAPI 应用实例
# ---------------------------------------------------------------------------

app = FastAPI(
    title="赛智通 Agent API",
    description="为前端 third-web 提供 Agent 调度 RESTful 接口",
    version="1.0.0",
)

# 允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@app.get("/")
def health_check() -> dict[str, str]:
    """健康检查端点，供 Render 等平台探测。"""
    return {"status": "ok", "service": "saizhitong-agent-api"}


@app.post("/api/agent/run", response_model=AgentRunResponse)
def run_agent(req: AgentRunRequest) -> AgentRunResponse:
    """【核心接口】接收前端请求 → 调度 MainAgent → 返回结果文本。"""
    try:
        # ---------------------------------------------------------------
        # [DIAG] 打印前端传来的完整请求
        # ---------------------------------------------------------------
        logger.info("=" * 80)
        logger.info("[STEP 1] 收到前端请求")
        logger.info(f"  user_input: {repr(req.user_input)}")
        logger.info(f"  task_type:  {repr(req.task_type)}")
        logger.info(f"  user_profile (原始): {json.dumps(req.user_profile, ensure_ascii=False)}")
        logger.info(f"  context keys: {list(req.context.keys()) if req.context else 'empty'}")
        logger.info(f"  input_data keys: {list(req.input_data.keys()) if req.input_data else 'empty'}")
        logger.info(f"  history turns: {len(req.history)}")

        # ---------------------------------------------------------------
        # 用户画像校验：full_process / recommendation 任务需要专业信息
        # ---------------------------------------------------------------
        profile = req.user_profile or {}
        major = str(profile.get("major") or "").strip()
        grade = str(profile.get("grade") or "").strip()

        # ---------------------------------------------------------------
        # 用户画像增强：从 user_input 中补充缺失的字段
        # ---------------------------------------------------------------
        user_text = str(req.user_input or "").strip()

        config = load_config()
        agent = MainAgent(config=config)
        conversation_state = {
            **(req.context or {}),
            **(req.user_profile or {}),
            "turns": [
                str(turn.get("content") or "")
                for turn in req.history
                if isinstance(turn, dict) and turn.get("role") == "user"
            ],
        }

        control = agent.handle_conversation_control(user_text, conversation_state)
        if control:
            return AgentRunResponse(
                success=True,
                response={
                    "text": control.get("data", {}).get(
                        "final_answer",
                        control.get("message", ""),
                    ),
                    "type": "agent",
                    "files": [],
                    "recommendations": [],
                },
            )

        understanding = agent.understand_conversation_turn(
            user_text,
            conversation_state,
        )
        resolved_task_type = _resolve_api_task_type(
            req.task_type,
            user_text,
            understanding,
        )
        needs_profile = resolved_task_type in {"recommend", "recommendation"}

        if needs_profile and not major:
            # 前端未传递专业信息，由后端自行从原始输入中提取
            major_hint = _detect_major_in_text(user_text)
            if major_hint:
                req.user_profile["major"] = major_hint
                req.user_profile["grade"] = _detect_grade_in_text(user_text)
            else:
                return AgentRunResponse(
                    success=False,
                    response={
                        "text": (
                            "我还不清楚你的专业和当前年级。\n\n"
                            "你可以这样告诉我：\n"
                            "• 「我是计算机科学与技术专业大二的学生」\n"
                            "• 「软件工程大三，想参加算法竞赛」\n"
                            "• 「电子信息工程大一，有推荐的比赛吗」\n\n"
                            "有了这些信息我才能帮你筛选真正适合的竞赛。"
                        ),
                        "type": "need_input",
                        "files": [],
                        "recommendations": [],
                    },
                )

        # 即使 major 已存在，也检查 interests 和 goal 是否缺失，从 user_input 中补充
        existing_interests = req.user_profile.get("interests", [])
        existing_goal = req.user_profile.get("goal", "")
        if not existing_interests:
            extracted_interests = _detect_interests_in_text(user_text)
            if extracted_interests:
                req.user_profile["interests"] = extracted_interests
                logger.info(f"  [画像增强] 从 user_input 提取 interests: {extracted_interests}")
        if not existing_goal:
            extracted_goal = _detect_goal_in_text(user_text)
            if extracted_goal:
                req.user_profile["goal"] = extracted_goal
                logger.info(f"  [画像增强] 从 user_input 提取 goal: {extracted_goal}")

        resolved_input_data = dict(req.input_data or {})
        if resolved_task_type == "material" and not resolved_input_data.get("project_info"):
            previous_recommendations = _context_recommendations(req.context or {})
            selected = _select_context_recommendation(
                req.user_input,
                previous_recommendations,
            )
            if selected is None:
                return _need_material_selection(previous_recommendations)
            resolved_input_data["project_info"] = _material_project_info(selected)

        standard_input = build_minimal_input(
            user_input=req.user_input,
            task_type=resolved_task_type,
            user_profile=req.user_profile,
            context=req.context,
            input_data=resolved_input_data,
            history=req.history,
        )

        # ---------------------------------------------------------------
        # [DIAG] 打印传入 MainAgent 的 standard_input
        # ---------------------------------------------------------------
        logger.info("[STEP 2] 构造的 standard_input 传给 MainAgent")
        logger.info(f"  user_input:     {repr(standard_input.get('user_input'))}")
        logger.info(f"  task_type:      {repr(standard_input.get('task_type'))}")
        logger.info(f"  understanding:  {json.dumps(understanding, ensure_ascii=False)}")
        logger.info(f"  user_profile:   {json.dumps(standard_input.get('user_profile'), ensure_ascii=False)}")
        logger.info(f"  input_data keys: {list(standard_input.get('input_data', {}).keys())}")

        # 特别检查 interests 字段是否存在
        up = standard_input.get("user_profile", {})
        interests = up.get("interests", [])
        major = up.get("major", "")
        goal = up.get("goal", "")
        logger.info(f"  >>> 提取的画像: major={repr(major)}, interests={interests}, goal={repr(goal)}")
        if not interests:
            logger.warning("  *** WARNING: interests 仍为空! 兴趣分将全部为 0")
        else:
            logger.info(f"  >>> interests 已填充 {len(interests)} 个兴趣关键词 ✓")
        if not goal:
            logger.info("  >>> goal 未提取（可选项，不影响推荐）")

        result = agent.run(standard_input)

        # 从 MainAgent 返回结果中提取可展示文本和推荐列表
        data = result.get("data", {})
        final_answer = (
            data.get("final_answer")
            or result.get("message", "")
        )
        if not final_answer:
            final_answer = "智能体执行完毕，但没有生成可展示的结果。"

        # 提取推荐列表（从任意子 agent 结果中获取）
        recommendations_list: list[dict[str, Any]] = []
        agent_results = data.get("agent_results", [])
        if isinstance(agent_results, list):
            for ar in agent_results:
                ar_data = ar.get("data", {}) if isinstance(ar, dict) else {}
                recs = ar_data.get("recommendations", [])
                if isinstance(recs, list) and recs:
                    recommendations_list = recs
                    break
        # 也检查根 data 层
        if not recommendations_list:
            recs = data.get("recommendations", [])
            if isinstance(recs, list) and recs:
                recommendations_list = recs

        # 确定 response type：
        # - success → "agent"（正常显示）
        # - partial + 有推荐 → "result"（显示推荐卡片）
        # - partial + 无推荐 → "agent"（仅展示说明文字）
        # - failed/need_input → "error" 或 "need_input"
        status = result.get("status", "failed")
        has_recs = bool(recommendations_list)
        if status == "partial":
            response_type = "result" if has_recs else "agent"
        elif status == "need_input":
            response_type = "need_input"
        elif status == "failed":
            response_type = "error"
        else:
            response_type = "agent"

        return AgentRunResponse(
            success=status in {"success", "partial"},
            response={
                "text": final_answer,
                "type": response_type,
                "files": [],
                "recommendations": recommendations_list,
            },
        )

    except Exception as exc:
        return AgentRunResponse(
            success=False,
            response={
                "text": f"服务器内部错误：{exc}",
                "type": "error",
                "files": [],
                "recommendations": [],
            },
        )


def _detect_major_in_text(text: str) -> str:
    """从用户输入中简单检测专业名称。"""
    known_majors = [
        "计算机科学与技术", "软件工程", "网络工程", "信息安全", "数据科学",
        "人工智能", "电子信息工程", "通信工程", "自动化", "电气工程",
        "机械工程", "土木工程", "建筑学", "数学", "应用数学", "统计学",
        "物理", "化学", "生物", "材料科学", "工商管理", "会计", "金融",
        "法学", "新闻传播", "汉语言文学", "英语", "医学", "药学",
    ]
    for major in known_majors:
        if major in text:
            return major
    # 尝试匹配 "XX专业" 模式
    match = re.search(r"([\u4e00-\u9fff]{2,8})专业", text)
    if match:
        return match.group(1)
    return ""


def _detect_grade_in_text(text: str) -> str:
    """从用户输入中检测年级。"""
    grade_map = {
        "大一": "大一", "大二": "大二", "大三": "大三", "大四": "大四",
        "研一": "研究生", "研二": "研究生", "研三": "研究生",
        "研究生": "研究生", "硕士": "研究生", "博士": "研究生",
    }
    for keyword, grade in grade_map.items():
        if keyword in text:
            return grade
    return ""


def _detect_interests_in_text(text: str) -> list[str]:
    """从用户输入中提取兴趣关键词（与前端 extractKeywords.ts 保持一致的兴趣集）。

    支持中英文混合表达，如 '对AI和编程感兴趣' → ['AI', '编程']。
    """
    interest_keywords = [
        "AI", "人工智能", "算法", "编程", "开发", "创新", "创业", "建模",
        "数学建模", "大数据", "数据", "数据分析", "数据挖掘", "数据科学",
        "安全", "网络安全", "游戏", "前端", "后端", "全栈", "产品",
        "设计", "UI", "UX", "机器学习", "深度学习", "视觉", "计算机视觉",
        "自然语言", "自然语言处理", "NLP", "物联网", "IoT",
        "区块链", "云计算", "嵌入式", "机器人", "图像", "图像处理",
        "音频", "视频", "多媒体", "硬件", "电路", "芯片", "半导体",
        "生物", "生物信息", "化学", "材料", "物理", "天文",
        "金融", "金融科技", "经济", "商业", "营销", "市场",
        "法律", "法学", "教育", "心理", "心理学", "社会", "社会学",
        "文学", "写作", "翻译", "外语", "英语",
        "医疗", "医学", "药学", "制药", "环境", "环保", "能源",
        "交通", "物流", "供应链", "农业", "食品",
    ]
    detected: list[str] = []
    normalized = text.lower()
    for keyword in interest_keywords:
        if keyword == "AI":
            if "ai" in normalized or "人工智能" in text:
                detected.append("AI")
        elif keyword == "数学建模":
            if "数学建模" in text or "建模" in text:
                detected.append("数学建模")
        elif keyword == "自然语言处理" or keyword == "NLP":
            if "自然语言" in text or "nlp" in normalized:
                detected.append("自然语言处理")
        elif keyword == "大数据":
            if "大数据" in text:
                detected.append("大数据")
        elif keyword in text and keyword not in detected:
            # 避免短词误匹配：长度 <=2 的词需要独立单词边界
            if len(keyword) <= 2:
                if re.search(rf"{re.escape(keyword)}", text):
                    detected.append(keyword)
            else:
                detected.append(keyword)
    # 去重并保持顺序
    seen = set()
    result: list[str] = []
    for item in detected:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _detect_goal_in_text(text: str) -> str:
    """从用户输入中提取目标/动机（与前端 extractKeywords.ts 一致的分类）。

    按优先级返回最先匹配到的目标类别：
    国奖类 > 省奖类 > 名次类 > 升学就业 > 能力提升 > 奖金奖励 > 入门尝试 > 进阶挑战
    """
    goal_rules: list[tuple[list[str], str]] = [
        (["国奖", "国家级", "国家一等奖", "国家二等奖", "国家三等奖",
          "全国一等奖", "全国二等奖", "全国三等奖"], "国家级奖项"),
        (["省奖", "省级", "省一", "省二", "省三",
          "省级一等奖", "省级二等奖", "省级三等奖"], "省级奖项"),
        (["一等奖", "二等奖", "三等奖", "金奖", "银奖", "铜奖",
          "最高奖", "特等奖"], "高名次奖项"),
        (["保研", "综测", "加分", "奖学金", "简历", "留学",
          "考研", "就业", "找工作"], "升学就业"),
        (["提升经验", "参与", "体验", "锻炼", "能力", "技能",
          "实践机会", "增长见识", "涨经验"], "能力提升"),
        (["奖金", "奖励", "奖品", "现金"], "奖金奖励"),
        (["入门", "新手", "小白", "零基础", "初级", "基础", "尝试"], "入门尝试"),
        (["进阶", "挑战", "突破", "提升", "拔高", "高难度"], "进阶挑战"),
    ]
    for keywords, label in goal_rules:
        if any(kw in text for kw in keywords):
            return label
    return ""


# ---------------------------------------------------------------------------
# 直接运行时启动开发服务器
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
