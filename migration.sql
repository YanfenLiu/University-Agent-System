-- 赛智通 Supabase 数据库初始化 SQL
-- 用法：在 Supabase 控制台的 SQL Editor 中执行本文件全部语句

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
);

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
);

-- 性能索引：避免 ORDER BY collected_at 全表扫描导致 PgBouncer 超时
CREATE INDEX IF NOT EXISTS idx_competitions_collected_at
  ON competitions (collected_at DESC);

-- Logical full refresh: retain unchanged extraction results.
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extraction_error TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS extracted_at TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS last_seen_at TEXT;
ALTER TABLE competitions ADD COLUMN IF NOT EXISTS refresh_job_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_competitions_content_hash ON competitions (content_hash);
CREATE INDEX IF NOT EXISTS idx_competitions_extraction_status ON competitions (extraction_status);
CREATE INDEX IF NOT EXISTS idx_competitions_last_seen_at ON competitions (last_seen_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status ON refresh_jobs (status);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_finished_at ON refresh_jobs (finished_at DESC);

-- Keep timestamptz columns timezone-safe while displaying new database sessions
-- (including Supabase Table Editor sessions) in Beijing time.
ALTER DATABASE postgres SET timezone TO 'Asia/Shanghai';
