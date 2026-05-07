from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models import License, MachineBinding, HeartbeatLog, LicenseType, User
from app.services.license_service import is_license_expired, build_license_response
from app.schemas import LicenseData
from app.database import engine

MAX_MACHINE_BINDINGS = 3


def _supports_for_update():
    return not str(engine.url).startswith("sqlite")


async def check_and_bind_machine(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
) -> bool:
    if not fingerprint:
        return True

    q = select(MachineBinding).where(MachineBinding.user_id == user_id)
    if _supports_for_update():
        q = q.with_for_update()
    result = await db.execute(q)
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

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        await db.execute(
            delete(HeartbeatLog).where(HeartbeatLog.created_at < cutoff)
        )
        await db.flush()
    except Exception:
        pass


async def validate_heartbeat(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
) -> Optional[LicenseData]:
    q = select(License).where(License.user_id == user_id)
    if _supports_for_update():
        q = q.with_for_update()
    result = await db.execute(q)
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
