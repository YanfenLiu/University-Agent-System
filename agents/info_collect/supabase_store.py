"""基于 Supabase 的竞赛数据存储，支持全文搜索。"""

import json as _json
import logging
import os
import re
import subprocess
import sys

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# raw_item 字段到 SQL 列的映射
FIELDS = [
    "title", "url", "source", "publish_date", "description",
    "organizer", "organizer_list", "co_organizers", "supporters",
    "regist_start", "regist_end", "contest_start", "contest_end",
    "category", "level", "attachments", "raw_text",
]

_COMPETITIONS_DDL = """\
CREATE TABLE IF NOT EXISTS competitions (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT '',
    publish_date  TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    organizer     TEXT NOT NULL DEFAULT '',
    organizer_list JSONB NOT NULL DEFAULT '[]'::jsonb,
    co_organizers  JSONB NOT NULL DEFAULT '[]'::jsonb,
    supporters     JSONB NOT NULL DEFAULT '[]'::jsonb,
    regist_start  TEXT NOT NULL DEFAULT '',
    regist_end    TEXT NOT NULL DEFAULT '',
    contest_start TEXT NOT NULL DEFAULT '',
    contest_end   TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT '',
    level         TEXT NOT NULL DEFAULT '',
    attachments   JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_text      TEXT NOT NULL DEFAULT '',
    collected_at  TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT '',
    UNIQUE (url, source)
);"""

_CRAWL_LOGS_DDL = """\
CREATE TABLE IF NOT EXISTS crawl_logs (
    id            BIGSERIAL PRIMARY KEY,
    task_id       TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT '',
    pages_crawled INTEGER NOT NULL DEFAULT 0,
    items_found   INTEGER NOT NULL DEFAULT 0,
    items_new     INTEGER NOT NULL DEFAULT 0,
    items_updated INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'running',
    error_message TEXT,
    started_at    TEXT NOT NULL DEFAULT '',
    finished_at   TEXT
);"""

_INDEX_DDL = """\
CREATE INDEX IF NOT EXISTS idx_competitions_collected_at
  ON competitions (collected_at DESC);"""


def _extract_project_ref(supabase_url: str) -> str | None:
    """Extract the Supabase project reference from a dashboard URL."""
    m = re.search(r"https?://([^.]+)\.supabase\.co", supabase_url)
    return m.group(1) if m else None


def _build_pg_dsn(supabase_url: str, password: str) -> str:
    """Build a direct PostgreSQL connection DSN (bypasses PgBouncer for DDL)."""
    ref = _extract_project_ref(supabase_url)
    if not ref:
        raise ValueError(f"Cannot extract project ref from SUPABASE_URL: {supabase_url}")
    return f"postgresql://postgres.{ref}:{password}@db.{ref}.supabase.co:5432/postgres"


class _EmbeddingWorker:
    """常驻 embedding 子进程管理器 — 模型只加载一次，复用进程。"""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._stderr_thread = None

    def _start(self):
        worker = Path(__file__).resolve().parent / "_embedding_worker.py"
        env = dict(os.environ)
        env["CUDA_VISIBLE_DEVICES"] = ""
        self._proc = subprocess.Popen(
            [sys.executable, str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        # 后台线程消费 stderr，防止管道堵塞
        def _drain():
            while self._proc and self._proc.stderr:
                try:
                    self._proc.stderr.read(4096)
                except Exception:
                    break

        self._stderr_thread = threading.Thread(target=_drain, daemon=True)
        self._stderr_thread.start()

    def compute(self, candidates: list[dict], intent: str) -> Optional[list[float]]:
        with self._lock:
            for attempt in range(2):
                try:
                    if self._proc is None or self._proc.poll() is not None:
                        if self._proc is not None:
                            print(f"[_EmbeddingWorker] 进程已死 (code={self._proc.poll()}), 重启", flush=True)
                        self._cleanup()
                        self._start()
                        print(f"[_EmbeddingWorker] daemon 进程已启动 (pid={self._proc.pid})", flush=True)

                    request = _json.dumps({"candidates": candidates, "intent": intent})
                    self._proc.stdin.write(request + "\n")
                    self._proc.stdin.flush()
                    response = self._proc.stdout.readline()

                    if not response:
                        print("[_EmbeddingWorker] daemon 无响应 (stdout EOF)", flush=True)
                        self._proc.kill()
                        try:
                            leftover = self._proc.stderr.read()
                            if leftover.strip():
                                print(f"[_EmbeddingWorker] daemon stderr: {leftover.strip()[-500:]}", flush=True)
                        except Exception:
                            pass
                        self._proc = None
                        if attempt == 0:
                            continue
                        return None

                    scores = _json.loads(response)
                    if isinstance(scores, list) and len(scores) == len(candidates):
                        return scores
                    print(f"[_EmbeddingWorker] daemon 返回 null (attempt {attempt})", flush=True)
                    return None
                except Exception as e:
                    print(f"[_EmbeddingWorker] 通信异常: {e} (attempt {attempt})", flush=True)
                    self._cleanup()
                    if attempt == 0:
                        continue
            return None

    def _cleanup(self):
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None


class SupabaseStore:
    """基于 Supabase PostgreSQL 的存储后端。

    接口与 Storage 对齐：upsert_item / exists / get_all_items / crawl_log。

    额外提供 search() 方法供下游 RAG agent 使用。
    """

    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        self._lock = threading.Lock()
        self._embed_worker = _EmbeddingWorker()
        self._ensure_tables(url)

    def _ensure_tables(self, supabase_url: str):
        """Auto-create required tables on first run via direct PostgreSQL connection.

        If SUPABASE_DB_PASSWORD is set in .env, tables are created automatically
        via a direct connection to the underlying PostgreSQL database (bypassing
        PgBouncer so DDL is supported).  Otherwise a clear message with the DDL
        is logged so the user can run it manually.
        """
        needs_tables = False
        try:
            self.client.table("competitions").select("id", count="exact").limit(1).execute()
        except Exception:
            needs_tables = True

        password = os.getenv("SUPABASE_DB_PASSWORD", "").strip()
        if not password or password == "your_database_password_here":
            if needs_tables:
                logger.warning(
                    "competitions 表不存在。设置 SUPABASE_DB_PASSWORD 可自动建表，"
                    "或手动在 Supabase SQL Editor 中执行：\n%s\n%s\n%s",
                    _COMPETITIONS_DDL, _CRAWL_LOGS_DDL, _INDEX_DDL,
                )
            return

        def _pg_run_ddl(ddl: str):
            pg = __import__("psycopg2")  # noqa: F811
            dsn = _build_pg_dsn(supabase_url, password)
            conn = pg.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.close()

        if needs_tables:
            try:
                _pg_run_ddl(_COMPETITIONS_DDL)
                _pg_run_ddl(_CRAWL_LOGS_DDL)
                _pg_run_ddl(_INDEX_DDL)
                logger.info("Supabase 表 + 索引已自动创建")
            except Exception as exc:
                logger.warning(
                    "自动建表失败 (%s)。请在 Supabase SQL Editor 中执行：\n%s\n%s\n%s",
                    exc, _COMPETITIONS_DDL, _CRAWL_LOGS_DDL, _INDEX_DDL,
                )
        else:
            try:
                _pg_run_ddl(_INDEX_DDL)
                logger.info("索引已就绪: idx_competitions_collected_at")
            except Exception as exc:
                logger.debug("索引创建跳过 (%s), 可手动: %s", exc, _INDEX_DDL)

    # ---- 竞赛数据 CRUD ----

    def exists(self, url: str, source: str) -> bool:
        result = (
            self.client.table("competitions")
            .select("id", count="exact")
            .eq("url", url)
            .eq("source", source)
            .execute()
        )
        return result.count > 0

    def upsert_item(self, item: dict) -> str:
        """插入或更新一条竞赛记录。去重键 = url + source。返回 'new' | 'updated'。

        新记录同时写入 collected_at 和 updated_at；已有记录（同 url + source）
        只刷新 updated_at，保留原始 collected_at，确保新鲜度计算不偏离。
        """
        row = self._to_row(item)
        now = datetime.now().isoformat()
        url = item["url"]
        source = item["source"]

        if self.exists(url, source):
            resp = (
                self.client.table("competitions")
                .update({"updated_at": now})
                .eq("url", url)
                .eq("source", source)
                .execute()
            )
            if resp.data:
                logger.info("Supabase 更新: %s", item.get("title", "")[:40])
            return "updated"

        row["collected_at"] = now
        row["updated_at"] = now
        resp = self.client.table("competitions").insert(row).execute()
        if resp.data:
            logger.info("Supabase 插入: %s", item.get("title", "")[:40])
        return "new"

    def get_all_items(self, source: Optional[str] = None) -> list[dict]:
        """返回所有竞赛记录的轻量字段（用于缓存检查 + embedding）。

        仅选 cache/embedding 需要的列，跳过 raw_text/attachments 等大字段，
        避免 Supabase 查询超时。
        """
        query = self.client.table("competitions").select(
            "id,title,description,source,category,contest_end,collected_at"
        ).limit(2000)
        if source:
            query = query.eq("source", source)
        result = query.execute()
        return result.data if result.data else []

    def get_full_items_by_ids(self, ids: list[int]) -> list[dict]:
        """按 ID 列表补全完整字段（raw_text, url 等），供下游 info_extract 使用。"""
        if not ids:
            return []
        all_rows: list[dict] = []
        # Supabase IN 查询分批，避免单次过滤太大
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            result = (
                self.client.table("competitions")
                .select("*")
                .in_("id", batch)
                .execute()
            )
            if result.data:
                all_rows.extend(result.data)
        return all_rows

    def delete_expired(self) -> int:
        """删除 contest_end 已明确过期的竞赛，返回删除条数。

        仅删除 contest_end 非空、可解析且日期 < 今天的条目。
        contest_end 为空或无法解析的保留，避免误删。
        """
        from datetime import date
        today = date.today()
        deleted = 0

        # 先查全表 contest_end（轻量字段），找到过期 ID
        result = (
            self.client.table("competitions")
            .select("id,contest_end")
            .limit(2000)
            .execute()
        )
        expired_ids = []
        for row in (result.data or []):
            end_str = str(row.get("contest_end", "")).strip()
            if not end_str:
                continue
            try:
                if date.fromisoformat(end_str[:10]) < today:
                    expired_ids.append(row["id"])
            except (ValueError, TypeError):
                continue

        # 逐条删除（Supabase REST 不支持 IN delete）
        for rid in expired_ids:
            try:
                self.client.table("competitions").delete().eq("id", rid).execute()
                deleted += 1
            except Exception:
                logger.debug("删除 id=%d 失败，跳过", rid)

        logger.info("过期清理完成: %d 条删除", deleted)
        return deleted

    # ---- 爬取日志 ----

    def start_crawl_log(self, task_id: str, source: str) -> int:
        resp = (
            self.client.table("crawl_logs")
            .insert({
                "task_id": task_id,
                "source": source,
                "status": "running",
                "started_at": datetime.now().isoformat(),
            })
            .execute()
        )
        log_id = resp.data[0]["id"] if resp.data else 0
        return log_id

    def update_crawl_log(self, log_id: int, **kwargs):
        if "finished_at" not in kwargs:
            kwargs["finished_at"] = datetime.now().isoformat()
        (
            self.client.table("crawl_logs")
            .update(kwargs)
            .eq("id", log_id)
            .execute()
        )

    # ---- RAG 语义搜索（LLM → sentence-transformers → TF-IDF 三层 fallback） ----

    def search_semantic(
        self,
        user_intent: str,
        limit: int = 20,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[dict]:
        """LLM 语义匹配 + 三层 fallback。

        1. DeepSeek API 批量打分（最准）
        2. sentence-transformers 本地 embedding（离线可用）
        3. TF-IDF 纯 Python 分词（零依赖兜底）
        """
        if not user_intent or not user_intent.strip():
            return self.get_all_items(source=source)[:limit]

        candidates = self._get_candidates(category=category, source=source)
        if not candidates:
            return []

        logger.info("语义搜索: '%s', 候选 %d 条", user_intent[:60], len(candidates))

        # 尝试 LLM 打分
        scores = self._try_llm_rank(candidates, user_intent)
        if scores is not None:
            return self._top_ranked(candidates, scores, limit)

        # 尝试本地 embedding
        scores = self._try_local_embedding(candidates, user_intent)
        if scores is not None:
            return self._top_ranked(candidates, scores, limit)

        # TF-IDF 兜底
        scores = self._tfidf_rank(candidates, user_intent)
        return self._top_ranked(candidates, scores, limit)

    def search_semantic_local(
        self,
        candidates: list[dict],
        user_intent: str,
        limit: int = 10,
    ) -> list[dict]:
        """语义搜索（纯本地，不调 LLM）：embedding → TF-IDF。

        由调用方传入已过滤的候选列表，避免重复查库。
        """
        if not user_intent or not user_intent.strip() or not candidates:
            return candidates[:limit] if candidates else []

        # 尝试本地 embedding
        scores = self._try_local_embedding(candidates, user_intent)
        if scores is not None:
            result = self._top_ranked(candidates, scores, limit)
            print(f"[supabase_store] embedding 返回 {len(result)} 条, top: {[(c['title'][:25], f'{s:.0f}') for c, s in sorted(zip(candidates, scores), key=lambda x: -x[1])[:10]]}", flush=True)
            return result

        # TF-IDF 兜底
        print(f"[supabase_store] embedding 失败，降级 TF-IDF", flush=True)
        scores = self._tfidf_rank(candidates, user_intent)
        return self._top_ranked(candidates, scores, limit)

    @staticmethod
    def filter_active(items: list[dict]) -> list[dict]:
        """过滤已过期的竞赛（contest_end 日期已过今天）。

        只过滤能明确判断为过期的条目：contest_end 为空或无法解析
        的保留，避免误删有效数据。
        """
        from datetime import date

        kept: list[dict] = []
        today = date.today()
        for it in items:
            end_str = str(it.get("contest_end", "")).strip()
            if not end_str:
                kept.append(it)
                continue
            try:
                # 只取日期部分 YYYY-MM-DD
                end_date = date.fromisoformat(end_str[:10])
                if end_date >= today:
                    kept.append(it)
                # else: 已过期，丢弃
            except (ValueError, TypeError):
                # 无法解析的日期视为未知，保留
                kept.append(it)
        return kept

    def _get_candidates(
        self,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[dict]:
        """获取候选竞赛列表，可按分类/来源粗筛。"""
        q = self.client.table("competitions").select("*")
        if category:
            q = q.eq("category", category)
        if source:
            q = q.eq("source", source)
        result = q.execute()
        return result.data if result.data else []

    def _try_llm_rank(self, candidates: list[dict], user_intent: str) -> Optional[list[float]]:
        """用 DeepSeek API 批量打分，失败返回 None。"""
        import os
        import json as _json

        try:
            from openai import OpenAI
        except ImportError:
            return None

        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            return None

        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        client = OpenAI(api_key=api_key, base_url=base_url)

        # 每批 30 条
        BATCH = 30
        all_scores: dict[int, float] = {}

        for batch_start in range(0, len(candidates), BATCH):
            batch = candidates[batch_start:batch_start + BATCH]
            lines = []
            for i, item in enumerate(batch):
                desc = (item.get("description") or "")[:120].replace("\n", " ")
                lines.append(f"{batch_start + i + 1}. {item['title'][:80]} | {desc}")

            prompt = (
                "你是一个大学生竞赛匹配专家。用户想要找：\"" + user_intent + "\"\n\n"
                "以下是候选竞赛列表，请对每条竞赛与用户需求的相关性打分(0-100分)。\n"
                "只输出 JSON 数组，不要解释：\n"
                "[{\"i\": 编号, \"s\": 分数}, ...]\n\n"
                + "\n".join(lines)
            )

            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=800,
                    timeout=25,
                )
                text = resp.choices[0].message.content
                # 从输出中提取 JSON
                import re
                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    results = _json.loads(match.group(0))
                    for r in results:
                        idx = int(r.get("i", r.get("index", 0))) - 1
                        score = float(r.get("s", r.get("score", 0)))
                        all_scores[idx] = score
            except Exception as e:
                logger.warning("LLM 打分失败 (batch %d): %s", batch_start // BATCH, e)
                return None

        if not all_scores:
            return None

        scores = [all_scores.get(i, 0.0) for i in range(len(candidates))]
        logger.info("LLM 打分完成: %d/%d 条有分数", len(all_scores), len(candidates))
        return scores

    def _try_local_embedding(self, candidates: list[dict], user_intent: str) -> Optional[list[float]]:
        """本机 embedding（常驻子进程，模型只加载一次）。"""
        worker = Path(__file__).resolve().parent / "_embedding_worker.py"
        if not worker.exists():
            print("[supabase_store] _embedding_worker.py 不存在", flush=True)
            return None

        try:
            scores = self._embed_worker.compute(candidates, user_intent)
            if scores is not None:
                print(f"[supabase_store] embedding daemon 成功: {len(scores)} 条", flush=True)
            else:
                print("[supabase_store] embedding daemon 返回 None", flush=True)
            return scores
        except Exception as e:
            print(f"[supabase_store] embedding daemon 异常: {e}", flush=True)
            return None

    def _tfidf_rank(self, candidates: list[dict], user_intent: str) -> list[float]:
        """纯 Python TF-IDF，零依赖兜底。"""
        import math
        import re as _re

        def tokenize(text: str) -> list[str]:
            # 中英文混合分词
            text = text.lower()
            # 保留中文连续字符、英文单词、数字
            tokens = _re.findall(r"[一-鿿]+|[a-zA-Z]+|\d+", text)
            return [t for t in tokens if len(t) > 1]

        docs = []
        for c in candidates:
            text = (c["title"] or "") + " " + (c.get("description") or "")[:300]
            docs.append(tokenize(text))
        query_tokens = tokenize(user_intent)

        # TF-IDF
        N = len(docs)
        idf = {}
        for token in set(query_tokens):
            df = sum(1 for d in docs if token in d)
            idf[token] = math.log((N + 1) / (df + 1)) + 1

        scores = []
        for d in docs:
            score = 0.0
            for token in set(query_tokens):
                if token in d:
                    tf = d.count(token) / max(len(d), 1)
                    score += tf * idf.get(token, 0)
            scores.append(score * 100)

        logger.info("TF-IDF 打分完成: %d 条", len(scores))
        return scores

    @staticmethod
    def _top_ranked(candidates: list[dict], scores: list[float], limit: int) -> list[dict]:
        """按分数排序返回 top-N（limit=0 返回全部）。"""
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        if limit and limit > 0:
            return [candidates[i] for i, _ in indexed[:limit]]
        return [candidates[i] for i, _ in indexed]

    # ---- RAG 全文搜索 ----

    def search(
        self,
        query: str,
        limit: int = 20,
        category: Optional[str] = None,
        source: Optional[str] = None,
        regist_end_after: Optional[str] = None,
    ) -> list[dict]:
        """全文搜索竞赛。

        Args:
            query: 搜索词，如 "大学生数学竞赛"
            limit: 返回条数上限
            category: 按分类过滤
            source: 按来源过滤
            regist_end_after: 截止日期之后，如 "2026-08-01"
        """
        # 用 ilike 实现模糊搜索（PostgreSQL 原生，中文可用）
        q = (
            self.client.table("competitions")
            .select("*")
            .ilike("title", f"%{query}%")
            .order("collected_at", desc=True)
            .limit(limit)
        )

        if category:
            q = q.eq("category", category)
        if source:
            q = q.eq("source", source)
        if regist_end_after:
            q = q.gte("regist_end", regist_end_after)

        result = q.execute()
        return result.data if result.data else []

    def search_multi(
        self,
        query: str,
        limit: int = 20,
        **filters,
    ) -> list[dict]:
        """多字段模糊搜索（title + description + organizer）。"""
        q = (
            self.client.table("competitions")
            .select("*")
            .ilike("title", f"%{query}%")
            .order("collected_at", desc=True)
            .limit(limit)
        )
        for k, v in filters.items():
            if v:
                q = q.eq(k, v)
        result = q.execute()
        return result.data if result.data else []

    def search_by_keywords(self, keywords: list[str], limit: int = 20) -> list[dict]:
        """Search competitions by multiple keywords across title + description."""
        if not keywords:
            return []
        or_parts = []
        for kw in keywords:
            escaped = kw.replace("%", r"\%").replace("_", r"\_")
            or_parts.append(f"title.ilike.%{escaped}%")
            or_parts.append(f"description.ilike.%{escaped}%")
        or_filter = ",".join(or_parts)
        try:
            q = (
                self.client.table("competitions")
                .select("*")
                .or_(or_filter)
                .order("collected_at", desc=True)
                .limit(limit)
            )
            result = q.execute()
            return result.data if result.data else []
        except Exception:
            logger.warning("Supabase search_by_keywords failed, falling back.", exc_info=True)
            return []

    # ---- 实用方法 ----

    def get_categories(self) -> list[str]:
        result = (
            self.client.table("competitions")
            .select("category", count="exact")
            .not_.is_("category", "null")
            .neq("category", "")
            .execute()
        )
        cats = set()
        for row in (result.data or []):
            cat = row.get("category", "").strip()
            if cat:
                cats.add(cat)
        return sorted(cats)

    def count(self, source: Optional[str] = None) -> int:
        q = self.client.table("competitions").select("id", count="exact")
        if source:
            q = q.eq("source", source)
        result = q.execute()
        # count 在 result.count 中
        if result.count is not None:
            return result.count
        return len(result.data) if result.data else 0

    # ---- 内部 ----

    @staticmethod
    def _to_row(item: dict) -> dict:
        row = {}
        for f in FIELDS:
            val = item.get(f)
            if val is None:
                val = "" if f not in ("attachments", "organizer_list", "co_organizers", "supporters", "raw_text") else []
            row[f] = val
        return row
