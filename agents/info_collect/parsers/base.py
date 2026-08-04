"""Parser 抽象基类 — 每个平台实现自己的 parser 子类。"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def fmt_date_beijing(val) -> str:
    """格式化日期时间值为 'YYYY-MM-DD'，时区统一转北京时间。

    带时区标记（Z / +08:00 等）的 ISO 时间先转北京时间再取日期，避免
    UTC 时间在跨天时被截断成前一天（如 2026-06-29T16:00:00Z 实际是北京 6 月 30 日）。
    无时区标记的时间视为已是北京时间，直接取日期部分。
    """
    if not val:
        return ""
    s = str(val)
    normalized = s.replace(" ", "T", 1) if (" " in s and "T" not in s) else s
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return (s.split("T")[0] if "T" in s else s.split(" ")[0])[:10]
        return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d")
    except ValueError:
        return s[:10] if len(s) >= 10 else s


class BaseParser(ABC):
    """每个平台实现自己的 parser 子类。

    子类需要实现:
      - parse_list(data) → list[dict]  解析列表数据为 raw_item 列表
      - parse_detail(data) → dict      解析详情数据为结构化字段

    可选覆盖:
      - merge_detail(item, detail_fields) → dict  合并详情到列表项
      - configure(config_data)                     接收配置/分类数据
    """

    def __init__(self, config: dict):
        self.config = config

    def configure(self, config_data):
        """接收客户端提供的辅助配置（如分类映射），子类按需覆盖。"""

    @abstractmethod
    def parse_list(self, data) -> list[dict]:
        """解析列表页数据，返回 raw_item 列表。

        data 类型取决于具体 Client 的返回：JSON API 返回 dict，HTML 页面返回 str。
        每个 raw_item 至少包含: title, url, source, raw_text, publish_date, collected_at
        """
        ...

    @abstractmethod
    def parse_detail(self, data) -> dict:
        """解析详情页数据，返回结构化字段。

        返回的字段包括: description, organizer, regist_start, regist_end,
                       contest_start, contest_end, category, level, attachments 等
        """
        ...

    def merge_detail(self, item: dict, detail_fields: dict) -> dict:
        """合并详情字段到列表项，子类可按需覆盖（如 raw_text 合并策略）。"""
        item.update(detail_fields)
        return item

    def parse_featured_list(self, items: list[dict]) -> list[dict]:
        """解析首页/推荐数据为 raw_item 列表。子类按需覆盖，默认返回空列表。"""
        return []
