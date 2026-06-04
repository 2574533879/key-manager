"""Key management API + page routes."""
import csv
import datetime
import io
import random
import string
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Application, Key, DeviceBinding
from app.schemas import (
    KeyGenerateRequest, KeyUpdateRequest, KeyResponse, KeyDetailResponse,
    DeviceInfo, BatchDeleteRequest,
)
from app.dependencies import get_current_admin, get_heartbeat_threshold
from app.routers.recycle import soft_delete_keys

router = APIRouter(prefix="/keys", tags=["keys"])


def _key_to_response(key: Key, db: Session, threshold_minutes: int) -> KeyResponse:
    """Convert Key model to KeyResponse with computed fields."""
    used_count = db.query(func.count(DeviceBinding.id)).filter(
        DeviceBinding.key_id == key.id
    ).scalar() or 0

    # Check online status
    online = False
    if used_count > 0:
        threshold = datetime.timedelta(minutes=threshold_minutes)
        recent = (
            db.query(DeviceBinding)
            .filter(
                DeviceBinding.key_id == key.id,
                DeviceBinding.last_heartbeat >= datetime.datetime.now() - threshold,
            )
            .count()
        )
        online = recent > 0

    return KeyResponse(
        id=key.id,
        key_code=key.key_code,
        batch_id=key.batch_id,
        app_id=key.app_id,
        app_name=key.application.name if key.application else "",
        key_type=key.key_type,
        device_limit=key.device_limit,
        status=key.status,
        start_time=key.start_time.strftime("%Y-%m-%d %H:%M:%S") if key.start_time else None,
        expire_time=key.expire_time.strftime("%Y-%m-%d %H:%M:%S") if key.expire_time else None,
        used_count=used_count,
        online=online,
        created_at=key.created_at.strftime("%Y-%m-%d %H:%M:%S") if key.created_at else "",
    )


def _generate_key_code(length: int = 20) -> str:
    """Generate a random key code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


# ── API ──────────────────────────────────────────

@router.get("", response_model=None)
async def list_keys(
    keyword: str = Query(default=""),
    app_keyword: str = Query(default=""),
    batch_id: str = Query(default=""),
    app_id: Optional[int] = Query(default=None),
    key_type: str = Query(default=""),
    status: str = Query(default=""),
    device_limit: Optional[int] = Query(default=None),
    expire_start: str = Query(default=""),
    expire_end: str = Query(default=""),
    created_start: str = Query(default=""),
    created_end: str = Query(default=""),
    online: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    threshold: int = Depends(get_heartbeat_threshold),
    _: any = Depends(get_current_admin),
):
    q = db.query(Key).join(Application)

    # Filters
    if batch_id:
        q = q.filter(Key.batch_id.contains(batch_id))
    if keyword:
        q = q.filter(Key.key_code.contains(keyword))
    if app_keyword:
        q = q.filter(Application.name.contains(app_keyword))

    if app_id:
        q = q.filter(Key.app_id == app_id)

    if key_type:
        q = q.filter(Key.key_type == key_type)

    if status:
        q = q.filter(Key.status == status)

    if device_limit is not None:
        q = q.filter(Key.device_limit == device_limit)

    # Date range filters
    if expire_start:
        try:
            dt = datetime.datetime.strptime(expire_start, "%Y-%m-%d")
            q = q.filter(Key.expire_time >= dt)
        except ValueError:
            pass

    if expire_end:
        try:
            dt = datetime.datetime.strptime(expire_end, "%Y-%m-%d")
            q = q.filter(Key.expire_time <= dt)
        except ValueError:
            pass

    if created_start:
        try:
            dt = datetime.datetime.strptime(created_start, "%Y-%m-%d")
            q = q.filter(Key.created_at >= dt)
        except ValueError:
            pass

    if created_end:
        try:
            dt = datetime.datetime.strptime(created_end, "%Y-%m-%d")
            q = q.filter(Key.created_at <= dt)
        except ValueError:
            pass

    total = q.count()
    keys = (
        q.order_by(Key.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_key_to_response(k, db, threshold) for k in keys]

    # Filter by online status (post-query, since it's computed)
    if online is not None:
        items = [item for item in items if item.online == online]
        total = len(items)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{key_id}", response_model=KeyDetailResponse)
async def get_key(
    key_id: int,
    db: Session = Depends(get_db),
    threshold: int = Depends(get_heartbeat_threshold),
    _: any = Depends(get_current_admin),
):
    key = db.query(Key).filter(Key.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="卡密不存在")

    base = _key_to_response(key, db, threshold)
    devices = [
        DeviceInfo(
            id=d.id,
            machine_code=d.machine_code,
            ip_address=d.ip_address,
            first_seen=d.first_seen.strftime("%Y-%m-%d %H:%M:%S") if d.first_seen else "",
            last_heartbeat=d.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if d.last_heartbeat else "",
        )
        for d in key.device_bindings
    ]
    return KeyDetailResponse(
        **base.model_dump(),
        devices=devices,
    )


@router.post("/generate", response_model=None)
async def generate_keys(
    data: KeyGenerateRequest,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    app = db.query(Application).filter(Application.id == data.app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")

    if data.count < 1 or data.count > 1000:
        raise HTTPException(status_code=400, detail="生成数量应在 1-1000 之间")

    prefix = data.prefix.strip() if data.prefix else ""
    suffix = data.suffix.strip() if data.suffix else ""

    batch_id = uuid.uuid4().hex[:12].upper()
    keys = []
    for _ in range(data.count):
        key_code = prefix + _generate_key_code() + suffix
        # Ensure uniqueness
        while db.query(Key).filter(Key.key_code == key_code).first():
            key_code = prefix + _generate_key_code() + suffix

        expire_time = None
        now = datetime.datetime.now()
        if data.expire_days:
            expire_time = now + datetime.timedelta(days=data.expire_days)

        k = Key(
            key_code=key_code,
            batch_id=batch_id,
            app_id=data.app_id,
            key_type=data.key_type,
            device_limit=data.device_limit,
            expire_time=expire_time,
        )
        db.add(k)
        keys.append(k)

    db.commit()
    return {
        "status": "success",
        "message": f"成功生成 {data.count} 张卡密",
        "batch_id": batch_id,
        "count": len(keys),
        "keys": [{"key_code": k.key_code, "key_type": k.key_type} for k in keys],
    }


@router.put("/{key_id}", response_model=None)
async def update_key(
    key_id: int,
    data: KeyUpdateRequest,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    key = db.query(Key).filter(Key.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="卡密不存在")

    if data.key_type is not None:
        key.key_type = data.key_type
    if data.device_limit is not None:
        key.device_limit = data.device_limit
    if data.status is not None:
        valid_statuses = {"active", "used", "expired", "disabled"}
        if data.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"无效状态，可选值: {valid_statuses}")
        key.status = data.status
    if data.expire_time is not None:
        try:
            key.expire_time = datetime.datetime.strptime(data.expire_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD HH:MM:SS")

    db.commit()
    return {"status": "success", "message": "更新成功"}


@router.delete("/{key_id}", response_model=None)
async def delete_key(
    key_id: int,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Single key delete → recycle bin."""
    key = db.query(Key).filter(Key.id == key_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="卡密不存在")
    batch_id = soft_delete_keys(db, [key_id])
    return {"status": "success", "message": "已移入回收站", "batch_id": batch_id}


@router.post("/batch-delete", response_model=None)
async def batch_delete_keys(
    data: BatchDeleteRequest,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Batch delete → recycle bin."""
    batch_id = soft_delete_keys(db, data.ids)
    return {"status": "success", "message": f"已移入回收站", "batch_id": batch_id}


@router.post("/delete-filtered", response_model=None)
async def delete_filtered_keys(
    body: dict = Body(...),
    keyword: str = Query(default=""),
    app_keyword: str = Query(default=""),
    batch_id: str = Query(default=""),
    app_id: Optional[int] = Query(default=None),
    key_type: str = Query(default=""),
    status: str = Query(default=""),
    expire_start: str = Query(default=""),
    expire_end: str = Query(default=""),
    created_start: str = Query(default=""),
    created_end: str = Query(default=""),
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Delete ALL keys matching the current filter → recycle bin."""
    q = db.query(Key).join(Application)

    if batch_id:
        q = q.filter(Key.batch_id.contains(batch_id))
    if keyword:
        q = q.filter(Key.key_code.contains(keyword))
    if app_keyword:
        q = q.filter(Application.name.contains(app_keyword))
    if app_id:
        q = q.filter(Key.app_id == app_id)
    if key_type:
        q = q.filter(Key.key_type == key_type)
    if status:
        q = q.filter(Key.status == status)
    if expire_start:
        try:
            dt = datetime.datetime.strptime(expire_start, "%Y-%m-%d")
            q = q.filter(Key.expire_time >= dt)
        except ValueError:
            pass
    if expire_end:
        try:
            dt = datetime.datetime.strptime(expire_end, "%Y-%m-%d")
            q = q.filter(Key.expire_time <= dt)
        except ValueError:
            pass
    if created_start:
        try:
            dt = datetime.datetime.strptime(created_start, "%Y-%m-%d")
            q = q.filter(Key.created_at >= dt)
        except ValueError:
            pass
    if created_end:
        try:
            dt = datetime.datetime.strptime(created_end, "%Y-%m-%d")
            q = q.filter(Key.created_at <= dt)
        except ValueError:
            pass

    key_ids = [k.id for k in q.all()]
    if not key_ids:
        return {"status": "success", "message": "没有符合条件的卡密", "count": 0}

    batch_id = soft_delete_keys(db, key_ids)
    return {"status": "success", "message": f"已移入回收站", "batch_id": batch_id, "count": len(key_ids)}


@router.delete("/{key_id}/devices/{device_id}", response_model=None)
async def unbind_device(
    key_id: int,
    device_id: int,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Unbind a device from a key."""
    binding = (
        db.query(DeviceBinding)
        .filter(DeviceBinding.id == device_id, DeviceBinding.key_id == key_id)
        .first()
    )
    if not binding:
        raise HTTPException(status_code=404, detail="设备绑定不存在")
    db.delete(binding)
    db.commit()
    return {"status": "success", "message": "设备已解绑"}


@router.delete("/batch/{batch_id}", response_model=None)
async def delete_keys_by_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Delete all keys with a given batch_id → recycle bin."""
    keys = db.query(Key).filter(Key.batch_id == batch_id).all()
    if not keys:
        raise HTTPException(status_code=404, detail="批次不存在或已删除")
    kid = [k.id for k in keys]
    rb_id = soft_delete_keys(db, kid)
    return {"status": "success", "message": f"已移入回收站", "batch_id": rb_id, "count": len(kid)}


@router.get("/export/csv")
async def export_keys_csv(
    keyword: str = Query(default=""),
    app_keyword: str = Query(default=""),
    app_id: Optional[int] = Query(default=None),
    key_type: str = Query(default=""),
    status: str = Query(default=""),
    expire_start: str = Query(default=""),
    expire_end: str = Query(default=""),
    created_start: str = Query(default=""),
    created_end: str = Query(default=""),
    db: Session = Depends(get_db),
    threshold: int = Depends(get_heartbeat_threshold),
    _: any = Depends(get_current_admin),
):
    """Export filtered keys as CSV, one row per device binding."""
    q = db.query(Key).join(Application)

    if keyword:
        q = q.filter(Key.key_code.contains(keyword))
    if app_keyword:
        q = q.filter(Application.name.contains(app_keyword))
    if app_id:
        q = q.filter(Key.app_id == app_id)
    if key_type:
        q = q.filter(Key.key_type == key_type)
    if status:
        q = q.filter(Key.status == status)
    if expire_start:
        try:
            dt = datetime.datetime.strptime(expire_start, "%Y-%m-%d")
            q = q.filter(Key.expire_time >= dt)
        except ValueError:
            pass
    if expire_end:
        try:
            dt = datetime.datetime.strptime(expire_end, "%Y-%m-%d")
            q = q.filter(Key.expire_time <= dt)
        except ValueError:
            pass
    if created_start:
        try:
            dt = datetime.datetime.strptime(created_start, "%Y-%m-%d")
            q = q.filter(Key.created_at >= dt)
        except ValueError:
            pass
    if created_end:
        try:
            dt = datetime.datetime.strptime(created_end, "%Y-%m-%d")
            q = q.filter(Key.created_at <= dt)
        except ValueError:
            pass

    keys = q.order_by(Key.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "卡密", "批次号", "应用", "应用编号", "类型", "状态", "设备限制",
        "已用设备", "在线", "开始时间", "过期时间", "创建时间",
        "设备机器码", "设备IP", "首次连接", "最近心跳",
    ])

    for key in keys:
        is_online = False
        devices = key.device_bindings or []
        if devices:
            threshold_delta = datetime.timedelta(minutes=threshold)
            recent = [d for d in devices if d.last_heartbeat and d.last_heartbeat >= datetime.datetime.now() - threshold_delta]
            is_online = len(recent) > 0

        app_name = key.application.name if key.application else ""
        app_code = key.application.app_code if key.application else ""
        type_label = {"day":"天卡","week":"周卡","month":"月卡","quarter":"季卡","year":"年卡","permanent":"永久","custom":"自定义"}.get(key.key_type, key.key_type)

        if devices:
            for d in devices:
                writer.writerow([
                    key.key_code, key.batch_id or "", app_name, app_code, type_label, key.status,
                    key.device_limit, len(devices), "在线" if is_online else "离线",
                    key.start_time.strftime("%Y-%m-%d %H:%M:%S") if key.start_time else "",
                    key.expire_time.strftime("%Y-%m-%d %H:%M:%S") if key.expire_time else "",
                    key.created_at.strftime("%Y-%m-%d %H:%M:%S") if key.created_at else "",
                    d.machine_code, d.ip_address,
                    d.first_seen.strftime("%Y-%m-%d %H:%M:%S") if d.first_seen else "",
                    d.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if d.last_heartbeat else "",
                ])
        else:
            writer.writerow([
                key.key_code, key.batch_id or "", app_name, app_code, type_label, key.status,
                key.device_limit, 0, "离线",
                key.start_time.strftime("%Y-%m-%d %H:%M:%S") if key.start_time else "",
                key.expire_time.strftime("%Y-%m-%d %H:%M:%S") if key.expire_time else "",
                key.created_at.strftime("%Y-%m-%d %H:%M:%S") if key.created_at else "",
                "", "", "", "",
            ])

    output.seek(0)
    content = output.getvalue().encode("utf-8-sig")
    filename = f"keys_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    from urllib.parse import quote
    safe_filename = quote(filename)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
            "Content-Length": str(len(content)),
        },
    )
