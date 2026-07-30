"""爬虫核心 — 注册表驱动的多数据源采集，全量入库不做关键词过滤。"""

import random
import logging
import time
from typing import Optional

from .registry import SourceRegistry, SourceSpec
from .storage import Storage
from .dedup import DedupManager

logger = logging.getLogger(__name__)


class Crawler:
    """编排数据采集流程。通过 SourceRegistry 动态加载各平台的 Client + Parser。

    爬取阶段全量入库（URL 去重），不做关键词过滤。
    检索阶段由 storage.search_semantic() 做 LLM 语义匹配。
    """

    def __init__(self, config: dict, storage: Storage):
        cfg = config.get("info_collect", {})
        self.delay_min = cfg.get("request_delay_min", 0.5)
        self.delay_max = cfg.get("request_delay_max", 1.5)
        self.max_pages = cfg.get("max_pages", 3)
        self.client_timeout = cfg.get("client_timeout", 10)
        self.crawl_timeout = cfg.get("crawl_timeout", 120)
        self.detail_limit = cfg.get("detail_limit", 30)
        self.source_configs = cfg.get("sources", {})
        self.storage = storage
        self.dedup = DedupManager(storage)
        self._closed = False

    def close(self):
        self._closed = True

    # 关键词 → 标题中可能出现的等价表述（供检索阶段 TF-IDF 扩展用）
    _KEYWORD_ALIASES: dict[str, list[str]] = {
        "人工智能": ["ai", "agent", "llm", "机器学习", "深度学习", "计算机视觉", "nlp", "自然语言处理"],
        "数据分析": ["数据挖掘", "大数据", "data"],
        "软件开发": ["编程", "coding", "hackathon", "黑客松", "程序设计", "hack"],
        "创新创业": ["创业", "创新", "startup", "商业"],
        "算法": ["算法赛", "algorithm", "程序", "acm"],
        "数学建模": ["数学", "建模", "math"],
        "机器人": ["robot", "ros", "无人", "自动化"],
        "电子设计": ["电子", "硬件", "嵌入式", "iot", "物联网", "stm32"],
        "自动化": ["控制", "pid", "plc"],
        "市场营销": ["营销", "商业策划", "策划"],
        "网络安全": ["安全", "ctf", "攻防", "security"],
    }

    @classmethod
    def _expand_keywords(cls, keywords: list[str]) -> list[str]:
        """Expand user keywords with known aliases for broader matching."""
        expanded = list(keywords)
        for kw in keywords:
            lower_kw = kw.lower()
            for base, aliases in cls._KEYWORD_ALIASES.items():
                if lower_kw == base.lower() or lower_kw in [a.lower() for a in aliases]:
                    expanded.extend(aliases)
                    if base.lower() not in [e.lower() for e in expanded]:
                        expanded.append(base)
        return expanded

    def _random_delay(self):
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    def crawl(
        self,
        keywords: list[str],
        sources: list[str],
        max_pages_per_source: int,
        log_id: int,
    ) -> tuple[list[dict], dict]:
        """全量采集：遍历 sources，所有条目不做过滤直接入库。"""
        all_items = []
        seen_urls = set()
        stats = {"pages_crawled": 0, "items_found": 0, "items_new": 0, "items_updated": 0, "items_expired": 0}
        elapsed_start = time.monotonic()

        def _is_expired(item: dict) -> bool:
            end_str = str(item.get("regist_end", "")).strip()
            if not end_str:
                return False
            try:
                from datetime import date as _date
                return _date.fromisoformat(end_str[:10]) < _date.today()
            except (ValueError, TypeError):
                return False

        def _add(parsed: dict) -> bool:
            nonlocal all_items, seen_urls
            if parsed["url"] in seen_urls:
                return False
            seen_urls.add(parsed["url"])
            if _is_expired(parsed):
                return False
            all_items.append(parsed)
            return True

        for source in sources:
            spec = SourceRegistry.get(source)
            if spec is None:
                logger.warning("未注册的数据源，跳过: %s", source)
                continue

            # 总超时保护：后续源直接跳过
            elapsed = time.monotonic() - elapsed_start
            if elapsed > self.crawl_timeout:
                logger.warning(
                    "采集总耗时 %.0fs 超过 crawl_timeout(%ds)，跳过剩余源: %s",
                    elapsed, self.crawl_timeout, [s for s in sources[sources.index(source):]],
                )
                break

            logger.info("开始采集数据源: %s", source)
            sc = self.source_configs.get(source, {})
            timeout = sc.get("timeout", self.client_timeout)
            max_pages = sc.get("max_pages", max_pages_per_source)
            client = spec.client_class(timeout=timeout)
            parser = spec.parser_class({})

            try:
                try:
                    config_data = _retry(client.get_config, f"{source} 配置")
                    if config_data:
                        parser.configure(config_data)
                except Exception as e:
                    logger.warning("获取 %s 配置失败: %s", source, e)

                try:
                    featured = _retry(lambda: client.get_featured(), f"{source} 首页推荐")
                    if featured:
                        for item in parser.parse_featured_list(featured):
                            stats["items_found"] += 1
                            if not _add(item):
                                stats["items_expired"] += 1
                except Exception as e:
                    logger.warning("获取 %s 首页推荐失败: %s", source, e)

                source_matched: list[dict] = []
                page = 1
                while page <= max_pages:
                    try:
                        data = _retry(
                            lambda p=page: client.get_contests(page=p, limit=20),
                            f"{source} 列表分页(p{page})",
                        )
                    except Exception as e:
                        logger.error("%s API 请求失败 (page=%d): %s", source, page, e)
                        break

                    parsed_list = parser.parse_list(data)
                    if not parsed_list:
                        break

                    stats["pages_crawled"] += 1

                    for item in parsed_list:
                        stats["items_found"] += 1
                        if _add(item):
                            source_matched.append(item)
                        else:
                            stats["items_expired"] += 1

                    page += 1
                    if page <= max_pages:
                        self._random_delay()

                # 只对前 N 条获取详情（全量爬取时太多条目，limit 防止超时）
                detail_limit = sc.get("detail_limit", self.detail_limit)
                for idx, item in enumerate(source_matched):
                    if idx >= detail_limit:
                        break
                    ident = _extract_ident(item["url"])
                    if not ident:
                        continue
                    _fetch_detail(client, parser, item, ident, source=source)

            finally:
                client.close()

        # 全部入库（URL + source 去重）
        for item in all_items:
            op = self.storage.upsert_item(item)
            if op == "new":
                stats["items_new"] += 1
            else:
                stats["items_updated"] += 1

        logger.info(
            "采集完成: %d 页, %d 条, 新增 %d, 更新 %d, 过期跳过 %d",
            stats["pages_crawled"], stats["items_found"],
            stats["items_new"], stats["items_updated"], stats["items_expired"],
        )
        return all_items, stats


def _retry(fn, label: str = "", max_retries: int = 2):
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt < max_retries:
                wait = (attempt + 1) * 3
                logger.debug("%s 重试 (%d/%d): %s", label, attempt + 1, max_retries, e)
                time.sleep(wait)
            else:
                raise


def _fetch_detail(client, parser, item: dict, ident: str, max_retries: int = 2, source: str = ""):
    for attempt in range(max_retries + 1):
        try:
            time.sleep(random.uniform(1, 3))
            detail = client.get_contest_detail(ident)
            detail_fields = parser.parse_detail(detail)
            parser.merge_detail(item, detail_fields)
            logger.info("详情获取成功 [%s]: %s", source, item["title"][:40])
            return
        except Exception as e:
            if attempt < max_retries:
                wait = (attempt + 1) * 5
                logger.debug(
                    "详情获取重试 [%s] (%d/%d): %s",
                    item["title"][:30], attempt + 1, max_retries, e,
                )
                time.sleep(wait)
            else:
                logger.warning("获取详情失败 [%s]: %s", item["title"][:30], e)


def _extract_ident(url: str) -> str:
    if "/vse/" in url:
        return url.split("/vse/")[-1].split("?")[0]

    from urllib.parse import urlparse
    path = urlparse(url).path.rstrip("/")
    if path:
        ident = path.split("/")[-1]
        import re
        return re.sub(r"\.\w+$", "", ident)
    return ""
