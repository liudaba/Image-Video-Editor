from packaging.version import Version
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AppVersion
from app.schemas import VersionInfo

router = APIRouter(prefix="/api/version", tags=["版本"])


@router.get("/latest", response_model=VersionInfo)
async def check_update(
    current_version: str = Query(..., description="当前版本号"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AppVersion)
        .where(AppVersion.is_active == True)
        .order_by(AppVersion.id.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if not latest:
        return VersionInfo(has_update=False)

    try:
        has_update = Version(latest.version) > Version(current_version)
    except Exception:
        has_update = latest.version != current_version

    if not has_update:
        return VersionInfo(has_update=False)

    changelog = []
    if latest.changelog:
        changelog = [line.strip() for line in latest.changelog.split("\n") if line.strip()]

    return VersionInfo(
        has_update=True,
        version=latest.version,
        release_date=latest.release_date.isoformat() if latest.release_date else None,
        changelog=changelog,
        file_size=latest.file_size,
        file_hash=latest.file_hash,
        download_url=latest.download_url,
        priority=latest.priority,
        force_update=latest.force_update,
    )
