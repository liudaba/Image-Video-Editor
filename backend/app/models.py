from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text, Numeric, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from .database import Base  # 使用相对导入
import enum


class LicenseType(str, enum.Enum):
    TRIAL = "trial"
    PRO = "pro"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PlanType(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"
    TRIAL_15D = "trial_15d"


class LicenseKeyStatus(str, enum.Enum):
    UNUSED = "unused"
    ACTIVATED = "activated"
    REVOKED = "revoked"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (UniqueConstraint("user_id", name="uq_license_user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    license_type = Column(Enum(LicenseType), default=LicenseType.TRIAL, nullable=False)
    license_key = Column(String(100), unique=True, nullable=True, index=True)
    is_valid = Column(Boolean, default=True, nullable=False)
    trial_start = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    machine_fingerprint = Column(String(255), nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    heartbeat_fingerprint = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    license_key = Column(String(100), unique=True, nullable=False, index=True)
    plan_type = Column(Enum(PlanType), nullable=False)
    status = Column(Enum(LicenseKeyStatus), default=LicenseKeyStatus.UNUSED, nullable=False)
    activated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_status", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)
    plan_type = Column(Enum(PlanType), nullable=False)
    payment_method = Column(String(20), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    transaction_id = Column(String(128), nullable=True)
    payment_url = Column(String(500), nullable=True)
    qr_code = Column(String(500), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PaymentNotifyLog(Base):
    __tablename__ = "payment_notify_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notify_id = Column(String(128), unique=True, nullable=False, index=True)
    order_no = Column(String(64), nullable=False, index=True)
    payment_method = Column(String(20), nullable=False)
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MachineBinding(Base):
    __tablename__ = "machine_bindings"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_machine_binding_user_fingerprint"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(255), nullable=False, index=True)
    machine_name = Column(String(255), nullable=True)
    bound_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class AppVersion(Base):
    __tablename__ = "app_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), nullable=False, unique=True)
    release_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    changelog = Column(Text, nullable=True)
    download_url = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=False)
    priority = Column(String(20), default="normal", nullable=False)
    force_update = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HeartbeatLog(Base):
    __tablename__ = "heartbeat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    app_version = Column(String(20), nullable=True)
    license_type = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, nullable=True)
    operator_name = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)