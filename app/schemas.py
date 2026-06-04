from __future__ import annotations
import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_code: str
    captcha_key: str
    otp_code: str = ""


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ── Application ───────────────────────────────────

class ApplicationCreate(BaseModel):
    name: str
    description: str = ""


class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    app_code: Optional[str] = None
    description: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    name: str
    app_code: str
    description: str
    key_count: int = 0
    created_at: str

    model_config = {"from_attributes": True}


# ── Key ───────────────────────────────────────────

class KeyGenerateRequest(BaseModel):
    app_id: int
    key_type: str = "month"
    count: int = 1
    device_limit: int = 1
    expire_days: Optional[int] = None
    prefix: str = ""
    suffix: str = ""


class KeyUpdateRequest(BaseModel):
    key_type: Optional[str] = None
    device_limit: Optional[int] = None
    status: Optional[str] = None
    expire_time: Optional[str] = None  # ISO format string


class KeyListQuery(BaseModel):
    """All fields optional for combined filtering."""
    keyword: Optional[str] = None         # fuzzy search key_code
    batch_id: Optional[str] = None
    app_id: Optional[int] = None
    key_type: Optional[str] = None
    status: Optional[str] = None
    device_limit: Optional[int] = None
    expire_start: Optional[str] = None    # expire_time >= this
    expire_end: Optional[str] = None      # expire_time <= this
    created_start: Optional[str] = None
    created_end: Optional[str] = None
    online: Optional[bool] = None         # filter by heartbeat status
    page: int = 1
    page_size: int = 20


class KeyResponse(BaseModel):
    id: int
    key_code: str
    batch_id: Optional[str] = None
    app_id: int
    app_name: str = ""
    key_type: str
    device_limit: int
    status: str
    start_time: Optional[str] = None
    expire_time: Optional[str] = None
    used_count: int = 0
    online: bool = False
    created_at: str

    model_config = {"from_attributes": True}


class KeyDetailResponse(KeyResponse):
    devices: List[DeviceInfo] = []


class DeviceInfo(BaseModel):
    id: int
    machine_code: str
    ip_address: str
    first_seen: str
    last_heartbeat: str

    model_config = {"from_attributes": True}


class BatchDeleteRequest(BaseModel):
    ids: List[int]


# ── Dashboard ─────────────────────────────────────

class DashboardStats(BaseModel):
    total_keys: int
    active_keys: int
    online_keys: int
    expiring_soon: int     # within 7 days
    expired_keys: int
    disabled_keys: int
    total_applications: int


# ── Client Auth ───────────────────────────────────

class ClientAuthRequest(BaseModel):
    machine_code: str
    key_code: str
    app_code: str
    ip_address: Optional[str] = None


class ClientAuthSuccess(BaseModel):
    status: str = "success"
    message: str = "认证成功"
    key_info: KeyInfoData


class KeyInfoData(BaseModel):
    key_code: str
    app_name: str
    key_type: str
    start_time: str
    expire_time: str
    device_limit: int
    used_count: int


class ClientAuthError(BaseModel):
    status: str = "error"
    message: str


# ── Settings ──────────────────────────────────────

class SettingsUpdate(BaseModel):
    api_prefix: Optional[str] = None
    heartbeat_threshold_minutes: Optional[int] = None
    otp_max_attempts: Optional[int] = None
    otp_lockout_minutes: Optional[int] = None


class SettingsResponse(BaseModel):
    api_prefix: str
    heartbeat_threshold_minutes: int
    otp_max_attempts: int
    otp_lockout_minutes: int
