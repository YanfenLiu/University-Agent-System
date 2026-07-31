-- 赛智通 身份认证与用户数据表初始化 SQL
-- 在 Supabase 控制台 SQL Editor 中执行

-- ============================================================
-- 1. 用户档案表 (profiles)
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    avatar TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 2. Refresh Token 表 (refresh_tokens)
-- 存储 SHA-256(token) 而非原始 token，防止数据库泄露时 token 直接被盗用
-- ============================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    device_info TEXT DEFAULT '',
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT false,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_lookup ON refresh_tokens (token_hash, revoked, expires_at);

-- ============================================================
-- 3. 用户画像表 (user_portraits)
-- 从对话 state_snapshot 中自动提取并持续更新
-- ============================================================
CREATE TABLE IF NOT EXISTS user_portraits (
    user_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    major TEXT DEFAULT '',
    grade TEXT DEFAULT '',
    interests TEXT[] DEFAULT '{}',
    skills TEXT[] DEFAULT '{}',
    competition_type TEXT DEFAULT '',
    competition_level TEXT DEFAULT '',
    preferred_levels TEXT[] DEFAULT '{}',
    development_goals TEXT[] DEFAULT '{}',
    available_time_per_week TEXT DEFAULT '',
    team_preference TEXT DEFAULT '',
    completeness INTEGER NOT NULL DEFAULT 0,
    extracted_from_turns INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 4. 对话历史表 (conversations)
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '新对话',
    state_snapshot JSONB NOT NULL DEFAULT '{}',
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_user_updated ON conversations (user_id, updated_at DESC);

-- ============================================================
-- 5. 用户收藏竞赛表 (saved_competitions)
-- 替代 localStorage
-- ============================================================
CREATE TABLE IF NOT EXISTS saved_competitions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    competition_id BIGINT NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, competition_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_competitions (user_id);

-- ============================================================
-- 6. 登录审计日志表 (login_attempts)
-- ============================================================
CREATE TABLE IF NOT EXISTS login_attempts (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    success BOOLEAN NOT NULL DEFAULT false,
    reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts (ip_address, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_attempts_user ON login_attempts (username, created_at DESC);
