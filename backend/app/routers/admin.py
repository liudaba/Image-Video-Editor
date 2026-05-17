from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_

from ..database import get_db
from ..models import (
    User, License, Order, AppVersion, HeartbeatLog, AuditLog,
    LicenseType, OrderStatus, LicenseKey, LicenseKeyStatus, PlanType,
    validate_order_status_transition,
)
from ..auth import get_current_user, require_admin, hash_password
from ..services.license_service import generate_license_key

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


async def _log_audit(db: AsyncSession, admin: User, action: str, detail: str = None, request: Request = None):
    log = AuditLog(
        operator_id=admin.id,
        operator_name=admin.username,
        action=action,
        detail=detail,
        ip_address=request.client.host if request and request.client else None,
    )
    db.add(log)
    await db.flush()


class VersionCreate(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    download_url: str = Field(..., pattern=r"^https?://")
    file_size: int = Field(..., gt=0)
    file_hash: Optional[str] = None
    changelog: str = ""
    priority: str = "normal"
    force_update: bool = False


class LicenseKeyGenerate(BaseModel):
    plan_type: str = Field("yearly", pattern=r"^(monthly|quarterly|yearly|lifetime)$")
    count: int = Field(1, ge=1, le=50)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    is_admin: bool = False
    plan_type: Optional[str] = None


@router.get("/stats")
async def get_stats(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = await db.scalar(select(func.count(User.id)))
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(License.is_valid == True)
    )
    trial_users = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.TRIAL)
    )
    pro_users = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.PRO)
    )
    paid_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
    )
    total_revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == OrderStatus.PAID)
    )

    return {
        "total_users": total_users,
        "active_licenses": active_licenses,
        "trial_users": trial_users,
        "pro_users": pro_users,
        "paid_orders": paid_orders,
        "total_revenue": float(total_revenue),
    }


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    status: str = None,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    query = select(User).order_by(User.created_at.desc())
    count_query = select(func.count(User.id))

    if search:
        search_filter = or_(
            User.username.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if status == "active":
        query = query.where(User.is_active == True)
        count_query = count_query.where(User.is_active == True)
    elif status == "inactive":
        query = query.where(User.is_active == False)
        count_query = count_query.where(User.is_active == False)

    total = await db.scalar(count_query)
    result = await db.execute(query.offset(offset).limit(page_size))
    users = result.scalars().all()

    user_list = []
    for u in users:
        lic_result = await db.execute(select(License).where(License.user_id == u.id))
        lic = lic_result.scalar_one_or_none()
        user_info = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "license_type": lic.license_type.value if lic else None,
            "license_is_valid": lic.is_valid if lic else None,
            "last_heartbeat": lic.last_heartbeat.isoformat() if lic and lic.last_heartbeat else None,
            "expiry_date": lic.expiry_date.isoformat() if lic and lic.expiry_date else None,
        }
        user_list.append(user_info)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": user_list,
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取单个用户信息"""
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    lic_result = await db.execute(select(License).where(License.user_id == user_id))
    lic = lic_result.scalar_one_or_none()

    current_plan = "trial_15d"
    if lic:
        if lic.license_type == LicenseType.PRO:
            if lic.expiry_date is None:
                current_plan = "lifetime"
            elif lic.expiry_date:
                from datetime import timedelta
                cur = lic.expiry_date
                if cur.tzinfo is None:
                    cur = cur.replace(tzinfo=timezone.utc)
                remaining = (cur - datetime.now(timezone.utc)).days
                if remaining <= 30:
                    current_plan = "monthly"
                elif remaining <= 90:
                    current_plan = "quarterly"
                else:
                    current_plan = "yearly"

    return {
        "id": target_user.id,
        "username": target_user.username,
        "email": target_user.email,
        "is_active": target_user.is_active,
        "is_admin": target_user.is_admin,
        "created_at": target_user.created_at.isoformat() if target_user.created_at else None,
        "license_type": lic.license_type.value if lic else None,
        "license_is_valid": lic.is_valid if lic else None,
        "expiry_date": lic.expiry_date.isoformat() if lic and lic.expiry_date else None,
        "current_plan": current_plan,
    }


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    plan_type: Optional[str] = None
    expiry_date: Optional[str] = None


class VersionUpdate(BaseModel):
    version: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    changelog: Optional[str] = None
    priority: Optional[str] = None
    force_update: Optional[bool] = None
    is_active: Optional[bool] = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if body.username is not None:
        target_user.username = body.username
    if body.email is not None:
        target_user.email = body.email
    if body.password is not None:
        target_user.hashed_password = hash_password(body.password)
    if body.is_active is not None and body.is_active is False and target_user.id == user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    if body.is_active is not None:
        target_user.is_active = body.is_active
        license_result = await db.execute(select(License).where(License.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if user_license:
            user_license.is_valid = body.is_active
            await db.flush()
    if body.is_admin is not None:
        target_user.is_admin = body.is_admin

    if body.plan_type is not None:
        from datetime import timedelta
        plan_deltas = {
            "trial_15d": (LicenseType.TRIAL, timedelta(days=15)),
            "monthly": (LicenseType.PRO, timedelta(days=30)),
            "quarterly": (LicenseType.PRO, timedelta(days=90)),
            "yearly": (LicenseType.PRO, timedelta(days=365)),
            "lifetime": (LicenseType.PRO, None),
        }
        if body.plan_type not in plan_deltas:
            raise HTTPException(status_code=400, detail=f"无效的套餐类型: {body.plan_type}")
        lic_type, delta = plan_deltas[body.plan_type]
        license_result = await db.execute(select(License).where(License.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if not user_license:
            user_license = License(
                user_id=user_id,
                license_type=lic_type,
                is_valid=True,
                expiry_date=None if delta is None else datetime.now(timezone.utc) + delta,
            )
            db.add(user_license)
        else:
            user_license.license_type = lic_type
            user_license.is_valid = True
            if delta is None:
                user_license.expiry_date = None
            else:
                now = datetime.now(timezone.utc)
                remaining = timedelta(0)
                if user_license.expiry_date:
                    cur = user_license.expiry_date
                    if cur.tzinfo is None:
                        cur = cur.replace(tzinfo=timezone.utc)
                    remaining = max(cur - now, timedelta(0))
                user_license.expiry_date = now + remaining + delta
            if lic_type.value == "trial":
                user_license.trial_start = datetime.now(timezone.utc)
                user_license.trial_end = user_license.expiry_date
            else:
                user_license.trial_start = None
                user_license.trial_end = None
        await db.flush()

    if body.expiry_date is not None:
        license_result = await db.execute(select(License).where(License.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if not user_license:
            user_license = License(
                user_id=user_id,
                license_type=LicenseType.PRO,
                is_valid=True,
            )
            db.add(user_license)
            await db.flush()
        if body.expiry_date == "never":
            user_license.expiry_date = None
        else:
            try:
                parsed = datetime.fromisoformat(body.expiry_date.replace("Z", "+00:00"))
                user_license.expiry_date = parsed
            except (ValueError, AttributeError):
                raise HTTPException(status_code=400, detail="无效的到期时间格式")
        await db.flush()

    await db.flush()

    await _log_audit(
        db, user, "update_user",
        f"user_id={user_id}, username={body.username}, is_active={body.is_active}, is_admin={body.is_admin}, plan_type={body.plan_type}, expiry_date={body.expiry_date}",
        request
    )
    
    await db.commit()
    return {"success": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账户")
    
    await db.delete(target)
    await db.flush()
    await _log_audit(db, user, "delete_user", f"user_id={user_id}", request)
    await db.commit()
    return {"success": True}


@router.get("/orders")
async def list_orders(
    recent: int = None,
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    
    query = select(Order).order_by(desc(Order.created_at))
    count_query = select(func.count(Order.id))

    if status:
        try:
            order_status = OrderStatus(status)
            query = query.where(Order.status == order_status)
            count_query = count_query.where(Order.status == order_status)
        except ValueError:
            pass

    if recent:
        query = query.limit(recent)
        result = await db.execute(query)
        orders = result.scalars().all()
        total = len(orders)
    else:
        total = await db.scalar(count_query)
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        orders = result.scalars().all()

    # 获取状态对应的中文描述
    status_map = {
        OrderStatus.PENDING: "待支付",
        OrderStatus.PAID: "已支付",
        OrderStatus.EXPIRED: "已过期",
        OrderStatus.REFUNDED: "已退款",
        OrderStatus.CANCELLED: "已取消"
    }
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "orders": [
            {
                "id": o.id,
                "order_no": o.order_no,
                "user_id": o.user_id,
                "plan_type": o.plan_type.value,
                "payment_method": o.payment_method,
                "amount": float(o.amount),
                "status": o.status.value,
                "status_text": status_map.get(o.status, o.status.value),
                "transaction_id": o.transaction_id,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
    }


@router.post("/orders/{order_id}/confirm-payment")
async def confirm_payment(
    order_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="只能确认待支付的订单")

    if not validate_order_status_transition(order.status, OrderStatus.PAID):
        raise HTTPException(status_code=400, detail="订单状态异常")

    order.status = OrderStatus.PAID
    order.transaction_id = f"MANUAL-{order.order_no}"
    order.paid_at = datetime.now(timezone.utc)
    await db.flush()

    license_result = await db.execute(
        select(License).where(License.user_id == order.user_id)
    )
    existing_license = license_result.scalar_one_or_none()
    if existing_license:
        existing_license.license_type = "pro"
        existing_license.is_valid = True
        from datetime import timedelta
        plan_deltas = {
            PlanType.MONTHLY: timedelta(days=30),
            PlanType.QUARTERLY: timedelta(days=90),
            PlanType.YEARLY: timedelta(days=365),
        }
        if order.plan_type == PlanType.LIFETIME:
            existing_license.expiry_date = None
        elif order.plan_type in plan_deltas:
            now = datetime.now(timezone.utc)
            remaining = timedelta(0)
            if existing_license.expiry_date:
                cur = existing_license.expiry_date
                if cur.tzinfo is None:
                    cur = cur.replace(tzinfo=timezone.utc)
                remaining = max(cur - now, timedelta(0))
            existing_license.expiry_date = now + remaining + plan_deltas[order.plan_type]
        await db.flush()

    await _log_audit(db, user, "confirm_payment", f"order_id={order_id}, order_no={order.order_no}, amount={order.amount}, plan={order.plan_type.value}", request)
    await db.commit()
    return {"success": True, "message": "订单已手动确认支付"}


@router.post("/orders/{order_id}/refund")
async def refund_order(
    order_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="只能退款已支付的订单")
    order.status = OrderStatus.REFUNDED
    await db.flush()

    license_result = await db.execute(
        select(License).where(License.user_id == order.user_id)
    )
    user_license = license_result.scalar_one_or_none()
    if user_license and user_license.license_key == order.order_no:
        user_license.is_valid = False
        user_license.license_type = LicenseType.TRIAL
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc)
        user_license.expiry_date = now + _td(days=7)
        user_license.trial_start = now
        user_license.trial_end = user_license.expiry_date
        await db.flush()
    elif user_license and user_license.is_valid and user_license.license_type == LicenseType.PRO:
        user_license.is_valid = False
        user_license.license_type = LicenseType.TRIAL
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc)
        user_license.expiry_date = now + _td(days=7)
        user_license.trial_start = now
        user_license.trial_end = user_license.expiry_date
        await db.flush()

    await _log_audit(db, user, "refund_order", f"order_id={order_id}, amount={order.amount}, license_revoked=True", request)
    await db.commit()
    return {"success": True}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status not in (OrderStatus.PENDING, OrderStatus.PAID):
        raise HTTPException(status_code=400, detail="只能取消待支付或已支付的订单")
    order.status = OrderStatus.CANCELLED
    await db.flush()
    await _log_audit(db, user, "cancel_order", f"order_id={order_id}", request)
    await db.commit()
    return {"success": True}


@router.post("/generate_license_keys")
async def admin_generate_license_keys(
    body: LicenseKeyGenerate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    keys = []
    for _ in range(min(body.count, 50)):
        key_str = generate_license_key()
        license_key = LicenseKey(
            license_key=key_str,
            plan_type=PlanType(body.plan_type),
            status=LicenseKeyStatus.UNUSED,
        )
        db.add(license_key)
        keys.append(key_str)

    await db.flush()
    await _log_audit(db, user, "generate_license_keys", f"count={len(keys)}, plan={body.plan_type}", request)
    await db.commit()
    return {"keys": keys, "count": len(keys)}


class TrialCodeGenerate(BaseModel):
    count: int = 20


@router.post("/generate_trial_codes")
async def admin_generate_trial_codes(
    body: TrialCodeGenerate = None,
    request: Request = None,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    count = body.count if body else 20
    count = max(1, min(count, 100))
    keys = []
    for _ in range(count):
        key_str = generate_license_key()
        license_key = LicenseKey(
            license_key=key_str,
            plan_type=PlanType.TRIAL_15D,
            status=LicenseKeyStatus.UNUSED,
        )
        db.add(license_key)
        keys.append(key_str)

    await db.flush()
    await _log_audit(db, user, "generate_trial_codes", f"count={len(keys)}", request)
    await db.commit()
    return {"keys": keys, "count": len(keys), "valid_days": 15}


@router.get("/trial_codes")
async def list_trial_codes(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    
    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
        .order_by(desc(LicenseKey.created_at))
    )
    keys = result.scalars().all()
    
    now = datetime.now(timezone.utc)
    response_keys = []
    
    for k in keys:
        created_at = k.created_at.replace(tzinfo=timezone.utc)
        age_days = (now - created_at).days
        days_remaining = max(0, 15 - age_days)
        is_expired = age_days >= 15
        
        response_keys.append({
            "id": k.id,
            "license_key": k.license_key,
            "status": k.status.value,
            "is_expired": is_expired,
            "days_remaining": days_remaining,
            "activated_by": k.activated_by,
            "activated_by_username": (await db.scalar(select(User.username).where(User.id == k.activated_by))) if k.activated_by else None,
            "activated_at": k.activated_at.isoformat() if k.activated_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        })
    
    return {
        "keys": response_keys
    }


@router.post("/users/{user_id}/toggle_active")
async def toggle_user_active(
    user_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    target.is_active = not target.is_active
    await db.flush()

    license_result = await db.execute(select(License).where(License.user_id == user_id))
    user_license = license_result.scalar_one_or_none()
    if user_license:
        user_license.is_valid = target.is_active
        await db.flush()

    await _log_audit(db, user, "toggle_user_active", f"user_id={user_id}, is_active={target.is_active}, license_synced=True", request)
    await db.commit()
    return {"success": True, "is_active": target.is_active}


@router.post("/versions")
async def create_version(
    body: VersionCreate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    new_version = AppVersion(
        version=body.version,
        download_url=body.download_url,
        file_size=body.file_size,
        file_hash=body.file_hash,
        changelog=body.changelog,
        priority=body.priority,
        force_update=body.force_update,
    )
    db.add(new_version)
    await db.flush()
    await _log_audit(db, user, "create_version", f"version={body.version}", request)
    await db.commit()
    return {"success": True, "version": body.version}


@router.post("/users")
async def create_user(
    body: UserCreate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).filter((User.username == body.username) | (User.email == body.email))
    )
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    
    new_user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        is_active=True,
        is_admin=body.is_admin,
    )
    db.add(new_user)
    await db.flush()

    if body.plan_type:
        from datetime import timedelta
        plan_deltas = {
            "trial_15d": (LicenseType.TRIAL, timedelta(days=15)),
            "monthly": (LicenseType.PRO, timedelta(days=30)),
            "quarterly": (LicenseType.PRO, timedelta(days=90)),
            "yearly": (LicenseType.PRO, timedelta(days=365)),
            "lifetime": (LicenseType.PRO, None),
        }
        if body.plan_type in plan_deltas:
            lic_type, delta = plan_deltas[body.plan_type]
            new_license = License(
                user_id=new_user.id,
                license_type=lic_type,
                is_valid=True,
                expiry_date=None if delta is None else datetime.now(timezone.utc) + delta,
            )
            if lic_type.value == "trial":
                new_license.trial_start = datetime.now(timezone.utc)
                new_license.trial_end = new_license.expiry_date
            db.add(new_license)
            await db.flush()

    await _log_audit(db, user, "create_user", f"username={body.username}, is_admin={body.is_admin}, plan_type={body.plan_type}", request)
    await db.commit()
    return {"success": True}


@router.get("/license_keys")
async def list_license_keys(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LicenseKey).order_by(desc(LicenseKey.created_at)))
    keys = result.scalars().all()
    
    return {
        "keys": [
            {
                "id": k.id,
                "license_key": k.license_key,
                "plan_type": k.plan_type.value,
                "status": k.status.value,
                "activated_by": k.activated_by,
                "activated_by_username": (await db.scalar(select(User.username).where(User.id == k.activated_by))) if k.activated_by else None,
                "activated_at": k.activated_at.isoformat() if k.activated_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ]
    }


@router.post("/license_keys/{license_key}/revoke")
async def revoke_license_key(
    license_key: str,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LicenseKey).where(LicenseKey.license_key == license_key))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="许可证密钥不存在")
    
    if key.status != LicenseKeyStatus.UNUSED:
        raise HTTPException(status_code=400, detail="只能撤销未使用的密钥")
    
    key.status = LicenseKeyStatus.REVOKED
    await db.flush()
    await _log_audit(db, user, "revoke_license_key", f"license_key={license_key}", request)
    await db.commit()
    return {"success": True}


@router.get("/user_licenses")
async def list_user_licenses(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(License).order_by(desc(License.created_at)))
    licenses = result.scalars().all()
    
    return {
        "licenses": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "username": (await db.scalar(select(User.username).where(User.id == l.user_id))) if l.user_id else None,
                "license_type": l.license_type.value,
                "license_key": l.license_key,
                "is_valid": l.is_valid,
                "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in licenses
        ]
    }


@router.get("/versions")
async def list_versions(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
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
                "download_url": v.download_url,
                "file_size": v.file_size,
                "file_hash": v.file_hash,
                "changelog": v.changelog,
                "priority": v.priority,
                "force_update": v.force_update,
                "is_active": v.is_active,
                "release_date": v.release_date.isoformat() if v.release_date else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
    }


@router.get("/versions/{version_id}")
async def get_version(
    version_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppVersion).where(AppVersion.id == version_id))
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    return {
        "id": version.id,
        "version": version.version,
        "download_url": version.download_url,
        "file_size": version.file_size,
        "file_hash": version.file_hash,
        "changelog": version.changelog,
        "priority": version.priority,
        "force_update": version.force_update,
        "is_active": version.is_active,
        "release_date": version.release_date.isoformat() if version.release_date else None,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


@router.put("/versions/{version_id}")
async def update_version(
    version_id: int,
    body: VersionUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppVersion).where(AppVersion.id == version_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    if body.version is not None:
        target.version = body.version
    if body.download_url is not None:
        target.download_url = body.download_url
    if body.file_size is not None:
        target.file_size = body.file_size
    if body.changelog is not None:
        target.changelog = body.changelog
    if body.priority is not None:
        target.priority = body.priority
    if body.force_update is not None:
        target.force_update = body.force_update
    if body.is_active is not None:
        target.is_active = body.is_active
    if body.file_hash is not None:
        target.file_hash = body.file_hash
    
    await db.flush()
    await _log_audit(db, user, "update_version", f"version_id={version_id}, version={body.version}", request)
    await db.commit()
    return {"success": True}


@router.delete("/versions/{version_id}")
async def delete_version(
    version_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppVersion).where(AppVersion.id == version_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    await db.delete(target)
    await db.flush()
    await _log_audit(db, user, "delete_version", f"version_id={version_id}, version={target.version}", request)
    await db.commit()
    return {"success": True}


@router.post("/versions/{version_id}/toggle_active")
async def toggle_version_active(
    version_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppVersion).where(AppVersion.id == version_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    target.is_active = not target.is_active
    await db.flush()
    await _log_audit(db, user, "toggle_version_active", f"version_id={version_id}, is_active={target.is_active}", request)
    await db.commit()
    return {"success": True, "is_active": target.is_active}


@router.get("/analytics")
async def get_analytics(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta
    
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    
    weekly_new_users = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= week_ago)
    )
    
    weekly_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.created_at >= week_ago)
    )
    
    weekly_revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            Order.created_at >= week_ago,
            Order.status == OrderStatus.PAID
        )
    )
    
    active_pro_licenses = await db.scalar(
        select(func.count(License.id)).where(
            License.license_type == LicenseType.PRO,
            License.is_valid == True
        )
    )
    
    trial_licenses = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.TRIAL)
    )
    
    pro_licenses = await db.scalar(
        select(func.count(License.id)).where(License.license_type == LicenseType.PRO)
    )
    
    alipay_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_method == "alipay")
    )
    
    wechat_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_method == "wechat")
    )
    
    daily_users = []
    daily_revenue = []
    for i in range(7):
        day_start = (now - timedelta(days=6 - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        day_users = await db.scalar(
            select(func.count(User.id)).where(
                User.created_at >= day_start,
                User.created_at < day_end
            )
        )
        daily_users.append(day_users or 0)
        
        day_revenue = await db.scalar(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.created_at >= day_start,
                Order.created_at < day_end,
                Order.status == OrderStatus.PAID
            )
        )
        daily_revenue.append(float(day_revenue) if day_revenue else 0)
    
    return {
        "weekly_new_users": weekly_new_users or 0,
        "weekly_orders": weekly_orders or 0,
        "weekly_revenue": float(weekly_revenue) if weekly_revenue else 0,
        "active_pro_licenses": active_pro_licenses or 0,
        "trial_licenses": trial_licenses or 0,
        "pro_licenses": pro_licenses or 0,
        "alipay_orders": alipay_orders or 0,
        "wechat_orders": wechat_orders or 0,
        "daily_users": daily_users,
        "daily_revenue": daily_revenue,
    }


@router.get("/audit_logs")
async def list_audit_logs(
    page: int = 1,
    page_size: int = 20,
    action: str = None,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    query = select(AuditLog).order_by(desc(AuditLog.created_at))
    count_query = select(func.count(AuditLog.id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    total = await db.scalar(count_query)
    result = await db.execute(query.offset(offset).limit(page_size))
    logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": [
            {
                "id": l.id,
                "operator_name": l.operator_name,
                "action": l.action,
                "detail": l.detail,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
