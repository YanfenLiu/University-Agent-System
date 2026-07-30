"""信息收集 Agent — 全量爬取 + LLM 语义检索。"""

import os
import logging

from datetime import datetime
from typing import Any

import yaml

from .info_collect.storage import Storage
from .info_collect.crawler import Crawler
from .info_collect.file_parser import parse_files
from .info_collect.registry import SourceRegistry
from .time_utils import beijing_now_iso

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")


class InfoCollectAgent:

    def __init__(self, config: dict | str | None = None):
        if config is None:
            config = DEFAULT_CONFIG_PATH
        if isinstance(config, str):
            with open(config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        self.config = config
        self._storage: Storage | None = None
        self._crawler: Crawler | None = None

    def _get_storage(self) -> Storage:
        if self._storage is None:
            self._storage = Storage.create(self.config)
        return self._storage

    def _get_crawler(self) -> Crawler:
        if self._crawler is None:
            self._crawler = Crawler(self.config, self._get_storage())
        return self._crawler

    @staticmethod
    def _build_raw_items(all_items: list[dict]) -> list[dict]:
        return [
            {
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "raw_text": it.get("raw_text", ""),
                "publish_date": it.get("publish_date", ""),
                "collected_at": it.get("collected_at", ""),
                "description": it.get("description", ""),
                "organizer": it.get("organizer", ""),
                "organizer_list": it.get("organizer_list", []),
                "co_organizers": it.get("co_organizers", []),
                "supporters": it.get("supporters", []),
                "regist_start": it.get("regist_start", ""),
                "regist_end": it.get("regist_end", ""),
                "contest_start": it.get("contest_start", ""),
                "contest_end": it.get("contest_end", ""),
                "category": it.get("category", ""),
                "level": it.get("level", ""),
                "attachments": it.get("attachments", []),
                "file_type": it.get("file_type", ""),
                "file_name": it.get("file_name", ""),
            }
            for it in all_items
        ]

    # ---- 统一接口 ----

    def run(self, input_data: dict) -> dict:
        task_id = input_data.get("task_id", "")
        try:
            self.validate_input(input_data)
            data, message, stats = self.process(input_data)

            return {
                "task_id": task_id,
                "agent_name": "info_collect_agent",
                "status": "success",
                "data": data,
                "message": message,
                "error": None,
                "next_action": "info_extraction",
                "metadata": {
                    "execution_time": datetime.now().isoformat(),
                    "stats": stats,
                },
            }

        except ValueError as e:
            is_need_input = "请提供" in str(e)
            return {
                "task_id": task_id,
                "agent_name": "info_collect_agent",
                "status": "need_input" if is_need_input else "failed",
                "data": {},
                "message": str(e),
                "error": None if is_need_input else {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "suggestion": "请检查 input_data 中的 sources",
                },
                "next_action": "ask_user" if is_need_input else None,
                "metadata": {"execution_time": datetime.now().isoformat()},
            }

        except Exception as e:
            logger.exception("InfoCollectAgent 执行异常")
            return {
                "task_id": task_id,
                "agent_name": "info_collect_agent",
                "status": "failed",
                "data": {},
                "message": f"执行失败: {e}",
                "error": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "suggestion": "请稍后重试或联系管理员",
                },
                "next_action": None,
                "metadata": {"execution_time": datetime.now().isoformat()},
            }

    def validate_input(self, input_data: dict):
        inner = input_data.get("input_data", {})
        if not inner:
            raise ValueError("input_data 不能为空")

        sources = inner.get("sources", [])
        if not sources:
            raise ValueError("请提供 sources 参数，例如 ['saikr'] 或 ['local_file']")

        web_sources = set(SourceRegistry.list_all())
        local_sources = {"local_file"}
        valid_sources = web_sources | local_sources

        for s in sources:
            if s not in valid_sources:
                raise ValueError(
                    f"不支持的数据源: '{s}'，目前支持: {', '.join(sorted(valid_sources))}"
                )

        if any(s in web_sources for s in sources):
            info_cfg = self.config.get("info_collect", {}) if isinstance(self.config, dict) else {}
            max_results = inner.get("max_results", info_cfg.get("max_results", 10))
            if not isinstance(max_results, int) or max_results < 1 or max_results > 100:
                raise ValueError("max_results 必须在 1-100 之间")

        if "local_file" in sources:
            file_paths = inner.get("file_paths", [])
            if not file_paths:
                raise ValueError("本地文件采集需要提供 file_paths 参数")
            for fp in file_paths:
                if not os.path.exists(fp):
                    raise ValueError(f"文件不存在: {fp}")

    def process(self, input_data: dict) -> tuple[dict, str, dict]:
        inner = input_data.get("input_data", {})
        task_id = input_data.get("task_id", "unknown")
        sources = inner.get("sources", SourceRegistry.list_all())
        keywords = inner.get("keywords", [])
        user_input = input_data.get("user_input", "")
        profile = input_data.get("user_profile", {})

        # embedding 粗筛仅用竞赛方向。profile 留给 recommendation agent 精排。
        user_intent = user_input.strip() if (user_input and user_input.strip()) else ""
        if not user_intent and keywords:
            user_intent = " ".join(keywords)

        storage = self._get_storage()
        all_items = []
        all_stats: dict[str, Any] = {}

        web_sources = set(SourceRegistry.list_all())
        web_srcs = [s for s in sources if s in web_sources]

        if web_srcs:
            info_cfg = self.config.get("info_collect", {}) if isinstance(self.config, dict) else {}
            max_results = inner.get("max_results") or info_cfg.get("max_results", 10)

            cached_all = storage.get_all_items()
            all_stats["web"] = {
                "pages_crawled": 0, "items_found": 0,
                "items_new": 0, "items_updated": 0,
                "cache_hits": len(cached_all),
            }

            # 过滤已过期竞赛 + 本地语义搜索（embedding → TF-IDF，不调 LLM）
            from .info_collect.supabase_store import SupabaseStore
            active = SupabaseStore.filter_active(cached_all)
            logger.info("过滤过期: %d → %d 条有效", len(cached_all), len(active))

            # keywords 驱动爬虫，不应混入语义排序。
            # user_intent 已包含 keywords 原文 + user_input + profile，足够语义匹配。
            if hasattr(storage, "search_semantic_local") and user_intent:
                print(f"[info_collect] 语义搜索 intent='{user_intent[:60]}' candidates={len(active)}", flush=True)
                matched = storage.search_semantic_local(active, user_intent, limit=max_results)
                # embedding 返回的是轻量字段，按 ID 补全 raw_text/url 等完整信息
                if matched and hasattr(storage, "get_full_items_by_ids"):
                    id_map = {it["id"]: it for it in storage.get_full_items_by_ids(
                        [it["id"] for it in matched]
                    )}
                    matched = [id_map.get(it["id"], it) for it in matched]
            else:
                print(f"[info_collect] 语义搜索 SKIPPED (has_search={hasattr(storage, 'search_semantic_local')} intent='{user_intent[:40] if user_intent else '(empty)'}')", flush=True)
                matched = active[:max_results]
            all_items.extend(matched)
            all_stats["web"]["matched"] = len(matched)
            all_stats["web"]["active_count"] = len(active)

        # 本地文件解析
        if "local_file" in sources:
            file_paths = inner.get("file_paths", [])
            log_id = storage.start_crawl_log(task_id, "local_file")
            fstats = {"files_found": len(file_paths), "files_parsed": 0, "files_failed": 0}
            try:
                file_items = parse_files(file_paths)
                for item in file_items:
                    storage.upsert_item(item)
                    all_items.append(item)
                fstats["files_parsed"] = len(file_items)
                fstats["files_failed"] = len(file_paths) - len(file_items)
            except RuntimeError as e:
                storage.update_crawl_log(
                    log_id, items_found=len(file_paths),
                    items_new=0, items_updated=0,
                    status="failed", error_message=str(e),
                    finished_at=beijing_now_iso(),
                )
                raise
            storage.update_crawl_log(
                log_id, items_found=len(file_paths),
                items_new=fstats["files_parsed"], items_updated=0,
                status="completed",
                finished_at=beijing_now_iso(),
            )
            all_stats["local_file"] = fstats

        collected = self._build_raw_items(all_items)
        data = {"raw_items": collected, "stats": all_stats}

        msg_parts = []
        if "web" in all_stats:
            ws = all_stats["web"]
            cache_str = f"缓存 {ws.get('cache_hits', 0)} 条" if ws.get("cache_hits") else ""
            matched_str = f"匹配返回 {ws.get('matched', 0)} 条"
            new_str = f"新增入库 {ws.get('items_new', 0)} 条" if ws.get("items_new") else ""
            parts = [p for p in [cache_str, new_str, matched_str] if p]
            msg_parts.append("网页采集: " + ", ".join(parts))
        if "local_file" in all_stats:
            fs = all_stats["local_file"]
            msg_parts.append(f"文件解析: {fs['files_found']} 个文件, 成功 {fs['files_parsed']} 个")
        message = "采集完成 | " + " | ".join(msg_parts) if msg_parts else "未执行任何采集"

        return data, message, all_stats
