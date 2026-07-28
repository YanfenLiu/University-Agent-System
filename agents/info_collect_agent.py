"""信息收集 Agent — 全量爬取 + LLM 语义检索。"""

import os
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import yaml

from .info_collect.storage import Storage
from .info_collect.crawler import Crawler
from .info_collect.file_parser import parse_files
from .info_collect.registry import SourceRegistry

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

    def _start_background_crawl(
        self, keywords: list[str], sources: list[str], task_id: str, config: dict,
    ):
        """在后台线程异步爬取过期源，不阻塞当前请求。"""
        # 复用当前连接的 storage，避免重新解析 ${VAR} 配置
        storage = self._get_storage()

        def _bg():
            logger.info("后台刷新开始: %s", sources)
            crawler = Crawler(config, storage)
            log_id = storage.start_crawl_log(task_id + "_bg", ",".join(sources))
            try:
                max_pages = config.get("info_collect", {}).get("max_pages", 3)
                _, wstats = crawler.crawl([], sources, max_pages, log_id)
                storage.update_crawl_log(
                    log_id,
                    pages_crawled=wstats.get("pages_crawled", 0),
                    items_found=wstats.get("items_found", 0),
                    items_new=wstats.get("items_new", 0),
                    items_updated=wstats.get("items_updated", 0),
                    status="completed",
                    finished_at=datetime.now().isoformat(),
                )
                logger.info(
                    "后台刷新完成: %s, 新增 %d, 更新 %d",
                    sources, wstats.get("items_new", 0), wstats.get("items_updated", 0),
                )
            except Exception as e:
                logger.warning("后台刷新失败: %s", e)
            finally:
                try:
                    crawler.close()
                except Exception:
                    pass

        t = threading.Thread(target=_bg, daemon=False)
        t.start()
        logger.info("已启动后台刷新线程: %s", sources)

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

    @staticmethod
    def _newest_age_hours(items: list[dict]) -> float:
        if not items:
            return float("inf")
        newest: datetime | None = None
        for item in items:
            raw = str(item.get("updated_at", "")).strip()
            if not raw:
                raw = str(item.get("collected_at", "")).strip()
            if not raw:
                continue
            try:
                if raw.endswith("Z"):
                    raw = raw[:-1] + "+00:00"
                elif "+" not in raw and raw.count("-") > 2:
                    raw += "+00:00"
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if newest is None or dt > newest:
                    newest = dt
            except (ValueError, TypeError):
                continue
        if newest is None:
            return float("inf")
        return (datetime.now(timezone.utc) - newest).total_seconds() / 3600

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

        intent_parts = []
        if keywords:
            intent_parts.append(" ".join(keywords))
        if user_input and user_input.strip():
            intent_parts.append(user_input.strip())
        grade = (profile.get("grade") or "").strip()
        if grade:
            intent_parts.append("年级: " + grade)
        major = (profile.get("major") or "").strip()
        if major:
            intent_parts.append("专业: " + major)
        interests = profile.get("interests", [])
        if interests:
            intent_parts.append("兴趣: " + ", ".join(interests))
        user_intent = "; ".join(intent_parts) if intent_parts else ""

        storage = self._get_storage()
        all_items = []
        all_stats: dict[str, Any] = {}

        web_sources = set(SourceRegistry.list_all())
        web_srcs = [s for s in sources if s in web_sources]

        if web_srcs:
            info_cfg = self.config.get("info_collect", {}) if isinstance(self.config, dict) else {}
            max_results = inner.get("max_results") or info_cfg.get("max_results", 10)
            cache_max_age_hours = info_cfg.get("cache_max_age_hours", 24)

            cached_all = storage.get_all_items()

            # 按源检查：完全没数据 → 同步爬取（必须等）；过期 → 后台刷新
            missing_srcs = []
            stale_srcs = []
            for src in web_srcs:
                src_items = [it for it in cached_all if it.get("source") == src]
                if not src_items:
                    missing_srcs.append(src)
                else:
                    age = self._newest_age_hours(src_items)
                    if age > cache_max_age_hours:
                        stale_srcs.append(src)
                        logger.info("%s 过期 (%.1fh > %dh), 后台刷新", src, age, cache_max_age_hours)
                    else:
                        logger.info("%s 新鲜 (%d 条, %.1fh)", src, len(src_items), age)

            # 缺失源 → 同步爬取（数据都没有，必须等）
            if missing_srcs:
                logger.info("缺失数据源，同步爬取: %s", missing_srcs)
                max_pages_per_source = info_cfg.get("max_pages", 10)
                crawler = self._get_crawler()
                log_id = storage.start_crawl_log(task_id, ",".join(missing_srcs))
                try:
                    _, wstats = crawler.crawl(keywords, missing_srcs, max_pages_per_source, log_id)
                finally:
                    try: crawler.close()
                    except Exception: pass
                storage.update_crawl_log(
                    log_id,
                    pages_crawled=wstats.get("pages_crawled", 0),
                    items_found=wstats.get("items_found", 0),
                    items_new=wstats.get("items_new", 0),
                    items_updated=wstats.get("items_updated", 0),
                    status="completed",
                    finished_at=datetime.now().isoformat(),
                )
                cached_all = storage.get_all_items()
                all_stats["web"] = wstats
            else:
                all_stats["web"] = {
                    "pages_crawled": 0, "items_found": 0,
                    "items_new": 0, "items_updated": 0,
                    "cache_hits": len(cached_all),
                }

            # 过期源 → 后台线程异步刷新，不阻塞用户
            if stale_srcs:
                self._start_background_crawl(keywords, stale_srcs, task_id, self.config)

                        # 语义搜索或关键词匹配 — 限制返回条数，避免下游处理271条全量数据
            if hasattr(storage, "search_semantic") and user_intent:
                logger.info("语义搜索: '%s'", user_intent[:80])
                matched = storage.search_semantic(user_intent, limit=max_results)
            elif keywords:
                # 本地 JSON 存储无语义搜索能力，用关键词匹配 title/description/organizer
                logger.info("关键词匹配: %s (上限 %d 条)", keywords, max_results)
                matched = storage.search(keywords, limit=max_results)
                if not matched and user_intent:
                    # 关键词未匹配 → 用最新 max_results 条兜底
                    logger.info("关键词无匹配，取最新 %d 条", max_results)
                    all_sorted = sorted(cached_all, key=lambda x: x.get('collected_at', ''), reverse=True)
                    matched = all_sorted[:max_results]
            else:
                # 没有关键词也没有意图 → 取最新 max_results 条
                logger.info("无搜索意图，取最新 %d 条", max_results)
                all_sorted = sorted(cached_all, key=lambda x: x.get('collected_at', ''), reverse=True)
                matched = all_sorted[:max_results]
            all_items.extend(matched)
            all_stats["web"]["matched"] = len(matched)

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
                    finished_at=datetime.now().isoformat(),
                )
                raise
            storage.update_crawl_log(
                log_id, items_found=len(file_paths),
                items_new=fstats["files_parsed"], items_updated=0,
                status="completed", finished_at=datetime.now().isoformat(),
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
