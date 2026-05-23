from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


def _version_tuple(version_str: str) -> tuple:
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _version_to_dict(v: AppVersion) -> dict:
    """将AppVersion模型转为API返回字典"""
    return {
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
        "update_type": v.update_type or "full",
        "patch_url": v.patch_url,
        "patch_hash": v.patch_hash,
        "patch_size": v.patch_size,
        "from_version": v.from_version,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.post("/", summary="创建或更新版本信息（仅管理员）")
async def create_version(
    version_info: VersionInfo,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(AppVersion).filter(AppVersion.version == version_info.version))
    existing_versions = result.scalars().all()

    # 同一版本号可能有多条记录（full + patch），查找匹配的记录
    existing_version = None
    for ev in existing_versions:
        if ev.update_type == (version_info.update_type or "full"):
            if version_info.update_type == "patch" and version_info.from_version:
                if ev.from_version == version_info.from_version:
                    existing_version = ev
                    break
            else:
                existing_version = ev
                break
    # 如果没有精确匹配，取第一条
    if existing_version is None and existing_versions:
        existing_version = existing_versions[0]

    if existing_version:
        existing_version.release_date = _parse_release_date(version_info.release_date)
        existing_version.changelog = "\n".join(version_info.changelog) if version_info.changelog else ""
        existing_version.download_url = version_info.download_url
        existing_version.file_hash = version_info.file_hash
        existing_version.file_size = version_info.file_size
        existing_version.priority = version_info.priority if version_info.priority is not None else "normal"
        existing_version.force_update = version_info.force_update if version_info.force_update is not None else False
        existing_version.is_active = version_info.is_active if version_info.is_active is not None else True
        existing_version.update_type = version_info.update_type if version_info.update_type else "full"
        existing_version.patch_url = version_info.patch_url
        existing_version.patch_hash = version_info.patch_hash
        existing_version.patch_size = version_info.patch_size
        existing_version.from_version = version_info.from_version
        await db.flush()
    else:
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
            update_type=version_info.update_type if version_info.update_type else "full",
            patch_url=version_info.patch_url,
            patch_hash=version_info.patch_hash,
            patch_size=version_info.patch_size,
            from_version=version_info.from_version,
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
    # 同一版本号可能有多条记录（full + 多个patch），需要精确匹配
    patch_info = None
    if current_version:
        # 1. 精确匹配：from_version == current_version
        for v in all_versions:
            if (v.version == latest_version.version
                    and v.update_type == "patch"
                    and v.from_version == current_version
                    and v.patch_url):
                patch_info = v
                break

        # 2. 如果没有精确匹配，查找任何可用的补丁（from_version 是当前版本的最近前序版本）
        # 注意：补丁只能从特定版本升级，from_version 必须 == current_version
        # 不应该用 <= 匹配，因为补丁是针对特定版本的差异文件
        # 如果没有精确匹配的补丁，则回退到全量更新

    # 构建返回信息
    # 优先使用最新版本号对应的全量包记录（确保download_url可用）
    full_info = None
    for v in all_versions:
        if v.version == latest_version.version and v.update_type == "full":
            full_info = v
            break
    # 如果没有full类型记录，使用latest_version本身
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
        # 找到匹配的补丁，返回补丁信息 + 全量包兜底
        base_info.update({
            "update_type": "patch",
            "patch_url": patch_info.patch_url,
            "patch_hash": patch_info.patch_hash,
            "patch_size": patch_info.patch_size,
            "from_version": patch_info.from_version,
        })
    else:
        # 无匹配补丁，返回全量更新（不返回patch_url，避免客户端误判）
        base_info.update({
            "update_type": "full",
            "patch_url": None,
            "patch_hash": None,
            "patch_size": None,
            "from_version": None,
        })

    return VersionInfo(**base_info)


@router.get("/", summary="获取所有版本信息（仅管理员）")
async def list_versions(
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(AppVersion))
    versions = list(result.scalars().all())

    versions.sort(key=lambda v: _version_tuple(v.version), reverse=True)

    return {
        "versions": [_version_to_dict(v) for v in versions]
    }
