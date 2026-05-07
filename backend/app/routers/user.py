from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models import User, License, MachineBinding, HeartbeatLog, AuditLog
from app.schemas import LicenseStatusResponse, HeartbeatRequest, HeartbeatResponse
from app.auth import get_current_user
from app.services.license_service import build_license_response, is_license_expired
from app.services.heartbeat_service import record_heartbeat, validate_heartbeat, check_and_bind_machine

router = APIRouter(prefix="/api/user", tags=["用户"])


async def _log_audit(db: AsyncSession, user: User, action: str, detail: str = None, request: Request = None):
    log = AuditLog(
        operator_id=user.id,
        operator_name=user.username,
        action=action,
        target_type="user",
        target_id=user.id,
        detail=detail,
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(log)
    await db.flush()


@router.get("/license_status", response_model=LicenseStatusResponse)
async def get_license_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(License).where(License.user_id == user.id))
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到授权记录")

    if is_license_expired(license_obj):
        license_obj.is_valid = False
        await db.flush()
        await db.refresh(license_obj)

    license_data = build_license_response(license_obj, user.username)
    return LicenseStatusResponse(license=license_data)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    body: HeartbeatRequest,
    user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    license_data = await validate_heartbeat(db, user.id, body.fingerprint)

    ip_address = request.client.host if request and request.client else None

    await record_heartbeat(
        db,
        user_id=user.id,
        fingerprint=body.fingerprint,
        ip_address=ip_address,
        app_version=body.app_version,
        license_type=license_data.license_type if license_data else None,
    )

    if license_data is None:
        return {"is_valid": False, "reason": "授权无效或已过期", "timestamp": datetime.now(timezone.utc).timestamp()}

    return {"is_valid": True, "license": license_data, "timestamp": datetime.now(timezone.utc).timestamp()}


@router.post("/bind_machine")
async def bind_machine(
    body: HeartbeatRequest,
    user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    if not body.fingerprint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="机器指纹不能为空")

    can_bind = await check_and_bind_machine(db, user.id, body.fingerprint)
    if not can_bind:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="已达到最大设备绑定数量(3台)，请在设置中解绑旧设备",
        )

    await _log_audit(db, user, "bind_machine", f"fingerprint={body.fingerprint[:16]}...", request)
    return {"success": True, "message": "设备绑定成功"}


@router.post("/unbind_machine")
async def unbind_machine(
    body: HeartbeatRequest,
    user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    if not body.fingerprint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="机器指纹不能为空")

    result = await db.execute(
        delete(MachineBinding).where(
            MachineBinding.user_id == user.id,
            MachineBinding.fingerprint == body.fingerprint,
        )
    )
    await db.flush()

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该设备绑定记录")

    await _log_audit(db, user, "unbind_machine", f"fingerprint={body.fingerprint[:16]}...", request)
    return {"success": True, "message": "设备解绑成功"}


@router.get("/machines")
async def list_machines(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MachineBinding).where(MachineBinding.user_id == user.id)
    )
    machines = result.scalars().all()
    return {
        "max_devices": 3,
        "devices": [
            {
                "fingerprint": m.fingerprint[:16] + "...",
                "machine_name": m.machine_name,
                "bound_at": m.bound_at.isoformat() if m.bound_at else None,
                "last_seen": m.last_seen.isoformat() if m.last_seen else None,
            }
            for m in machines
        ],
    }
