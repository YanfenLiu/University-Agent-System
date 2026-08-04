"""和鲸社区数据解析器 — 将 API JSON 转换为 raw_item。"""

import json
from datetime import datetime
from bs4 import BeautifulSoup
from .base import BaseParser, fmt_date_beijing

DETAIL_BASE = "https://www.heywhale.com"

# DetailType 映射
TYPE_MAP = {
    "ALGORITHM": "算法赛",
    "SCHEME": "方案赛",
    "LIVE": "交流活动",
    "CREATIVE": "创意赛",
    "CHALLENGE": "挑战赛",
    "HACKATHON": "黑客松",
    "TRAINING_CAMP": "训练营",
    "DATA_ANALYSIS": "数据分析",
    "OTHER": "其他",
}


class HeywhaleParser(BaseParser):
    """解析和鲸社区竞赛数据。"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._categories: dict[str, str] = {}

    def configure(self, config_data):
        """建立 category Key → Name 映射。"""
        if isinstance(config_data, dict):
            for item in config_data.get("data", []):
                key = item.get("Key", "")
                name = item.get("Name", "")
                if key and name:
                    self._categories[key] = name

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
        items = data.get("data", [])
        # 兼容 {"data": {"results": [...]}} 格式
        if isinstance(items, dict):
            items = items.get("results") or items.get("list") or items.get("records") or []
        if not isinstance(items, list):
            return []
        return [self._parse_list_item(item) for item in items]

    def _parse_list_item(self, item: dict) -> dict:
        cid = item.get("_id", "")
        return {
            "title": item.get("Name", ""),
            "url": f"{DETAIL_BASE}/home/competition/{cid}",
            "source": "heywhale",
            "raw_text": json.dumps(item, ensure_ascii=False),
            "publish_date": _fmt_iso(item.get("StartDate")),
            "collected_at": datetime.now().isoformat(),
            "description": (item.get("ShortDescription") or ""),
            "organizer": "",
            "organizer_list": [],
            "co_organizers": [],
            "supporters": [],
            "regist_start": _fmt_iso(item.get("StartDate")),
            # 列表 API 不返回 RegisterEndDate（仅详情有）；LIVE 录播课无独立报名期，
            # 用活动 EndDate 作为截止时间，否则 regist_end 永远为空。
            "regist_end": _fmt_iso(
                item.get("RegisterEndDate")
                or (item.get("EndDate") if item.get("DetailType") == "LIVE" else None)
            ),
            "contest_start": _fmt_iso(item.get("StartDate")),
            "contest_end": _fmt_iso(item.get("EndDate")),
            "category": TYPE_MAP.get(item.get("DetailType", ""), item.get("DetailType", "")),
            "level": "",
            "attachments": [],
        }

    # ---- merge_detail ----

    def merge_detail(self, item: dict, detail_fields: dict) -> dict:
        """合并详情到列表项，列表已有值不覆盖，但 description 取更长的。"""
        # 列表有的不覆盖，只填列表缺失的
        for key, val in detail_fields.items():
            if key == "description":
                if val and len(val) > len(item.get("description", "")):
                    item[key] = val
            elif not item.get(key) and val:
                item[key] = val

        # raw_text 合并
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
        """解析竞赛详情 JSON。"""
        if isinstance(data, dict) and "_id" in data:
            return self._parse_api_detail(data)
        if isinstance(data, str):
            if data.strip().startswith("{"):
                return self._parse_api_detail(json.loads(data))
            return self._parse_html_detail(data)
        return self._empty_detail()

    def _parse_api_detail(self, detail: dict) -> dict:
        org = detail.get("Organization", {})
        org_name = org.get("Name", "") if isinstance(org, dict) else ""

        # Stages → 赛程信息
        stages = detail.get("Stages", [])
        stage_info = []
        for s in (stages or []):
            if isinstance(s, dict):
                stage_info.append({
                    "name": s.get("Name", ""),
                    "start": s.get("StartDate", ""),
                    "end": s.get("EndDate", ""),
                })

        # 从 Tabs 提取正文（Markdown 格式）
        tabs = detail.get("Tabs", [])
        tab_texts = []
        for tab in (tabs or []):
            if isinstance(tab, dict):
                title = tab.get("Title", "")
                content = tab.get("Content", "")
                if title and content:
                    tab_texts.append(f"## {title}\n{content}")
        description = "\n\n".join(tab_texts) if tab_texts else (detail.get("ShortDescription") or "")

        return {
            "description": description,
            "organizer": org_name,
            "organizer_list": [org_name] if org_name else [],
            "co_organizers": [],
            "supporters": [],
            "regist_start": _fmt_iso(detail.get("StartDate")),
            # 只有 LIVE 录播课才用 EndDate 兜底报名截止；普通竞赛 EndDate 是比赛结束，
            # 不能当成报名截止。
            "regist_end": _fmt_iso(
                detail.get("RegisterEndDate")
                or (detail.get("EndDate") if detail.get("DetailType") == "LIVE" else None)
            ),
            "contest_start": _fmt_iso(detail.get("StartDate")),
            "contest_end": _fmt_iso(detail.get("EndDate")),
            "category": TYPE_MAP.get(detail.get("DetailType", ""), detail.get("DetailType", "")),
            "level": "",
            "attachments": [],
            "display_label": detail.get("DisplayLabel", ""),
            "max_members": detail.get("MaxMembersPerTeam", 0),
            "users_number": detail.get("UsersNumber", 0),
            "teams_number": detail.get("TeamsNumber", 0),
            "stages": stage_info,
            "raw_detail": json.dumps(detail, ensure_ascii=False),
        }

    # ---- HTML 备用 ----

    def _parse_html_list(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/competition/" not in href:
                continue
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            results.append({
                "title": title,
                "url": href if href.startswith("http") else f"{DETAIL_BASE}{href}",
                "source": "heywhale",
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
        body = soup.find("body") or soup
        return {
            "description": body.get_text(separator="\n", strip=True),
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
    """格式化日期为北京时间日期；和鲸返回 UTC ISO 时间，需转换时区。"""
    return fmt_date_beijing(val)


# ---- 自注册 ----
from ..registry import SourceRegistry  # noqa: E402
from ..clients.heywhale import HeywhaleClient  # noqa: E402

SourceRegistry.register("heywhale", HeywhaleClient, HeywhaleParser)
