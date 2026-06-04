"""System settings API router."""
import pyotp
import qrcode
import io
import base64
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.schemas import SettingsUpdate, SettingsResponse
from app.dependencies import get_current_admin, get_setting, set_setting
from app.config import settings as app_settings
from passlib.context import CryptContext

router = APIRouter(prefix="/settings", tags=["settings"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    prefix = get_setting(db, "api_prefix", app_settings.DEFAULT_API_PREFIX)
    threshold = get_setting(db, "heartbeat_threshold_minutes", str(app_settings.DEFAULT_HEARTBEAT_THRESHOLD_MINUTES))
    otp_attempts = get_setting(db, "otp_max_attempts", "5")
    otp_lockout = get_setting(db, "otp_lockout_minutes", "2")
    return SettingsResponse(
        api_prefix=prefix,
        heartbeat_threshold_minutes=int(threshold),
        otp_max_attempts=int(otp_attempts),
        otp_lockout_minutes=int(otp_lockout),
    )


# ── OTP ──────────────────────────────────────────

@router.get("/otp-status", response_model=None)
async def get_otp_status(
    admin: Admin = Depends(get_current_admin),
):
    """Check if OTP is enabled for current admin."""
    return {
        "otp_enabled": bool(admin.otp_secret),
        "otp_secret": admin.otp_secret or "",
    }


# Pending OTP secret (in-memory, cleared after use or restart)
_pending_otp: Dict[str, str] = {}

@router.post("/otp-setup", response_model=None)
async def setup_otp(
    admin: Admin = Depends(get_current_admin),
):
    """Generate new OTP secret, return QR code. Secret NOT saved until verified."""
    if admin.otp_secret:
        raise HTTPException(status_code=400, detail="OTP已启用，请先禁用再重新设置")

    secret = pyotp.random_base32()
    # Store pending secret in memory (not in DB yet)
    _pending_otp[str(admin.id)] = secret

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=admin.username, issuer_name="卡密管理系统")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "otp_secret": secret,
        "otp_uri": uri,
        "qr_code": f"data:image/png;base64,{qr_b64}",
    }


@router.post("/otp-verify-setup", response_model=None)
async def verify_otp_setup(
    code: str = Body(..., embed=True),
    secret: str = Body("", embed=True),
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    """Verify OTP code against the pending secret, then save to DB."""
    if admin.otp_secret:
        raise HTTPException(status_code=400, detail="OTP已启用")

    # Use the secret passed from frontend (from otp-setup response)
    pending = secret or _pending_otp.pop(str(admin.id), None)
    if not pending:
        raise HTTPException(status_code=400, detail="OTP密钥已过期，请重新生成")

    totp = pyotp.TOTP(pending)
    if not totp.verify(code, valid_window=1):
        # Put back for retry
        _pending_otp[str(admin.id)] = pending
        raise HTTPException(status_code=400, detail="动态码验证失败")

    # Save to DB — now OTP is really enabled
    admin.otp_secret = pending
    db.commit()
    return {"status": "success", "message": "OTP已启用"}


@router.post("/otp-disable", response_model=None)
async def disable_otp(
    code: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    """Disable OTP (requires valid OTP code)."""
    if not admin.otp_secret:
        raise HTTPException(status_code=400, detail="OTP未启用")

    totp = pyotp.TOTP(admin.otp_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="动态码错误")

    admin.otp_secret = None
    db.commit()
    return {"status": "success", "message": "OTP已禁用"}


@router.put("", response_model=None)
async def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    if data.api_prefix is not None:
        prefix = data.api_prefix.strip()
        if not prefix:
            raise HTTPException(status_code=400, detail="API路由前缀不能为空")
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        # strip trailing slash
        prefix = prefix.rstrip("/")
        set_setting(db, "api_prefix", prefix)

    if data.heartbeat_threshold_minutes is not None:
        t = data.heartbeat_threshold_minutes
        if t < 1 or t > 1440:
            raise HTTPException(status_code=400, detail="心跳阈值应在 1-1440 分钟之间")
        set_setting(db, "heartbeat_threshold_minutes", str(t))

    if data.otp_max_attempts is not None:
        t = data.otp_max_attempts
        if t < 1 or t > 20:
            raise HTTPException(status_code=400, detail="OTP错误次数应在 1-20 之间")
        set_setting(db, "otp_max_attempts", str(t))

    if data.otp_lockout_minutes is not None:
        t = data.otp_lockout_minutes
        if t < 1 or t > 60:
            raise HTTPException(status_code=400, detail="OTP锁定时间应在 1-60 分钟之间")
        set_setting(db, "otp_lockout_minutes", str(t))

    return {"status": "success", "message": "设置已更新"}
