import logging
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import json

from ..database import get_db
from ..models import Order, User, License, LicenseKey, OrderStatus, PlanType, LicenseKeyStatus, PaymentNotifyLog, validate_order_status_transition
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


@router.post("/create-order", response_model=OrderResponse, summary="创建支付订单")
async def create_payment_order_route(
    order_data: PaymentCreateOrder,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if order_data.payment_method.lower() not in ["alipay", "wechat"]:
        raise HTTPException(status_code=400, detail="不支持的支付方式")
    
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
    form_data = await request.form()
    params = dict(form_data)
    
    if not await verify_alipay_notification(params):
        return {"code": "FAIL", "msg": "签名验证失败"}
    
    order_no = params.get('out_trade_no')
    trade_status = params.get('trade_status')
    
    if trade_status in ['TRADE_SUCCESS', 'TRADE_FINISHED']:
        notify_id = params.get('notify_id', params.get('trade_no', ''))
        existing_notify = await db.execute(
            select(PaymentNotifyLog).where(PaymentNotifyLog.notify_id == notify_id)
        )
        if existing_notify.scalar_one_or_none():
            return {"code": "SUCCESS", "msg": "OK"}

        notify_log = PaymentNotifyLog(
            notify_id=notify_id,
            order_no=order_no or "",
            payment_method="alipay",
            raw_data=json.dumps(params, ensure_ascii=False),
        )
        db.add(notify_log)
        await db.flush()

        result = await db.execute(
            select(Order).filter(Order.order_no == order_no).with_for_update()
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
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
                select(License).filter(License.user_id == order.user_id)
            )
            existing_license = license_result.scalar_one_or_none()
            if existing_license:
                existing_license.license_type = "pro"
                existing_license.is_valid = True
                from datetime import timedelta
                if order.plan_type == PlanType.MONTHLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
                elif order.plan_type == PlanType.QUARTERLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=90)
                elif order.plan_type == PlanType.YEARLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=365)
                elif order.plan_type == PlanType.LIFETIME:
                    existing_license.expiry_date = None
                await db.flush()

            await db.commit()
    
    return {"code": "SUCCESS", "msg": "OK"}


@router.post("/callback/wechat", summary="微信支付回调")
async def wechat_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.body()
    headers = request.headers
    
    if not await verify_wechat_notification(headers, body):
        return {"code": "FAIL", "msg": "签名验证失败"}
    
    try:
        data = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError:
        from defusedxml.ElementTree import fromstring as safe_fromstring
        root = safe_fromstring(body)
        data = {}
        for child in root:
            data[child.tag] = child.text
    
    order_no = data.get('out_trade_no')
    trade_state = data.get('trade_state')
    
    if trade_state == 'SUCCESS':
        wx_notify_id = data.get('transaction_id', data.get('id', ''))
        existing_notify = await db.execute(
            select(PaymentNotifyLog).where(PaymentNotifyLog.notify_id == wx_notify_id)
        )
        if existing_notify.scalar_one_or_none():
            return {"code": "SUCCESS", "msg": "OK"}

        notify_log = PaymentNotifyLog(
            notify_id=wx_notify_id,
            order_no=order_no or "",
            payment_method="wechat",
            raw_data=body.decode('utf-8')[:65535],
        )
        db.add(notify_log)
        await db.flush()

        result = await db.execute(
            select(Order).filter(Order.order_no == order_no).with_for_update()
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
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
                select(License).filter(License.user_id == order.user_id)
            )
            existing_license = license_result.scalar_one_or_none()
            if existing_license:
                existing_license.license_type = "pro"
                existing_license.is_valid = True
                from datetime import timedelta
                if order.plan_type == PlanType.MONTHLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
                elif order.plan_type == PlanType.QUARTERLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=90)
                elif order.plan_type == PlanType.YEARLY:
                    existing_license.expiry_date = datetime.now(timezone.utc) + timedelta(days=365)
                elif order.plan_type == PlanType.LIFETIME:
                    existing_license.expiry_date = None
                await db.flush()

            await db.commit()
    
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


@router.get("/methods", summary="获取支持的支付方式")
async def get_payment_methods():
    return {
        "methods": [
            {
                "id": "alipay",
                "name": "支付宝",
                "description": "使用支付宝扫码支付",
                "icon": "alipay",
                "support_qr_code": True,
            },
            {
                "id": "wechat",
                "name": "微信支付",
                "description": "使用微信扫码支付",
                "icon": "wechat",
                "support_qr_code": True,
            },
        ]
    }