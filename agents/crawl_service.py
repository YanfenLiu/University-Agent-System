"""独立爬虫服务 — 供前端手动触发，与 info_collect 语义搜索解耦。

用法:
    from agents.crawl_service import CrawlService
    svc = CrawlService(config)
    result = svc.crawl(keywords=["金融"], sources=["saikr"])
    print(result)  # {"log_id": 42, "status": "running", "stats": {...}}
"""

import logging
import os
from typing import Any, Optional

import yaml

from .info_collect.storage import Storage
from .info_collect.crawler import Crawler
from .info_collect.registry import SourceRegistry
from .time_utils import beijing_now_iso

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")


class CrawlService:
    """独立爬虫触发与状态查询服务。"""

    def __init__(self, config: dict | str | None = None):
        if config is None:
            config = DEFAULT_CONFIG_PATH
        if isinstance(config, str):
            with open(config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        self.config = config
        self._storage: Storage | None = None

    def _get_storage(self) -> Storage:
        if self._storage is None:
            self._storage = Storage.create(self.config)
        return self._storage

    # ---- 爬取 ----

    def crawl(
        self,
        keywords: Optional[list[str]] = None,
        sources: Optional[list[str]] = None,
        max_pages_per_source: Optional[int] = None,
        task_id: str = "",
        refresh_job_id: int | None = None,
    ) -> dict[str, Any]:
        """同步爬取指定源，返回 stats + log_id。

        Args:
            keywords: 搜索关键词（传 None 则全量爬取，不做关键词过滤）
            sources: 数据源列表（传 None 则爬取所有已注册源）
            max_pages_per_source: 每源最大翻页数（传 None 用 config 默认值）
            task_id: 关联的任务 ID
        """
        info_cfg = self.config.get("info_collect", {}) if isinstance(self.config, dict) else {}
        keywords = keywords or []
        sources = sources or SourceRegistry.list_all()
        max_pages = max_pages_per_source or info_cfg.get("max_pages", 10)

        # 过滤无效源
        valid_sources = set(SourceRegistry.list_all())
        sources = [s for s in sources if s in valid_sources]
        if not sources:
            raise ValueError(f"无有效数据源，可用: {', '.join(sorted(valid_sources))}")

        storage = self._get_storage()

        # 爬取前清理库中已有的过期数据
        if hasattr(storage, "delete_expired"):
            try:
                n = storage.delete_expired()
                if n:
                    logger.info("爬前清理: %d 条过期", n)
            except Exception:
                pass

        log_id = storage.start_crawl_log(task_id or "manual_crawl", ",".join(sources))

        crawler = Crawler(self.config, storage)
        try:
            _, wstats = crawler.crawl(
                keywords,
                sources,
                max_pages,
                log_id,
                refresh_job_id=refresh_job_id,
            )
        except Exception as e:
            logger.exception("爬取失败: %s", sources)
            storage.update_crawl_log(
                log_id,
                status="failed",
                error_message=str(e)[:500],
                finished_at=beijing_now_iso(),
            )
            return {
                "log_id": log_id,
                "status": "failed",
                "error": str(e),
                "stats": {"pages_crawled": 0, "items_found": 0, "items_new": 0, "items_updated": 0},
            }
        else:
            if not wstats.get("pages_crawled") and not wstats.get("items_found"):
                error_message = "No pages or competition items were returned by the source."
                storage.update_crawl_log(
                    log_id,
                    status="failed",
                    error_message=error_message,
                    finished_at=beijing_now_iso(),
                )
                return {
                    "log_id": log_id,
                    "status": "failed",
                    "error": error_message,
                    "stats": wstats,
                }
            storage.update_crawl_log(
                log_id,
                pages_crawled=wstats.get("pages_crawled", 0),
                items_found=wstats.get("items_found", 0),
                items_new=wstats.get("items_new", 0),
                items_updated=wstats.get("items_updated", 0),
                status="completed",
                finished_at=beijing_now_iso(),
            )
            logger.info(
                "爬取完成: %s, 新增 %d, 更新 %d",
                sources, wstats.get("items_new", 0), wstats.get("items_updated", 0),
            )
            return {"log_id": log_id, "status": "completed", "stats": wstats}
        finally:
            try:
                crawler.close()
            except Exception:
                pass

    # ---- 过期清理 ----

    def cleanup_expired(self) -> dict[str, Any]:
        """删除 contest_end 已过期的竞赛记录。"""
        storage = self._get_storage()
        if not hasattr(storage, "delete_expired"):
            return {"deleted": 0, "error": "当前存储后端不支持删除操作"}
        try:
            deleted = storage.delete_expired()
            return {"deleted": deleted}
        except Exception as e:
            logger.exception("过期清理失败")
            return {"deleted": 0, "error": str(e)}

    # ---- 状态查询 ----

    def get_status(self, log_id: int) -> Optional[dict[str, Any]]:
        """查询某次爬取的状态（从 Supabase crawl_logs 表）。"""
        storage = self._get_storage()
        try:
            result = (
                storage.client.table("crawl_logs")
                .select("*")
                .eq("id", log_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            return None

    def get_recent_logs(self, limit: int = 10) -> list[dict[str, Any]]:
        """最近爬取记录。"""
        storage = self._get_storage()
        try:
            result = (
                storage.client.table("crawl_logs")
                .select("*")
                .order("id", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data if result.data else []
        except Exception:
            return []

    def get_all_sources(self) -> list[str]:
        """返回所有可用数据源名称，供前端选择。"""
        return sorted(SourceRegistry.list_all())
