import logging
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db, engine
from app.models import User, License, Order, OrderStatus, PlanType, PaymentNotifyLog
from app.schemas import PaymentCreateOrder, OrderResponse
from app.auth import get_current_user
from app.services.payment_service import generate_order_no, create_alipay_order, create_wechat_order
from app.services.license_service import PLAN_PRICING

logger = logging.getLogger("videogen")
router = APIRouter(prefix="/api/payment", tags=["支付"])


@router.post("/create_order")
async def create_order(
    body: PaymentCreateOrder,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pricing = PLAN_PRICING.get(body.plan_type)
    if not pricing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的套餐类型")

    order_no = generate_order_no()

    order = Order(
        user_id=user.id,
        order_no=order_no,
        plan_type=PlanType(body.plan_type),
        payment_method=body.payment_method,
        amount=Decimal(str(pricing["price"])),
        status=OrderStatus.PENDING,
    )
    db.add(order)
    await db.flush()

    if body.payment_method == "alipay":
        result = await create_alipay_order(order_no, body.plan_type, user.id)
    elif body.payment_method == "wechat":
        result = await create_wechat_order(order_no, body.plan_type, user.id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的支付方式")

    if "error" in result:
        logger.error(f"Payment order creation failed: {result['error']}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建订单失败,请稍后重试")

    return result


@router.post("/alipay_notify")
async def alipay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    data = dict(form_data)

    from app.services.payment_service import verify_alipay_notification
    if not await verify_alipay_notification(data):
        return "fail"

    trade_status = data.get("trade_status")
    out_trade_no = data.get("out_trade_no")
    trade_no = data.get("trade_no")
    total_amount = data.get("total_amount")
    notify_id = data.get("notify_id", "")

    if trade_status == "TRADE_SUCCESS":
        if notify_id:
            try:
                db.add(PaymentNotifyLog(
                    notify_id=notify_id,
                    order_no=out_trade_no or "",
                    payment_method="alipay",
                ))
                await db.flush()
            except IntegrityError:
                return "success"

        _sqlite = str(engine.url).startswith("sqlite")
        q = select(Order).where(Order.order_no == out_trade_no)
        if not _sqlite:
            q = q.with_for_update()
        result = await db.execute(q)
        order = result.scalar_one_or_none()

        if not order or order.status != OrderStatus.PENDING:
            return "success"

        if not total_amount:
            logger.warning(f"Alipay notify missing total_amount: order={order.order_no}")
            return "fail"
        if Decimal(total_amount) != order.amount:
            logger.warning(f"Alipay amount mismatch: order={order.order_no}, expected={order.amount}, got={total_amount}")
            return "fail"

        order.status = OrderStatus.PAID
        order.transaction_id = trade_no
        order.paid_at = datetime.now(timezone.utc)
        await db.flush()

        pricing = PLAN_PRICING.get(order.plan_type.value)
        if pricing:
            from app.services.license_service import extend_license
            await extend_license(db, order.user_id, pricing["days"])

    return "success"


@router.post("/wechat_notify")
async def wechat_notify(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()

    from app.services.payment_service import verify_wechat_notification
    headers = dict(request.headers)
    if not await verify_wechat_notification(headers, body):
        return {"return_code": "FAIL", "return_msg": "验签失败"}

    try:
        from defusedxml.ElementTree import fromstring as safe_fromstring
        root = safe_fromstring(body.decode("utf-8"))
    except ImportError:
        logger.error("defusedxml未安装,拒绝处理微信回调")
        return {"return_code": "FAIL", "return_msg": "服务配置错误"}
    except Exception as e:
        logger.error(f"WeChat XML parse error: {e}")
        return {"return_code": "FAIL", "return_msg": "XML解析失败"}

    try:
        out_trade_no = root.findtext(".//out_trade_no")
        transaction_id = root.findtext(".//transaction_id")
        result_code = root.findtext(".//result_code")
        total_fee = root.findtext(".//total_fee")
        nonce_str = root.findtext(".//nonce_str") or ""

        if result_code == "SUCCESS" and out_trade_no:
            notify_id = f"wx:{transaction_id}:{nonce_str}"
            try:
                db.add(PaymentNotifyLog(
                    notify_id=notify_id,
                    order_no=out_trade_no,
                    payment_method="wechat",
                ))
                await db.flush()
            except IntegrityError:
                return {"return_code": "SUCCESS", "return_msg": "OK"}

            _sqlite = str(engine.url).startswith("sqlite")
            q = select(Order).where(Order.order_no == out_trade_no)
            if not _sqlite:
                q = q.with_for_update()
            result = await db.execute(q)
            order = result.scalar_one_or_none()

            if not order or order.status != OrderStatus.PENDING:
                return {"return_code": "SUCCESS", "return_msg": "OK"}

            if total_fee:
                expected_cents = int(order.amount * 100)
                if int(total_fee) != expected_cents:
                    logger.warning(f"WeChat amount mismatch: order={order.order_no}, expected={expected_cents}, got={total_fee}")
                    return {"return_code": "FAIL", "return_msg": "金额不匹配"}
            else:
                logger.warning(f"WeChat notify missing total_fee: order={order.order_no}")
                return {"return_code": "FAIL", "return_msg": "金额校验失败"}

            order.status = OrderStatus.PAID
            order.transaction_id = transaction_id
            order.paid_at = datetime.now(timezone.utc)
            await db.flush()

            pricing = PLAN_PRICING.get(order.plan_type.value)
            if pricing:
                from app.services.license_service import extend_license
                await extend_license(db, order.user_id, pricing["days"])
    except Exception as e:
        logger.error(f"WeChat notify processing error: {e}")

    return {"return_code": "SUCCESS", "return_msg": "OK"}
