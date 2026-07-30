"""DataFountain 数据解析器 — 将 API JSON 转换为 raw_item。

API 格式:
  列表: {cmpt: {competitions: [{id, title, subTitle, startTime, endTime,
          organizers: [{name, roleName}], tags: [{nameCn}], typeLabel, reward, ...}]}}
  详情: {id, title, cmptDescription, cmptDataDescription, organizers, schedules,
          reward, totalBonus, ...}
"""

import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
from .base import BaseParser

DETAIL_BASE = "https://www.datafountain.cn"


class DatafountainParser(BaseParser):
    """解析 DataFountain 竞赛数据。"""

    def __init__(self, config: dict):
        super().__init__(config)

    # ---- 列表解析 ----

    def parse_list(self, data) -> list[dict]:
        """解析 API JSON 列表。"""
        if isinstance(data, dict):
            return self._parse_api_list(data)
        if isinstance(data, str):
            if data.strip().startswith("{"):
                return self._parse_api_list(json.loads(data))
            return self._parse_html_list(data)
        return []

    def _parse_api_list(self, data: dict) -> list[dict]:
        competitions = data.get("cmpt", {}).get("competitions", [])
        return [self._parse_list_item(c) for c in competitions]

    def _parse_list_item(self, c: dict) -> dict:
        cid = c.get("id", "")

        # 主办方
        organizers = c.get("organizers") or []
        org_names = [
            o.get("name", "").strip()
            for o in organizers
            if o.get("name") and o.get("roleName") == "主办单位"
        ]
        organizer = "、".join(org_names) if org_names else ""

        # 分类 — tags nameCn + typeLabel
        tags = c.get("tags") or []
        tag_names = [t.get("nameCn", "") for t in tags if t.get("nameCn")]
        category = ", ".join(tag_names)
        if c.get("typeLabel") and c["typeLabel"] not in category:
            category = f"{c['typeLabel']}, {category}" if category else c["typeLabel"]

        # 比赛阶段 (race.startTime ~ race.endTime)
        race = c.get("race") or {}
        contest_start = _fmt_iso(race.get("startTime") or c.get("startTime"))
        contest_end = _fmt_iso(race.get("endTime") or c.get("endTime"))

        return {
            "title": c.get("title", ""),
            "url": f"{DETAIL_BASE}/competitions/{cid}",
            "source": "datafountain",
            "raw_text": json.dumps(c, ensure_ascii=False, default=str),
            "publish_date": _fmt_iso(c.get("orderTime") or c.get("startTime")),
            "collected_at": datetime.now().isoformat(),
            "description": (c.get("subTitle") or "").strip(),
            "organizer": organizer,
            "organizer_list": org_names,
            "co_organizers": [
                o.get("name", "").strip()
                for o in organizers
                if o.get("name") and o.get("roleName") != "主办单位"
            ],
            "supporters": [],
            "regist_start": _fmt_iso(c.get("startTime")),
            "regist_end": _fmt_iso(c.get("endTime")),
            "contest_start": contest_start,
            "contest_end": contest_end,
            "category": category,
            "level": "",
            "attachments": [],
            "reward": c.get("reward", ""),
            "type_label": c.get("typeLabel", ""),
            "teams": c.get("teams", 0),
            "users": c.get("users", 0),
        }

    # ---- merge_detail ----
    # 列表 API 已有 organizer/tags/dates 等结构化字段。
    # 详情 API 的核心价值是 cmptDescription（完整赛事说明 Markdown）。
    # 合并策略：详情不覆盖列表已有的非空值。

    def merge_detail(self, item: dict, detail_fields: dict) -> dict:
        # 只从详情中取列表没有的值
        for key in ("description", "regist_start", "regist_end",
                     "contest_start", "contest_end", "reward", "attachments"):
            detail_val = detail_fields.get(key)
            if detail_val and not item.get(key):
                item[key] = detail_val

        # description 特殊处理：用详情的 cmptDescription 替换列表的 subTitle
        detail_desc = detail_fields.get("description", "")
        if detail_desc and len(detail_desc) > len(item.get("description", "")):
            item["description"] = detail_desc

        # schedules / stages
        stages = detail_fields.get("stages", [])
        if stages:
            item["contest_stage"] = stages

        # raw_text 合并
        list_data = {}
        try:
            list_data = json.loads(item.get("raw_text", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        item["raw_text"] = json.dumps(
            {"list": list_data, "detail": json.dumps(detail_fields, ensure_ascii=False, default=str)},
            ensure_ascii=False,
        )
        return item

    # ---- 详情解析 ----

    def parse_detail(self, data) -> dict:
        """解析竞赛详情 JSON。"""
        if isinstance(data, dict) and "id" in data:
            return self._parse_api_detail(data)
        if isinstance(data, str):
            if data.strip().startswith("{"):
                return self._parse_api_detail(json.loads(data))
            return self._parse_html_detail(data)
        return self._empty_detail()

    def _parse_api_detail(self, detail: dict) -> dict:
        # 正文 — cmptDescription 是 Markdown 格式
        desc_parts = []
        cmpt_desc = detail.get("cmptDescription") or ""
        if cmpt_desc:
            desc_parts.append(cmpt_desc)
        data_desc = detail.get("cmptDataDescription") or ""
        if data_desc:
            desc_parts.append(data_desc)
        description = "\n\n".join(desc_parts)

        # 主办方
        organizers = detail.get("organizers") or []
        org_names = [
            o.get("name", "").strip()
            for o in organizers
            if o.get("name") and o.get("roleName") == "主办单位"
        ]
        organizer = "、".join(org_names) if org_names else ""

        # 赛程
        schedules = detail.get("schedules") or []
        stages = []
        for s in schedules:
            if isinstance(s, dict):
                stages.append({
                    "title": s.get("title", ""),
                    "start": s.get("startTime", ""),
                    "end": s.get("endTime", ""),
                })

        return {
            "description": description,
            "organizer": organizer,
            "organizer_list": org_names,
            "co_organizers": [
                o.get("name", "").strip()
                for o in organizers
                if o.get("name") and o.get("roleName") != "主办单位"
            ],
            "supporters": [],
            "regist_start": _fmt_iso(detail.get("startTime")),
            "regist_end": _fmt_iso(detail.get("endTime")),
            "contest_start": _fmt_iso(detail.get("startTime")),
            "contest_end": _fmt_iso(detail.get("endTime")),
            "category": "",
            "level": "",
            "attachments": [],
            "reward": detail.get("reward") or detail.get("totalBonus") or "",
            "stages": stages,
            "raw_detail": json.dumps(detail, ensure_ascii=False, default=str),
        }

    # ---- HTML 备用 ----

    def _parse_html_list(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if not href.startswith("/competitions/") or href == "/competitions":
                continue
            title = a_tag.get_text(strip=True)
            if not title:
                continue
            results.append({
                "title": title,
                "url": f"{DETAIL_BASE}{href}",
                "source": "datafountain",
                "raw_text": title,
                "publish_date": "",
                "collected_at": datetime.now().isoformat(),
                "description": "",
                "organizer": "",
                "organizer_list": [],
                "co_organizers": [], "supporters": [],
                "regist_start": "", "regist_end": "",
                "contest_start": "", "contest_end": "",
                "category": "", "level": "",
                "attachments": [],
            })
        return results

    def _parse_html_detail(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        return {
            "description": (soup.find("body") or soup).get_text(separator="\n", strip=True),
            "organizer": "",
            "organizer_list": [], "co_organizers": [], "supporters": [],
            "regist_start": "", "regist_end": "",
            "contest_start": "", "contest_end": "",
            "category": "", "level": "", "attachments": [],
        }

    @staticmethod
    def _empty_detail() -> dict:
        return {
            "description": "", "organizer": "", "organizer_list": [],
            "co_organizers": [], "supporters": [],
            "regist_start": "", "regist_end": "",
            "contest_start": "", "contest_end": "",
            "category": "", "level": "", "attachments": [],
        }


def _fmt_iso(val) -> str:
    if not val:
        return ""
    s = str(val)
    if "T" in s:
        return s.split("T")[0]
    if " " in s:
        return s.split(" ")[0]
    return s[:10] if len(s) >= 10 else s


# ---- 自注册 ----
from ..registry import SourceRegistry  # noqa: E402
from ..clients.datafountain import DatafountainClient  # noqa: E402

SourceRegistry.register("datafountain", DatafountainClient, DatafountainParser)
