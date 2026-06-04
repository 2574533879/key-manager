import datetime
import uuid
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12].upper()


def now() -> datetime.datetime:
    return datetime.datetime.now()


class Admin(Base):
    __tablename__ = "admin"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    otp_secret = Column(String(32), nullable=True)  # TOTP secret, None = not enabled


class Setting(Base):
    """Key-value store for dynamic configuration."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    app_code = Column(String(32), unique=True, nullable=False, default=gen_uuid)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    keys = relationship("Key", back_populates="application", cascade="all, delete-orphan")


class Key(Base):
    __tablename__ = "keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_code = Column(String(64), unique=True, nullable=False, index=True)
    batch_id = Column(String(20), nullable=True, index=True)  # generation batch
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    key_type = Column(String(32), nullable=False)  # day/week/month/quarter/year/permanent/custom
    device_limit = Column(Integer, default=1)
    status = Column(String(16), default="active")  # "active", "used", "expired", "disabled"
    start_time = Column(DateTime, nullable=True)  # set on first use
    expire_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)

    application = relationship("Application", back_populates="keys")
    device_bindings = relationship("DeviceBinding", back_populates="key", cascade="all, delete-orphan")


class DeviceBinding(Base):
    __tablename__ = "device_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_id = Column(Integer, ForeignKey("keys.id", ondelete="CASCADE"), nullable=False)
    machine_code = Column(String(64), nullable=False)
    ip_address = Column(String(45), default="")
    first_seen = Column(DateTime, default=now)
    last_heartbeat = Column(DateTime, default=now, onupdate=now)

    key = relationship("Key", back_populates="device_bindings")


class KeyRecycleBin(Base):
    """Soft-deleted keys, grouped by batch."""
    __tablename__ = "key_recycle_bin"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(32), nullable=False, index=True)
    original_key_id = Column(Integer, nullable=False)
    key_data = Column(Text, nullable=False)          # JSON: key fields
    devices_data = Column(Text, default="[]")         # JSON: device binding fields
    deleted_at = Column(DateTime, default=now)
