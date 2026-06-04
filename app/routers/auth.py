"""Admin authentication router."""
import datetime
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.models import Admin
from app.schemas import LoginRequest, TokenResponse, RefreshRequest, ChangePasswordRequest
from app.dependencies import (
    create_token, get_current_admin, check_rate_limit, get_setting,
)
from passlib.context import CryptContext

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_LOGIN_FAIL = "用户名或密码或动态码错误"

_otp_failures: Dict[str, List[datetime.datetime]] = {}


def _get_otp_settings(db: Session):
    max_attempts = int(get_setting(db, "otp_max_attempts", "5"))
    lockout_minutes = int(get_setting(db, "otp_lockout_minutes", "2"))
    return max_attempts, lockout_minutes


@router.post("/login", response_model=None)
async def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    import pyotp
    ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(f"login:{ip}", 10, 60):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    admin = db.query(Admin).filter(Admin.username == req.username).first()

    # Verify password
    if not admin or not pwd_context.verify(req.password, admin.password_hash):
        raise HTTPException(status_code=401, detail=_LOGIN_FAIL)

    # If OTP enabled, verify in the same step — same error on failure
    if admin.otp_secret:
        otp_max, otp_lockout = _get_otp_settings(db)
        now = datetime.datetime.now()
        window = datetime.timedelta(minutes=otp_lockout)

        if ip not in _otp_failures:
            _otp_failures[ip] = []
        _otp_failures[ip] = [t for t in _otp_failures[ip] if now - t < window]

        if len(_otp_failures[ip]) >= otp_max:
            remain = int((_otp_failures[ip][0] + window - now).total_seconds())
            raise HTTPException(status_code=429, detail=f"登录失败次数过多，请{remain//60}分{remain%60}秒后重试")

        if not req.otp_code or len(req.otp_code) != 6:
            _otp_failures[ip].append(now)
            raise HTTPException(status_code=401, detail=_LOGIN_FAIL)

        totp = pyotp.TOTP(admin.otp_secret)
        if not totp.verify(req.otp_code, valid_window=1):
            _otp_failures[ip].append(now)
            raise HTTPException(status_code=401, detail=_LOGIN_FAIL)

    # Issue tokens
    access_token = create_token(
        {"sub": str(admin.id)},
        datetime.timedelta(minutes=app_settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_token(
        {"sub": str(admin.id), "type": "refresh"},
        datetime.timedelta(days=app_settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token).model_dump()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    from jose import jwt, JWTError, ExpiredSignatureError
    try:
        payload = jwt.decode(
            req.refresh_token, app_settings.JWT_SECRET,
            algorithms=[app_settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="令牌无效")
        admin_id = int(payload.get("sub"))
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效")

    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=401, detail="令牌无效")

    access_token = create_token(
        {"sub": str(admin.id)},
        datetime.timedelta(minutes=app_settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_token(
        {"sub": str(admin.id), "type": "refresh"},
        datetime.timedelta(days=app_settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/change-password", response_model=None)
async def change_password(
    req: ChangePasswordRequest,
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not pwd_context.verify(req.old_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    admin.password_hash = pwd_context.hash(req.new_password)
    db.commit()
    return {"status": "success", "message": "密码修改成功"}
