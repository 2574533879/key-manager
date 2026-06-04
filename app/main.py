"""FastAPI application entry point."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

from app.database import engine, SessionLocal, Base
from app.models import Admin
from app.config import settings as app_settings
from app.dependencies import get_setting


# ── Prefix caching helper ─────────────────────────

# In-memory cache of the API prefix, refreshed on each request
# (simple approach — reads from DB settings table)

def get_current_prefix() -> str:
    """Read the current admin API prefix from DB (with fallback)."""
    try:
        db = SessionLocal()
        prefix = get_setting(db, "api_prefix", app_settings.DEFAULT_API_PREFIX)
        db.close()
        return prefix
    except Exception:
        return app_settings.DEFAULT_API_PREFIX


# ── Lifespan ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Auto-migrate: add columns that may be missing from older DB
    from sqlalchemy import inspect, text
    with engine.connect() as conn:
        # Check/add batch_id column on keys table
        insp = inspect(conn)
        if "keys" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("keys")]
            if "batch_id" not in cols:
                conn.execute(text("ALTER TABLE keys ADD COLUMN batch_id VARCHAR(20)"))
                conn.commit()
                print("[MIGRATE] Added batch_id column to keys table")
        # Check/add otp_secret on admin table
        if "admin" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("admin")]
            if "otp_secret" not in cols:
                conn.execute(text("ALTER TABLE admin ADD COLUMN otp_secret VARCHAR(32)"))
                conn.commit()
                print("[MIGRATE] Added otp_secret column to admin table")

    # Seed admin + settings on first run
    db = SessionLocal()
    try:
        existing = db.query(Admin).first()
        if not existing:
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            admin = Admin(
                username=app_settings.ADMIN_USERNAME,
                password_hash=pwd_context.hash(app_settings.ADMIN_PASSWORD),
            )
            db.add(admin)
            db.commit()
            print(f"[INIT] Admin created — user: {app_settings.ADMIN_USERNAME}")

        from app.dependencies import set_setting
        # Seed settings if missing
        if not get_setting(db, "api_prefix"):
            set_setting(db, "api_prefix", app_settings.DEFAULT_API_PREFIX)
        if not get_setting(db, "heartbeat_threshold_minutes"):
            set_setting(db, "heartbeat_threshold_minutes", str(app_settings.DEFAULT_HEARTBEAT_THRESHOLD_MINUTES))
        if not get_setting(db, "otp_max_attempts"):
            set_setting(db, "otp_max_attempts", "5")
        if not get_setting(db, "otp_lockout_minutes"):
            set_setting(db, "otp_lockout_minutes", "2")
    finally:
        db.close()

    prefix = get_current_prefix()
    print(f"[INIT] Admin API prefix: {prefix}")
    yield


# ── Create app ────────────────────────────────────

app = FastAPI(
    title="卡密管理系统",
    version="2.0.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

# Serve static files
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── Dynamic prefix middleware ─────────────────────
# Admin API routes are registered internally at /__admin/
# This middleware:
#   1. Blocks direct access to /__admin/... from external (404)
#   2. Rewrites {configured_prefix}/... → /__admin/...
#   3. Passes through /api/client/... (fixed client auth) and web pages

FIXED_CLIENT_PATH = "/api/client"
FIXED_PREFIX_PATH = "/api/prefix"
INTERNAL_ADMIN = "/__admin"

@app.middleware("http")
async def dynamic_prefix_middleware(request: Request, call_next):
    path = request.url.path

    # Block direct access to internal admin paths (prevent bypass)
    if path.startswith(INTERNAL_ADMIN):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    # Never rewrite the fixed client auth path and prefix endpoint
    if path.startswith(FIXED_CLIENT_PATH) or path == FIXED_PREFIX_PATH:
        return await call_next(request)

    # Check if this matches the configured admin prefix
    prefix = get_current_prefix()

    if path.startswith(prefix + "/"):
        # Rewrite to internal /__admin/ path
        new_path = path.replace(prefix, "/__admin", 1)
        request.scope["path"] = new_path
        request.scope["raw_path"] = new_path.encode()

    response = await call_next(request)
    return response


# ── Client auth API (FIXED path: ALWAYS /api/client/auth) ─
# Use a sub-app so we can set custom exception handlers

client_app = FastAPI()

from app.routers.client import router as client_router
client_app.include_router(client_router)


@client_app.exception_handler(Exception)
async def client_error_handler(request: Request, exc: Exception):
    """Return errors in the format expected by existing clients."""
    from fastapi.responses import JSONResponse as JR
    status = 500
    detail = "服务器内部错误"
    if isinstance(exc, HTTPException):
        status = exc.status_code
        detail = exc.detail
    return JR(status_code=status, content={"status": "error", "message": str(detail)})

# Public prefix endpoint (inside the client sub-app)
@client_app.get("/prefix")
async def get_public_prefix():
    return {"api_prefix": get_current_prefix()}

app.mount("/api", client_app, name="client_api")


# ── Admin API routes (INTERNAL path: /__admin/...) ──────

from app.routers import auth, applications, keys, dashboard, settings_router

app.include_router(auth.router, prefix="/__admin")
app.include_router(applications.router, prefix="/__admin")
app.include_router(keys.router, prefix="/__admin")
app.include_router(dashboard.router, prefix="/__admin")
app.include_router(settings_router.router, prefix="/__admin")

# Recycle bin
from app.routers.recycle import router as recycle_router
app.include_router(recycle_router, prefix="/__admin")


# ── Web page routes ───────────────────────────────

from app.routers.pages import router as pages_router
app.include_router(pages_router)
