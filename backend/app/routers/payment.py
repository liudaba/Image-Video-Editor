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
    create_order,
    generate_payment_qr_code,
    get_payment_callback_url,
    verify_alipay_signature,
    verify_wechat_signature
)

logger = logging.getLogger("videogen")
router = APIRouter(prefix="/payment", tags=["payment"])


@router.post("/create-order", response_model=OrderResponse, summary="创建支付订单")
async def create_payment_order(
    order_data: PaymentCreateOrder,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    plan_type = PlanType(order_data.plan_type)
    order = await create_order(db, current_user.id, plan_type, order_data.payment_method)
    
    # 生成模拟支付二维码或链接
    if order_data.payment_method == "alipay":
        qr_code = generate_payment_qr_code(order.order_no, float(order.amount), "alipay")
        callback_url = get_payment_callback_url("alipay")
        payment_url = f"https://openapi.alipay.com/gateway.do?order_no={order.order_no}&amount={order.amount}"
    else:  # wechat
        qr_code = generate_payment_qr_code(order.order_no, float(order.amount), "wechat")
        callback_url = get_payment_callback_url("wechat")
        payment_url = None  # 微信支付可能返回二维码图片
    
    # 更新订单中的支付链接
    order.payment_url = payment_url
    await db.flush()
    await db.commit()
    
    return OrderResponse(
        order_id=order.order_no,
        payment_url=payment_url,
        qr_code=qr_code
    )


@router.post("/callback/alipay", summary="支付宝回调")
async def alipay_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    params = dict(form_data)
    
    # 验证签名
    if not verify_alipay_signature(params, ""):  # 实际应用中传入公钥
        raise HTTPException(status_code=400, detail="签名验证失败")
    
    # 处理支付结果
    order_no = params.get('out_trade_no')
    trade_status = params.get('trade_status')
    
    if trade_status in ['TRADE_SUCCESS', 'TRADE_FINISHED']:
        # 更新订单状态
        result = await db.execute(
            select(Order).filter(Order.order_no == order_no)
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            order.transaction_id = params.get('trade_no')
            await db.flush()
            await db.commit()
            
            # 这里可以添加激活许可证的逻辑
    
    return {"result": "success"}


@router.post("/callback/wechat", summary="微信支付回调")
async def wechat_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.body()
    data = json.loads(body.decode('utf-8'))
    
    # 验证签名
    headers = request.headers
    signature = headers.get('Wechatpay-Signature')
    if not verify_wechat_signature(data, ""):  # 实际应用中传入API密钥
        raise HTTPException(status_code=400, detail="签名验证失败")
    
    # 处理支付结果
    order_no = data.get('out_trade_no')
    trade_state = data.get('trade_state')
    
    if trade_state == 'SUCCESS':
        # 更新订单状态
        result = await db.execute(
            select(Order).filter(Order.order_no == order_no)
        )
        order = result.scalar_one_or_none()
        
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            order.transaction_id = data.get('transaction_id')
            await db.flush()
            await db.commit()
            
            # 这里可以添加激活许可证的逻辑
    
    return {"result": "success"}


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
