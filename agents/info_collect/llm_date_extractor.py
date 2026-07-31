"""使用 DeepSeek API 从文本中智能提取报名截止日期，作为正则提取兜底。"""
"未使用，截止时间由抽取agent抽取回填数据库"

import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

_PROMPT = """从以下竞赛信息中提取"报名截止日期"，只输出日期，不要解释。

规则：
1. 报名截止日期是参赛者最后可以提交报名/注册的日期
2. 不是比赛开始日期，不是决赛日期，不是作品提交截止日期
3. 如果文本中只有"截止时间""截止日期"没有明确说是报名的，但上下文明显指报名，也可以提取
4. 格式统一为 YYYY-MM-DD，例如 2026-08-15
5. 如果找不到报名截止日期，输出 null

竞赛信息:
标题: {title}
描述: {description}

输出 (仅日期或 null):"""


def extract_regist_end(item: dict) -> str:
    """用 LLM 从 item 的描述文本中提取报名截止日期。

    只在 item['regist_end'] 为空时才调用此函数。
    返回提取到的日期字符串或 ""。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return ""

    title = (item.get("title") or "")[:200]
    description = (item.get("description") or "")[:1500]

    if not description.strip():
        return ""

    prompt = _PROMPT.format(title=title, description=description)

    try:
        from openai import OpenAI
    except ImportError:
        return ""

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=50,
            timeout=15,
        )
        text = resp.choices[0].message.content.strip()
        text = text.strip("'").strip('"').strip()

        if text.lower() == "null" or not text:
            return ""

        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        return ""
    except Exception as e:
        logger.debug("LLM 提取 regist_end 失败: %s", e)
        return ""


# 限流：两次 LLM 调用之间最小间隔（秒）
_last_call = 0.0
_MIN_INTERVAL = 1.0


def extract_regist_end_throttled(item: dict) -> str:
    """带限流的 LLM 提取，避免请求过快被限频。"""
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    result = extract_regist_end(item)
    _last_call = time.monotonic()
    return result
