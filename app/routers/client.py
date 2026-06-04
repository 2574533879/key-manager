"""Client authentication router — fixed path, no JWT required."""
import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Key, Application, DeviceBinding
from app.schemas import ClientAuthRequest, ClientAuthSuccess, KeyInfoData
from app.dependencies import check_rate_limit

router = APIRouter(prefix="/client", tags=["client-auth"])


def _err(status_code: int, message: str) -> JSONResponse:
    """Return error in the format expected by existing clients."""
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message},
    )


@router.post("/auth", response_model=None)
async def client_auth(req: ClientAuthRequest, request: Request, db: Session = Depends(get_db)):
    # ── Rate limit ──────────────────────────────
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"client_auth:{ip}", 10, 60):
        return _err(429, "请求过于频繁，请稍后再试")

    # ── Validate required fields ──────────────────
    if not req.machine_code:
        return _err(400, "缺少必要参数：machine_code")
    if not req.key_code:
        return _err(400, "缺少必要参数：key_code")
    if not req.app_code:
        return _err(400, "缺少必要参数：app_code")

    # ── Validate application ──────────────────────
    app = db.query(Application).filter(Application.app_code == req.app_code).first()
    if not app:
        return _err(404, "应用编号无效")

    # ── Validate key ──────────────────────────────
    key = db.query(Key).filter(Key.key_code == req.key_code).first()
    if not key:
        return _err(404, "卡密不存在")

    # ── Key belongs to app ─────────────────────────
    if key.app_id != app.id:
        return _err(400, "卡密与应用不匹配")

    # ── Key status check ──────────────────────────
    if key.status == "disabled":
        return _err(403, "卡密已被禁用")

    now = datetime.datetime.now()

    # ── First-use activation ──────────────────────
    if key.start_time is None:
        key.start_time = now
        if key.expire_time is None:
            defaults = {
                "day": 1, "week": 7, "month": 30,
                "quarter": 90, "year": 365,
            }
            days = defaults.get(key.key_type)
            if days:
                key.expire_time = now + datetime.timedelta(days=days)

    # ── Expiry check ──────────────────────────────
    if key.expire_time and now > key.expire_time:
        key.status = "expired"
        db.commit()
        return _err(403, "卡密已过期")

    # ── Device binding ────────────────────────────
    ip_addr = req.ip_address or ip

    existing = (
        db.query(DeviceBinding)
        .filter(
            DeviceBinding.key_id == key.id,
            DeviceBinding.machine_code == req.machine_code,
        )
        .first()
    )

    if existing:
        existing.last_heartbeat = now
        existing.ip_address = ip_addr
    else:
        current_count = (
            db.query(DeviceBinding).filter(DeviceBinding.key_id == key.id).count()
        )
        if current_count >= key.device_limit:
            return _err(403, f"设备数量已达上限（{key.device_limit}台）")
        db.add(DeviceBinding(
            key_id=key.id,
            machine_code=req.machine_code,
            ip_address=ip_addr,
            first_seen=now,
            last_heartbeat=now,
        ))

    if key.status == "active":
        key.status = "used"
    db.commit()

    used_count = (
        db.query(DeviceBinding).filter(DeviceBinding.key_id == key.id).count()
    )

    return ClientAuthSuccess(
        key_info=KeyInfoData(
            key_code=key.key_code,
            app_name=app.name,
            key_type=key.key_type,
            start_time=key.start_time.strftime("%Y-%m-%d %H:%M:%S") if key.start_time else "",
            expire_time=key.expire_time.strftime("%Y-%m-%d %H:%M:%S") if key.expire_time else "",
            device_limit=key.device_limit,
            used_count=used_count,
        )
    )
