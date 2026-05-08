from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db  # 修复导入路径
from ..models import AppVersion
from ..auth import require_admin, get_current_user
from ..schemas import VersionInfo

router = APIRouter(prefix="/version", tags=["version"])


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
        existing_version.release_date = version_info.release_date
        existing_version.changelog = "\n".join(version_info.changelog) if version_info.changelog else ""
        existing_version.download_url = version_info.download_url
        existing_version.file_hash = version_info.file_hash
        existing_version.file_size = version_info.file_size
        existing_version.priority = version_info.priority or "normal"
        existing_version.force_update = version_info.force_update or False
        existing_version.is_active = version_info.is_active or False
        await db.flush()
    else:
        # 创建新版本
        version = AppVersion(
            version=version_info.version,
            release_date=version_info.release_date,
            changelog="\n".join(version_info.changelog) if version_info.changelog else "",
            download_url=version_info.download_url,
            file_hash=version_info.file_hash,
            file_size=version_info.file_size,
            priority=version_info.priority or "normal",
            force_update=version_info.force_update or False,
            is_active=version_info.is_active or False,
        )
        db.add(version)
    
    await db.commit()
    
    return {"message": "版本信息已保存"}


@router.get("/latest", response_model=VersionInfo, summary="获取最新版本信息")
async def get_latest_version(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)  # 可选依赖，允许未登录用户获取版本信息
):
    from sqlalchemy import select
    
    result = await db.execute(
        select(AppVersion)
        .filter(AppVersion.is_active == True)
        .order_by(AppVersion.release_date.desc())
    )
    latest_version = result.scalar_one_or_none()
    
    if not latest_version:
        return VersionInfo(has_update=False)
    
    # 检查是否有更新
    has_update = False  # 在实际实现中，这里应该比较客户端版本与服务器版本
    
    return VersionInfo(
        has_update=has_update,
        version=latest_version.version,
        release_date=latest_version.release_date,
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
    
    result = await db.execute(
        select(AppVersion)
        .order_by(AppVersion.release_date.desc())
    )
    versions = result.scalars().all()

    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "release_date": v.release_date,
                "changelog": v.changelog.split('\n') if v.changelog else [],
                "download_url": v.download_url,
                "file_size": v.file_size,
                "file_hash": v.file_hash,
                "priority": v.priority,
                "force_update": v.force_update,
                "is_active": v.is_active,
                "created_at": v.created_at
            }
            for v in versions
        ]
    }