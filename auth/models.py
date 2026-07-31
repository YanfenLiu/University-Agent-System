"""认证模块 — Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    avatar: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class UserInfoResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    avatar: str
    status: str
    created_at: str


class UserPortraitResponse(BaseModel):
    major: str = ""
    grade: str = ""
    interests: list[str] = []
    skills: list[str] = []
    competition_type: str = ""
    competition_level: str = ""
    preferred_levels: list[str] = []
    development_goals: list[str] = []
    available_time_per_week: str = ""
    team_preference: str = ""
    completeness: int = 0


class SessionInfo(BaseModel):
    id: str
    device_info: str
    created_at: str
    last_used_at: str | None
    is_current: bool = False


class SaveConversationRequest(BaseModel):
    conversation_id: str | None = None
    title: str = ""
    state_snapshot: dict = Field(default_factory=dict)
    messages: list[dict] = Field(default_factory=list)
