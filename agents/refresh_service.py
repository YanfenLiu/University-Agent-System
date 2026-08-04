"""Logical full refresh pipeline for the competition database."""

from __future__ import annotations

import logging
from typing import Any

from .crawl_service import CrawlService
from .info_collect.registry import SourceRegistry
from .info_collect.storage import Storage
from .info_extract_agent import InfoExtractAgent
from .time_utils import beijing_now_iso

logger = logging.getLogger(__name__)


class RefreshService:
    """Refresh every source, extract only new/changed rows, and persist status."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.storage = Storage.create(config)

    def run(
        self,
        *,
        job_id: int | None = None,
        trigger_type: str = "manual",
    ) -> dict[str, Any]:
        if job_id is None and not hasattr(self.storage, "create_refresh_job"):
            raise RuntimeError("Refresh jobs require the Supabase storage backend.")

        if job_id is None:
            job = self.storage.create_refresh_job(trigger_type, status="running")
            job_id = int(job["id"])
        else:
            self.storage.update_refresh_job(
                job_id,
                status="running",
                started_at=beijing_now_iso(),
                error_message=None,
            )

        totals = {
            "items_found": 0,
            "items_new": 0,
            "items_changed": 0,
            "items_unchanged": 0,
            "items_extracted": 0,
            "items_failed": 0,
            "items_deleted": 0,
        }
        source_results: dict[str, Any] = {}
        extraction_ids: list[int] = []

        try:
            for source in SourceRegistry.list_all():
                service = CrawlService(self.config)
                result = service.crawl(
                    keywords=[],
                    sources=[source],
                    task_id=f"refresh_{job_id}_{source}",
                    refresh_job_id=job_id,
                )
                source_results[source] = result
                if result.get("status") != "completed":
                    continue
                stats = result.get("stats", {})
                for field in ("items_found", "items_new", "items_unchanged"):
                    totals[field] += int(stats.get(field, 0) or 0)
                # crawler 用 items_updated 表示「内容变化的条数」，对应 refresh_jobs.items_changed
                totals["items_changed"] += int(stats.get("items_updated", 0) or 0)
                extraction_ids.extend(
                    int(value) for value in stats.get("extraction_ids", []) if value
                )

            self._extract_rows(extraction_ids, totals)
            totals["items_deleted"] = int(self.storage.delete_expired())
            final_status = (
                "completed"
                if all(row.get("status") == "completed" for row in source_results.values())
                else "partial"
            )
            self.storage.update_refresh_job(
                job_id,
                status=final_status,
                finished_at=beijing_now_iso(),
                source_results=source_results,
                **totals,
            )
            return {"job_id": job_id, "status": final_status, **totals}
        except Exception as exc:
            logger.exception("Competition refresh failed")
            self.storage.update_refresh_job(
                job_id,
                status="failed",
                finished_at=beijing_now_iso(),
                source_results=source_results,
                error_message=str(exc)[:1000],
                **totals,
            )
            raise

    def _extract_rows(self, record_ids: list[int], totals: dict[str, int]) -> None:
        unique_ids = list(dict.fromkeys(record_ids))
        if not unique_ids:
            return
        extractor = InfoExtractAgent(self.config)
        for start in range(0, len(unique_ids), 20):
            batch_ids = unique_ids[start:start + 20]
            rows = self.storage.get_full_items_by_ids(batch_ids)
            for row in rows:
                if not str(row.get("raw_text") or "").strip():
                    row["raw_text"] = (
                        str(row.get("description") or "").strip()
                        or str(row.get("title") or "").strip()
                    )
            by_url = {(row.get("source"), row.get("url")): row for row in rows}
            response = extractor.run({
                "task_id": f"refresh_extract_{start}",
                "user_input": "Refresh competition database",
                "task_type": "info_extract",
                "user_profile": {},
                "context": {},
                "input_data": {"raw_items": rows},
                "history": [],
                "required_output": "json",
                "metadata": {"source": "refresh_service"},
            })
            structured_items = response.get("data", {}).get("structured_items", [])
            if response.get("status") not in {"success", "partial"}:
                error = response.get("message") or "Extraction failed"
                for row in rows:
                    self.storage.save_extraction_result(row["id"], {}, error=error)
                    totals["items_failed"] += 1
                continue

            completed_ids: set[int] = set()
            for structured in structured_items:
                key = (structured.get("_source"), structured.get("source_url"))
                raw = by_url.get(key)
                if raw is None:
                    continue
                if structured.get("_extract_status") == "failed":
                    self.storage.save_extraction_result(
                        raw["id"],
                        {},
                        error=str(structured.get("_extract_error") or "Extraction failed."),
                    )
                    completed_ids.add(raw["id"])
                    totals["items_failed"] += 1
                    continue
                self.storage.save_extraction_result(raw["id"], structured)
                completed_ids.add(raw["id"])
                totals["items_extracted"] += 1
            for row in rows:
                if row["id"] not in completed_ids:
                    self.storage.save_extraction_result(
                        row["id"], {}, error="Extractor returned no matching item."
                    )
                    totals["items_failed"] += 1
