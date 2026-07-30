"""阿里天池数据解析器 — 将 API JSON 转换为 raw_item。

API 结构:
  {data: {list: [{raceId, name, isSeries, introduction, referUrl,
    raceStartTime, raceEndTime, bonus, teamCount, tagsList,
    trackList: [{raceId, name, signupStartTime, signupEndTime, ...}]}]}}

  系列赛(isSeries=1)展开为子赛道，独立赛直接作为一条。
"""

import json
from datetime import datetime
from bs4 import BeautifulSoup
from .base import BaseParser

DETAIL_BASE = "https://tianchi.aliyun.com"

# visualTab 分类映射
VISUAL_TAB_MAP = {
    1: "数据算法赛",
    2: "创新方案赛",
    3: "学习训练营",
    4: "其他",
}


class TianchiParser(BaseParser):
    """解析阿里天池竞赛数据。"""

    def __init__(self, config: dict):
        super().__init__(config)

    # ---- 列表解析 ----

    def parse_list(self, data) -> list[dict]:
        """解析 API JSON 列表。"""
        if isinstance(data, dict) and "data" in data:
            return self._parse_api_list(data)
        if isinstance(data, str):
            if data.strip().startswith("{"):
                return self._parse_api_list(json.loads(data))
            return self._parse_html_list(data)
        return []

    def _parse_api_list(self, data: dict) -> list[dict]:
        items = data.get("data", {}).get("list", [])
        results = []
        for race in items:
            if not isinstance(race, dict):
                continue
            # 系列赛展开为子赛道
            if race.get("isSeries") and race.get("trackList"):
                for track in race["trackList"]:
                    if isinstance(track, dict):
                        results.append(self._parse_race_item(track, series=race))
            else:
                results.append(self._parse_race_item(race))
        return results

    def _parse_race_item(self, race: dict, series: dict = None) -> dict:
        """将一条 race/track 转为 raw_item。"""
        race_id = race.get("raceId", "")
        name = race.get("name", "")
        introduction = race.get("introduction") or ""

        # 如果是子赛道，名称为 "系列赛名 - 子赛道名"
        if series:
            series_name = series.get("name", "")
            name = f"{series_name} - {name}"

        # URL
        url = race.get("referUrl") or ""
        if not url and series:
            url = series.get("referUrl") or f"{DETAIL_BASE}/competition/entrance/{race_id}"
        if not url:
            url = f"{DETAIL_BASE}/competition/entrance/{race_id}"

        # 时间字段
        publish_date = _fmt_datetime(race.get("raceStartTime"))
        regist_end = _fmt_datetime(race.get("signupEndTime"))
        if not regist_end and series:
            # 系列赛的报名时间在子赛道 track 中
            pass
        contest_start = _fmt_datetime(race.get("raceStartTime"))
        contest_end = _fmt_datetime(race.get("raceEndTime"))
        regist_start = _fmt_datetime(race.get("signupStartTime"))

        # 分类 — 从 tagsList 或 visualTab 获取
        category = ""
        tags = race.get("tagsList", [])
        if not tags and series:
            tags = series.get("tagsList", [])
        if tags and isinstance(tags, list) and len(tags) > 0:
            category = ", ".join(
                t.get("tagNameCn", t.get("tagName", ""))
                for t in tags if t.get("tagNameCn") or t.get("tagName")
            )
        if not category:
            vt = race.get("visualTab") or (series.get("visualTab") if series else 1)
            category = VISUAL_TAB_MAP.get(vt, "")

        # 主办方 — 从 orgUrl / coverUrl 等字段推导
        organizer = "阿里云天池"

        return {
            "title": name,
            "url": url,
            "source": "ali_tianchi",
            "raw_text": json.dumps({"race": race, "series": series}, ensure_ascii=False, default=str),
            "publish_date": publish_date,
            "collected_at": datetime.now().isoformat(),
            "description": introduction,
            "organizer": organizer,
            "organizer_list": [organizer],
            "co_organizers": [],
            "supporters": [],
            "regist_start": regist_start,
            "regist_end": regist_end,
            "contest_start": contest_start,
            "contest_end": contest_end,
            "category": category,
            "level": "",
            "attachments": [],
            "bonus": race.get("bonus", 0),
            "team_count": race.get("teamCount", 0),
        }

    # ---- merge_detail ----
    # 天池列表 API 已含 introduction/tagsList/bonus/teamCount 等完整信息。
    # 详情 API 为空，所以 merge 时保留列表已有的字段不被空值覆盖。

    def merge_detail(self, item: dict, detail_fields: dict) -> dict:
        for key, val in detail_fields.items():
            if val and not item.get(key):  # 只在列表值为空时才从详情补充
                item[key] = val

        list_data = {}
        try:
            list_data = json.loads(item.get("raw_text", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        item["raw_text"] = json.dumps(
            {"list": list_data, "detail": json.dumps(detail_fields, ensure_ascii=False)},
            ensure_ascii=False,
        )
        return item

    # ---- 详情解析 ----

    def parse_detail(self, data) -> dict:
        """天池列表已含详情字段，此方法返回空。"""
        if isinstance(data, dict) and ("introduction" in data or "name" in data):
            return self._parse_race_detail(data)
        return self._empty_detail()

    def _parse_race_detail(self, race: dict) -> dict:
        tags = race.get("tagsList", [])
        category = ", ".join(
            t.get("tagNameCn", t.get("tagName", ""))
            for t in tags if t.get("tagNameCn") or t.get("tagName")
        ) if tags else ""
        vt = race.get("visualTab", 1)
        if not category:
            category = VISUAL_TAB_MAP.get(vt, "")

        return {
            "description": race.get("introduction") or "",
            "organizer": "阿里云天池",
            "organizer_list": ["阿里云天池"],
            "co_organizers": [],
            "supporters": [],
            "regist_start": _fmt_datetime(race.get("signupStartTime")),
            "regist_end": _fmt_datetime(race.get("signupEndTime")),
            "contest_start": _fmt_datetime(race.get("raceStartTime")),
            "contest_end": _fmt_datetime(race.get("raceEndTime")),
            "category": category,
            "level": "",
            "attachments": [],
            "bonus": race.get("bonus", 0),
            "team_count": race.get("teamCount", 0),
            "raw_detail": json.dumps(race, ensure_ascii=False, default=str),
        }

    # ---- HTML 备用 ----

    def _parse_html_list(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        import re
        for a_tag in soup.find_all("a", href=re.compile(r"/competition/")):
            href = a_tag.get("href", "")
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            results.append({
                "title": title,
                "url": href if href.startswith("http") else f"{DETAIL_BASE}{href}",
                "source": "ali_tianchi",
                "raw_text": title,
                "publish_date": "",
                "collected_at": datetime.now().isoformat(),
                "description": "",
                "organizer": "阿里云天池",
                "organizer_list": ["阿里云天池"],
                "co_organizers": [], "supporters": [],
                "regist_start": "", "regist_end": "",
                "contest_start": "", "contest_end": "",
                "category": "", "level": "",
                "attachments": [],
            })
        return results

    @staticmethod
    def _empty_detail() -> dict:
        return {
            "description": "", "organizer": "阿里云天池", "organizer_list": ["阿里云天池"],
            "co_organizers": [], "supporters": [],
            "regist_start": "", "regist_end": "",
            "contest_start": "", "contest_end": "",
            "category": "", "level": "", "attachments": [],
        }


def _fmt_datetime(val) -> str:
    """格式化日期时间字符串为日期。"""
    if not val:
        return ""
    s = str(val)
    # "2026-07-17 00:00:00" → "2026-07-17"
    if " " in s:
        return s.split(" ")[0]
    # "2026-07-17T00:00:00.000Z" → "2026-07-17"
    if "T" in s:
        return s.split("T")[0]
    return s[:10] if len(s) >= 10 else s


# ---- 自注册 ----
from ..registry import SourceRegistry  # noqa: E402
from ..clients.tianchi import TianchiClient  # noqa: E402

SourceRegistry.register("ali_tianchi", TianchiClient, TianchiParser)
