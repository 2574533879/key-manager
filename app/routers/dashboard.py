"""Dashboard API router."""
import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Application, Key, DeviceBinding
from app.schemas import DashboardStats
from app.dependencies import get_current_admin, get_heartbeat_threshold

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    threshold: int = Depends(get_heartbeat_threshold),
    _: any = Depends(get_current_admin),
):
    now = datetime.datetime.now()
    week_later = now + datetime.timedelta(days=7)
    threshold_delta = datetime.timedelta(minutes=threshold)

    total_keys = db.query(func.count(Key.id)).scalar() or 0
    active_keys = db.query(func.count(Key.id)).filter(
        Key.status.in_(["active", "used"])
    ).scalar() or 0
    disabled_keys = db.query(func.count(Key.id)).filter(
        Key.status == "disabled"
    ).scalar() or 0
    expired_keys = db.query(func.count(Key.id)).filter(
        Key.status == "expired"
    ).scalar() or 0
    expiring_soon = db.query(func.count(Key.id)).filter(
        Key.status.in_(["active", "used"]),
        Key.expire_time.isnot(None),
        Key.expire_time <= week_later,
        Key.expire_time > now,
    ).scalar() or 0

    online_keys = (
        db.query(func.count(func.distinct(DeviceBinding.key_id)))
        .join(Key)
        .filter(
            Key.status.in_(["active", "used"]),
            DeviceBinding.last_heartbeat >= now - threshold_delta,
        )
        .scalar()
    ) or 0

    total_apps = db.query(func.count(Application.id)).scalar() or 0

    return DashboardStats(
        total_keys=total_keys,
        active_keys=active_keys,
        online_keys=online_keys,
        expiring_soon=expiring_soon,
        expired_keys=expired_keys,
        disabled_keys=disabled_keys,
        total_applications=total_apps,
    )


@router.get("/per-app", response_model=None)
async def get_per_app_stats(
    db: Session = Depends(get_db),
    threshold: int = Depends(get_heartbeat_threshold),
    _: any = Depends(get_current_admin),
):
    """Per-application statistics for dashboard cards."""
    now = datetime.datetime.now()
    week_later = now + datetime.timedelta(days=7)
    threshold_delta = datetime.timedelta(minutes=threshold)

    apps = db.query(Application).order_by(Application.name).all()
    result = []
    for app in apps:
        keys = db.query(Key).filter(Key.app_id == app.id).all()
        total = len(keys)
        active = sum(1 for k in keys if k.status in ("active", "used"))
        expired = sum(1 for k in keys if k.status == "expired")
        disabled = sum(1 for k in keys if k.status == "disabled")
        expiring = sum(
            1 for k in keys
            if k.status in ("active", "used")
            and k.expire_time and k.expire_time <= week_later and k.expire_time > now
        )

        # online count for this app
        key_ids = [k.id for k in keys]
        online = 0
        if key_ids:
            online = (
                db.query(func.count(func.distinct(DeviceBinding.key_id)))
                .filter(
                    DeviceBinding.key_id.in_(key_ids),
                    DeviceBinding.last_heartbeat >= now - threshold_delta,
                )
                .scalar()
            ) or 0

        # used device count
        used_count = 0
        if key_ids:
            used_count = db.query(func.count(DeviceBinding.id)).filter(
                DeviceBinding.key_id.in_(key_ids)
            ).scalar() or 0

        result.append({
            "app_id": app.id,
            "app_name": app.name,
            "app_code": app.app_code,
            "total": total,
            "active": active,
            "online": online,
            "expired": expired,
            "disabled": disabled,
            "expiring": expiring,
            "used_devices": used_count,
        })

    return {"apps": result}

