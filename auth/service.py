"""认证核心逻辑：JWT 签发/验证、密码哈希、用户 CRUD、画像管理"""

import hashlib
import os
import secrets
import bcrypt
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from supabase import create_client

# 数据库存储使用北京时间
CN_TZ = timezone(timedelta(hours=8))
_utc = timezone.utc


def _now() -> str:
    """返回带北京时区的 ISO 时间字符串"""
    return datetime.now(CN_TZ).isoformat()


def _dt_now():
    """返回北京时间 datetime 对象，用于计算过期时间"""
    return datetime.now(CN_TZ)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-64-chars-minimum")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _supabase_client():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# 密码
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """bcrypt 哈希，自动处理 72 字节截断"""
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw_bytes = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(pw_bytes, hashed.encode("utf-8"))


def validate_password_strength(password: str) -> str | None:
    """返回 None 表示通过，否则返回错误描述"""
    if len(password) < 8:
        return "密码长度至少 8 位"
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        return "密码需包含字母和数字"
    return None


# ---------------------------------------------------------------------------
# JWT Access Token
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    expire = datetime.now(_utc) + timedelta(minutes=ACCESS_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(_utc), "type": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Refresh Token (随机字符串 + SHA-256 存储)
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


MAX_SESSIONS_PER_USER = 5


def create_refresh_token(user_id: str, device_info: str = "") -> tuple[str, str]:
    """返回 (raw_token, token_hash) — raw 给客户端，hash 存数据库"""
    client = _supabase_client()
    now = _now()

    # 限制每用户最多 5 个活跃 session：超出时删除最旧的
    active = client.table("refresh_tokens") \
        .select("id") \
        .eq("user_id", user_id) \
        .eq("revoked", False) \
        .gt("expires_at", now) \
        .order("created_at", desc=True) \
        .execute()
    if active.data and len(active.data) >= MAX_SESSIONS_PER_USER:
        to_delete = [row["id"] for row in active.data[MAX_SESSIONS_PER_USER - 1:]]
        for tid in to_delete:
            client.table("refresh_tokens").update({"revoked": True}).eq("id", tid).execute()

    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)
    expires_at = _dt_now() + timedelta(days=REFRESH_EXPIRE_DAYS)
    client.table("refresh_tokens").insert({
        "user_id": user_id,
        "token_hash": token_hash,
        "device_info": device_info,
        "expires_at": expires_at.isoformat(),
    }).execute()
    return raw, token_hash


def verify_refresh_token(raw_token: str) -> dict | None:
    """验证 refresh token，返回 token 行数据或 None"""
    token_hash = _hash_token(raw_token)
    client = _supabase_client()
    now = _now()
    result = client.table("refresh_tokens") \
        .select("*") \
        .eq("token_hash", token_hash) \
        .eq("revoked", False) \
        .gt("expires_at", now) \
        .execute()
    if not result.data:
        return None
    row = result.data[0]
    # 更新最后使用时间
    client.table("refresh_tokens").update({"last_used_at": now}).eq("id", row["id"]).execute()
    return row


def revoke_refresh_token(raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    client = _supabase_client()
    client.table("refresh_tokens").update({"revoked": True}).eq("token_hash", token_hash).execute()


def revoke_all_user_tokens(user_id: str) -> None:
    client = _supabase_client()
    client.table("refresh_tokens").update({"revoked": True}).eq("user_id", user_id).execute()


def revoke_session(user_id: str, session_id: str) -> bool:
    client = _supabase_client()
    result = client.table("refresh_tokens") \
        .update({"revoked": True}) \
        .eq("id", session_id) \
        .eq("user_id", user_id) \
        .execute()
    return bool(result.data)


# ---------------------------------------------------------------------------
# 用户 CRUD
# ---------------------------------------------------------------------------

def _user_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "avatar": row.get("avatar", ""),
        "status": row.get("status", "active"),
        "created_at": str(row.get("created_at", "")),
    }


def register_user(username: str, password: str, display_name: str = "") -> tuple[dict, str, str]:
    """返回 (user_dict, access_token, refresh_token_raw)"""
    client = _supabase_client()

    existing = client.table("profiles").select("id").eq("username", username).execute()
    if existing.data:
        raise ValueError("用户名已被占用")

    pw_error = validate_password_strength(password)
    if pw_error:
        raise ValueError(pw_error)

    result = client.table("profiles").insert({
        "username": username,
        "password_hash": hash_password(password),
        "display_name": display_name or username,
        "role": "user",
    }).execute()
    row = result.data[0]
    user = _user_dict(row)

    # 创建初始画像记录
    client.table("user_portraits").insert({"user_id": row["id"]}).execute()

    access_token = create_access_token(row["id"])
    refresh_raw, _ = create_refresh_token(row["id"])

    return user, access_token, refresh_raw


def login_user(username: str, password: str, ip_address: str = "") -> tuple[dict, str, str]:
    """返回 (user_dict, access_token, refresh_token_raw)"""
    client = _supabase_client()

    result = client.table("profiles").select("*").eq("username", username).execute()
    if not result.data:
        _log_attempt(username, ip_address, False, "user_not_found")
        raise ValueError("用户名或密码错误")

    row = result.data[0]

    if row.get("status") == "frozen":
        _log_attempt(username, ip_address, False, "account_frozen")
        raise ValueError("账号已被冻结，请联系管理员")

    if not verify_password(password, row["password_hash"]):
        _log_attempt(username, ip_address, False, "invalid_password")
        raise ValueError("用户名或密码错误")

    _log_attempt(username, ip_address, True, "")
    user = _user_dict(row)
    access_token = create_access_token(row["id"])
    refresh_raw, _ = create_refresh_token(row["id"])

    return user, access_token, refresh_raw


def get_user_by_id(user_id: str) -> dict | None:
    client = _supabase_client()
    result = client.table("profiles").select("*").eq("id", user_id).execute()
    if not result.data:
        return None
    return _user_dict(result.data[0])


def update_user_profile(user_id: str, display_name: str | None = None, avatar: str | None = None) -> dict | None:
    client = _supabase_client()
    fields = {}
    if display_name is not None:
        fields["display_name"] = display_name
    if avatar is not None:
        fields["avatar"] = avatar
    if not fields:
        return get_user_by_id(user_id)
    fields["updated_at"] = _now()
    client.table("profiles").update(fields).eq("id", user_id).execute()
    return get_user_by_id(user_id)


def change_password(user_id: str, old_password: str, new_password: str) -> None:
    client = _supabase_client()
    result = client.table("profiles").select("password_hash").eq("id", user_id).execute()
    if not result.data:
        raise ValueError("用户不存在")
    if not verify_password(old_password, result.data[0]["password_hash"]):
        raise ValueError("原密码错误")
    pw_error = validate_password_strength(new_password)
    if pw_error:
        raise ValueError(pw_error)
    client.table("profiles").update({
        "password_hash": hash_password(new_password),
        "updated_at": _now(),
    }).eq("id", user_id).execute()
    # 修改密码后吊销所有 token，强制重新登录
    revoke_all_user_tokens(user_id)


def delete_account(user_id: str) -> None:
    """软删除：标记为 frozen + 吊销所有 token"""
    client = _supabase_client()
    revoke_all_user_tokens(user_id)
    client.table("profiles").update({
        "status": "frozen",
        "updated_at": _now(),
    }).eq("id", user_id).execute()


def get_user_sessions(user_id: str, current_token_hash: str = "") -> list[dict]:
    """获取用户所有活跃 session"""
    client = _supabase_client()
    now = _now()
    result = client.table("refresh_tokens") \
        .select("id,device_info,created_at,last_used_at,token_hash") \
        .eq("user_id", user_id) \
        .eq("revoked", False) \
        .gt("expires_at", now) \
        .order("last_used_at", desc=True) \
        .execute()
    sessions = []
    for row in result.data:
        sessions.append({
            "id": row["id"],
            "device_info": row.get("device_info", ""),
            "created_at": str(row.get("created_at", "")),
            "last_used_at": str(row.get("last_used_at", "")),
            "is_current": row["token_hash"] == current_token_hash,
        })
    return sessions


# ---------------------------------------------------------------------------
# 登录审计
# ---------------------------------------------------------------------------

def _log_attempt(username: str, ip_address: str, success: bool, reason: str) -> None:
    try:
        client = _supabase_client()
        client.table("login_attempts").insert({
            "username": username,
            "ip_address": ip_address,
            "success": success,
            "reason": reason,
        }).execute()
    except Exception:
        pass


def get_recent_failed_attempts(username: str, minutes: int = 15) -> int:
    """返回最近 N 分钟内某用户登录失败次数"""
    client = _supabase_client()
    since = (_dt_now() - timedelta(minutes=minutes)).isoformat()
    result = client.table("login_attempts") \
        .select("id", count="exact") \
        .eq("username", username) \
        .eq("success", False) \
        .gt("created_at", since) \
        .execute()
    return result.count or 0


# ---------------------------------------------------------------------------
# 用户画像
# ---------------------------------------------------------------------------

PORTRAIT_FIELDS = [
    "major", "grade", "interests", "skills",
    "competition_type", "competition_level", "preferred_levels",
    "development_goals", "available_time_per_week", "team_preference",
]


def get_user_portrait(user_id: str) -> dict | None:
    client = _supabase_client()
    result = client.table("user_portraits").select("*").eq("user_id", user_id).execute()
    if not result.data:
        return None
    row = result.data[0]
    return {
        "major": row.get("major", ""),
        "grade": row.get("grade", ""),
        "interests": row.get("interests", []),
        "skills": row.get("skills", []),
        "competition_type": row.get("competition_type", ""),
        "competition_level": row.get("competition_level", ""),
        "preferred_levels": row.get("preferred_levels", []),
        "development_goals": row.get("development_goals", []),
        "available_time_per_week": row.get("available_time_per_week", ""),
        "team_preference": row.get("team_preference", ""),
        "completeness": row.get("completeness", 0),
    }


def update_user_portrait(user_id: str, state_snapshot: dict) -> dict | None:
    """从 state_snapshot 提取画像字段并更新 user_portraits 表"""
    fields = {}
    field_map = {
        "major": "major",
        "grade": "grade",
        "interests": "interests",
        "skills": "skills",
        "competition_type": "competition_type",
        "competition_level": "competition_level",
        "preferred_levels": "preferred_levels",
        "development_goals": "development_goals",
        "available_time_per_week": "available_time_per_week",
        "team_preference": "team_preference",
    }
    for state_key, db_col in field_map.items():
        val = state_snapshot.get(state_key)
        if val is not None and val != "" and val != []:
            fields[db_col] = val

    if not fields:
        return get_user_portrait(user_id)

    # 计算完整度
    client = _supabase_client()
    existing = client.table("user_portraits").select("*").eq("user_id", user_id).execute()
    if existing.data:
        current = existing.data[0]
        merged = {**current, **fields}
    else:
        merged = fields

    filled = sum(1 for f in PORTRAIT_FIELDS if merged.get(f) and merged[f] != [] and merged[f] != "")
    merged["completeness"] = int(filled / len(PORTRAIT_FIELDS) * 100)
    merged["extracted_from_turns"] = (merged.get("extracted_from_turns") or 0) + 1
    merged["updated_at"] = _now()

    client.table("user_portraits").upsert(merged, on_conflict="user_id").execute()
    return get_user_portrait(user_id)
