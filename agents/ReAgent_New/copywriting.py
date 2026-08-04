"""
等级映射与 reason / risk / suggested_action 文案（含个性化解释）。
"""

from __future__ import annotations

from typing import List, Optional

from .constants import COPY_DIM_KEYS, DIM_NAME_MAP, LEVEL_ORDER


def to_level(score: float, level_thresholds: list) -> tuple:
    """根据综合得分返回 (等级代码, 等级中文描述)。"""
    for threshold, code, label in level_thresholds:
        if score >= threshold:
            return code, label
    return "C", "不推荐"


def apply_level_cap(level_code: str, detail: dict, caps: dict) -> str:
    """年级或能力明显不足时封顶推荐等级（如最高 B）。"""
    max_level = caps.get("max_level", "B")
    grade_threshold = caps.get("grade_score_below", 40)
    ability_threshold = caps.get("ability_score_below", 30)
    should_cap = (
        detail.get("grade_score", 100) < grade_threshold
        or detail.get("ability_score", 100) < ability_threshold
    )
    if should_cap and LEVEL_ORDER.get(level_code, 0) > LEVEL_ORDER.get(max_level, 0):
        return max_level
    return level_code


def build_reason_template(detail: dict) -> str:
    """用内部评分选择自然理由，不向用户展示分数。"""
    phrases = {
        "interest_score": "方向与你的兴趣比较接近",
        "ability_score": "现有能力能够覆盖主要准备要求",
        "deadline_score": "当前准备时间相对合适",
        "team_score": "参赛形式与你的组队偏好比较接近",
        "grade_score": "对你目前所处阶段比较友好",
        "major_score": "与所学专业有一定关联",
    }
    ranked = sorted(
        ((key, float(detail.get(key, 0) or 0)) for key in COPY_DIM_KEYS),
        key=lambda value: value[1],
        reverse=True,
    )
    strengths = [phrases[key] for key, score in ranked[:2] if score >= 60 and key in phrases]
    if strengths:
        return f"这个项目{'，'.join(strengths)}，可以放在候选中进一步了解。"
    return "这个项目与当前条件有一定关联，可以作为备选了解。建议先查看赛题方向和参赛要求。"


def build_reason(
    detail: dict,
    user: Optional[dict] = None,
    item: Optional[dict] = None,
    matched_signals: Optional[List[str]] = None,
    unmatched_signals: Optional[List[str]] = None,
) -> str:
    """个性化推荐理由：把信号翻成完整句子；失败回退模板。"""
    sentences: List[str] = []
    signals = list(matched_signals or [])

    for sig in signals:
        if not isinstance(sig, str) or ":" not in sig:
            continue
        kind, text = sig.split(":", 1)
        text = text.strip()
        if not text:
            continue
        if kind == "兴趣":
            if "<->" in text:
                left, right = [x.strip() for x in text.split("<->", 1)]
                if left == right:
                    sentences.append(f"你的兴趣「{left}」与该赛主题高度吻合")
                else:
                    sentences.append(
                        f"你的兴趣「{left}」与赛事标签「{right}」相符"
                    )
            else:
                sentences.append(f"你的兴趣「{text}」与该赛方向一致")
        elif kind == "奖项":
            sentences.append(
                text if text.startswith("你有") else f"你有{text}相关经历"
            )
        elif kind == "团队":
            if "<->" in text:
                left, right = [x.strip() for x in text.split("<->", 1)]
                sentences.append(f"该赛要求{right}，与你当前「{left}」状态匹配")
            else:
                sentences.append(f"组队情况：{text}")
        elif kind == "技能命中":
            sentences.append(f"你的技能「{text}」能覆盖赛事要求")
        elif kind == "能力":
            sentences.append(text if "经历" in text else f"能力方面：{text}")
        if len(sentences) >= 3:
            break

    if not sentences and user and item:
        awards = user.get("awards") or []
        if awards and isinstance(awards[0], dict):
            a = awards[0]
            name = a.get("competition_name") or ""
            level = a.get("level") or ""
            award_name = a.get("award_name") or ""
            if name or award_name:
                sentences.append(f"你有{name}{level}{award_name}")
        team = (user.get("team_status") or "").strip()
        reqs = item.get("requirements", {}) if isinstance(item, dict) else {}
        team_req = ""
        if isinstance(reqs, dict):
            team_req = (reqs.get("team_requirement") or "").strip()
        if team and team_req:
            sentences.append(f"该赛要求{team_req}，与你「{team}」一致")

    if sentences:
        return "。".join(sentences[:2]) + "，可以放在候选中进一步了解。"
    return build_reason_template(detail)


def build_risk(
    detail: dict,
    unmatched_signals: Optional[List[str]] = None,
) -> str:
    """根据得分细节与未匹配信号构建风险提示。"""
    low_dims = [k for k in COPY_DIM_KEYS if detail.get(k, 100) < 50]

    extra = []
    for sig in (unmatched_signals or [])[:2]:
        text = sig.split(":", 1)[-1] if ":" in sig else sig
        if text:
            extra.append(text)

    advice = {
        "interest_score": "建议先查看赛题方向，确认是否符合你的兴趣",
        "ability_score": "建议先查看往届题目和技能要求，再判断准备时间是否足够",
        "deadline_score": "建议尽快核对截止时间和当前准备周期",
        "team_score": "建议先确认组队人数和队友要求",
        "grade_score": "建议确认参赛年级或培养阶段限制",
        "major_score": "建议确认专业限制和跨专业参赛要求",
    }
    notes = [advice[key] for key in low_dims[:2] if key in advice]
    if 50 <= detail.get("team_score", 100) < 70 and "team_score" not in low_dims:
        notes.append("建议报名前确认参赛形式和组队要求")
    if extra:
        notes.append(f"还需要留意{'、'.join(extra)}")
    if notes:
        return "。".join(notes[:2]) + "。"
    return "现有信息中没有发现明显限制，报名时再核对一次官方要求即可。"


def build_action(level_code: str, detail: dict, is_backup: bool = False) -> str:
    """根据推荐等级和得分细节生成建议行动。"""
    if is_backup:
        return "可以先了解赛题和准备周期，当前更适合作为备选。"
    if level_code == "S":
        return "可以先查看完整通知和往届内容，再决定是否重点准备。"
    if level_code == "A":
        actionable = {k: detail[k] for k in COPY_DIM_KEYS if k in detail}
        if actionable:
            low_key, low_score = min(actionable.items(), key=lambda x: x[1])
            if low_score < 70:
                return f"建议先确认{DIM_NAME_MAP[low_key]}相关要求，再决定是否报名。"
        return "可以和其他候选一起比较赛题方向和准备周期。"
    if level_code == "B":
        actionable = {k: detail[k] for k in COPY_DIM_KEYS if k in detail}
        if actionable:
            low_key, low_score = min(actionable.items(), key=lambda x: x[1])
            if low_score < 50 and low_key in DIM_NAME_MAP:
                return (
                    f"建议先确认{DIM_NAME_MAP[low_key]}相关要求，"
                    "并和其他候选一起比较。"
                )
        return "可以先简单了解，暂时不必投入过多准备时间。"
    return "当前更适合作为参考，可以继续比较其他项目。"
