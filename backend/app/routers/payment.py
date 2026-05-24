import logging
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import json

from ..database import get_db
from ..models import Order, User, License, LicenseKey, OrderStatus, PlanType, LicenseType, LicenseKeyStatus, PaymentNotifyLog, validate_order_status_transition
from ..auth import require_admin, get_current_user
from ..schemas import PaymentCreateOrder, OrderResponse
from ..services.payment_service import (
    create_payment_order,
    create_alipay_order,
    create_wechat_order,
    verify_alipay_notification,
    verify_wechat_notification,
)
from ..services.license_service import activate_license

logger = logging.getLogger("videogen")
router = APIRouter(prefix="/api/payment", tags=["payment"])


def _check_callback_ip(request: Request) -> bool:
    from ..config import settings
    from ..main import _get_real_ip
    allowed_str = settings.PAYMENT_CALLBACK_ALLOWED_IPS
    if not allowed_str or not allowed_str.strip():
        return True
    allowed = [ip.strip() for ip in allowed_str.split(",") if ip.strip()]
    if not allowed:
        return True
    client_ip = _get_real_ip(request)
    return client_ip in allowed


@router.post("/create-order", response_model=OrderResponse, summary="创建支付订单")
async def create_payment_order_route(
    order_data: PaymentCreateOrder,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if order_data.payment_method.lower() not in ["alipay", "wechat"]:
        raise HTTPException(status_code=422, detail="不支持的支付方式")
    
    # 检查用户是否被禁用
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用，无法创建订单")
    
    result = await create_payment_order(
        db,
        current_user.id,
        order_data.plan_type,
        order_data.payment_method,
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return OrderResponse(
        order_id=result["order_id"],
        payment_url=result.get("payment_url"),
        qr_code=result.get("qr_code"),
        method=result.get("method"),
        message=result.get("message"),
    )


@router.post("/alipay/qr", summary="创建支付宝扫码支付订单")
async def create_alipay_qr_order(
    order_data: PaymentCreateOrder,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await create_payment_order(
        db,
        current_user.id,
        order_data.plan_type,
        "alipay",
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "order_id": result["order_id"],
        "qr_code": result.get("qr_code"),
        "method": "alipay",
        "message": result.get("message"),
    }


@router.post("/wechat/qr", summary="创建微信扫码支付订单")
async def create_wechat_qr_order(
    order_data: PaymentCreateOrder,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await create_payment_order(
        db,
        current_user.id,
        order_data.plan_type,
        "wechat",
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "order_id": result["order_id"],
        "qr_code": result.get("qr_code"),
        "method": "wechat",
        "message": result.get("message"),
    }


@router.post("/callback/alipay", summary="支付宝回调")
async def alipay_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    if not _check_callback_ip(request):
        return {"code": "FAIL", "msg": "IP未授权"}
    form_data = await request.form()
    params = dict(form_data)
    
    if not await verify_alipay_notification(params):
        return {"code": "FAIL", "msg": "签名验证失败"}
    
    order_no = params.get('out_trade_no')
    if not order_no:
        return {"code": "FAIL", "msg": "缺少订单号"}
    trade_status = params.get('trade_status')
    
    if trade_status in ['TRADE_SUCCESS', 'TRADE_FINISHED']:
        # 先锁定订单行，防止并发回调重复处理
        order_query = select(Order).filter(Order.order_no == order_no).with_for_update()
        result = await db.execute(order_query)
        order = result.scalar_one_or_none()

        # 在订单锁内检查是否已处理过此通知（防止重复激活）
        notify_id = params.get('notify_id', params.get('trade_no', ''))
        existing_notify = await db.execute(
            select(PaymentNotifyLog).where(PaymentNotifyLog.notify_id == notify_id)
        )
        if existing_notify.scalar_one_or_none():
            return {"code": "SUCCESS", "msg": "OK"}

        if order and order.status == OrderStatus.PENDING:
            # 记录通知日志（在订单锁内，确保原子性）
            notify_log = PaymentNotifyLog(
                notify_id=notify_id,
                order_no=order_no or "",
                payment_method="alipay",
                raw_data=json.dumps(params, ensure_ascii=False),
            )
            db.add(notify_log)
            await db.flush()
            if not validate_order_status_transition(order.status, OrderStatus.PAID):
                logger.warning(f"Invalid order status transition for order {order_no}: {order.status} -> PAID")
                return {"code": "FAIL", "msg": "订单状态异常"}
            paid_amount = Decimal(str(params.get('total_amount', '0')))
            if paid_amount != order.amount:
                logger.warning(f"Payment amount mismatch for order {order_no}: expected {order.amount}, got {paid_amount}")
                return {"code": "FAIL", "msg": "金额不匹配"}

            order.status = OrderStatus.PAID
            order.transaction_id = params.get('trade_no')
            order.paid_at = datetime.now(timezone.utc)
            await db.flush()

            license_result = await db.execute(
                select(License).filter(License.user_id == order.user_id).with_for_update()
            )
            existing_license = license_result.scalar_one_or_none()
            if existing_license:
                # 终身会员不允许被任何支付降级
                if existing_license.plan_type == PlanType.LIFETIME:
                    logger.info(f"User {order.user_id} is lifetime member, skipping license downgrade from alipay order {order_no}")
                else:
                    existing_license.license_type = LicenseType.PRO
                    existing_license.plan_type = order.plan_type
                    # 检查用户是否被禁用
                    order_user_result = await db.execute(select(User).where(User.id == order.user_id))
                    order_user = order_user_result.scalar_one_or_none()
                    existing_license.is_valid = order_user.is_active if order_user else True
                    existing_license.trial_start = None
                    existing_license.trial_end = None
                    from ..services.license_service import calc_renewal_expiry
                    existing_license.expiry_date = calc_renewal_expiry(existing_license.expiry_date, order.plan_type)
                    # 在线支付无激活码，用订单号标识来源
                    if not existing_license.license_key:
                        existing_license.license_key = f"ALIPAY-{order_no}"
                await db.flush()
            else:
                from ..services.license_service import PLAN_DELTAS
                now = datetime.now(timezone.utc)
                expiry = None
                if order.plan_type == PlanType.LIFETIME:
                    expiry = None
                elif order.plan_type in PLAN_DELTAS:
                    expiry = now + PLAN_DELTAS[order.plan_type]
                # 检查用户是否被禁用
                order_user_result2 = await db.execute(select(User).where(User.id == order.user_id))
                order_user2 = order_user_result2.scalar_one_or_none()
                new_license = License(
                    user_id=order.user_id,
                    license_type=LicenseType.PRO,
                    plan_type=order.plan_type,
                    license_key=f"ALIPAY-{order_no}",
                    is_valid=order_user2.is_active if order_user2 else True,
                    expiry_date=expiry,
                )
                db.add(new_license)
                await db.flush()

            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to commit alipay callback for order {order_no}: {e}")
                return {"code": "FAIL", "msg": "数据库提交失败"}

    return {"code": "SUCCESS", "msg": "OK"}


@router.post("/callback/wechat", summary="微信支付回调")
async def wechat_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    if not _check_callback_ip(request):
        return {"code": "FAIL", "msg": "IP未授权"}
    body = await request.body()
    headers = request.headers
    
    if not await verify_wechat_notification(headers, body):
        return {"code": "FAIL", "msg": "签名验证失败"}
    
    try:
        data = json.loads(body.decode('utf-8'))
        # 微信V3 JSON格式，检查是否包含必要字段
        if 'trade_state' not in data and 'out_trade_no' not in data:
            # 可能是嵌套结构（V3 resource），尝试提取
            resource = data.get('resource', {})
            if isinstance(resource, dict):
                for key in ['trade_state', 'out_trade_no']:
                    if key in resource and key not in data:
                        data[key] = resource[key]
    except json.JSONDecodeError:
        from defusedxml.ElementTree import fromstring as safe_fromstring
        root = safe_fromstring(body)
        data = {}
        for child in root:
            data[child.tag] = child.text
    
    order_no = data.get('out_trade_no')
    if not order_no:
        return {"code": "FAIL", "msg": "缺少订单号"}
    trade_state = data.get('trade_state')
    
    if trade_state == 'SUCCESS':
        # 先锁定订单行，防止并发回调重复处理
        order_query = select(Order).filter(Order.order_no == order_no).with_for_update()
        result = await db.execute(order_query)
        order = result.scalar_one_or_none()

        # 在订单锁内检查是否已处理过此通知（防止重复激活）
        wx_notify_id = data.get('transaction_id', data.get('id', ''))
        existing_notify = await db.execute(
            select(PaymentNotifyLog).where(PaymentNotifyLog.notify_id == wx_notify_id)
        )
        if existing_notify.scalar_one_or_none():
            return {"code": "SUCCESS", "msg": "OK"}

        if order and order.status == OrderStatus.PENDING:
            # 记录通知日志（在订单锁内，确保原子性）
            notify_log = PaymentNotifyLog(
                notify_id=wx_notify_id,
                order_no=order_no or "",
                payment_method="wechat",
                raw_data=body.decode('utf-8')[:65535],
            )
            db.add(notify_log)
            await db.flush()
            if not validate_order_status_transition(order.status, OrderStatus.PAID):
                logger.warning(f"Invalid order status transition for order {order_no}: {order.status} -> PAID")
                return {"code": "FAIL", "msg": "订单状态异常"}
            paid_amount_cents = 0
            amount_data = data.get('amount')
            if isinstance(amount_data, dict):
                paid_amount_cents = amount_data.get('total', 0)
            elif data.get('total_fee'):
                try:
                    paid_amount_cents = int(data.get('total_fee', 0))
                except (ValueError, TypeError):
                    pass
            if paid_amount_cents and abs(Decimal(str(paid_amount_cents)) / 100 - order.amount) > Decimal('0.01'):
                logger.warning(f"WeChat payment amount mismatch for order {order_no}: expected {order.amount}, got {paid_amount_cents}")
                return {"code": "FAIL", "msg": "金额不匹配"}

            order.status = OrderStatus.PAID
            order.transaction_id = data.get('transaction_id')
            order.paid_at = datetime.now(timezone.utc)
            await db.flush()

            license_result = await db.execute(
                select(License).filter(License.user_id == order.user_id).with_for_update()
            )
            existing_license = license_result.scalar_one_or_none()
            if existing_license:
                # 终身会员不允许被任何支付降级
                if existing_license.plan_type == PlanType.LIFETIME:
                    logger.info(f"User {order.user_id} is lifetime member, skipping license downgrade from wechat order {order_no}")
                else:
                    existing_license.license_type = LicenseType.PRO
                    existing_license.plan_type = order.plan_type
                    # 检查用户是否被禁用
                    order_user_result = await db.execute(select(User).where(User.id == order.user_id))
                    order_user = order_user_result.scalar_one_or_none()
                    existing_license.is_valid = order_user.is_active if order_user else True
                    existing_license.trial_start = None
                    existing_license.trial_end = None
                    from ..services.license_service import calc_renewal_expiry
                    existing_license.expiry_date = calc_renewal_expiry(existing_license.expiry_date, order.plan_type)
                    # 在线支付无激活码，用订单号标识来源
                    if not existing_license.license_key:
                        existing_license.license_key = f"WXPAY-{order_no}"
                await db.flush()
            else:
                from ..services.license_service import PLAN_DELTAS
                now = datetime.now(timezone.utc)
                expiry = None
                if order.plan_type == PlanType.LIFETIME:
                    expiry = None
                elif order.plan_type in PLAN_DELTAS:
                    expiry = now + PLAN_DELTAS[order.plan_type]
                # 检查用户是否被禁用
                order_user_result2 = await db.execute(select(User).where(User.id == order.user_id))
                order_user2 = order_user_result2.scalar_one_or_none()
                new_license = License(
                    user_id=order.user_id,
                    license_type=LicenseType.PRO,
                    plan_type=order.plan_type,
                    license_key=f"WXPAY-{order_no}",
                    is_valid=order_user2.is_active if order_user2 else True,
                    expiry_date=expiry,
                )
                db.add(new_license)
                await db.flush()

            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to commit wechat callback for order {order_no}: {e}")
                return {"code": "FAIL", "msg": "数据库提交失败"}
    
    return {"code": "SUCCESS", "msg": "OK"}


@router.get("/orders", summary="获取订单列表（仅管理员）")
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Order)
        .offset(skip)
        .limit(limit)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": order.id,
                "user_id": order.user_id,
                "order_no": order.order_no,
                "plan_type": order.plan_type,
                "payment_method": order.payment_method,
                "amount": order.amount,
                "status": order.status,
                "transaction_id": order.transaction_id,
                "paid_at": order.paid_at,
                "created_at": order.created_at
            }
            for order in orders
        ]
    }


@router.get("/order-status/{order_id}", summary="查询订单状态")
async def get_order_status(
    order_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "status": order.status.value,
        "plan_type": order.plan_type.value if order.plan_type else None,
        "amount": float(order.amount),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


@router.get("/methods", summary="获取支持的支付方式")
async def get_payment_methods():
    from ..services.payment_service import _get_alipay_instance, _get_wechat_client

    alipay_available = _get_alipay_instance() is not None
    wechat_available = _get_wechat_client() is not None

    return {
        "methods": [
            {
                "id": "alipay",
                "name": "支付宝",
                "description": "使用支付宝扫码支付",
                "icon": "alipay",
                "support_qr_code": True,
                "available": alipay_available,
                "unavailable_hint": "在线支付暂未开通，请联系客服购买激活码" if not alipay_available else "",
            },
            {
                "id": "wechat",
                "name": "微信支付",
                "description": "使用微信扫码支付",
                "icon": "wechat",
                "support_qr_code": True,
                "available": wechat_available,
                "unavailable_hint": "在线支付暂未开通，请联系客服购买激活码" if not wechat_available else "",
            },
        ],
        "any_online_available": alipay_available or wechat_available,
    }