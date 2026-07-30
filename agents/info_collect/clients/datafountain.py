"""DataFountain 客户端 — 通过 REST API 获取竞赛数据。

API:
  GET /api/competitions        → {cmpt: {competitions: [{id, title, startTime, endTime,
                                   organizers, tags, typeLabel, reward, ...}]}}
  GET /api/competitions/{id}   → {id, title, cmptDescription, cmptDataDescription,
                                   organizers, schedules, reward, ...}
"""

import logging
from .base import BaseSourceClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.datafountain.cn"

DF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.datafountain.cn/competitions",
}


class DatafountainClient(BaseSourceClient):

    def _default_headers(self) -> dict:
        return DF_HEADERS

    def get_contests(self, page: int = 1, limit: int = 20) -> dict:
        """获取竞赛列表。DF 的列表 API 一次返回全部，不分页。"""
        resp = self.get_with_retry(f"{BASE_URL}/api/competitions")
        return resp.json()

    def get_contest_detail(self, contest_id: str) -> dict:
        """获取单条竞赛详情。contest_id 为数字 ID。"""
        cid = contest_id
        if contest_id.startswith("http"):
            import re
            m = re.search(r"/competitions?/(\d+)", contest_id)
            cid = m.group(1) if m else contest_id.split("/")[-1]

        resp = self.get_with_retry(f"{BASE_URL}/api/competitions/{cid}")
        return resp.json()

    def get_config(self) -> dict:
        return {}

    def get_featured(self) -> list[dict]:
        return []
