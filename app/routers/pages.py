"""Web page routes — serve Jinja2 templates."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.dependencies import get_setting, get_api_prefix
from app.database import SessionLocal

router = APIRouter(tags=["pages"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page — the only public page."""
    return request.app.state.templates.TemplateResponse("login.html", {"request": request})


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return request.app.state.templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request):
    return request.app.state.templates.TemplateResponse("applications.html", {"request": request})


@router.get("/keys", response_class=HTMLResponse)
async def keys_page(request: Request):
    db = next(get_db())
    prefix = get_api_prefix(db)
    db.close()
    return request.app.state.templates.TemplateResponse(
        "keys.html",
        {"request": request, "api_prefix": prefix}
    )


@router.get("/keys/{key_id}", response_class=HTMLResponse)
async def key_detail_page(key_id: int, request: Request):
    return request.app.state.templates.TemplateResponse(
        "key_detail.html",
        {"request": request, "key_id": key_id}
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return request.app.state.templates.TemplateResponse("settings.html", {"request": request})


@router.get("/recycle-bin", response_class=HTMLResponse)
async def recycle_bin_page(request: Request):
    return request.app.state.templates.TemplateResponse("recycle_bin.html", {"request": request})


@router.get("/logout")
async def logout():
    return RedirectResponse(url="/login")
