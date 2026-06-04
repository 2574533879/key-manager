"""Application CRUD API + page routes."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Application, Key
from app.schemas import ApplicationCreate, ApplicationUpdate, ApplicationResponse, BatchDeleteRequest
from app.dependencies import get_current_admin

router = APIRouter(prefix="/applications", tags=["applications"])


# ── API ──────────────────────────────────────────

@router.get("", response_model=List[ApplicationResponse])
async def list_applications(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    q = db.query(Application)
    if search:
        q = q.filter(
            (Application.name.contains(search)) |
            (Application.app_code.contains(search)) |
            (Application.description.contains(search))
        )
    total = q.count()
    apps = q.order_by(Application.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for a in apps:
        key_count = db.query(func.count(Key.id)).filter(Key.app_id == a.id).scalar()
        result.append(ApplicationResponse(
            id=a.id,
            name=a.name,
            app_code=a.app_code,
            description=a.description,
            key_count=key_count or 0,
            created_at=a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
        ))
    return result


@router.post("", response_model=ApplicationResponse)
async def create_application(
    data: ApplicationCreate,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    existing = db.query(Application).filter(Application.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="应用名称已存在")
    app = Application(name=data.name, description=data.description)
    db.add(app)
    db.commit()
    db.refresh(app)
    return ApplicationResponse(
        id=app.id, name=app.name, app_code=app.app_code,
        description=app.description, key_count=0,
        created_at=app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "",
    )


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: int,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    key_count = db.query(func.count(Key.id)).filter(Key.app_id == app.id).scalar()
    return ApplicationResponse(
        id=app.id, name=app.name, app_code=app.app_code,
        description=app.description, key_count=key_count or 0,
        created_at=app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else "",
    )


@router.put("/{app_id}", response_model=None)
async def update_application(
    app_id: int,
    data: ApplicationUpdate,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    if data.name is not None:
        # Check name uniqueness (excluding self)
        dup = db.query(Application).filter(
            Application.name == data.name, Application.id != app_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="应用名称已存在")
        app.name = data.name
    if data.app_code is not None:
        dup = db.query(Application).filter(
            Application.app_code == data.app_code, Application.id != app_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="应用编号已存在")
        app.app_code = data.app_code
    if data.description is not None:
        app.description = data.description
    db.commit()
    return {"status": "success", "message": "更新成功"}


@router.delete("/{app_id}", response_model=None)
async def delete_application(
    app_id: int,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    key_count = db.query(func.count(Key.id)).filter(Key.app_id == app_id).scalar()
    if key_count and key_count > 0:
        raise HTTPException(status_code=400, detail=f"该应用下有 {key_count} 张卡密，请先删除卡密")
    db.delete(app)
    db.commit()
    return {"status": "success", "message": "删除成功"}


@router.post("/batch-delete", response_model=None)
async def batch_delete_applications(
    data: BatchDeleteRequest,
    db: Session = Depends(get_db),
    _: any = Depends(get_current_admin),
):
    for app_id in data.ids:
        app = db.query(Application).filter(Application.id == app_id).first()
        if app:
            key_count = db.query(func.count(Key.id)).filter(Key.app_id == app_id).scalar()
            if key_count and key_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"应用 [{app.name}] 下有 {key_count} 张卡密，请先删除卡密"
                )
            db.delete(app)
    db.commit()
    return {"status": "success", "message": f"已删除 {len(data.ids)} 个应用"}
