"""爬虫 HTTP API — 供前端通过 REST 调用触发爬取。

挂载方式（Gradio / FastAPI）:
    from agents.crawl_api import create_crawl_router
    app.mount("/api", create_crawl_router(config))

独立运行（调试）:
    python -m agents.crawl_api --port 8765

端点:
    POST /crawl            触发爬取
    GET  /crawl/status/{id} 查询状态
    GET  /crawl/recent      最近记录
    GET  /crawl/sources     可用数据源
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Optional

# FastAPI 是可选依赖，未安装时前端可直接 import CrawlService 调用
try:
    from fastapi import FastAPI, APIRouter, HTTPException
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    # 定义轻量 fallback
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): ...

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code, detail): ...

from .crawl_service import CrawlService


# ---- Pydantic models ----

if HAS_FASTAPI:
    class CrawlRequest(BaseModel):
        keywords: list[str] = Field(default_factory=list, description="搜索关键词，空列表=全量爬取")
        sources: Optional[list[str]] = Field(default=None, description="数据源，None=全部源")
        max_pages: Optional[int] = Field(default=None, description="每源最大翻页数")

    class CrawlResponse(BaseModel):
        log_id: int
        status: str
        stats: dict[str, int]
        error: Optional[str] = None


def create_crawl_router(config: dict | str | None = None) -> Any:
    """创建 FastAPI Router，包含爬虫相关端点。"""
    if not HAS_FASTAPI:
        raise ImportError("fastapi 未安装，请执行: pip install fastapi uvicorn")

    svc = CrawlService(config)
    router = APIRouter(prefix="/crawl", tags=["crawl"])

    @router.post("", response_model=CrawlResponse)  # type: ignore[misc]
    async def trigger_crawl(req: CrawlRequest):
        """手动触发一次爬取（同步执行，可能需要数分钟）。"""
        try:
            result = svc.crawl(
                keywords=req.keywords,
                sources=req.sources,
                max_pages_per_source=req.max_pages,
            )
            return CrawlResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/async")  # type: ignore[misc]
    async def trigger_crawl_async(req: CrawlRequest):
        """异步触发爬取（立即返回，后台执行）。"""
        try:
            sources = req.sources
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 先创建 log，返回 log_id
        from .info_collect.storage import Storage
        storage = Storage.create(svc.config) if isinstance(svc.config, dict) else Storage.create(None)
        valid_sources = set(svc.get_all_sources())
        sources = [s for s in (req.sources or valid_sources) if s in valid_sources]
        if not sources:
            raise HTTPException(status_code=400, detail="无有效数据源")
        log_id = storage.start_crawl_log("manual_async", ",".join(sources))

        def _bg():
            svc.crawl(keywords=req.keywords, sources=sources, max_pages_per_source=req.max_pages)

        t = threading.Thread(target=_bg, daemon=True)
        t.start()
        return {"log_id": log_id, "status": "started"}

    @router.get("/status/{log_id}")  # type: ignore[misc]
    async def crawl_status(log_id: int):
        """查询爬取状态。"""
        result = svc.get_status(log_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"log_id={log_id} 不存在")
        return result

    @router.get("/recent")  # type: ignore[misc]
    async def recent_logs(limit: int = 10):
        """最近爬取记录。"""
        return svc.get_recent_logs(limit=limit)

    @router.get("/sources")  # type: ignore[misc]
    async def available_sources():
        """可用数据源列表。"""
        return {"sources": svc.get_all_sources()}

    @router.post("/cleanup")  # type: ignore[misc]
    async def cleanup_expired():
        """删除所有 contest_end 已过期的竞赛。"""
        result = svc.cleanup_expired()
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    return router


def create_crawl_app(config: dict | str | None = None) -> Any:
    """创建独立的 FastAPI 应用（用于调试 / 独立部署）。"""
    if not HAS_FASTAPI:
        raise ImportError("fastapi 未安装")
    app = FastAPI(title="Crawl API", version="1.0")
    router = create_crawl_router(config)
    app.include_router(router)
    return app


# ---- 直接调用接口（供 Streamlit 等框架 import 使用） ----

def crawl_sync(
    keywords: Optional[list[str]] = None,
    sources: Optional[list[str]] = None,
    max_pages: Optional[int] = None,
    config: dict | str | None = None,
) -> dict[str, Any]:
    """同步爬取（阻塞），供前端直接 import 调用。

    Usage in streamlit_app.py:
        from agents.crawl_api import crawl_sync
        if st.button("刷新数据"):
            with st.spinner("爬取中..."):
                result = crawl_sync(keywords=[], sources=None)
            st.json(result)
    """
    svc = CrawlService(config)
    return svc.crawl(keywords=keywords, sources=sources, max_pages_per_source=max_pages)


def get_crawl_status(log_id: int, config: dict | str | None = None) -> Optional[dict[str, Any]]:
    svc = CrawlService(config)
    return svc.get_status(log_id)


def cleanup_expired_contests(config: dict | str | None = None) -> dict[str, Any]:
    """删除所有 contest_end 已过期的竞赛。"""
    svc = CrawlService(config)
    return svc.cleanup_expired()


def get_recent_crawls(limit: int = 10, config: dict | str | None = None) -> list[dict[str, Any]]:
    svc = CrawlService(config)
    return svc.get_recent_logs(limit=limit)


def get_available_sources(config: dict | str | None = None) -> list[str]:
    svc = CrawlService(config)
    return svc.get_all_sources()


# ---- CLI 独立运行 ----

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crawl API server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    if not HAS_FASTAPI:
        print("请安装 fastapi + uvicorn: pip install fastapi uvicorn")
        sys.exit(1)

    import uvicorn
    app = create_crawl_app()
    uvicorn.run(app, host=args.host, port=args.port)
