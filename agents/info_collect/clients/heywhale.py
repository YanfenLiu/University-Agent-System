"""和鲸社区客户端 — 通过 REST API 获取竞赛数据。

API 已确认:
  GET /v2/api/competitions?page=N&perPage=20  → 竞赛列表 (528 条)
  GET /v2/api/competitions/{_id}               → 竞赛详情
  GET /v2/api/competitionFields                 → 分类字段

数据格式:
  列表: {totalNum, page, perPage, data: [{_id, Name, StartDate, EndDate, ShortDescription, DetailType, ...}]}
  详情: {_id, Name, Organization, StartDate, EndDate, RegisterEndDate, Stages, DisplayLabel, ...}
"""

import logging
from .base import BaseSourceClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.heywhale.com"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.heywhale.com/home/competition",
}


class HeywhaleClient(BaseSourceClient):

    def _default_headers(self) -> dict:
        return DEFAULT_HEADERS

    def get_contests(self, page: int = 1, limit: int = 20) -> dict:
        """获取竞赛列表。

        GET /v2/api/competitions?page=N&perPage=N
        返回 JSON dict: {totalNum, data: [...]}
        """
        resp = self.get_with_retry(
            f"{BASE_URL}/v2/api/competitions",
            params={"page": page, "perPage": limit},
        )
        return resp.json()

    def get_contest_detail(self, contest_id: str) -> dict:
        """获取单条竞赛详情。

        GET /v2/api/competitions/{_id}
        contest_id: MongoDB _id，如 "69c0dfa34f302f8f0122e1bb"
        """
        resp = self.get_with_retry(f"{BASE_URL}/v2/api/competitions/{contest_id}")
        return resp.json()

    def get_config(self) -> dict:
        """获取分类字段配置列表。"""
        resp = self.get_with_retry(f"{BASE_URL}/v2/api/competitionFields")
        return resp.json()

    def get_featured(self) -> list[dict]:
        return []
