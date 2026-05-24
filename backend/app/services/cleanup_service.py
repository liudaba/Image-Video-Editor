import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session, engine
from ..models import (
    AuditLog,
    HeartbeatLog,
    Order,
    PaymentNotifyLog,
    OrderStatus,
)
from .license_service import cleanup_expired_license_keys
from ..config import settings

logger = logging.getLogger("videogen")

AUDIT_LOG_RETENTION_DAYS = settings.AUDIT_LOG_RETENTION_DAYS
PAYMENT_NOTIFY_RETENTION_DAYS = settings.PAYMENT_NOTIFY_RETENTION_DAYS
EXPIRED_ORDER_RETENTION_DAYS = settings.EXPIRED_ORDER_RETENTION_DAYS
HEARTBEAT_RETENTION_DAYS = settings.HEARTBEAT_RETENTION_DAYS
PENDING_ORDER_EXPIRE_HOURS = 2
CLEANUP_INTERVAL_HOURS = settings.CLEANUP_INTERVAL_HOURS
# 每批删除的最大行数，避免长事务锁表
BATCH_DELETE_SIZE = 5000


async def _batch_delete(db: AsyncSession, model, condition, batch_size: int = BATCH_DELETE_SIZE) -> int:
    """分批删除，避免单次删除过多行导致长事务锁表"""
    total = 0
    while True:
        # 使用子查询获取要删除的ID，再批量删除，兼容PostgreSQL
        subquery = select(model.id).where(condition).limit(batch_size)
        result = await db.execute(
            delete(model).where(model.id.in_(subquery))
        )
        deleted = result.rowcount
        total += deleted
        if deleted < batch_size:
            break
        await db.flush()
    return total


async def run_database_cleanup():
    async with async_session() as db:
        try:
            results = {}

            cutoff_audit = datetime.now(timezone.utc) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
            total = await _batch_delete(db, AuditLog, AuditLog.created_at < cutoff_audit)
            results["audit_logs"] = total

            cutoff_payment = datetime.now(timezone.utc) - timedelta(days=PAYMENT_NOTIFY_RETENTION_DAYS)
            total = await _batch_delete(db, PaymentNotifyLog, PaymentNotifyLog.created_at < cutoff_payment)
            results["payment_notify_logs"] = total

            cutoff_order = datetime.now(timezone.utc) - timedelta(days=EXPIRED_ORDER_RETENTION_DAYS)
            total = await _batch_delete(
                db, Order,
                (Order.status.in_([OrderStatus.EXPIRED, OrderStatus.CANCELLED]))
                & (Order.created_at < cutoff_order)
            )
            results["expired_orders"] = total

            cutoff_heartbeat = datetime.now(timezone.utc) - timedelta(days=HEARTBEAT_RETENTION_DAYS)
            total = await _batch_delete(db, HeartbeatLog, HeartbeatLog.created_at < cutoff_heartbeat)
            results["heartbeat_logs"] = total

            pending_cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_ORDER_EXPIRE_HOURS)
            result = await db.execute(
                Order.__table__.update()
                .where(Order.status == OrderStatus.PENDING)
                .where(Order.created_at < pending_cutoff)
                .values(status=OrderStatus.EXPIRED)
            )
            results["pending_orders_expired"] = result.rowcount

            expired_keys_count = await cleanup_expired_license_keys(db)
            results["expired_license_keys"] = expired_keys_count

            await db.commit()

            # 只对清理涉及的表执行VACUUM ANALYZE，避免全库锁表
            vacuum_tables = ["audit_logs", "payment_notify_logs", "orders", "heartbeat_logs", "license_keys"]
            try:
                async with engine.connect() as conn:
                    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                    for table in vacuum_tables:
                        try:
                            await conn.execute(text(f"VACUUM (ANALYZE) {table}"))
                        except Exception:
                            pass
            except Exception:
                pass

            logger.info(f"Database cleanup completed: {results}")
            return results

        except Exception as e:
            await db.rollback()
            logger.error(f"Database cleanup failed: {e}", exc_info=True)
            return {"error": str(e)}


async def cleanup_loop():
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
            await run_database_cleanup()
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled, exiting...")
            break
        except Exception as e:
            logger.error(f"Cleanup loop error: {e}", exc_info=True)
            await asyncio.sleep(300)
