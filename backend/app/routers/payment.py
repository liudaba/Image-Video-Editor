import logging
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import json

from ..database import get_db
from ..models import Order, User, OrderStatus, PlanType
from ..auth import require_admin, get_current_user
from ..schemas import PaymentCreateOrder, OrderResponse
from ..services.payment_service import (
    create_payment_order,
    create_alipay_order,
    create_wechat_order,
    verify_alipay_notification,
    verify_wechat_notification,
)

logger = logging.getLogger("videogen")
router = APIRouter(prefix="/payment", tags=["payment"])


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
        result = await db.execute(
            select(Order).filter(Order.order_no == order_no)
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            order.transaction_id = params.get('trade_no')
            order.paid_at = datetime.now(timezone.utc)
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
        result = await db.execute(
            select(Order).filter(Order.order_no == order_no)
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            order.transaction_id = data.get('transaction_id')
            order.paid_at = datetime.now(timezone.utc)
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