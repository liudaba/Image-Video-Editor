from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, delete, update

from ..database import get_db
from ..models import (
    User, License, Order, AppVersion, HeartbeatLog, AuditLog, MachineBinding,
    LicenseType, OrderStatus, LicenseKey, LicenseKeyStatus, PlanType,
    validate_order_status_transition,
)
from ..auth import get_current_user, require_admin, hash_password
from ..services.license_service import generate_license_key

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


async def _log_audit(db: AsyncSession, admin: User, action: str, detail: str = None, request: Request = None):
    ip_address = None
    if request:
        from ..main import _get_real_ip
        ip_address = _get_real_ip(request)
    log = AuditLog(
        operator_id=admin.id,
        operator_name=admin.username,
        action=action,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(log)
    await db.flush()


class VersionCreate(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    changelog: Optional[List[str]] = None
    priority: str = "normal"
    force_update: bool = False
    update_type: str = Field("full", pattern=r"^(full|patch)$")
    patch_url: Optional[str] = None
    patch_hash: Optional[str] = None
    patch_size: Optional[int] = None
    from_version: Optional[str] = Field(None, pattern=r"^(\d+\.\d+\.\d+)?$")

    def validate_urls(self):
        """校验：至少提供 download_url 或 patch_url 之一"""
        if not self.download_url and not self.patch_url:
            raise ValueError("至少需要提供全量包下载地址(download_url)或补丁包下载地址(patch_url)")
        if self.update_type == "patch" and not self.from_version:
            raise ValueError("增量补丁类型必须指定适用源版本(from_version)")
        return self


class LicenseKeyGenerate(BaseModel):
    plan_type: str = Field("yearly", pattern=r"^(monthly|quarterly|yearly|lifetime|trial_15d)$")
    count: int = Field(1, ge=1, le=50)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    is_admin: bool = False
    is_active: bool = True
    plan_type: Optional[str] = None

    @staticmethod
    def validate_password_strength(v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少6位")
        return v

    def model_post_init(self, __context):
        self.validate_password_strength(self.password)


@router.get("/stats")
async def get_stats(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = await db.scalar(select(func.count(User.id)))
    # 活跃许可证：is_valid=True 且未过期（或无过期时间即终身）
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(
            License.is_valid == True,
            or_(License.expiry_date == None, License.expiry_date > datetime.now(timezone.utc))
        )
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

    # 今日新增用户
    from datetime import timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_new_users = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )

    # 即将到期用户（7天内到期）
    expiry_warning_date = datetime.now(timezone.utc) + timedelta(days=7)
    expiring_soon = await db.scalar(
        select(func.count(License.id)).where(
            License.is_valid == True,
            License.expiry_date != None,
            License.expiry_date <= expiry_warning_date,
            License.expiry_date > datetime.now(timezone.utc),
        )
    )

    # 在线设备数（24小时内有心跳）
    online_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    online_devices = await db.scalar(
        select(func.count(License.id)).where(
            License.last_heartbeat != None,
            License.last_heartbeat >= online_cutoff,
        )
    )

    return {
        "total_users": total_users,
        "active_licenses": active_licenses,
        "trial_users": trial_users,
        "pro_users": pro_users,
        "paid_orders": paid_orders,
        "total_revenue": float(total_revenue),
        "today_new_users": today_new_users or 0,
        "expiring_soon": expiring_soon or 0,
        "online_devices": online_devices or 0,
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

    user_ids = [u.id for u in users]

    lic_map = {}
    if user_ids:
        lic_result = await db.execute(select(License).where(License.user_id.in_(user_ids)))
        for lic in lic_result.scalars().all():
            lic_map[lic.user_id] = lic

    activated_keys_map = {}
    if user_ids:
        ak_result = await db.execute(
            select(LicenseKey).where(
                LicenseKey.activated_by.in_(user_ids),
                LicenseKey.status == LicenseKeyStatus.ACTIVATED
            )
        )
        for ak in ak_result.scalars().all():
            if ak.activated_by not in activated_keys_map:
                activated_keys_map[ak.activated_by] = []
            activated_keys_map[ak.activated_by].append({
                "license_key": ak.license_key,
                "plan_type": ak.plan_type.value,
            })

    bindings_map = {}
    if user_ids:
        mb_result = await db.execute(
            select(MachineBinding).where(MachineBinding.user_id.in_(user_ids))
        )
        for mb in mb_result.scalars().all():
            if mb.user_id not in bindings_map:
                bindings_map[mb.user_id] = []
            bindings_map[mb.user_id].append({
                "fingerprint": mb.fingerprint,
                "machine_name": mb.machine_name,
                "bound_at": mb.bound_at.isoformat() if mb.bound_at else None,
                "last_seen": mb.last_seen.isoformat() if mb.last_seen else None,
            })

    user_list = []
    for u in users:
        lic = lic_map.get(u.id)
        user_info = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "license_type": lic.license_type.value if lic else None,
            "plan_type": lic.plan_type.value if lic and lic.plan_type else None,
            "license_is_valid": lic.is_valid if lic else None,
            "last_heartbeat": lic.last_heartbeat.isoformat() if lic and lic.last_heartbeat else None,
            "expiry_date": lic.expiry_date.isoformat() if lic and lic.expiry_date else None,
            "machine_fingerprint": lic.machine_fingerprint if lic else None,
            "heartbeat_fingerprint": lic.heartbeat_fingerprint if lic else None,
            "activated_keys": activated_keys_map.get(u.id, []),
            "machine_bindings": bindings_map.get(u.id, []),
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

    current_plan = lic.plan_type.value if lic and lic.plan_type else None
    if not current_plan and lic:
        if lic.license_type == LicenseType.PRO:
            if lic.expiry_date is None:
                current_plan = "lifetime"
            else:
                # plan_type为空的历史数据，无法可靠推断套餐类型
                current_plan = "pro"
        elif lic.license_type == LicenseType.TRIAL:
            current_plan = "trial_15d"
    if not current_plan:
        current_plan = "trial_15d"

    return {
        "id": target_user.id,
        "username": target_user.username,
        "email": target_user.email,
        "is_active": target_user.is_active,
        "is_admin": target_user.is_admin,
        "created_at": target_user.created_at.isoformat() if target_user.created_at else None,
        "license_type": lic.license_type.value if lic else None,
        "plan_type": lic.plan_type.value if lic and lic.plan_type else None,
        "license_is_valid": lic.is_valid if lic else None,
        "expiry_date": lic.expiry_date.isoformat() if lic and lic.expiry_date else None,
        "current_plan": current_plan,
        "last_heartbeat": lic.last_heartbeat.isoformat() if lic and lic.last_heartbeat else None,
        "machine_fingerprint": lic.machine_fingerprint if lic else None,
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
    changelog: Optional[List[str]] = None
    priority: Optional[str] = None
    force_update: Optional[bool] = None
    is_active: Optional[bool] = None
    update_type: Optional[str] = None
    patch_url: Optional[str] = None
    patch_hash: Optional[str] = None
    patch_size: Optional[int] = None
    from_version: Optional[str] = None


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
        # 检查用户名是否与其他用户冲突
        if body.username != target_user.username:
            existing = await db.execute(
                select(User).filter(User.username == body.username)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="用户名已存在")
        target_user.username = body.username
    if body.email is not None:
        # 检查邮箱是否与其他用户冲突
        if body.email != target_user.email:
            existing = await db.execute(
                select(User).filter(User.email == body.email)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="邮箱已存在")
        target_user.email = body.email
    if body.password is not None:
        # 管理员修改自己的密码时，必须通过 /api/auth/admin/change-password 接口验证旧密码
        # 此接口不允许直接修改自己的密码，防止绕过旧密码验证
        if user_id == user.id:
            raise HTTPException(status_code=400, detail="请使用修改密码功能修改自己的密码")
        # 验证新密码强度
        try:
            from ..schemas import UserRegister
            UserRegister.validate_password_strength.__func__(None, body.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        target_user.hashed_password = hash_password(body.password)
        target_user.password_changed_at = datetime.now(timezone.utc)
    if body.is_active is not None and body.is_active is False and target_user.id == user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    if body.is_active is not None:
        target_user.is_active = body.is_active
        license_result = await db.execute(select(License).where(License.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if user_license:
            if body.is_active:
                from ..services.license_service import is_license_time_expired
                user_license.is_valid = not is_license_time_expired(user_license)
            else:
                user_license.is_valid = False
            await db.flush()
    if body.is_admin is not None:
        # 管理员不能取消自己的管理员权限
        if not body.is_admin and user_id == user.id:
            raise HTTPException(status_code=400, detail="不能取消自己的管理员权限")
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
            now = datetime.now(timezone.utc)
            user_license = License(
                user_id=user_id,
                license_type=lic_type,
                plan_type=PlanType(body.plan_type),
                is_valid=target_user.is_active,
                expiry_date=None if delta is None else now + delta,
                trial_start=now if lic_type.value == "trial" else None,
                trial_end=(now + delta) if lic_type.value == "trial" and delta else None,
            )
            db.add(user_license)
        else:
            # 终身会员只能升级（维持终身），不允许降级
            if user_license.plan_type == PlanType.LIFETIME and body.plan_type != "lifetime":
                raise HTTPException(status_code=400, detail="终身会员不允许降级为其他套餐")
            user_license.license_type = lic_type
            user_license.plan_type = PlanType(body.plan_type)
            # 根据用户状态设置is_valid
            if target_user.is_active:
                user_license.is_valid = True
            else:
                user_license.is_valid = False
            if delta is None:
                user_license.expiry_date = None
            elif body.plan_type == "trial_15d":
                # 试用码续费走activate_license的叠加逻辑（含3倍上限）
                from ..services.license_service import calc_renewal_expiry
                user_license.expiry_date = calc_renewal_expiry(user_license.expiry_date, PlanType(body.plan_type))
            else:
                # 付费套餐续费也走统一的3倍上限逻辑
                from ..services.license_service import calc_renewal_expiry
                user_license.expiry_date = calc_renewal_expiry(user_license.expiry_date, PlanType(body.plan_type))
            if lic_type.value == "trial":
                user_license.trial_start = datetime.now(timezone.utc)
                user_license.trial_end = user_license.expiry_date
            else:
                user_license.trial_start = None
                user_license.trial_end = None
        # 注意：不修改已激活密钥的plan_type，密钥的套餐类型是创建时确定的
        # 修改用户套餐只影响用户的License记录，不影响密钥记录

    if body.expiry_date is not None:
        license_result = await db.execute(select(License).where(License.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if not user_license:
            user_license = License(
                user_id=user_id,
                license_type=LicenseType.PRO,
                plan_type=PlanType.LIFETIME if body.expiry_date == "never" else PlanType.YEARLY,
                is_valid=target_user.is_active,
                expiry_date=None if body.expiry_date == "never" else None,
            )
            db.add(user_license)
            await db.flush()
        if body.expiry_date == "never":
            user_license.expiry_date = None
            user_license.plan_type = PlanType.LIFETIME
            user_license.license_type = LicenseType.PRO
            if target_user.is_active:
                user_license.is_valid = True
            else:
                user_license.is_valid = False
        else:
            try:
                parsed = datetime.fromisoformat(body.expiry_date.replace("Z", "+00:00"))
                user_license.expiry_date = parsed
                # 如果plan_type为空，根据到期时间推断合理的套餐类型
                if not user_license.plan_type:
                    now = datetime.now(timezone.utc)
                    remaining = parsed - now
                    remaining_days = remaining.days if remaining.days > 0 else 0
                    if remaining_days <= 30:
                        user_license.plan_type = PlanType.MONTHLY
                    elif remaining_days <= 90:
                        user_license.plan_type = PlanType.QUARTERLY
                    else:
                        user_license.plan_type = PlanType.YEARLY
                    user_license.license_type = LicenseType.PRO
                if target_user.is_active:
                    from ..services.license_service import is_license_time_expired
                    user_license.is_valid = not is_license_time_expired(user_license)
                else:
                    user_license.is_valid = False
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
    
    # 级联删除关联数据
    await db.execute(delete(HeartbeatLog).where(HeartbeatLog.user_id == user_id))
    await db.execute(delete(MachineBinding).where(MachineBinding.user_id == user_id))
    await db.execute(delete(License).where(License.user_id == user_id))
    await db.execute(delete(Order).where(Order.user_id == user_id))
    # 将该用户关联的所有密钥状态设为已撤销（包括已激活和未使用的）
    await db.execute(
        update(LicenseKey)
        .where(LicenseKey.activated_by == user_id, LicenseKey.status.in_([LicenseKeyStatus.ACTIVATED, LicenseKeyStatus.UNUSED]))
        .values(status=LicenseKeyStatus.REVOKED)
    )
    
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

    order_user_ids = list(set(o.user_id for o in orders))
    order_users_map = {}
    if order_user_ids:
        ou_result = await db.execute(select(User).where(User.id.in_(order_user_ids)))
        for ou in ou_result.scalars().all():
            order_users_map[ou.id] = {"username": ou.username, "email": ou.email}

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
                "username": order_users_map.get(o.user_id, {}).get("username"),
                "email": order_users_map.get(o.user_id, {}).get("email"),
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
        # 终身会员不允许被任何订单降级
        if existing_license.plan_type == PlanType.LIFETIME:
            await _log_audit(db, user, "confirm_payment", f"order_id={order_id}, order_no={order.order_no}, SKIPPED: user already lifetime member", request)
            await db.commit()
            return {"success": True, "message": "订单已确认支付，但用户已是终身会员，许可证未变更"}
        else:
            existing_license.license_type = LicenseType.PRO
            existing_license.plan_type = order.plan_type
            # 检查用户是否被禁用
            target_user_result = await db.execute(select(User).where(User.id == order.user_id))
            target_user_obj = target_user_result.scalar_one_or_none()
            existing_license.is_valid = target_user_obj.is_active if target_user_obj else True
            existing_license.trial_start = None
            existing_license.trial_end = None
            from ..services.license_service import calc_renewal_expiry
            existing_license.expiry_date = calc_renewal_expiry(existing_license.expiry_date, order.plan_type)
        await db.flush()
    else:
        # 用户没有 License 记录，创建新的
        from ..services.license_service import PLAN_DELTAS
        now = datetime.now(timezone.utc)
        expiry = None
        if order.plan_type == PlanType.LIFETIME:
            expiry = None
        elif order.plan_type in PLAN_DELTAS:
            expiry = now + PLAN_DELTAS[order.plan_type]
        # 检查用户是否被禁用
        target_user_result = await db.execute(select(User).where(User.id == order.user_id))
        target_user_obj = target_user_result.scalar_one_or_none()
        new_license = License(
            user_id=order.user_id,
            license_type=LicenseType.PRO,
            plan_type=order.plan_type,
            is_valid=target_user_obj.is_active if target_user_obj else True,
            expiry_date=expiry,
        )
        db.add(new_license)
        await db.flush()

    await _log_audit(db, user, "confirm_payment", f"order_id={order_id}, order_no={order.order_no}, amount={order.amount}, plan={order.plan_type.value}", request)
    await db.commit()
    return {"success": True, "message": "订单已手动确认支付"}


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
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    
    # 分页查询
    total = await db.scalar(
        select(func.count(LicenseKey.id)).where(LicenseKey.plan_type == PlanType.TRIAL_15D)
    )
    offset = (page - 1) * page_size
    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
        .order_by(desc(LicenseKey.created_at))
        .offset(offset).limit(page_size)
    )
    keys = result.scalars().all()

    tc_user_ids = list(set(k.activated_by for k in keys if k.activated_by))
    tc_users_map = {}
    if tc_user_ids:
        tcu_result = await db.execute(select(User).where(User.id.in_(tc_user_ids)))
        for tcu in tcu_result.scalars().all():
            tc_users_map[tcu.id] = {"username": tcu.username, "email": tcu.email}

    now = datetime.now(timezone.utc)
    response_keys = []

    for k in keys:
        # 只有已激活的试用码才计算过期时间（从激活时间算起15天）
        # 未激活的试用码永不过期
        if k.status == LicenseKeyStatus.ACTIVATED and k.activated_at:
            activated_at = k.activated_at.replace(tzinfo=timezone.utc) if k.activated_at.tzinfo is None else k.activated_at
            age_days = (now - activated_at).days
            days_remaining = max(0, 15 - age_days)
            is_expired = age_days >= 15
        else:
            # 未激活或已撤销的试用码不计算过期
            days_remaining = 15
            is_expired = False

        tc_user_info = tc_users_map.get(k.activated_by, {}) if k.activated_by else {}
        response_keys.append({
            "id": k.id,
            "license_key": k.license_key,
            "status": k.status.value,
            "is_expired": is_expired,
            "days_remaining": days_remaining,
            "activated_by": k.activated_by,
            "activated_by_username": tc_user_info.get("username"),
            "activated_by_email": tc_user_info.get("email"),
            "activated_at": k.activated_at.isoformat() if k.activated_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        })
    
    return {
        "keys": response_keys,
        "total": total,
        "page": page,
        "page_size": page_size,
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
        if target.is_active:
            # 重新启用时，仅检查过期时间（不检查is_valid，因为当前is_valid=False会导致死锁）
            from ..services.license_service import is_license_time_expired
            user_license.is_valid = not is_license_time_expired(user_license)
        else:
            user_license.is_valid = False
        await db.flush()

    await _log_audit(db, user, "toggle_user_active", f"user_id={user_id}, is_active={target.is_active}, license_synced=True", request)
    await db.commit()
    return {"success": True, "is_active": target.is_active}


class BatchUserStatus(BaseModel):
    user_ids: list[int]
    is_active: bool


@router.post("/users/batch_status")
async def batch_set_user_status(
    body: BatchUserStatus,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from ..services.license_service import is_license_time_expired
    success_count = 0
    fail_count = 0
    for uid in body.user_ids:
        if uid == user.id:
            fail_count += 1
            continue
        result = await db.execute(select(User).where(User.id == uid))
        target = result.scalar_one_or_none()
        if not target:
            fail_count += 1
            continue
        target.is_active = body.is_active
        license_result = await db.execute(select(License).where(License.user_id == uid))
        user_license = license_result.scalar_one_or_none()
        if user_license:
            if body.is_active:
                user_license.is_valid = not is_license_time_expired(user_license)
            else:
                user_license.is_valid = False
        success_count += 1
    await db.flush()
    await _log_audit(db, user, "batch_set_user_status", f"user_ids={body.user_ids}, is_active={body.is_active}, success={success_count}, fail={fail_count}", request)
    await db.commit()
    return {"success": True, "success_count": success_count, "fail_count": fail_count}


@router.post("/versions")
async def create_version(
    body: VersionCreate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        body.validate_urls()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    new_version = AppVersion(
        version=body.version,
        download_url=body.download_url,
        file_size=body.file_size,
        file_hash=body.file_hash,
        changelog="\n".join(body.changelog) if isinstance(body.changelog, list) else str(body.changelog or ""),
        priority=body.priority,
        force_update=body.force_update,
        update_type=body.update_type,
        patch_url=body.patch_url,
        patch_hash=body.patch_hash,
        patch_size=body.patch_size,
        from_version=body.from_version,
    )
    db.add(new_version)
    await db.flush()
    await _log_audit(db, user, "create_version", f"version={body.version}", request)
    await db.commit()
    return {"success": True, "version": {"id": new_version.id, "version": new_version.version}}


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
        is_active=body.is_active,
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
                plan_type=PlanType(body.plan_type),
                is_valid=new_user.is_active,
                expiry_date=None if delta is None else datetime.now(timezone.utc) + delta,
            )
            if lic_type.value == "trial":
                new_license.trial_start = datetime.now(timezone.utc)
                new_license.trial_end = new_license.expiry_date
            db.add(new_license)
            await db.flush()
    else:
        # 未指定套餐时自动创建试用License，否则用户无法登录
        from ..services.license_service import create_trial_license
        await create_trial_license(db, new_user.id)

    await _log_audit(db, user, "create_user", f"username={body.username}, is_admin={body.is_admin}, plan_type={body.plan_type}", request)
    await db.commit()
    return {"success": True, "user": {"id": new_user.id, "username": new_user.username, "email": new_user.email}}


@router.get("/license_keys")
async def list_license_keys(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 分页查询
    total = await db.scalar(select(func.count(LicenseKey.id)))
    offset = (page - 1) * page_size
    result = await db.execute(
        select(LicenseKey).order_by(desc(LicenseKey.created_at))
        .offset(offset).limit(page_size)
    )
    keys = result.scalars().all()

    lk_user_ids = list(set(k.activated_by for k in keys if k.activated_by))
    lk_users_map = {}
    if lk_user_ids:
        lku_result = await db.execute(select(User).where(User.id.in_(lk_user_ids)))
        for lku in lku_result.scalars().all():
            lk_users_map[lku.id] = {"username": lku.username, "email": lku.email}

    plan_validity_days = {
        "trial_15d": 15,
        "monthly": 30,
        "quarterly": 90,
        "yearly": 365,
        "lifetime": None,
    }

    now = datetime.now(timezone.utc)
    response_keys = []
    for k in keys:
        is_expired = False
        if k.plan_type.value in plan_validity_days:
            validity = plan_validity_days[k.plan_type.value]
            if validity is not None:
                if k.status == LicenseKeyStatus.ACTIVATED and k.activated_at:
                    # 已激活的密钥：从激活时间算起
                    activated = k.activated_at.replace(tzinfo=timezone.utc) if k.activated_at.tzinfo is None else k.activated_at
                    is_expired = (now - activated).days >= validity
                # 未使用的密钥不算过期（长期未激活的试用码90天后才清理）

        lk_user_info = lk_users_map.get(k.activated_by, {}) if k.activated_by else {}
        response_keys.append({
            "id": k.id,
            "license_key": k.license_key,
            "plan_type": k.plan_type.value,
            "status": k.status.value,
            "is_expired": is_expired,
            "activated_by": k.activated_by,
            "activated_by_username": lk_user_info.get("username"),
            "activated_by_email": lk_user_info.get("email"),
            "activated_at": k.activated_at.isoformat() if k.activated_at else None,
            "expiry_date": k.expiry_date.isoformat() if k.expiry_date else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        })

    return {"keys": response_keys, "total": total, "page": page, "page_size": page_size}


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
    
    if key.status == LicenseKeyStatus.REVOKED:
        raise HTTPException(status_code=400, detail="密钥已被撤销")

    # 撤销已激活的密钥时，检查用户是否还有其他有效密钥
    previous_status = key.status.value
    if key.status == LicenseKeyStatus.ACTIVATED and key.activated_by:
        # 查找该用户的其他有效密钥（排除当前密钥）
        other_keys_result = await db.execute(
            select(LicenseKey).where(
                LicenseKey.activated_by == key.activated_by,
                LicenseKey.status == LicenseKeyStatus.ACTIVATED,
                LicenseKey.license_key != license_key,
            )
        )
        other_active_keys = other_keys_result.scalars().all()
        # 如果没有其他有效密钥，根据许可证过期时间决定is_valid
        if not other_active_keys:
            lic_result = await db.execute(select(License).where(License.user_id == key.activated_by))
            user_lic = lic_result.scalar_one_or_none()
            if user_lic:
                from ..services.license_service import is_license_time_expired
                user_lic.is_valid = not is_license_time_expired(user_lic)
                # 清除License对已撤销密钥的引用
                if user_lic.license_key == license_key:
                    user_lic.license_key = None
                await db.flush()

    key.status = LicenseKeyStatus.REVOKED
    await db.flush()
    await _log_audit(db, user, "revoke_license_key", f"license_key={license_key}, previous_status={previous_status}", request)
    await db.commit()
    return {"success": True}


@router.delete("/license_keys/{license_key}")
async def delete_license_key(
    license_key: str,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LicenseKey).where(LicenseKey.license_key == license_key))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="许可证密钥不存在")

    if key.status == LicenseKeyStatus.ACTIVATED and key.activated_by is not None:
        raise HTTPException(status_code=400, detail="已激活的密钥不能删除，请先撤销")

    await db.delete(key)
    await db.flush()
    await _log_audit(db, user, "delete_license_key", f"license_key={license_key}, plan_type={key.plan_type.value}, status={key.status.value}", request)
    await db.commit()
    return {"success": True}


@router.get("/user_licenses")
async def list_user_licenses(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 分页查询
    total = await db.scalar(select(func.count(License.id)))
    offset = (page - 1) * page_size
    result = await db.execute(
        select(License).order_by(desc(License.created_at))
        .offset(offset).limit(page_size)
    )
    licenses = result.scalars().all()

    ul_user_ids = list(set(l.user_id for l in licenses if l.user_id))
    ul_users_map = {}
    if ul_user_ids:
        ulu_result = await db.execute(select(User).where(User.id.in_(ul_user_ids)))
        for ulu in ulu_result.scalars().all():
            ul_users_map[ulu.id] = {"username": ulu.username, "email": ulu.email}

    return {
        "licenses": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "username": ul_users_map.get(l.user_id, {}).get("username"),
                "email": ul_users_map.get(l.user_id, {}).get("email"),
                "license_type": l.license_type.value,
                "plan_type": l.plan_type.value if l.plan_type else None,
                "license_key": l.license_key,
                "is_valid": l.is_valid,
                "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None,
                "machine_fingerprint": l.machine_fingerprint,
                "last_heartbeat": l.last_heartbeat.isoformat() if l.last_heartbeat else None,
                "heartbeat_fingerprint": l.heartbeat_fingerprint,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in licenses
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/versions")
async def list_versions(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count(AppVersion.id)))
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AppVersion).order_by(desc(AppVersion.created_at))
        .offset(offset).limit(page_size)
    )
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
                "update_type": v.update_type,
                "patch_url": v.patch_url,
                "patch_hash": v.patch_hash,
                "patch_size": v.patch_size,
                "from_version": v.from_version,
                "release_date": v.release_date.isoformat() if v.release_date else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
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
        "update_type": version.update_type,
        "patch_url": version.patch_url,
        "patch_hash": version.patch_hash,
        "patch_size": version.patch_size,
        "from_version": version.from_version,
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
        target.changelog = "\n".join(body.changelog) if isinstance(body.changelog, list) else str(body.changelog)
    if body.priority is not None:
        target.priority = body.priority
    if body.force_update is not None:
        target.force_update = body.force_update
    if body.is_active is not None:
        target.is_active = body.is_active
    if body.file_hash is not None:
        target.file_hash = body.file_hash
    if body.update_type is not None:
        target.update_type = body.update_type
    if body.patch_url is not None:
        target.patch_url = body.patch_url
    if body.patch_hash is not None:
        target.patch_hash = body.patch_hash
    if body.patch_size is not None:
        target.patch_size = body.patch_size
    if body.from_version is not None:
        target.from_version = body.from_version

    # 校验：更新后仍需满足至少一个URL
    if not target.download_url and not target.patch_url:
        raise HTTPException(status_code=422, detail="至少需要提供全量包下载地址或补丁包下载地址")
    # 校验：patch类型必须有from_version
    if target.update_type == "patch" and not target.from_version:
        raise HTTPException(status_code=422, detail="增量补丁类型必须指定适用源版本(from_version)")

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


@router.delete("/audit_logs")
async def clear_audit_logs(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """清空所有审计日志"""
    count = await db.scalar(select(func.count(AuditLog.id)))
    if count == 0:
        return {"success": True, "deleted_count": 0}
    # 先记录审计日志（flush后获得新记录id），再删除除该记录外的所有日志
    await _log_audit(db, user, "clear_audit_logs", f"deleted {count} log entries", request)
    await db.flush()
    # 获取刚插入的审计记录id（当前session中最后一条）
    latest_log = (await db.execute(select(AuditLog).order_by(desc(AuditLog.id)).limit(1))).scalar_one_or_none()
    keep_id = latest_log.id if latest_log else 0
    await db.execute(delete(AuditLog).where(AuditLog.id != keep_id))
    await db.commit()
    return {"success": True, "deleted_count": count}


@router.get("/expiring_users")
async def list_expiring_users(
    days: int = 7,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """即将到期的用户列表，方便运营提前介入"""
    from datetime import timedelta
    days = max(1, min(days, 30))
    now = datetime.now(timezone.utc)
    expiry_cutoff = now + timedelta(days=days)

    result = await db.execute(
        select(License, User)
        .join(User, User.id == License.user_id)
        .where(
            License.is_valid == True,
            License.expiry_date != None,
            License.expiry_date > now,
            License.expiry_date <= expiry_cutoff,
        )
        .order_by(License.expiry_date.asc())
    )
    rows = result.scalars().all()

    # 需要重新查询获取User信息
    expiring_list = []
    lic_result = await db.execute(
        select(License, User)
        .join(User, User.id == License.user_id)
        .where(
            License.is_valid == True,
            License.expiry_date != None,
            License.expiry_date > now,
            License.expiry_date <= expiry_cutoff,
        )
        .order_by(License.expiry_date.asc())
    )
    for lic, u in lic_result:
        exp = lic.expiry_date
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - now
        days_remaining = delta.days + (1 if delta.seconds > 0 else 0)
        expiring_list.append({
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "license_type": lic.license_type.value,
            "plan_type": lic.plan_type.value if lic.plan_type else None,
            "expiry_date": lic.expiry_date.isoformat() if lic.expiry_date else None,
            "days_remaining": days_remaining,
            "last_heartbeat": lic.last_heartbeat.isoformat() if lic.last_heartbeat else None,
        })

    return {"users": expiring_list, "total": len(expiring_list)}


@router.get("/users/{user_id}/heartbeat_history")
async def get_user_heartbeat_history(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """查看用户心跳历史，了解设备使用情况"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    count_query = select(func.count(HeartbeatLog.id)).where(HeartbeatLog.user_id == user_id)
    total = await db.scalar(count_query)

    result = await db.execute(
        select(HeartbeatLog)
        .where(HeartbeatLog.user_id == user_id)
        .order_by(desc(HeartbeatLog.created_at))
        .offset(offset)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": [
            {
                "id": l.id,
                "fingerprint": l.fingerprint,
                "app_version": l.app_version,
                "license_type": l.license_type,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
