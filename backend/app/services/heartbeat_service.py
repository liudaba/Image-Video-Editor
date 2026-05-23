from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..models import MachineBinding, HeartbeatLog

MAX_MACHINE_BINDINGS = 3


async def check_and_bind_machine(
    db: AsyncSession,
    user_id: int,
    fingerprint: Optional[str],
) -> bool:
    if not fingerprint:
        return True

    q = select(MachineBinding).where(MachineBinding.user_id == user_id).with_for_update()
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
