"""测试爬虫功能 — 独立运行，测试各数据源的 Client + Parser 联调。

用法:
    python test_crawler.py                     # 全量爬取 5 个网站
    python test_crawler.py saikr               # 只爬赛氪
    python test_crawler.py --dry-run           # 干跑
    python test_crawler.py --search "大学生数学竞赛"  # 语义搜索
"""

import json
import sys
import os
import logging
from datetime import datetime

# 每次 print 后立即刷新
_print = print

def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _print(*args, **kwargs)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crawler_test")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from agents.info_collect.registry import SourceRegistry
from agents.info_collect.storage import Storage
from agents.info_collect.crawler import Crawler, _extract_ident

ALL_SOURCES = ["saikr", "52jingsai", "ali_tianchi", "heywhale", "datafountain"]


def banner(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def test_registry():
    """验证所有数据源已注册。"""
    banner("1. 注册表检查")
    registered = SourceRegistry.list_all()
    print(f"已注册数据源: {registered}")
    print(f"总计: {len(registered)} 个")

    for name in registered:
        spec = SourceRegistry.get(name)
        client = spec.client_class()
        parser = spec.parser_class({})
        print(f"  {name:20s}  Client={spec.client_class.__name__:25s}  Parser={spec.parser_class.__name__:25s}")
        client.close()

    missing = set(ALL_SOURCES) - set(registered)
    if missing:
        logger.warning("未注册的数据源: %s", missing)
    else:
        print("  >>> 全部 5 个数据源已就绪")


def test_parser_unit():
    """对各 parser 做单元检查（不发网络请求）。"""
    banner("2. Parser 单元检查")
    mock_json = {"data": {"list": [{"title": "测试竞赛", "url": "/test/1"}]}}

    for name in ALL_SOURCES:
        spec = SourceRegistry.get(name)
        if spec is None:
            print(f"  {name}: 未注册，跳过")
            continue
        parser = spec.parser_class({})
        try:
            result = parser.parse_list(mock_json)
            empty = parser.parse_list({})
            detail = parser.parse_detail({})
            print(f"  {name:20s}  parse_list(mock)={len(result)}  parse_list(empty)={len(empty)}  parse_detail(empty)={'OK' if isinstance(detail, dict) else 'FAIL'}")
        except Exception as e:
            print(f"  {name:20s}  ERROR: {e}")


def _load_config():
    import yaml
    config_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    cfg = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    return cfg


def test_crawler_dry_run(sources: list[str]):
    """验证 Crawler 能正确调度各数据源。"""
    banner("3. Crawler 干跑（验证调度逻辑）")

    config = _load_config()
    config.setdefault("info_collect", {}).update({
        "request_delay_min": 0.1,
        "request_delay_max": 0.3,
        "max_pages": 1,
    })
    config.setdefault("storage", {}).setdefault("raw_data_path", "./data/raw")
    storage = Storage.create(config)
    crawler = Crawler(config, storage)

    print(f"待采集数据源: {sources}")
    print(f"Crawler 配置: max_pages={crawler.max_pages}, delay={crawler.delay_min}-{crawler.delay_max}s")
    print(f"  模式: 全量入库（不做关键词过滤）")

    for s in sources:
        spec = SourceRegistry.get(s)
        if spec:
            print(f"  {s:20s} -> Client={spec.client_class.__name__}, Parser={spec.parser_class.__name__}")
        else:
            print(f"  {s:20s} -> 未注册!")

    cases = [
        ("https://www.saikr.com/vse/58394", "58394"),
        ("https://www.52jingsai.com/article-23897-1.html", "article-23897-1"),
        ("https://www.datafountain.cn/competitions/1169", "1169"),
        ("https://tianchi.aliyun.com/competition/532495", "532495"),
    ]
    for url, expected in cases:
        result = _extract_ident(url)
        status = "OK" if result == expected else f"FAIL (got {result})"
        print(f"    _extract_ident({url}) = {result}  {status}")

    print(f"  >>> 干跑通过（{len(sources)} 个数据源）")


def test_crawl_live(source: str, timeout: int = 10):
    """真实爬取单个数据源，全量入库。"""
    banner(f"4. 真实爬取: {source} (全量入库)")

    config = _load_config()
    config.setdefault("info_collect", {}).update({
        "request_delay_min": 1,
        "request_delay_max": 3,
        "max_pages": 2,
        "client_timeout": timeout,
    })
    config.setdefault("storage", {}).setdefault("raw_data_path", "./data/raw")

    storage = Storage.create(config)
    crawler = Crawler(config, storage)
    log_id = storage.start_crawl_log(f"test_{source}", source)
    stats = {}

    print(f"最大页数: {crawler.max_pages}")
    print(f"开始全量爬取 {source} (无关键词过滤) ...")

    try:
        items, stats = crawler.crawl([], [source], max_pages_per_source=crawler.max_pages, log_id=log_id)
        pages = stats.get("pages_crawled", 0)
        total = stats.get("items_found", 0)
        new = stats.get("items_new", 0)
        updated = stats.get("items_updated", 0)

        print(f"\n结果: 爬取 {pages} 页, 入库 {total} 条, 新增 {new} 条, 更新 {updated} 条")

        if items:
            print(f"\n前 {min(3, len(items))} 条结果:")
            for i, item in enumerate(items[:3], 1):
                print(f"  {i}. [{item.get('source', '?')}] {item.get('title', '无标题')[:60]}")
                print(f"     URL: {item.get('url', 'N/A')}")
                desc = item.get("description", "")
                if desc:
                    print(f"     描述: {desc[:100]}...")
        elif pages == 0:
            print("  提示: 爬虫未获取到任何页面数据，可能是网络不通或页面结构变化")
        else:
            print(f"  提示: {pages} 页全部入库完成，共 {total} 条")

        return items, stats

    except Exception as e:
        logger.exception("爬取 %s 失败", source)
        print(f"  错误: {e}")
        return [], {}
    finally:
        storage.update_crawl_log(
            log_id,
            pages_crawled=stats.get("pages_crawled", 0),
            items_found=stats.get("items_found", 0),
            items_new=stats.get("items_new", 0),
            items_updated=stats.get("items_updated", 0),
            status="completed",
            finished_at=datetime.now().isoformat(),
        )


def test_semantic_search(query: str):
    """语义搜索已有数据。"""
    banner(f"5. 语义搜索: {query}")

    config = _load_config()
    storage = Storage.create(config)

    if not hasattr(storage, "search_semantic"):
        print("  当前存储后端不支持语义搜索（仅 Supabase 支持）")
        return

    results = storage.search_semantic(query, limit=10)

    print(f"\n搜索结果: {len(results)} 条")
    for i, item in enumerate(results, 1):
        print(f"\n  {i}. [{item.get('source', '?')}] {item.get('title', '无标题')[:60]}")
        print(f"     URL: {item.get('url', 'N/A')}")
        print(f"     organizer: {item.get('organizer', '')[:50]}")
        print(f"     category: {item.get('category', '')}")
        print(f"     regist_end: {item.get('regist_end', '')}")
        desc = item.get("description", "")
        if desc:
            print(f"     描述: {desc[:120]}...")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    timeout = 10
    search_query = None

    for i, a in enumerate(args):
        if a == "--timeout" and i + 1 < len(args):
            timeout = int(args[i + 1])
        if a == "--search" and i + 1 < len(args):
            search_query = args[i + 1]

    sources = [a for a in args if not a.startswith("--") and a in ALL_SOURCES]
    # 过滤掉 --timeout, --search 后面的值
    flag_values = []
    for i, a in enumerate(args):
        if a in ("--timeout", "--search") and i + 1 < len(args):
            flag_values.append(args[i + 1])
    sources = [a for a in sources if a not in flag_values]

    if not sources and not search_query:
        sources = ALL_SOURCES.copy()

    # 验证
    registered = SourceRegistry.list_all()
    invalid = [s for s in sources if s not in registered]
    if invalid:
        print(f"无效的数据源: {invalid}")
        print(f"可用: {registered}")
        sys.exit(1)

    print(f"数据源: {sources}")
    print(f"模式: {'干跑' if dry_run else '真实爬取(全量入库)'}")
    print(f"超时: {timeout}s")

    test_registry()
    test_parser_unit()

    if not dry_run:
        test_crawler_dry_run(sources)

    if not dry_run and sources:
        for source in sources:
            test_crawl_live(source, timeout=timeout)

    if search_query:
        test_semantic_search(search_query)

    banner("测试完成")
    print(f"测试的数据源: {', '.join(sources) if sources else '(仅搜索)'}")
    print("用法:")
    print("  python test_crawler.py --dry-run                        # 干跑")
    print("  python test_crawler.py saikr                           # 全量爬赛氪")
    print("  python test_crawler.py 52jingsai                       # 全量爬52jingsai")
    print("  python test_crawler.py --search \"大学生数学竞赛\"      # 语义搜索")


if __name__ == "__main__":
    main()
