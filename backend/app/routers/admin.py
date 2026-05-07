from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import (
    User, License, Order, AppVersion, HeartbeatLog, AuditLog,
    LicenseType, OrderStatus, LicenseKey, LicenseKeyStatus, PlanType,
)
from app.auth import get_current_user, require_admin
from app.services.license_service import generate_license_key

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


async def _log_audit(db: AsyncSession, admin: User, action: str, detail: str = None, request: Request = None):
    log = AuditLog(
        operator_id=admin.id,
        operator_name=admin.username,
        action=action,
        detail=detail,
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(log)
    await db.flush()


class VersionCreate(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    download_url: str = Field(..., pattern=r"^https?://")
    file_size: int = Field(..., gt=0)
    changelog: str = ""
    priority: str = "normal"
    force_update: bool = False


class LicenseKeyGenerate(BaseModel):
    plan_type: str = "yearly"
    count: int = 1


@router.get("/stats")
async def get_stats(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = await db.scalar(select(func.count(User.id)))
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(License.is_valid == True)
    )
    trial_users = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.TRIAL)
    )
    pro_users = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.PRO)
    )
    paid_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
    )
    total_revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == OrderStatus.PAID)
    )

    return {
        "total_users": total_users,
        "active_licenses": active_licenses,
        "trial_users": trial_users,
        "pro_users": pro_users,
        "paid_orders": paid_orders,
        "total_revenue": float(total_revenue),
    }


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()
    total = await db.scalar(select(func.count(User.id)))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@router.post("/generate_license_keys")
async def admin_generate_license_keys(
    body: LicenseKeyGenerate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    keys = []
    for _ in range(min(body.count, 50)):
        key_str = generate_license_key()
        license_key = LicenseKey(
            license_key=key_str,
            plan_type=PlanType(body.plan_type),
            status=LicenseKeyStatus.UNUSED,
        )
        db.add(license_key)
        keys.append(key_str)

    await db.flush()
    await _log_audit(db, user, "generate_license_keys", f"count={len(keys)}, plan={body.plan_type}", request)
    return {"keys": keys, "count": len(keys)}


@router.post("/users/{user_id}/toggle_active")
async def toggle_user_active(
    user_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    target.is_active = not target.is_active
    await db.flush()
    await _log_audit(db, user, "toggle_user_active", f"user_id={user_id}, is_active={target.is_active}", request)
    return {"success": True, "is_active": target.is_active}


@router.post("/versions")
async def create_version(
    body: VersionCreate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    new_version = AppVersion(
        version=body.version,
        download_url=body.download_url,
        file_size=body.file_size,
        changelog=body.changelog,
        priority=body.priority,
        force_update=body.force_update,
    )
    db.add(new_version)
    await db.flush()
    await _log_audit(db, user, "create_version", f"version={body.version}", request)
    return {"success": True, "version": body.version}
