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

    # 先无锁查询，减少锁竞争
    q = select(MachineBinding).where(MachineBinding.user_id == user_id)
    result = await db.execute(q)
    bindings = result.scalars().all()

    # 检查是否已有此指纹的绑定
    for b in bindings:
        if b.fingerprint == fingerprint:
            # 需要更新last_seen，加锁后再更新
            lock_result = await db.execute(
                select(MachineBinding).where(MachineBinding.id == b.id).with_for_update()
            )
            locked_binding = lock_result.scalar_one_or_none()
            if locked_binding:
                locked_binding.last_seen = datetime.now(timezone.utc)
                await db.flush()
            return True

    if len(bindings) >= MAX_MACHINE_BINDINGS:
        return False

    # 需要添加新绑定，加锁防止并发添加超过限制
    lock_result = await db.execute(
        select(MachineBinding).where(MachineBinding.user_id == user_id).with_for_update()
    )
    locked_bindings = lock_result.scalars().all()

    # 双重检查：加锁后再次确认绑定数量
    if len(locked_bindings) >= MAX_MACHINE_BINDINGS:
        # 加锁期间可能已有同指纹绑定
        for b in locked_bindings:
            if b.fingerprint == fingerprint:
                b.last_seen = datetime.now(timezone.utc)
                await db.flush()
                return True
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
        # 使用子查询限制每次删除的行数，避免长时间锁表
        subq = select(HeartbeatLog.id).where(
            HeartbeatLog.created_at < cutoff
        ).limit(1000)
        await db.execute(
            delete(HeartbeatLog).where(HeartbeatLog.id.in_(subq))
        )
        await db.flush()
    except Exception:
        pass
