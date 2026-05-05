from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import License, MachineBinding, HeartbeatLog, LicenseType, User
from app.services.license_service import is_license_expired, build_license_response
from app.schemas import LicenseData


MAX_MACHINE_BINDINGS = 3


async def check_and_bind_machine(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
) -> bool:
    if not fingerprint:
        return True

    result = await db.execute(
        select(MachineBinding)
        .where(MachineBinding.user_id == user_id)
        .with_for_update()
    )
    bindings = result.scalars().all()

    for b in bindings:
        if b.fingerprint == fingerprint:
            b.last_seen = datetime.now(timezone.utc)
            await db.flush()
            return True

    if len(bindings) >= MAX_MACHINE_BINDINGS:
        return False

    new_binding = MachineBinding(
        user_id=user_id,
        fingerprint=fingerprint,
    )
    db.add(new_binding)
    await db.flush()
    return True


async def record_heartbeat(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
    ip_address: Optional[str],
    app_version: Optional[str],
    license_type: Optional[str],
) -> None:
    log = HeartbeatLog(
        user_id=user_id,
        fingerprint=fingerprint,
        ip_address=ip_address,
        app_version=app_version,
        license_type=license_type,
    )
    db.add(log)
    await db.flush()


async def validate_heartbeat(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
) -> Optional[LicenseData]:
    result = await db.execute(
        select(License).where(License.user_id == user_id).with_for_update()
    )
    license_obj = result.scalar_one_or_none()

    if license_obj is None:
        return None

    if is_license_expired(license_obj):
        license_obj.is_valid = False
        await db.flush()
        return None

    if fingerprint:
        can_bind = await check_and_bind_machine(db, user_id, fingerprint)
        if not can_bind:
            return None

    license_obj.last_heartbeat = datetime.now(timezone.utc)
    license_obj.heartbeat_fingerprint = fingerprint
    await db.flush()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    username = user.username if user else "unknown"

    return build_license_response(license_obj, username)
