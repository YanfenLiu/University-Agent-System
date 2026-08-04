"""基于 Supabase 的竞赛数据存储，支持全文搜索。"""

import hashlib
import json as _json
import logging
import os
import re
import subprocess
import sys

import threading
from datetime import date
from pathlib import Path
from typing import Optional

from supabase import create_client, Client
from ..time_utils import beijing_now_iso

logger = logging.getLogger(__name__)

# raw_item 字段到 SQL 列的映射
FIELDS = [
    "title", "url", "source", "publish_date", "description",
    "organizer", "organizer_list", "co_organizers", "supporters",
    "regist_start", "regist_end", "contest_start", "contest_end",
    "category", "level", "attachments", "raw_text", "summary",
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
    summary       TEXT NOT NULL DEFAULT '',
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

_REFRESH_DDL = """\
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extraction_error TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extracted_at TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS last_seen_at TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS refresh_job_id BIGINT;
CREATE TABLE IF NOT EXISTS refresh_jobs (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    trigger_ip_hash TEXT,
    started_at TEXT,
    finished_at TEXT,
    items_found INTEGER NOT NULL DEFAULT 0,
    items_new INTEGER NOT NULL DEFAULT 0,
    items_changed INTEGER NOT NULL DEFAULT 0,
    items_unchanged INTEGER NOT NULL DEFAULT 0,
    items_extracted INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,
    items_deleted INTEGER NOT NULL DEFAULT 0,
    source_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_competitions_content_hash ON competitions (content_hash);
CREATE INDEX IF NOT EXISTS idx_competitions_extraction_status ON competitions (extraction_status);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status ON refresh_jobs (status);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_finished_at ON refresh_jobs (finished_at DESC);"""


def _extract_first_date(text: str) -> str:
    """从文本中提取首个日期（YYYY-MM-DD / YYYY年M月D日 等），提取不到返回空。

    用于把 LLM 输出的报名时间范围描述（如"2026年9月1日至2026年9月30日"）
    清洗成 regist_start 列需要的单个起始日期。
    """
    if not text:
        return ""
    m = re.search(r"(20\d{2})[年.\-/](\d{1,2})[月.\-/](\d{1,2})[日号]?", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    if m:
        return m.group(0)
    return ""


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
                _pg_run_ddl(_REFRESH_DDL)
                logger.info("Supabase 表 + 索引已自动创建")
            except Exception as exc:
                logger.warning(
                    "自动建表失败 (%s)。请在 Supabase SQL Editor 中执行：\n%s\n%s\n%s",
                    exc, _COMPETITIONS_DDL, _CRAWL_LOGS_DDL, _INDEX_DDL,
                )
        else:
            try:
                _pg_run_ddl(_INDEX_DDL)
                _pg_run_ddl(_REFRESH_DDL)
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

    def _legacy_upsert_item(self, item: dict) -> str:
        """插入或更新一条竞赛记录。去重键 = url + source。返回 'new' | 'updated'。

        新记录同时写入 collected_at 和 updated_at。
        已有记录（同 url + source）：用新数据补充空的字段（回填缺失的 regist_end 等），
        已有值的字段不覆盖。
        """
        row = self._to_row(item)
        now = beijing_now_iso()
        url = item["url"]
        source = item["source"]

        if self.exists(url, source):
            # 取出现有记录，只回填空字段
            existing = (
                self.client.table("competitions")
                .select("*")
                .eq("url", url)
                .eq("source", source)
                .limit(1)
                .execute()
            )
            if existing.data:
                existing_row = existing.data[0]
                patch = {"updated_at": now}
                # 只补充现有记录为空的字段；description 取更长的
                for field in FIELDS:
                    existing_val = existing_row.get(field)
                    new_val = row.get(field)
                    if field == "description":
                        old_len = len(existing_val) if isinstance(existing_val, str) else 0
                        new_len = len(new_val) if isinstance(new_val, str) else 0
                        if new_len > old_len:
                            patch[field] = new_val
                        continue
                    is_empty = (
                        existing_val is None
                        or existing_val == ""
                        or existing_val == []
                    )
                    is_non_empty = (
                        new_val is not None
                        and new_val != ""
                        and new_val != []
                    )
                    if is_empty and is_non_empty:
                        patch[field] = new_val
                self.client.table("competitions") \
                    .update(patch) \
                    .eq("url", url) \
                    .eq("source", source) \
                    .execute()
                if len(patch) > 1:
                    logger.info("Supabase 回填 %d 个字段: %s",
                                len(patch) - 1, item.get("title", "")[:40])
                else:
                    logger.info("Supabase 更新 (无新字段): %s", item.get("title", "")[:40])
            return "updated"

        row["collected_at"] = now
        row["updated_at"] = now
        resp = self.client.table("competitions").insert(row).execute()
        if resp.data:
            logger.info("Supabase 插入: %s", item.get("title", "")[:40])
        return "new"

    # 爬虫每次爬取都会变化的统计类字段，不能参与 content_hash，
    # 否则赛氪等源因浏览量/关注数变化导致全部记录被判定 changed、每次都重抽 LLM。
    _VOLATILE_FIELDS = {
        # saikr：浏览量/关注/通知/排名等
        "look_count", "focus_num", "notice_count", "news_count",
        "can_register", "is_contest_status", "teams", "users", "rank", "sons_num",
        # heywhale：参与人数/队伍数/作品数/排序
        "Sequence", "TeamsNumber", "UsersNumber", "WorksNumber",
        # 天池：队伍数（防御性，raw_text 里可能不存在）
        "teamCount", "raceListStatus",
    }

    @classmethod
    def _content_hash(cls, item: dict) -> str:
        payload = {field: item.get(field, "") for field in FIELDS}
        # raw_text 是原始 JSON（含 list/detail），清洗掉易变字段后参与哈希，
        # 使"内容没变"的记录哈希稳定 → 判定 unchanged → 不重复调 LLM
        try:
            raw = payload.get("raw_text", "")
            if raw:
                parsed = _json.loads(raw)
                cls._strip_volatile(parsed)
                payload["raw_text"] = _json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        except (ValueError, TypeError):
            pass
        encoded = _json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _strip_volatile(cls, obj) -> None:
        """递归删除 dict 中的易变字段（原地修改）。"""
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                if key in cls._VOLATILE_FIELDS:
                    obj.pop(key, None)
                else:
                    cls._strip_volatile(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                cls._strip_volatile(item)

    def upsert_item_detailed(
        self,
        item: dict,
        *,
        refresh_job_id: int | None = None,
    ) -> dict:
        """Upsert raw data and report new/changed/unchanged."""
        row = self._to_row(item)
        now = beijing_now_iso()
        content_hash = self._content_hash(item)
        existing = (
            self.client.table("competitions")
            .select("id,content_hash")
            .eq("url", item["url"])
            .eq("source", item["source"])
            .limit(1)
            .execute()
        )
        current = existing.data[0] if existing.data else None

        if current is None:
            row.update({
                "content_hash": content_hash,
                "extraction_status": "pending",
                "extraction_error": None,
                "last_seen_at": now,
                "refresh_job_id": refresh_job_id,
                "collected_at": now,
                "updated_at": now,
            })
            try:
                response = self.client.table("competitions").insert(row).execute()
            except Exception as exc:
                logger.warning("插入失败(跳过): %s - %s", item.get("title", "")[:40], exc)
                return {"operation": "unchanged", "record_id": None, "needs_extraction": False}
            record = response.data[0] if response.data else {}
            return {"operation": "new", "record_id": record.get("id"), "needs_extraction": True}

        record_id = current["id"]
        if current.get("content_hash") == content_hash:
            try:
                self.client.table("competitions").update({
                    "last_seen_at": now,
                    "refresh_job_id": refresh_job_id,
                }).eq("id", record_id).execute()
            except Exception as exc:
                logger.warning("更新时间戳失败(跳过): %s - %s", item.get("title", "")[:40], exc)
            return {"operation": "unchanged", "record_id": record_id, "needs_extraction": False}

        row.update({
            "content_hash": content_hash,
            "extraction_status": "pending",
            "extraction_error": None,
            "last_seen_at": now,
            "refresh_job_id": refresh_job_id,
            "updated_at": now,
        })
        try:
            self.client.table("competitions").update(row).eq("id", record_id).execute()
        except Exception as exc:
            logger.warning("更新失败(跳过): %s - %s", item.get("title", "")[:40], exc)
            return {"operation": "unchanged", "record_id": record_id, "needs_extraction": False}
        return {"operation": "changed", "record_id": record_id, "needs_extraction": True}

    def upsert_item(self, item: dict) -> str:
        result = self.upsert_item_detailed(item)
        return "new" if result["operation"] == "new" else "updated"

    def save_extraction_result(
        self,
        record_id: int,
        structured: dict,
        *,
        error: str | None = None,
    ) -> None:
        now = beijing_now_iso()
        if error:
            values = {
                "extraction_status": "failed",
                "extraction_error": error[:1000],
                "updated_at": now,
            }
        else:
            values = {
                "extraction_status": "completed",
                "extraction_error": None,
                "extracted_at": now,
                "updated_at": now,
            }
            for source_field, column in {
                "title": "title",
                "summary": "summary",
                "description": "description",
                "organizer": "organizer",
                "deadline": "regist_end",
                "registration_time": "regist_start",
                "contest_start": "contest_start",
                "contest_end": "contest_end",
                "type": "category",
            }.items():
                value = structured.get(source_field)
                if value not in (None, "", "unknown"):
                    if column == "regist_start":
                        # registration_time 是报名时间范围描述（如"2026年9月1日至9月30日"），
                        # regist_start 列约定存起始日期，提取首个日期，提取不到置空
                        value = _extract_first_date(str(value))
                    values[column] = value
        try:
            self.client.table("competitions").update(values).eq("id", record_id).execute()
        except Exception as exc:
            logger.warning("抽取结果回填失败(跳过): record_id=%s - %s", record_id, exc)

    def create_refresh_job(
        self,
        trigger_type: str,
        trigger_ip_hash: str | None = None,
        *,
        status: str = "queued",
    ) -> dict:
        response = self.client.table("refresh_jobs").insert({
            "status": status,
            "trigger_type": trigger_type,
            "trigger_ip_hash": trigger_ip_hash,
            "started_at": beijing_now_iso(),
        }).execute()
        return response.data[0] if response.data else {}

    def update_refresh_job(self, job_id: int, **values) -> None:
        self.client.table("refresh_jobs").update(values).eq("id", job_id).execute()

    def get_latest_refresh_job(self) -> dict | None:
        result = self.client.table("refresh_jobs").select("*").order(
            "id", desc=True
        ).limit(1).execute()
        return result.data[0] if result.data else None

    def get_active_refresh_job(self) -> dict | None:
        result = self.client.table("refresh_jobs").select("*").in_(
            "status", ["queued", "dispatched", "running"]
        ).order("id", desc=True).limit(1).execute()
        return result.data[0] if result.data else None

    def get_recent_ip_refresh(self, trigger_ip_hash: str, since_iso: str) -> dict | None:
        result = self.client.table("refresh_jobs").select(
            "id,status,started_at"
        ).eq("trigger_ip_hash", trigger_ip_hash).gte(
            "started_at", since_iso
        ).order("id", desc=True).limit(1).execute()
        return result.data[0] if result.data else None

    def list_refresh_jobs(self, limit: int = 20, offset: int = 0) -> list[dict]:
        result = self.client.table("refresh_jobs").select("*").order(
            "id", desc=True
        ).range(offset, offset + limit - 1).execute()
        return result.data or []

    def get_all_items(self, source: Optional[str] = None) -> list[dict]:
        """返回所有竞赛记录的轻量字段（用于缓存检查 + embedding）。

        仅选 cache/embedding 需要的列，跳过 raw_text/attachments 等大字段，
        避免 Supabase 查询超时。
        """
        query = self.client.table("competitions").select(
            "id,title,description,source,category,regist_end,contest_end,collected_at"
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
        """删除已过期的竞赛，返回删除条数。

        优先按报名截止（regist_end）判断；regist_end 为空时按比赛结束
        （contest_end）判断，避免 LIVE 等无报名截止字段的已结束竞赛
        永远清理不掉。两者均缺失或无法解析的保留，避免误删。
        """
        today = date.today()
        deleted = 0

        # 先查全表（含 contest_end），找到过期 ID
        result = (
            self.client.table("competitions")
            .select("id,regist_end,contest_end")
            .limit(2000)
            .execute()
        )
        expired_ids = [
            row["id"]
            for row in (result.data or [])
            if self._is_expired(row, today)
        ]

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
                "started_at": beijing_now_iso(),
            })
            .execute()
        )
        log_id = resp.data[0]["id"] if resp.data else 0
        return log_id

    def update_crawl_log(self, log_id: int, **kwargs):
        if "finished_at" not in kwargs:
            kwargs["finished_at"] = beijing_now_iso()
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
        """过滤已过期的竞赛。

        优先按报名截止（regist_end），为空时按比赛结束（contest_end）；
        两者均缺失或无法解析的保留，避免误删。
        """
        today = date.today()
        return [
            item
            for item in items
            if not SupabaseStore._is_expired(item, today)
        ]

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
        """Run the optional local embedding worker.

        The ONNX model runs in a child process and can push a small web
        instance over its memory limit.  It is therefore opt-in; callers
        transparently fall back to the lightweight TF-IDF ranker.
        """
        enabled = os.getenv("ENABLE_LOCAL_EMBEDDING", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            logger.info(
                "Local embedding is disabled; using the lightweight ranking fallback."
            )
            return None

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

    @staticmethod
    def _is_expired(item: dict, today: Optional[date] = None) -> bool:
        """判断竞赛是否已过期。

        优先用报名截止（regist_end）；LIVE 录播课等无独立报名截止的记录
        （regist_end 为空）用比赛结束（contest_end）判断，避免已结束的
        比赛因缺报名截止字段而永远清理不掉。
        """
        today = today or date.today()
        for field in ("regist_end", "contest_end"):
            end_str = str(item.get(field, "") or "").strip()
            if not end_str:
                continue
            try:
                if date.fromisoformat(end_str[:10]) < today:
                    return True
            except (ValueError, TypeError):
                continue
        return False

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
