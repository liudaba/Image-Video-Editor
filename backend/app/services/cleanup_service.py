import asyncio
import logging
import subprocess
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models import (
    AuditLog,
    HeartbeatLog,
    Order,
    PaymentNotifyLog,
    OrderStatus,
)
from .license_service import cleanup_expired_license_keys

logger = logging.getLogger("videogen")

AUDIT_LOG_RETENTION_DAYS = 90
PAYMENT_NOTIFY_RETENTION_DAYS = 90
EXPIRED_ORDER_RETENTION_DAYS = 30
HEARTBEAT_RETENTION_DAYS = 30
CLEANUP_INTERVAL_HOURS = 6


def _run_docker_command(cmd: list[str]) -> dict:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        output = result.stdout.strip()
        return {"success": True, "output": output, "returncode": result.returncode}
    except FileNotFoundError:
        return {"success": False, "output": "Docker CLI not found", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "output": str(e), "returncode": -1}


async def run_docker_cleanup() -> dict:
    results = {}

    container_result = _run_docker_command(["docker", "container", "prune", "-f"])
    if container_result["success"]:
        lines = container_result["output"]
        deleted = 0
        for line in lines.split("\n"):
            if "Deleted" in line or "Total" in line:
                try:
                    import re
                    nums = re.findall(r'\d+', line)
                    if nums:
                        deleted = int(nums[-1])
                except Exception:
                    pass
        results["containers"] = {"cleaned": True, "detail": lines, "deleted_count": deleted}
    else:
        results["containers"] = {"cleaned": False, "detail": container_result["output"]}

    image_result = _run_docker_command(["docker", "image", "prune", "-a", "-f"])
    if image_result["success"]:
        lines = image_result["output"]
        reclaimed = "0B"
        for line in lines.split("\n"):
            if "reclaimed" in line.lower() or "Total" in line:
                reclaimed = line
        results["images"] = {"cleaned": True, "detail": lines, "reclaimed": reclaimed}
    else:
        results["images"] = {"cleaned": False, "detail": image_result["output"]}

    volume_result = _run_docker_command(["docker", "volume", "prune", "-f"])
    if volume_result["success"]:
        lines = volume_result["output"]
        results["volumes"] = {"cleaned": True, "detail": lines}
    else:
        results["volumes"] = {"cleaned": False, "detail": volume_result["output"]}

    builder_result = _run_docker_command(["docker", "builder", "prune", "-a", "-f"])
    if builder_result["success"]:
        lines = builder_result["output"]
        results["build_cache"] = {"cleaned": True, "detail": lines}
    else:
        results["build_cache"] = {"cleaned": False, "detail": builder_result["output"]}

    disk_result = _run_docker_command(["docker", "system", "df"])
    if disk_result["success"]:
        results["disk_usage"] = disk_result["output"]
    else:
        results["disk_usage"] = "Unable to get disk usage"

    logger.info(f"Docker cleanup completed: {results}")
    return results


async def run_database_cleanup():
    async with async_session() as db:
        try:
            results = {}

            cutoff_audit = datetime.now(timezone.utc) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
            result = await db.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff_audit)
            )
            results["audit_logs"] = result.rowcount

            cutoff_payment = datetime.now(timezone.utc) - timedelta(days=PAYMENT_NOTIFY_RETENTION_DAYS)
            result = await db.execute(
                delete(PaymentNotifyLog).where(PaymentNotifyLog.created_at < cutoff_payment)
            )
            results["payment_notify_logs"] = result.rowcount

            cutoff_order = datetime.now(timezone.utc) - timedelta(days=EXPIRED_ORDER_RETENTION_DAYS)
            result = await db.execute(
                delete(Order).where(
                    Order.status.in_([OrderStatus.EXPIRED, OrderStatus.CANCELLED]),
                    Order.created_at < cutoff_order,
                )
            )
            results["expired_orders"] = result.rowcount

            cutoff_heartbeat = datetime.now(timezone.utc) - timedelta(days=HEARTBEAT_RETENTION_DAYS)
            result = await db.execute(
                delete(HeartbeatLog).where(HeartbeatLog.created_at < cutoff_heartbeat)
            )
            results["heartbeat_logs"] = result.rowcount

            expired_keys_count = await cleanup_expired_license_keys(db)
            results["expired_license_keys"] = expired_keys_count

            await db.commit()

            try:
                await db.execute(text("VACUUM (ANALYZE)"))
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
