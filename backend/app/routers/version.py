from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from ..database import get_db
from ..models import AppVersion
from ..auth import require_admin, get_current_user_optional
from ..schemas import VersionInfo

router = APIRouter(prefix="/api/version", tags=["version"])


def _parse_release_date(release_date_str):
    """将release_date字符串解析为datetime对象，None则返回当前UTC时间"""
    if release_date_str is None:
        return datetime.now(timezone.utc)
    if isinstance(release_date_str, datetime):
        if release_date_str.tzinfo is None:
            return release_date_str.replace(tzinfo=timezone.utc)
        return release_date_str
    try:
        from dateutil.parser import isoparse
        dt = isoparse(release_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            dt = datetime.fromisoformat(release_date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)


@router.post("/", summary="创建或更新版本信息（仅管理员）")
async def create_version(
    version_info: VersionInfo,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    
    # 检查版本是否已存在
    result = await db.execute(select(AppVersion).filter(AppVersion.version == version_info.version))
    existing_version = result.scalar_one_or_none()
    
    if existing_version:
        # 更新现有版本
        existing_version.release_date = _parse_release_date(version_info.release_date)
        existing_version.changelog = "\n".join(version_info.changelog) if version_info.changelog else ""
        existing_version.download_url = version_info.download_url
        existing_version.file_hash = version_info.file_hash
        existing_version.file_size = version_info.file_size
        existing_version.priority = version_info.priority if version_info.priority is not None else "normal"
        existing_version.force_update = version_info.force_update if version_info.force_update is not None else False
        existing_version.is_active = version_info.is_active if version_info.is_active is not None else True
        await db.flush()
    else:
        # 创建新版本
        version = AppVersion(
            version=version_info.version,
            release_date=_parse_release_date(version_info.release_date),
            changelog="\n".join(version_info.changelog) if version_info.changelog else "",
            download_url=version_info.download_url,
            file_hash=version_info.file_hash,
            file_size=version_info.file_size,
            priority=version_info.priority if version_info.priority is not None else "normal",
            force_update=version_info.force_update if version_info.force_update is not None else False,
            is_active=version_info.is_active if version_info.is_active is not None else True,
        )
        db.add(version)
    
    await db.commit()
    
    return {"message": "版本信息已保存"}


@router.get("/latest", response_model=VersionInfo, summary="获取最新版本信息")
async def get_latest_version(
    current_version: str = Query(None, max_length=20),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional)
):
    from sqlalchemy import select

    result = await db.execute(
        select(AppVersion).filter(AppVersion.is_active == True)
    )
    all_versions = result.scalars().all()

    if not all_versions:
        return VersionInfo(has_update=False)

    def _version_key(v):
        try:
            return tuple(int(x) for x in v.version.split("."))
        except (ValueError, AttributeError):
            return (0, 0, 0)

    latest_version = max(all_versions, key=_version_key)

    has_update = False
    if current_version:
        try:
            client_parts = tuple(int(x) for x in current_version.split("."))
            server_parts = tuple(int(x) for x in latest_version.version.split("."))
            has_update = server_parts > client_parts
        except (ValueError, AttributeError):
            has_update = True

    return VersionInfo(
        has_update=has_update,
        version=latest_version.version,
        release_date=latest_version.release_date.isoformat() if latest_version.release_date else None,
        changelog=latest_version.changelog.split('\n') if latest_version.changelog else [],
        download_url=latest_version.download_url,
        file_size=latest_version.file_size,
        file_hash=latest_version.file_hash,
        priority=latest_version.priority,
        force_update=latest_version.force_update
    )


@router.get("/", summary="获取所有版本信息（仅管理员）")
async def list_versions(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    
    result = await db.execute(select(AppVersion))
    versions = list(result.scalars().all())

    def _version_key(v):
        try:
            return tuple(int(x) for x in v.version.split("."))
        except (ValueError, AttributeError):
            return (0, 0, 0)

    versions.sort(key=_version_key, reverse=True)

    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "release_date": v.release_date.isoformat() if v.release_date else None,
                "changelog": v.changelog.split('\n') if v.changelog else [],
                "download_url": v.download_url,
                "file_size": v.file_size,
                "file_hash": v.file_hash,
                "priority": v.priority,
                "force_update": v.force_update,
                "is_active": v.is_active,
                "created_at": v.created_at.isoformat() if v.created_at else None
            }
            for v in versions
        ]
    }