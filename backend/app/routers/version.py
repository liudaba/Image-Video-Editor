from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from ..database import get_db
from ..models import AppVersion
from ..auth import get_current_user_optional
from ..schemas import VersionInfo

router = APIRouter(prefix="/api/version", tags=["version"])


def _version_tuple(version_str: str) -> tuple:
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


@router.get("/latest", response_model=VersionInfo, summary="获取最新版本信息")
async def get_latest_version(
    current_version: str = Query(None, max_length=20),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional)
):
    result = await db.execute(
        select(AppVersion).filter(AppVersion.is_active == True)
    )
    all_versions = result.scalars().all()

    if not all_versions:
        return VersionInfo(has_update=False)

    latest_version = max(all_versions, key=lambda v: _version_tuple(v.version))

    has_update = False
    if current_version:
        client_parts = _version_tuple(current_version)
        server_parts = _version_tuple(latest_version.version)
        has_update = server_parts > client_parts

    if not has_update:
        return VersionInfo(has_update=False)

    # 智能匹配：优先查找适用于当前版本的增量补丁
    patch_info = None
    if current_version:
        for v in all_versions:
            if (v.version == latest_version.version
                    and v.update_type == "patch"
                    and v.from_version == current_version
                    and v.patch_url):
                patch_info = v
                break

    # 构建返回信息：优先使用最新版本号对应的全量包记录
    full_info = None
    for v in all_versions:
        if v.version == latest_version.version and v.update_type == "full":
            full_info = v
            break
    base_record = full_info or latest_version

    base_info = {
        "has_update": True,
        "version": latest_version.version,
        "release_date": base_record.release_date.isoformat() if base_record.release_date else None,
        "changelog": base_record.changelog.split('\n') if base_record.changelog else [],
        "download_url": base_record.download_url,
        "file_size": base_record.file_size,
        "file_hash": base_record.file_hash,
        "priority": base_record.priority,
        "force_update": base_record.force_update,
    }

    if patch_info:
        base_info.update({
            "update_type": "patch",
            "patch_url": patch_info.patch_url,
            "patch_hash": patch_info.patch_hash,
            "patch_size": patch_info.patch_size,
            "from_version": patch_info.from_version,
        })
    else:
        base_info.update({
            "update_type": "full",
            "patch_url": None,
            "patch_hash": None,
            "patch_size": None,
            "from_version": None,
        })

    return VersionInfo(**base_info)
