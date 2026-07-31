"""API 服务层：为前端 third-web 提供 RESTful API 接口。

用法
----
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import secrets
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    """返回北京时间字符串（不带时区标记）"""
    return datetime.now(CN_TZ).isoformat()


def _dt_now():
    return datetime.now(CN_TZ)
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from supabase import create_client

from agents.main_agent import MainAgent

from auth.models import (
    LoginRequest, RegisterRequest, RefreshRequest, ChangePasswordRequest,
    UserProfileUpdate, SaveConversationRequest, TokenResponse,
)
from auth.service import (
    register_user, login_user, get_user_by_id, update_user_profile,
    change_password, delete_account, get_user_sessions, revoke_session,
    verify_refresh_token, revoke_refresh_token, create_access_token,
    get_user_portrait, update_user_portrait, get_recent_failed_attempts,
)
from auth.dependencies import get_current_user, get_current_admin, get_optional_user
from auth.rate_limit import limiter, LOGIN_LIMIT
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ---------------------------------------------------------------------------
# 临时诊断日志
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[DIAG] %(asctime)s %(message)s")
logger = logging.getLogger("api_diagnosis")

# ---------------------------------------------------------------------------
# 项目路径与配置加载
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DOWNLOAD_REGISTRY: dict[str, Path] = {}


def _first_configured_env(*names: str) -> str:
    """Return the first non-empty value from compatible environment names."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _supabase_api_config() -> tuple[str, str]:
    """Read Supabase API credentials. Prefers service_role key for write access."""
    url = _first_configured_env("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = _first_configured_env(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "VITE_SUPABASE_ANON_KEY",
        "SUPABASE_KEY",
    )
    return url, key


def load_config() -> dict:
    """加载 YAML 配置，失败时返回空 dict。"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# 请求 / 响应数据模型
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    """前端 POST /api/agent/run 请求体。"""
    user_input: str = ""
    state_snapshot: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    """返回给前端的统一响应结构。"""
    success: bool
    response: dict[str, Any]
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetitionListResponse(BaseModel):
    """Supabase 竞赛列表分页响应。"""
    success: bool = True
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 200
    source: str = "supabase"


class RefreshResponse(BaseModel):
    success: bool
    status: str
    message: str
    job_id: int | None = None
    retry_after_seconds: int | None = None


# ---------------------------------------------------------------------------
# FastAPI 应用实例
# ---------------------------------------------------------------------------

app = FastAPI(
    title="赛智通 Agent API",
    description="为前端 third-web 提供 Agent 调度 RESTful 接口",
    version="1.0.0",
)

# Slowapi 限流
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS：生产环境使用白名单，不可用 "*" + credentials
_allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allow_origins = [o.strip() for o in _allowed.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@app.get("/")
def health_check() -> dict[str, str]:
    """健康检查端点，供 Render 等平台探测。"""
    return {"status": "ok", "service": "saizhitong-agent-api"}


@app.get("/api/files/{token}")
def download_generated_file(token: str) -> FileResponse:
    """Download a file generated by MaterialAgent in this server process."""
    path = DOWNLOAD_REGISTRY.get(token)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    return FileResponse(path, filename=path.name)


@app.get("/api/competitions", response_model=CompetitionListResponse)
def list_competitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
) -> CompetitionListResponse:
    """Return the live competition rows used by the backend agents."""
    url, key = _supabase_api_config()
    if not url or not key:
        missing = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_ANON_KEY")
        logger.error(
            "Supabase configuration missing: %s. Configure these on the backend service.",
            ", ".join(missing),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Supabase backend configuration is missing: {', '.join(missing)}.",
        )

    start = (page - 1) * page_size
    end = start + page_size - 1
    try:
        result = (
            create_client(url, key)
            .table("competitions")
            .select(
                "id,title,url,source,description,organizer,"
                "regist_end,contest_end,category,level,collected_at,updated_at",
                count="exact",
            )
            .neq("source", "permission_test")
            .order("collected_at", desc=True)
            .range(start, end)
            .execute()
        )
    except Exception as exc:
        logger.exception("Supabase competition query failed")
        raise HTTPException(
            status_code=503,
            detail="Competition database is temporarily unavailable.",
        ) from exc

    return CompetitionListResponse(
        items=result.data or [],
        total=int(result.count or 0),
        page=page,
        page_size=page_size,
    )


def _refresh_store():
    from agents.info_collect.supabase_store import SupabaseStore

    url, anon_key = _supabase_api_config()
    key = _first_configured_env("SUPABASE_SERVICE_ROLE_KEY") or anon_key
    if not url or not key:
        raise HTTPException(status_code=503, detail="Supabase refresh configuration is missing.")
    return SupabaseStore(url=url, key=key)


def _client_ip_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",", 1)[0].strip()
    if not address and request.client:
        address = request.client.host
    salt = os.getenv("REFRESH_IP_HASH_SALT", "competition-refresh")
    return hashlib.sha256(f"{salt}:{address}".encode("utf-8")).hexdigest()


def _dispatch_refresh_workflow(job_id: int) -> None:
    token = os.getenv("GITHUB_ACTIONS_TOKEN", "").strip()
    repository = os.getenv(
        "GITHUB_REPOSITORY", "Yhrjkcz1/University-Agent-System"
    ).strip()
    workflow = os.getenv(
        "GITHUB_REFRESH_WORKFLOW", "refresh-competitions.yml"
    ).strip()
    ref = os.getenv("GITHUB_REFRESH_REF", "main").strip()
    if not token:
        raise RuntimeError("GITHUB_ACTIONS_TOKEN is not configured.")

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/dispatches",
        data=json.dumps({
            "ref": ref,
            "inputs": {"job_id": str(job_id), "trigger_type": "manual"},
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "saizhitong-refresh-api",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 204:
            raise RuntimeError(f"GitHub workflow dispatch returned {response.status}.")


@app.post("/api/competitions/refresh", response_model=RefreshResponse, status_code=202)
def start_competition_refresh(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> RefreshResponse:
    store = _refresh_store()
    active = store.get_active_refresh_job()
    if active:
        try:
            started_at = datetime.fromisoformat(str(active.get("started_at")))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=CN_TZ)
            is_stale = _dt_now() - started_at > timedelta(hours=1)
        except (TypeError, ValueError):
            is_stale = True
        if is_stale:
            store.update_refresh_job(
                int(active["id"]),
                status="failed",
                finished_at=_now(),
                error_message="Refresh task did not start or finish within one hour.",
            )
        else:
            return RefreshResponse(
                success=True,
                status="already_running",
                job_id=int(active["id"]),
                message="竞赛数据库正在刷新，请稍后查看。",
            )

    ip_hash = _client_ip_hash(request)
    since = (_dt_now() - timedelta(minutes=10)).isoformat()
    recent = store.get_recent_ip_refresh(ip_hash, since)
    if recent:
        return RefreshResponse(
            success=False,
            status="rate_limited",
            job_id=int(recent["id"]),
            retry_after_seconds=600,
            message="刷新请求过于频繁，请十分钟后再试。",
        )

    job = store.create_refresh_job("manual", ip_hash, status="queued")
    job_id = int(job["id"])
    try:
        _dispatch_refresh_workflow(job_id)
    except Exception as exc:
        store.update_refresh_job(
            job_id,
            status="failed",
            finished_at=_now(),
            error_message=str(exc)[:1000],
        )
        logger.exception("Failed to dispatch refresh workflow")
        raise HTTPException(
            status_code=503,
            detail="无法启动数据库刷新任务，请检查 GitHub Actions 配置。",
        ) from exc

    return RefreshResponse(
        success=True,
        status="accepted",
        job_id=job_id,
        message="已开始刷新，请等待几分钟后刷新网站。",
    )


@app.get("/api/competitions/refresh/status")
def competition_refresh_status(
    current_admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    latest = _refresh_store().get_latest_refresh_job()
    return {"success": True, "job": latest}


def _register_generated_files(result: dict[str, Any]) -> None:
    response = result.get("response", {})
    raw_files = response.get("files", []) if isinstance(response, dict) else []
    urls: list[str] = []
    for raw_path in raw_files if isinstance(raw_files, list) else []:
        try:
            path = Path(str(raw_path)).resolve()
            path.relative_to(PROJECT_ROOT)
        except (OSError, ValueError):
            continue
        if not path.is_file():
            continue
        token = secrets.token_urlsafe(18)
        DOWNLOAD_REGISTRY[token] = path
        urls.append(f"/api/files/{token}")
    if isinstance(response, dict):
        response["files"] = urls


@app.post("/api/agent/run", response_model=AgentRunResponse)
def run_agent(
    req: AgentRunRequest,
    current_user: dict | None = Depends(get_optional_user),
) -> AgentRunResponse:
    """Pass one browser turn to MainAgent's conversational entry point."""
    try:
        logger.info(f"  user_input: {repr(req.user_input)}")
        config = load_config()
        agent = MainAgent(config=config)
        result = agent.run_conversation_turn(
            req.user_input,
            req.state_snapshot,
        )
        _register_generated_files(result)

        # 已登录用户：从 state_snapshot 提取画像
        if current_user and result.get("state_snapshot"):
            try:
                update_user_portrait(current_user["id"], result["state_snapshot"])
            except Exception:
                pass

        return AgentRunResponse(**result)

    except Exception as exc:
        logger.exception("MainAgent conversation request failed")
        return AgentRunResponse(
            success=False,
            response={
                "text": f"服务器内部错误：{exc}",
                "type": "error",
                "files": [],
                "recommendations": [],
            },
            state_snapshot=req.state_snapshot,
            metadata={"status": "error", "reset": False},
        )
# ---------------------------------------------------------------------------
# 认证路由
# ---------------------------------------------------------------------------


@app.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def auth_register(request: Request, req: RegisterRequest) -> TokenResponse:
    """注册新用户"""
    try:
        user, access_token, refresh_token = register_user(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")


@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def auth_login(request: Request, req: LoginRequest) -> TokenResponse:
    """登录"""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host

    # 检查账号锁定（15分钟内连续5次失败）
    recent_fails = get_recent_failed_attempts(req.username, minutes=15)
    if recent_fails >= 5:
        raise HTTPException(
            status_code=429,
            detail="登录尝试过于频繁，请15分钟后再试",
        )

    try:
        user, access_token, refresh_token = login_user(req.username, req.password, ip)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.exception("Login failed")
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")


@app.post("/api/auth/refresh", response_model=TokenResponse)
def auth_refresh(req: RefreshRequest) -> TokenResponse:
    """用 refresh token 换取新的 access token"""
    token_row = verify_refresh_token(req.refresh_token)
    if token_row is None:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    user = get_user_by_id(token_row["user_id"])
    if user is None or user.get("status") == "frozen":
        raise HTTPException(status_code=403, detail="账号不可用")

    # 吊销旧 token，签发新的一对
    revoke_refresh_token(req.refresh_token)
    new_access = create_access_token(user["id"])
    from auth.service import create_refresh_token as _create_rf
    new_refresh_raw, _ = _create_rf(user["id"], token_row.get("device_info", ""))

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh_raw,
        user=user,
    )


class LogoutRequest(BaseModel):
    refresh_token: str = ""


@app.post("/api/auth/logout")
def auth_logout(req: LogoutRequest, current_user: dict = Depends(get_current_user)):
    """退出登录，吊销 refresh token"""
    if req.refresh_token:
        revoke_refresh_token(req.refresh_token)
    return {"success": True}


@app.get("/api/auth/me")
def auth_me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user


@app.patch("/api/auth/me")
def auth_update_me(
    req: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    updated = update_user_profile(
        current_user["id"],
        display_name=req.display_name,
        avatar=req.avatar,
    )
    return updated or current_user


@app.put("/api/auth/me/password")
def auth_change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        change_password(current_user["id"], req.old_password, req.new_password)
        return {"success": True, "message": "密码修改成功，请重新登录"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/auth/me")
def auth_delete_account(current_user: dict = Depends(get_current_user)) -> dict:
    delete_account(current_user["id"])
    return {"success": True, "message": "账号已注销"}


@app.get("/api/auth/me/portrait")
def auth_portrait(current_user: dict = Depends(get_current_user)) -> dict:
    portrait = get_user_portrait(current_user["id"])
    return {"success": True, "portrait": portrait}


@app.get("/api/auth/me/sessions")
def auth_sessions(current_user: dict = Depends(get_current_user)) -> dict:
    sessions = get_user_sessions(current_user["id"])
    return {"success": True, "sessions": sessions}


@app.delete("/api/auth/me/sessions/{session_id}")
def auth_revoke_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    ok = revoke_session(current_user["id"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session 不存在")
    return {"success": True}


# ---------------------------------------------------------------------------
# 对话持久化路由
# ---------------------------------------------------------------------------


@app.post("/api/conversations")
def save_conversation(
    req: SaveConversationRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    payload = {
        "user_id": current_user["id"],
        "title": req.title or "新对话",
        "state_snapshot": req.state_snapshot,
        "messages": req.messages,
        "updated_at": _now(),
    }

    if req.conversation_id:
        client.table("conversations").update(payload).eq("id", req.conversation_id).eq("user_id", current_user["id"]).execute()
        return {"success": True, "id": req.conversation_id}
    else:
        result = client.table("conversations").insert(payload).execute()
        return {"success": True, "id": result.data[0]["id"]}


@app.get("/api/conversations")
def list_conversations(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, le=100),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    result = client.table("conversations") \
        .select("id,title,created_at,updated_at") \
        .eq("user_id", current_user["id"]) \
        .order("updated_at", desc=True) \
        .limit(limit) \
        .execute()
    items = []
    for row in result.data:
        items.append({
            "id": row["id"],
            "title": row["title"],
            "created_at": str(row.get("created_at", "")),
            "updated_at": str(row.get("updated_at", "")),
        })
    return {"success": True, "items": items}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    result = client.table("conversations") \
        .select("*") \
        .eq("id", conversation_id) \
        .eq("user_id", current_user["id"]) \
        .execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "conversation": result.data[0]}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    client.table("conversations") \
        .delete() \
        .eq("id", conversation_id) \
        .eq("user_id", current_user["id"]) \
        .execute()
    return {"success": True}


# ---------------------------------------------------------------------------
# 用户收藏竞赛路由（替代 localStorage）
# ---------------------------------------------------------------------------


@app.post("/api/saved-competitions/{competition_id}")
def save_competition(
    competition_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    try:
        client.table("saved_competitions").insert({
            "user_id": current_user["id"],
            "competition_id": competition_id,
        }).execute()
    except Exception:
        pass
    return {"success": True}


@app.delete("/api/saved-competitions/{competition_id}")
def unsave_competition(
    competition_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    client.table("saved_competitions") \
        .delete() \
        .eq("user_id", current_user["id"]) \
        .eq("competition_id", competition_id) \
        .execute()
    return {"success": True}


@app.get("/api/saved-competitions")
def list_saved_competitions(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """返回用户收藏的竞赛完整数据（JOIN competitions 表）"""
    url, key = _supabase_api_config()
    client = create_client(url, key)

    # 1. 获取收藏的竞赛 ID 列表
    saved = client.table("saved_competitions") \
        .select("competition_id, saved_at") \
        .eq("user_id", current_user["id"]) \
        .order("saved_at", desc=True) \
        .execute()

    if not saved.data:
        return {"success": True, "items": []}

    # 2. 批量获取竞赛完整数据
    ids = [row["competition_id"] for row in saved.data]
    saved_map = {row["competition_id"]: row["saved_at"] for row in saved.data}

    # Supabase IN 查询（分批，每批最多 50 个）
    all_comps = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        comps = client.table("competitions") \
            .select("id,title,url,description,organizer,regist_end,contest_end,category,level") \
            .in_("id", batch) \
            .execute()
        all_comps.extend(comps.data or [])

    # 3. 合并为前端格式，保持收藏顺序
    comp_map = {row["id"]: row for row in all_comps}
    items = []
    for cid in ids:
        comp = comp_map.get(cid)
        if comp is None:
            continue
        items.append({
            "id": comp["id"],
            "name": comp.get("title", ""),
            "summary": comp.get("description", ""),
            "difficulty": _map_difficulty(comp.get("level", "")),
            "deadline": comp.get("regist_end") or comp.get("contest_end", ""),
            "officialUrl": comp.get("url", ""),
            "tags": [tag for tag in [comp.get("category", ""), comp.get("level", "")] if tag],
            "status": "报名中",
            "organizer": comp.get("organizer", ""),
            "saved_at": str(saved_map.get(cid, "")),
        })

    return {"success": True, "items": items}


def _map_difficulty(level: str) -> str:
    if level in ("国际级", "国家级"):
        return "挑战"
    elif level in ("省级", "区域级"):
        return "进阶"
    elif level in ("校级", "院级"):
        return "入门"
    return "进阶"


# ---------------------------------------------------------------------------
# 管理员路由
# ---------------------------------------------------------------------------


@app.get("/api/admin/stats")
def admin_stats(current_admin: dict = Depends(get_current_admin)) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    total_users = client.table("profiles").select("id", count="exact").execute()
    active_users = client.table("profiles").select("id", count="exact").eq("status", "active").execute()
    total_conv = client.table("conversations").select("id", count="exact").execute()

    today_start = _dt_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_conv = client.table("conversations").select("id", count="exact").gte("created_at", today_start).execute()

    return {
        "success": True,
        "stats": {
            "total_users": total_users.count or 0,
            "active_users": active_users.count or 0,
            "total_conversations": total_conv.count or 0,
            "today_conversations": today_conv.count or 0,
        },
    }


class AdminUpdateUserRequest(BaseModel):
    status: str | None = None
    role: str | None = None


@app.get("/api/admin/users")
def admin_list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    search: str = Query(""),
    status: str = Query(""),
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    query = client.table("profiles").select("*", count="exact").order("created_at", desc=True)
    if search:
        query = query.or_(f"username.ilike.%{search}%,display_name.ilike.%{search}%")
    if status:
        query = query.eq("status", status)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    items = []
    for row in (result.data or []):
        row_copy = dict(row)
        row_copy.pop("password_hash", None)
        row_copy["created_at"] = str(row_copy.get("created_at", ""))
        row_copy["updated_at"] = str(row_copy.get("updated_at", ""))
        items.append(row_copy)

    return {"success": True, "items": items, "total": result.count or 0, "page": page}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(
    user_id: str,
    req: AdminUpdateUserRequest,
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    fields = {}
    if req.status is not None:
        fields["status"] = req.status
    if req.role is not None:
        fields["role"] = req.role
    if fields:
        fields["updated_at"] = _now()
        client.table("profiles").update(fields).eq("id", user_id).execute()

    return {"success": True}


@app.get("/api/admin/conversations")
def admin_list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    user_id: str = Query(""),
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    query = client.table("conversations") \
        .select("id,user_id,title,created_at,updated_at", count="exact") \
        .order("updated_at", desc=True)
    if user_id:
        query = query.eq("user_id", user_id)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    items = []
    for row in (result.data or []):
        row["created_at"] = str(row.get("created_at", ""))
        row["updated_at"] = str(row.get("updated_at", ""))
        items.append(row)

    return {"success": True, "items": items, "total": result.count or 0, "page": page}


@app.get("/api/admin/conversations/{conversation_id}")
def admin_get_conversation(
    conversation_id: str,
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    result = client.table("conversations").select("*").eq("id", conversation_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "conversation": result.data[0]}


@app.delete("/api/admin/conversations/{conversation_id}")
def admin_delete_conversation(
    conversation_id: str,
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)
    client.table("conversations").delete().eq("id", conversation_id).execute()
    return {"success": True}


@app.get("/api/admin/login-logs")
def admin_login_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    url, key = _supabase_api_config()
    client = create_client(url, key)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = client.table("login_attempts") \
        .select("*", count="exact") \
        .order("created_at", desc=True) \
        .range(start, end) \
        .execute()

    items = []
    for row in (result.data or []):
        row["created_at"] = str(row.get("created_at", ""))
        items.append(row)

    return {"success": True, "items": items, "total": result.count or 0, "page": page}


@app.get("/api/admin/refresh-jobs")
def admin_refresh_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    store = _refresh_store()
    try:
        result = store.list_refresh_jobs(limit=page_size, offset=(page - 1) * page_size)
        return {"success": True, "items": result, "page": page}
    except Exception:
        return {"success": True, "items": [], "page": page}


# ---------------------------------------------------------------------------
# 直接运行时启动开发服务器
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 直接运行时启动开发服务器
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
