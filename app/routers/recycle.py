"""Recycle bin API router."""
import json
import uuid
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import KeyRecycleBin, Key, DeviceBinding, Application
from app.dependencies import get_current_admin

router = APIRouter(prefix="/recycle", tags=["recycle"])


def _make_batch_id() -> str:
    return uuid.uuid4().hex[:16].upper()


def _serialize_key(key: Key) -> dict:
    return {
        "key_code": key.key_code,
        "batch_id": key.batch_id,
        "app_id": key.app_id,
        "key_type": key.key_type,
        "device_limit": key.device_limit,
        "status": key.status,
        "start_time": key.start_time.strftime("%Y-%m-%d %H:%M:%S") if key.start_time else None,
        "expire_time": key.expire_time.strftime("%Y-%m-%d %H:%M:%S") if key.expire_time else None,
        "created_at": key.created_at.strftime("%Y-%m-%d %H:%M:%S") if key.created_at else None,
    }


def _serialize_devices(key: Key) -> list:
    return [
        {
            "machine_code": d.machine_code,
            "ip_address": d.ip_address,
            "first_seen": d.first_seen.strftime("%Y-%m-%d %H:%M:%S") if d.first_seen else None,
            "last_heartbeat": d.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if d.last_heartbeat else None,
        }
        for d in (key.device_bindings or [])
    ]


def soft_delete_keys(db: Session, key_ids: List[int]) -> str:
    """Move keys to recycle bin. Returns batch_id."""
    batch_id = _make_batch_id()
    now = datetime.datetime.now()
    for kid in key_ids:
        key = db.query(Key).filter(Key.id == kid).first()
        if not key:
            continue
        bin_entry = KeyRecycleBin(
            batch_id=batch_id,
            original_key_id=kid,
            key_data=json.dumps(_serialize_key(key), ensure_ascii=False),
            devices_data=json.dumps(_serialize_devices(key), ensure_ascii=False),
            deleted_at=now,
        )
        db.add(bin_entry)
        db.delete(key)  # cascade deletes device_bindings too
    db.commit()
    return batch_id


# ── API ──────────────────────────────────────────

@router.get("", response_model=None)
async def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """List deleted batches, grouped by batch_id."""
    # Get distinct batch_ids with counts
    batches_q = (
        db.query(
            KeyRecycleBin.batch_id,
            func.count(KeyRecycleBin.id).label("count"),
            func.max(KeyRecycleBin.deleted_at).label("deleted_at"),
        )
        .group_by(KeyRecycleBin.batch_id)
        .order_by(func.max(KeyRecycleBin.deleted_at).desc())
    )

    total = batches_q.count()
    batches = batches_q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for batch_id, count, deleted_at in batches:
        # Get first entry to show a preview
        first = (
            db.query(KeyRecycleBin)
            .filter(KeyRecycleBin.batch_id == batch_id)
            .first()
        )
        key_data = json.loads(first.key_data) if first else {}
        # Get app name
        app_name = ""
        app_id = key_data.get("app_id")
        if app_id:
            app = db.query(Application).filter(Application.id == app_id).first()
            if app:
                app_name = app.name

        items.append({
            "batch_id": batch_id,
            "count": count,
            "preview_key": key_data.get("key_code", "")[:20],
            "app_name": app_name,
            "deleted_at": deleted_at.strftime("%Y-%m-%d %H:%M:%S") if deleted_at else "",
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{batch_id}", response_model=None)
async def get_batch_detail(
    batch_id: str,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Get all keys in a batch with their details."""
    entries = (
        db.query(KeyRecycleBin)
        .filter(KeyRecycleBin.batch_id == batch_id)
        .order_by(KeyRecycleBin.id)
        .all()
    )
    if not entries:
        raise HTTPException(status_code=404, detail="批次不存在")

    items = []
    for e in entries:
        kd = json.loads(e.key_data)
        # Get app name
        app_name = ""
        app_id = kd.get("app_id")
        if app_id:
            app = db.query(Application).filter(Application.id == app_id).first()
            if app:
                app_name = app.name

        devices = json.loads(e.devices_data) if e.devices_data else []
        items.append({
            "bin_id": e.id,
            "original_key_id": e.original_key_id,
            "key_code": kd.get("key_code", ""),
            "app_name": app_name,
            "key_type": kd.get("key_type", ""),
            "device_limit": kd.get("device_limit", 0),
            "status": kd.get("status", ""),
            "start_time": kd.get("start_time") or "",
            "expire_time": kd.get("expire_time") or "",
            "device_count": len(devices),
            "devices": devices,
            "deleted_at": e.deleted_at.strftime("%Y-%m-%d %H:%M:%S") if e.deleted_at else "",
        })

    return {"batch_id": batch_id, "items": items}


@router.post("/{batch_id}/restore", response_model=None)
async def restore_batch(
    batch_id: str,
    key_ids: Optional[List[int]] = Body(None),
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Restore keys from a batch. If key_ids provided, only restore those bin entries."""
    q = db.query(KeyRecycleBin).filter(KeyRecycleBin.batch_id == batch_id)
    if key_ids:
        q = q.filter(KeyRecycleBin.id.in_(key_ids))
    entries = q.all()

    restored = 0
    for e in entries:
        kd = json.loads(e.key_data)
        dd = json.loads(e.devices_data) if e.devices_data else []

        # Check if key_code already exists (might have been re-generated)
        existing = db.query(Key).filter(Key.key_code == kd["key_code"]).first()
        if existing:
            continue

        key = Key(
            key_code=kd["key_code"],
            batch_id=kd.get("batch_id"),
            app_id=kd["app_id"],
            key_type=kd["key_type"],
            device_limit=kd["device_limit"],
            status=kd["status"],
            start_time=datetime.datetime.strptime(kd["start_time"], "%Y-%m-%d %H:%M:%S") if kd["start_time"] else None,
            expire_time=datetime.datetime.strptime(kd["expire_time"], "%Y-%m-%d %H:%M:%S") if kd["expire_time"] else None,
            created_at=datetime.datetime.strptime(kd["created_at"], "%Y-%m-%d %H:%M:%S") if kd.get("created_at") else None,
        )
        db.add(key)
        db.flush()

        for d in dd:
            db.add(DeviceBinding(
                key_id=key.id,
                machine_code=d["machine_code"],
                ip_address=d.get("ip_address", ""),
                first_seen=datetime.datetime.strptime(d["first_seen"], "%Y-%m-%d %H:%M:%S") if d.get("first_seen") else None,
                last_heartbeat=datetime.datetime.strptime(d["last_heartbeat"], "%Y-%m-%d %H:%M:%S") if d.get("last_heartbeat") else None,
            ))

        db.delete(e)
        restored += 1

    db.commit()
    return {"status": "success", "message": f"已恢复 {restored} 张卡密"}


@router.delete("/{batch_id}", response_model=None)
async def permanent_delete_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    """Permanently delete a batch from the recycle bin."""
    entries = db.query(KeyRecycleBin).filter(KeyRecycleBin.batch_id == batch_id).all()
    count = len(entries)
    for e in entries:
        db.delete(e)
    db.commit()
    return {"status": "success", "message": f"已永久删除 {count} 条记录"}
