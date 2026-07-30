"""Read already-processed competition candidates from Supabase."""

from __future__ import annotations

from typing import Any

from .info_collect.storage import Storage


class CompetitionSearchService:
    """Database retrieval used by recommendation conversations."""

    def __init__(self, config: dict[str, Any]):
        self.storage = Storage.create(config)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.storage.get_all_items()
        if hasattr(self.storage, "filter_active"):
            rows = self.storage.filter_active(rows)
        if query and hasattr(self.storage, "search_semantic_local"):
            rows = self.storage.search_semantic_local(rows, query, limit=limit)
        else:
            rows = rows[:limit]
        if rows and hasattr(self.storage, "get_full_items_by_ids"):
            rows = self.storage.get_full_items_by_ids(
                [row["id"] for row in rows if row.get("id")]
            )
        return [self._to_recommendation_item(row) for row in rows]

    @staticmethod
    def _to_recommendation_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "title": row.get("title", ""),
            "summary": row.get("description", ""),
            "deadline": row.get("regist_end", ""),
            "registration_time": row.get("regist_start", ""),
            "organizer": row.get("organizer", ""),
            "type": row.get("category", ""),
            "source_url": row.get("url", ""),
        }
