from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..database import get_db  # 修复导入路径
from ..models import User, License, AuditLog
from ..auth import require_admin, get_current_user
from ..schemas import UserRegister

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/", summary="获取用户列表（仅管理员）")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    
    result = await db.execute(
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            for user in users
        ]
    }


@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at
    }


@router.put("/{user_id}", summary="更新用户信息（仅管理员）")
async def update_user(
    user_id: int,
    username: str = None,
    email: str = None,
    is_active: bool = None,
    is_admin: bool = None,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新字段
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    
    await db.flush()
    await db.commit()
    
    # 记录审计日志
    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="update_user",
        target_type="user",
        target_id=user.id,
        detail=f"Updated user {user.username}",
        ip_address=None  # 从request获取IP
    )
    db.add(audit_log)
    await db.commit()
    
    return {"message": "用户更新成功"}


@router.delete("/{user_id}", summary="删除用户（仅管理员）")
async def delete_user(
    user_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, delete
    
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    
    # 记录审计日志
    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="delete_user",
        target_type="user",
        target_id=user_id,
        detail=f"Deleted user {user.username}",
        ip_address=None  # 从request获取IP
    )
    db.add(audit_log)
    await db.commit()
    
    return {"message": "用户删除成功"}


@router.post("/reset-password/{user_id}", summary="重置用户密码（仅管理员）")
async def reset_user_password(
    user_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    from ..auth import hash_password
    import secrets
    import string
    
    # 生成随机密码
    alphabet = string.ascii_letters + string.digits
    random_password = ''.join(secrets.choice(alphabet) for _ in range(12))
    
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.hashed_password = hash_password(random_password)
    await db.flush()
    await db.commit()
    
    # 记录审计日志
    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="reset_password",
        target_type="user",
        target_id=user_id,
        detail=f"Reset password for user {user.username}",
        ip_address=None  # 从request获取IP
    )
    db.add(audit_log)
    await db.commit()
    
    return {"message": "密码重置成功", "new_password": random_password}