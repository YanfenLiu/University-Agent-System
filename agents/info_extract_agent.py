"""
InfoExtractAgent -- 信息抽取 Agent
-----------------------------------
负责将非结构化通知文本（竞赛/科研项目）转换为结构化 JSON 数据。

规范遵循：PROJECT_SPEC_CN.md §12.2
文件位置：agents/info_extract_agent.py
类名：InfoExtractAgent
接口：run(input_data: dict) -> dict
"""

import json
import re
import time
import os
import importlib.util
import yaml
from typing import Optional, Any


class InfoExtractAgent:
    """从高校竞赛/科研通知文本中抽取结构化信息。"""

    # ── 类常量 ────────────────────────────────────────────
    AGENT_NAME = "info_extract_agent"

    VALID_TYPES = {"学科竞赛", "科研项目", "创新创业", "社会实践", "其他"}

    VALID_GRADES = {"大一", "大二", "大三", "大四", "大五"}

    VALID_EDUCATION = {"本科", "硕士", "博士"}

    VALID_TEAM_REQUIREMENT = {"单人", "组队", "不限", ""}

    REQUIRED_FIELDS = [
        "title", "type", "deadline", "registration_time",
        "contest_start", "contest_end",
        "requirements", "reward", "organizer", "source_url", "summary"
    ]

    REQUIRED_REQUIREMENT_FIELDS = [
        "target_majors", "target_grades", "target_education",
        "required_skills", "team_requirement", "tags", "category"
    ]

    FIELD_DEFAULTS = {
        "title": "unknown",
        "type": "其他",
        "deadline": "unknown",
        "registration_time": "unknown",
        "contest_start": "unknown",
        "contest_end": "unknown",
        "requirements": {
            "target_majors": [],
            "target_grades": [],
            "target_education": [],
            "required_skills": [],
            "team_requirement": "不限",
            "tags": [],
            "category": "unknown",
        },
        "reward": "unknown",
        "organizer": "unknown",
        "source_url": "",
        "summary": "unknown",
    }

    DEADLINE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def __init__(self, config: Optional[dict] = None):
        """
        初始化 Agent。

        Args:
            config: 配置字典。若为 None，从 config/config.yaml 读取。
                    必须包含 model 和 api 相关字段。
        """
        self.config = self._load_config(config)
        self.prompt_config = self._load_prompt_config()
        self.system_prompt = self.prompt_config.get("system", "")
        self.user_template = self.prompt_config.get("user_template", "")
        self.system_prompt_batch = self.prompt_config.get("system_batch", self.system_prompt)
        self.user_template_batch = self.prompt_config.get("user_template_batch", "")
        self.output_schema = self.prompt_config.get("output_schema", {})

        self._openai_available = False
        # 使用 find_spec 检查 openai 是否已安装（可选依赖，未安装时自动 Mock）
        if importlib.util.find_spec("openai") is not None:
            import openai  # type: ignore[no-redef]
            self.openai = openai
            self._openai_available = True

    # ── 配置加载 ─────────────────────────────────────────

    def _load_config(self, config: Optional[dict]) -> dict:
        """加载项目配置。"""
        if config is not None:
            return config

        config_paths = [
            os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"),
            os.path.join(os.getcwd(), "config", "config.yaml"),
        ]
        for p in config_paths:
            p = os.path.normpath(p)
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        return {}

    def _load_prompt_config(self) -> dict:
        """加载抽取 Prompt 模板配置。"""
        prompt_file = (
            self.config.get("agent", {})
            .get("info_extract", {})
            .get("prompt_file", "")
        )
        if prompt_file:
            prompt_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", prompt_file)
            )
        else:
            prompt_path = os.path.normpath(
                os.path.join(
                    os.path.dirname(__file__), "..",
                    "config", "extraction_prompt.yaml"
                )
            )

        if os.path.isfile(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    # ── 对外唯一入口 ─────────────────────────────────────

    def run(self, input_data: dict) -> dict:
        """
        Agent 唯一对外入口。

        输入（统一规范 §5）：
        {
            "task_id": "xxx",
            "user_input": "...",
            "task_type": "info_extract",
            "user_profile": {},
            "context": {},
            "input_data": {
                "raw_items": [
                    {
                        "title": "...",
                        "url": "...",
                        "source": "...",
                        "raw_text": "...",
                        "publish_date": "...",
                        "collected_at": "..."
                    }
                ],
                "extract_fields": [...]
            },
            "history": [],
            "required_output": "json",
            "metadata": {}
        }

        输出（统一规范 §6）：
        {
            "task_id": "xxx",
            "agent_name": "info_extract_agent",
            "status": "success|partial|failed",
            "data": { "structured_items": [...] },
            "message": "...",
            "error": null | {...},
            "next_action": null | "...",
            "metadata": {...}
        }
        """
        task_id = input_data.get("task_id", "")
        metadata = {"start_time": time.strftime("%Y-%m-%d %H:%M:%S")}

        # 1. 输入校验
        valid, err_msg = self.validate_input(input_data)
        if not valid:
            return self._build_response(
                task_id=task_id,
                status="failed",
                data={},
                message=f"输入校验失败: {err_msg}",
                error={
                    "error_type": "ValidationError",
                    "error_message": err_msg,
                    "suggestion": "请检查 input_data 中的 raw_items 格式是否正确。",
                },
                metadata=metadata,
            )

        # 2. 核心处理
        try:
            result_data = self.process(input_data)
        except Exception as e:
            return self._build_response(
                task_id=task_id,
                status="failed",
                data={},
                message=f"处理异常: {str(e)}",
                error={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "suggestion": "请检查 LLM API 配置或输入数据。",
                },
                metadata=metadata,
            )

        # 3. 判断整体状态
        structured_items = result_data.get("structured_items", [])
        success_count = sum(
            1 for it in structured_items
            if it.get("_extract_status") == "success"
        )
        failed_count = sum(
            1 for it in structured_items
            if it.get("_extract_status") == "failed"
        )

        if failed_count == 0:
            status = "success"
            message = f"全部 {success_count} 条文本抽取成功。"
        elif success_count > 0:
            status = "partial"
            message = f"部分成功：{success_count} 条成功，{failed_count} 条失败。"
        else:
            status = "failed"
            message = f"全部 {failed_count} 条文本抽取失败。"

        return self._build_response(
            task_id=task_id,
            status=status,
            data=result_data,
            message=message,
            metadata=metadata,
        )

    # ── 输入校验 ─────────────────────────────────────────

    def validate_input(self, input_data: dict):
        """
        校验输入格式。

        Returns:
            (bool, str): (是否合法, 错误信息)
        """
        if "input_data" not in input_data:
            return False, "缺少 input_data 字段。"

        inner = input_data["input_data"]
        if not isinstance(inner, dict):
            return False, "input_data 必须是 dict 类型。"

        if "raw_items" not in inner:
            return False, "input_data 中缺少 raw_items 字段。"

        raw_items = inner["raw_items"]
        if not isinstance(raw_items, list):
            return False, "raw_items 必须是 list 类型。"

        if len(raw_items) == 0:
            return False, "raw_items 不能为空。"

        for i, item in enumerate(raw_items):
            if not isinstance(item, dict):
                return False, f"raw_items[{i}] 必须是 dict 类型。"
            if "raw_text" not in item or not item["raw_text"]:
                return False, f"raw_items[{i}] 缺少 raw_text 或为空。"

        return True, ""

        # ── 核心业务逻辑 ─────────────────────────────────────

    MAX_BATCH_SIZE = 40  # 单次批量抽取最大条数（每条截断 3000 字符，40 条约 6 万 tokens，远低于 1M 上限）

    def process(self, input_data: dict) -> dict:
        """智能提取：已有结构化数据的数据项跳过 LLM，仅对脏数据做 LLM 提取。

        流程：
        1. 检查 API 是否可用，不可用则全部用缓存数据/回退（不调 LLM）
        2. 遍历 raw_items，区分「已有结构化数据」与「需 LLM 提取」
           - 已有 title+organizer 非空 → 直接 convert 为输出格式（跳过 LLM）
           - 其余项 → 加入待提取队列
        3. API 可用时：待提取队列分片批量调用 LLM（每片 ≤ MAX_BATCH_SIZE 条）
        4. 批量失败或 API 不可用 → 用缓存已有的字段做 fallback
        """
        inner = input_data.get("input_data", {})
        raw_items = inner.get("raw_items", [])
        total = len(raw_items)

        mock_enabled = self._should_use_mock()
        api_available = mock_enabled or self._llm_is_configured()
        if not api_available:
            print("[提取] API 未配置或不可用，跳过所有 LLM 调用，使用缓存数据")

        structured_items: list = [None] * total
        needs_llm_indices: list[int] = []
        needs_llm_raw: list[dict] = []

        # ── 第一步：所有记录都进 LLM 队列（保证 summary 是真生成的摘要，而非 description 原文）──
        # parser 已提取的结构化字段（title/时间/主办方）由 _apply_source_fallbacks 兜底，
        # LLM 负责生成真 summary 并补全缺失字段；仅 API 不可用时才缓存直通。
        for i, item in enumerate(raw_items):
            needs_llm_indices.append(i)
            needs_llm_raw.append(item)

        # ── 第二步：对需要 LLM 提取的项做批量抽取 ──
        if needs_llm_raw and api_available:
            n = len(needs_llm_raw)
            print(f"[提取] {n}/{total} 条需要 LLM 提取（最多分片 {self.MAX_BATCH_SIZE} 条/批）")

            for chunk_start in range(0, n, self.MAX_BATCH_SIZE):
                chunk_end = min(chunk_start + self.MAX_BATCH_SIZE, n)
                chunk_items = needs_llm_raw[chunk_start:chunk_end]
                chunk_indices = needs_llm_indices[chunk_start:chunk_end]

                batch_results, batch_ok = self._call_llm_batch_extract(chunk_items)

                if batch_ok and batch_results is not None:
                    for offset, extracted in enumerate(batch_results):
                        global_i = chunk_indices[offset]
                        if isinstance(extracted, dict):
                            try:
                                structured_items[global_i] = self._finalize_item(
                                    extracted, chunk_items[offset]
                                )
                            except Exception:
                                self._use_cache_fallback(global_i, chunk_items[offset],
                                                          raw_items, structured_items)
                        else:
                            self._use_cache_fallback(global_i, chunk_items[offset],
                                                      raw_items, structured_items)
                else:
                    # 本分片批量失败 → 用缓存字段兜底（不逐条调 LLM）
                    for offset, global_i in enumerate(chunk_indices):
                        self._use_cache_fallback(global_i, chunk_items[offset],
                                                  raw_items, structured_items)

        elif needs_llm_raw and not api_available:
            raise RuntimeError(
                "当前无法连接可靠的信息抽取服务，已停止处理以避免生成模拟结果。"
            )
        else:
            print(f"[提取] 全部 {total} 条自带结构化数据，跳过 LLM 提取")

        # ── 第三步：确保无 None ──
        for i in range(total):
            if structured_items[i] is None:
                structured_items[i] = self._build_fallback_item(
                    raw_items[i], "处理遗漏"
                )

        return {"structured_items": structured_items}

    def _use_cache_fallback(
        self,
        idx: int,
        chunk_item: dict,
        raw_items: list[dict],
        structured_items: list,
    ):
        """使用缓存数据中的已有字段做 fallback，不调 LLM。"""
        print(f"  [缓存兜底] ({idx+1}/? ) {chunk_item.get('title','')[:50]} ...")
        extracted = {
            "title": chunk_item.get("title", "") or "unknown",
            "deadline": chunk_item.get("regist_end", "") or "unknown",
            "registration_time": chunk_item.get("regist_start", "") or "unknown",
            "organizer": chunk_item.get("organizer", "") or "unknown",
            "summary": self._rule_based_summary(
                str(chunk_item.get("description", "") or chunk_item.get("title", "unknown"))
            ),
            "type": "其他",
            "reward": "unknown",
            "requirements": dict(self.FIELD_DEFAULTS["requirements"]),
            "source_url": chunk_item.get("url", ""),
        }
        structured_items[idx] = self._finalize_item(extracted, chunk_item)

    def _apply_source_fallbacks(self, extracted: dict, raw_item: dict) -> dict:
        """Keep trustworthy collector fields when LLM extraction is unavailable."""
        result = dict(extracted)
        missing = {None, "", "unknown"}

        if result.get("title") in missing and raw_item.get("title"):
            result["title"] = str(raw_item["title"])
        if result.get("organizer") in missing and raw_item.get("organizer"):
            result["organizer"] = str(raw_item["organizer"])
        if result.get("summary") in missing:
            description = str(raw_item.get("description", "")).strip()
            result["summary"] = self._rule_based_summary(description) or str(raw_item.get("title", "unknown"))

        if result.get("deadline") in missing:
            deadline = str(raw_item.get("regist_end", "")).strip()
            date_match = re.search(r"\d{4}[/-]\d{2}[/-]\d{2}", deadline)
            if date_match:
                result["deadline"] = date_match.group(0).replace("/", "-")

        if result.get("registration_time") in missing:
            registration_time = str(raw_item.get("regist_start", "")).strip()
            if registration_time:
                result["registration_time"] = registration_time

        # 比赛时间：LLM 没抽到就用 parser 从列表/详情解析的兜底
        for llm_field, parser_field in (("contest_start", "contest_start"), ("contest_end", "contest_end")):
            if result.get(llm_field) in missing:
                parsed = str(raw_item.get(parser_field, "") or "").strip()
                if parsed:
                    result[llm_field] = parsed

        requirements = result.get("requirements", {})
        if not isinstance(requirements, dict):
            requirements = dict(self.FIELD_DEFAULTS["requirements"])
        requirements = dict(requirements)
        source_tags = [
            str(value).strip()
            for value in (raw_item.get("category"), raw_item.get("level"))
            if value not in missing
        ]
        if source_tags and not requirements.get("tags"):
            requirements["tags"] = source_tags
        if requirements.get("category") in missing and raw_item.get("category"):
            requirements["category"] = str(raw_item["category"])
        result["requirements"] = requirements
        return result

    # ── 批量抽取 ───────────────────────────────────────

    def _build_batch_user_prompt(self, raw_items: list[dict]) -> str:
        """将多条 raw_items 拼接为一个批量抽取 user prompt。"""
        parts = []
        for i, item in enumerate(raw_items, 1):
            title = item.get("title", "") or "未知项目"
            url = item.get("url", item.get("source_url", ""))
            raw_text = item.get("raw_text", "")
            # 正文智能截断：取前 1500 + 后 1500 字符（头尾含核心信息，中段多为规则细节）
            head = raw_text[:1500]
            tail = raw_text[-1500:] if len(raw_text) > 3000 else ""
            if tail:
                raw_text = head + "\n...(中段省略)...\n" + tail
            else:
                raw_text = head
            parts.append(
                f"--- 第{i}条 ---\n"
                f"标题：{title}\n"
                f"来源：{url}\n"
                f"正文：\n{raw_text}\n"
            )
        items_text = "\n".join(parts)
        return self.user_template_batch.format(items_text=items_text)

    def _parse_llm_json_array(self, text: str) -> list | None:
        """解析 LLM 返回的 JSON 数组，失败返回 None。"""
        if not text or not text.strip():
            return None
        text = text.strip()

        # 策略 1：直接解析数组
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 策略 2：```json [...] ```
        match = re.search(r"```json\s*(\[[\s\S]*?\])\s*```", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略 3：``` [...] ```
        match = re.search(r"```\s*(\[[\s\S]*?\])\s*```", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略 4：定位第一个 [ 到最后一个 ]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略 5：单引号 → 双引号
        try:
            candidate = text.replace("'", '"')
            start = candidate.find("[")
            end = candidate.rfind("]")
            if start != -1 and end != -1 and end > start:
                result = json.loads(candidate[start:end + 1])
                if isinstance(result, list):
                    return result
        except json.JSONDecodeError:
            pass

        return None

    def _call_llm_batch_extract(
        self, raw_items: list[dict]
    ) -> tuple:
        """批量调用 LLM 一次性抽取所有通知。

        Returns:
            (list | None, ok: bool)
            - ok=True：返回 list，长度与 raw_items 对齐
            - ok=False：批量失败，调用方应降级逐条
        """
        if not self.system_prompt_batch or not self.user_template_batch:
            return None, False

        user_prompt = self._build_batch_user_prompt(raw_items)
        messages = [
            {"role": "system", "content": self.system_prompt_batch},
            {"role": "user", "content": user_prompt},
        ]

        try:
            total = len(raw_items)
            batch_max_tokens = max(2048, 400 * total)
            print(f"[批量抽取] 尝试一次抽取 {total} 条通知 ...")
            response_text = self._call_api(messages, max_tokens=batch_max_tokens)
            parsed = self._parse_llm_json_array(response_text)

            if parsed is None or not isinstance(parsed, list):
                print("  [批量] JSON 解析失败，将降级逐条重试")
                return None, False

            if len(parsed) < total:
                print(
                    f"  [批量] 返回 {len(parsed)} 条，期望 {total} 条，"
                    f"缺 {total - len(parsed)} 条将逐条补抽"
                )
                parsed.extend([None] * (total - len(parsed)))

            if len(parsed) > total:
                parsed = parsed[:total]

            success_n = sum(1 for p in parsed if p is not None)
            print(f"  [批量] 成功返回 {success_n}/{total} 条有效结果")
            return parsed, True

        except Exception as e:
            print(f"  [批量] API 调用失败: {e}，将降级逐条重试")
            return None, False

    def _finalize_item(self, extracted: dict, raw_item: dict) -> dict:
        """对单条 LLM 抽取结果做 validate + fallback + 元数据标记。"""
        source_url = raw_item.get("url", raw_item.get("source_url", ""))
        validated = self._validate_and_fix(extracted)
        validated = self._apply_source_fallbacks(validated, raw_item)
        if not validated.get("source_url") or validated["source_url"] == "unknown":
            validated["source_url"] = source_url
        validated["_extract_status"] = "success"
        validated["_source_title"] = raw_item.get("title", "")
        validated["_source"] = raw_item.get("source", "")
        validated["_collected_at"] = raw_item.get("collected_at", "")
        # P2-1: 统一后处理校验 summary 质量
        validated["summary"] = self._normalize_summary(validated.get("summary", ""))
        return validated

    # ── 缓存直通路径：摘要生成 ─────────────────────────

    def _generate_cache_summary(self, text: str) -> str:
        """对缓存直通路径的原始 description/raw_text 调用 LLM 生成精炼摘要。"""
        if not text or len(text) < 20:
            return text
        # 截断到 2000 字符 — 摘要不需要完整原文
        source = text[:2000]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个信息摘要助手。将下面的竞赛/科研项目文本精炼为一段"
                    "80-150字的中文摘要。提取核心差异化信息而非堆砌字段值："
                    "包括比赛形式特点、与同类活动的差异、参赛可获得的收益。"
                    "不要输出任何格式标记，直接返回摘要文本。"
                ),
            },
            {"role": "user", "content": source},
        ]
        try:
            response_text = self._call_api(messages, max_tokens=300)
            result = str(response_text or "").strip()
            # 清理可能残留的 markdown 标记
            result = result.strip("`\"' '\n\r\t")
            if result and len(result) >= 15:
                return result
        except Exception as e:
            print(f"  [摘要生成] LLM 调用失败: {e}，回退规则提取")
        return self._rule_based_summary(text)

    @staticmethod
    def _rule_based_summary(text: str) -> str:
        """规则提取摘要：取前 2 句；原文很长时附上末尾一句（含奖励/联系方式等信息）。"""
        if not text or len(text) < 20:
            return text or "unknown"
        import re as _re
        sentences = _re.split(r"[。！；\n]", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 6]
        if not sentences:
            return text[:150].strip()
        # 取前两句
        result = "。".join(sentences[:2]) + "。"
        # 如果原文很长（>500 字），附上最后一句
        if len(text) > 500 and len(sentences) > 3:
            last = sentences[-1]
            if last and last != sentences[0] and last != sentences[1]:
                if len(result) + len(last) + 1 <= 200:
                    result = result.rstrip("。") + "；" + last + "。"
        result = result[:200].strip()
        return result

    # ── 摘要后处理校验 ──────────────────────────────────

    @staticmethod
    def _normalize_summary(summary: str) -> str:
        """统一校验并修复 summary 字段质量。

        - 过长（>350 字）→ 截断
        - 含 HTML 标签 → 清洗
        - 实质为空 → 标记
        """
        import re as _re
        if not summary or summary in ("unknown", ""):
            return summary
        # 清洗 HTML 标签
        cleaned = _re.sub(r"<[^>]+>", "", summary)
        cleaned = _re.sub(r"\s{2,}", " ", cleaned).strip()
        if not cleaned:
            return "unknown"
        # 过长截断
        if len(cleaned) > 350:
            # 尝试在句号处截断
            break_at = cleaned.rfind("。", 0, 320)
            if break_at > 100:
                cleaned = cleaned[:break_at + 1]
            else:
                cleaned = cleaned[:320] + "…"
        return cleaned

    def _build_fallback_item(self, raw_item: dict, error: str) -> dict:
        """构造单条抽取失败时的占位条目。"""
        source_url = raw_item.get("url", raw_item.get("source_url", ""))
        return {
            "title": raw_item.get("title", "unknown"),
            "type": "其他",
            "deadline": "unknown",
            "registration_time": "unknown",
            "requirements": dict(self.FIELD_DEFAULTS["requirements"]),
            "reward": "unknown",
            "organizer": "unknown",
            "source_url": source_url,
            "summary": "unknown",
            "_extract_status": "failed",
            "_extract_error": error,
            "_source_title": raw_item.get("title", ""),
            "_source": raw_item.get("source", ""),
            "_collected_at": raw_item.get("collected_at", ""),
        }

    # ── 逐条抽取（保留，供批量降级时使用）───────────────

    def _call_llm_extract(self, raw_text: str, source_url: str) -> dict:
        """
        调用 LLM API 进行信息抽取。

        Args:
            raw_text: 通知原文
            source_url: 来源链接

        Returns:
            LLM 返回的 dict

        Raises:
            RuntimeError: API 调用失败
        """
        user_prompt = self.user_template.format(
            raw_text=raw_text[:4000],
            source_url=source_url,
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response_text = self._call_api(messages)
        return self._parse_llm_json(response_text)

    def _should_use_mock(self) -> bool:
        """仅在测试环境或显式配置时允许使用 Mock。"""
        testing_config = self.config.get("testing", {})
        explicitly_enabled = bool(
            isinstance(testing_config, dict)
            and testing_config.get("mock_enabled", False)
        )
        env_enabled = os.getenv("SAIZHITONG_MOCK_ENABLED", "").lower() in {
            "1", "true", "yes"
        }
        return explicitly_enabled or env_enabled

    def _llm_is_configured(self) -> bool:
        """生产抽取必须具备真实模型依赖与凭证。"""
        if not self._openai_available:
            return False
        llm_config = self.config.get("llm", {})
        api_config = self.config.get("api", {})
        api_key_env = llm_config.get("api_key_env", "DEEPSEEK_API_KEY")
        api_key = api_config.get("key", "") or os.getenv(api_key_env, "")
        base_url = api_config.get("base_url", "") or llm_config.get("base_url", "")
        return bool(api_key and base_url)

    def _call_api(self, messages: list, max_tokens: int = 0) -> str:
        """
        调用 OpenAI 兼容 API，未配置时回退到 Mock 模式。
        400 类客户端错误不重试（重试也无意义）。
        """
        if self._should_use_mock():
            return self._mock_extract(messages)
        if not self._llm_is_configured():
            raise RuntimeError(
                "当前无法连接可靠的信息抽取服务，已停止处理以避免生成模拟结果。"
            )

        llm_config = self.config.get("llm", {})
        model_config = self.config.get("model", {}) or llm_config
        api_config = self.config.get("api", {})

        api_key = api_config.get("key", "") or os.getenv(llm_config.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        base_url = api_config.get("base_url", "") or llm_config.get("base_url", "")
        model_name = model_config.get("name", "") or model_config.get("model", "")
        temperature = model_config.get("temperature", 0.3)
        resolved_max_tokens = max_tokens or model_config.get("max_tokens", 2048)

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = self.openai.OpenAI(**client_kwargs)

        timeout = self.config.get("agent", {}).get("timeout", 60)
        max_retry = self.config.get("agent", {}).get("max_retry", 3)
        last_error = None

        for attempt in range(max_retry):
            try:
                print(f"  [API] 第 {attempt+1}/{max_retry} 次调用 {model_name} ...")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=resolved_max_tokens,
                    timeout=timeout,
                )
                print(f"  [API] 调用成功")
                return response.choices[0].message.content
            except KeyboardInterrupt:
                print(f"  [API] 用户中断，正在退出...")
                raise
            except Exception as e:
                last_error = e
                err_str = str(e)
                print(f"  [API] 调用失败: {type(e).__name__}: {err_str[:120]}")
                # 400 BadRequest / 401 Unauthorized / 404 NotFound → 不重试
                if "400" in err_str or "401" in err_str or "404" in err_str:
                    if attempt == 0:
                        print(f"  [API] 客户端错误，不再重试")
                    break
                if attempt < max_retry - 1:
                    wait = 1 * (attempt + 1)
                    print(f"  [API] {wait}s 后重试...")
                    time.sleep(wait)
                continue

        raise RuntimeError(
            f"LLM API 调用失败（{max_retry} 次）: {last_error}"
        )

    def _mock_extract(self, messages: list) -> str:
        """
        Mock 模式：API 未配置时返回默认 JSON 占位。
        正式开发时请在 config.yaml 填入真实 API 配置。
        """
        return json.dumps(self.FIELD_DEFAULTS, ensure_ascii=False)

    # ── JSON 解析与修复 ──────────────────────────────────

    def _parse_llm_json(self, text: str) -> dict:
        """
        解析 LLM 返回文本为 dict，带多层降级策略。

        策略：
            1. 直接 json.loads
            2. 提取 ```json ... ``` 代码块
            3. 提取 ``` ... ``` 代码块
            4. 定位第一个 { 到最后一个 }
            5. 单引号替换为双引号后重试
        """
        if not text or not text.strip():
            raise ValueError("LLM 返回为空。")

        text = text.strip()

        # 策略 1：直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略 2：```json ... ```
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略 3：``` ... ```
        match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略 4：{ ... }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 策略 5：单引号 → 双引号
        try:
            candidate = text.replace("'", '"')
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            pass

        raise ValueError(
            f"无法解析 LLM 返回为合法 JSON。"
            f"原始返回前 200 字符: {text[:200]}"
        )

    # ── 字段校验与修复 ───────────────────────────────────

    def _validate_and_fix(self, extracted: dict) -> dict:
        """
        校验并修复抽取结果：
            1. 补全缺失字段
            2. 校验 type 枚举
            3. 校验 deadline 格式
            4. requirements 嵌套对象校验（7子字段 + 枚举约束）
        """
        result = {}

        for field in self.REQUIRED_FIELDS:
            value = extracted.get(field, self.FIELD_DEFAULTS[field])

            # ── type 枚举校验 ──
            if field == "type":
                if value not in self.VALID_TYPES:
                    value = "其他"

            # ── deadline / contest 日期格式校验 ──
            if field in ("deadline", "contest_start", "contest_end"):
                if value != "unknown" and not self.DEADLINE_PATTERN.match(
                    str(value)
                ):
                    date_match = re.search(r"(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})[日号]?", str(value))
                    if date_match:
                        value = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                    else:
                        value = "unknown"

            # ── requirements 嵌套对象校验 ──
            if field == "requirements":
                value = self._validate_requirements(value)

            # ── 其他字符串字段 ──
            if field not in ("requirements",):
                if not isinstance(value, str):
                    value = (
                        str(value)
                        if value is not None
                        else self.FIELD_DEFAULTS[field]
                    )

            result[field] = value

        return result

    def _validate_requirements(self, reqs: Any) -> dict:
        """
        校验并修复 requirements 嵌套对象。

        确保 7 个子字段全部存在、类型正确、枚举值合法。
        如果传入的是旧版数组格式（向后兼容），转换为新版对象。
        """
        # ── 向后兼容：旧版数组格式 → 新版嵌套对象 ──
        if isinstance(reqs, list):
            return dict(self.FIELD_DEFAULTS["requirements"])

        # ── 不是 dict → 返回默认值 ──
        if not isinstance(reqs, dict):
            return dict(self.FIELD_DEFAULTS["requirements"])

        default = self.FIELD_DEFAULTS["requirements"]
        result = {}

        # target_majors：数组
        value = reqs.get("target_majors", default["target_majors"])
        result["target_majors"] = value if isinstance(value, list) else []

        # target_grades：数组 + 枚举校验
        value = reqs.get("target_grades", default["target_grades"])
        if isinstance(value, list):
            result["target_grades"] = [
                g for g in value if g in self.VALID_GRADES
            ]
        else:
            result["target_grades"] = []

        # target_education：数组 + 枚举校验
        value = reqs.get("target_education", default["target_education"])
        if isinstance(value, list):
            result["target_education"] = [
                e for e in value if e in self.VALID_EDUCATION
            ]
        else:
            result["target_education"] = []

        # required_skills：数组
        value = reqs.get("required_skills", default["required_skills"])
        result["required_skills"] = value if isinstance(value, list) else []

        # team_requirement：字符串 + 枚举校验
        value = reqs.get("team_requirement", default["team_requirement"])
        result["team_requirement"] = (
            value if value in self.VALID_TEAM_REQUIREMENT
            else default["team_requirement"]
        )

        # tags：数组
        value = reqs.get("tags", default["tags"])
        result["tags"] = value if isinstance(value, list) else []

        # category：字符串
        value = reqs.get("category", default["category"])
        result["category"] = str(value) if value is not None else "unknown"

        return result

    # ── 响应构造 ─────────────────────────────────────────

    def _build_response(
        self,
        task_id: str,
        status: str,
        data: dict,
        message: str = "",
        error: Optional[dict] = None,
        next_action: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """构造统一输出格式。"""
        response = {
            "task_id": task_id,
            "agent_name": self.AGENT_NAME,
            "status": status,
            "data": data,
            "message": message,
            "error": error,
            "next_action": next_action,
            "metadata": metadata or {},
        }
        response["metadata"]["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        response["metadata"]["agent_version"] = "1.0"
        return response


# ── 独立测试入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    """
    使用 data/raw/sample_notifications.json 进行独立测试。

    用法：
        python agents/info_extract_agent.py
    """
    import sys

    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    agent = InfoExtractAgent()

    samples_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "raw", "projects.json",
    )

    if not os.path.isfile(samples_path):
        print(f"[ERROR] 样例文件不存在: {samples_path}")
        sys.exit(1)

    with open(samples_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    # 自动适配两种数据格式：
    #   sample_notifications.json → 含 expected_output 嵌套
    #   projects.json             → 扁平结构，字段名为 url/source 等
    first_item = samples[0] if samples else {}
    is_projects_format = "url" in first_item and "expected_output" not in first_item

    raw_items = []
    for s in samples:
        if is_projects_format:
            # projects.json 格式
            raw_items.append({
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "source": s.get("source", ""),
                "raw_text": s.get("raw_text", ""),
                "publish_date": s.get("publish_date", ""),
                "collected_at": s.get("collected_at", time.strftime("%Y-%m-%d %H:%M:%S")),
            })
        else:
            # sample_notifications.json 格式
            raw_items.append({
                "title": s.get("expected_output", {}).get("title", ""),
                "url": s.get("source_url", ""),
                "source": s.get("source", ""),
                "raw_text": s.get("raw_text", ""),
                "publish_date": s.get("publish_date", ""),
                "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    # 构造统一输入
    test_input = {
        "task_id": "test_extract_001",
        "user_input": "批量抽取竞赛通知信息",
        "task_type": "info_extract",
        "user_profile": {},
        "context": {},
        "input_data": {
            "raw_items": raw_items,
            "extract_fields": [
                "title", "type", "deadline", "registration_time",
                "requirements", "reward", "organizer", "source_url", "summary",
            ],
        },
        "history": [],
        "required_output": "json",
        "metadata": {"test": True},
    }

    result = agent.run(test_input)

    print(f"\n{'='*60}")
    print(f"Agent: {result['agent_name']}")
    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    print(f"{'='*60}")

    items = result.get("data", {}).get("structured_items", [])
    for i, item in enumerate(items):
        flag = item.pop("_extract_status", "?")
        item.pop("_extract_error", None)
        item.pop("_source_title", None)
        item.pop("_source", None)
        item.pop("_collected_at", None)
        print(f"\n--- Item {i+1} [{flag}] ---")
        print(json.dumps(item, ensure_ascii=False, indent=2))
