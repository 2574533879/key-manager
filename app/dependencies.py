"""JWT auth dependencies and utility functions."""
import datetime
from typing import Optional, Dict, List
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Admin, Setting

bearer_scheme = HTTPBearer(auto_error=False)

# ── In-memory rate limiting (simple, per-process) ──
_rate_store: Dict[str, List[datetime.datetime]] = {}

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """Return True if under limit, False if exceeded."""
    now = datetime.datetime.now()
    window = datetime.timedelta(seconds=window_seconds)
    if key not in _rate_store:
        _rate_store[key] = []
    # prune old entries
    _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
    if len(_rate_store[key]) >= max_requests:
        return False
    _rate_store[key].append(now)
    return True


def create_token(data: dict, expires_delta: datetime.timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.datetime.utcnow() + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少令牌")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        admin_id_str = payload.get("sub")
        if admin_id_str is None:
            raise HTTPException(status_code=401, detail="令牌无效")
        admin_id = int(admin_id_str)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效")

    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if admin is None:
        raise HTTPException(status_code=401, detail="令牌无效")
    return admin


def get_setting(db: Session, key: str, default: str = "") -> str:
    """Read a setting value from DB, falling back to default."""
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    """Upsert a setting."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def get_api_prefix(db: Session = Depends(get_db)) -> str:
    return get_setting(db, "api_prefix", settings.DEFAULT_API_PREFIX)


def get_heartbeat_threshold(db: Session = Depends(get_db)) -> int:
    val = get_setting(db, "heartbeat_threshold_minutes", str(settings.DEFAULT_HEARTBEAT_THRESHOLD_MINUTES))
    return int(val)
