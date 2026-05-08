import json
import time
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import settings  # 使用相对导入
from ..database import get_db
from ..models import Order, OrderStatus, PlanType, User
from ..schemas import OrderResponse


def generate_order_no() -> str:
    """生成订单号"""
    return f"ORD{int(time.time())}{int(time.time()*1000000)%1000000:06d}"


def calculate_plan_amount(plan_type: PlanType) -> float:
    """根据计划类型计算金额"""
    amounts = {
        PlanType.MONTHLY: 19.9,
        PlanType.YEARLY: 199.0,
        PlanType.LIFETIME: 599.0,
    }
    return amounts.get(plan_type, 0.0)


def generate_payment_qr_code(order_no: str, amount: float, method: str) -> str:
    """生成模拟支付二维码"""
    # 实际应用中这里会调用支付宝或微信API生成真实二维码
    # 这里只是模拟返回一个二维码内容
    return f"mock_qr_{method}_{order_no}_{amount}"


async def create_order(
    db: AsyncSession, 
    user_id: int, 
    plan_type: PlanType, 
    payment_method: str
) -> Order:
    """创建支付订单"""
    order_no = generate_order_no()
    amount = calculate_plan_amount(plan_type)
    
    order = Order(
        user_id=user_id,
        order_no=order_no,
        plan_type=plan_type,
        payment_method=payment_method,
        amount=amount,
        status=OrderStatus.PENDING,
    )
    
    db.add(order)
    await db.flush()
    
    return order


def get_payment_callback_url(method: str) -> str:
    """获取支付回调地址"""
    base_url = "https://api.videogen.com/api/payment/callback"
    return f"{base_url}/{method}"


def verify_alipay_signature(params: Dict, alipay_public_key: str) -> bool:
    """验证支付宝签名"""
    # 实际应用中这里会验证支付宝签名
    # 这里简单返回True以供测试
    return True


def verify_wechat_signature(params: Dict, wechat_api_key: str) -> bool:
    """验证微信支付签名"""
    # 实际应用中这里会验证微信支付签名
    # 这里简单返回True以供测试
    return True


async def create_alipay_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    base_url = _get_site_base_url()
    try:
        alipay = _get_alipay_instance()
        if alipay is None:
            return {
                "order_id": order_no,
                "payment_url": f"{base_url}/pay/alipay?order={order_no}",
                "qr_code": None,
            }

        pricing = PLAN_PRICING.get(plan_type)
        if not pricing:
            return {"error": "无效的套餐类型"}

        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_no,
            total_amount=str(pricing["price"]),
            subject=f"短视频生成器专业版-{plan_type}",
            return_url=f"{base_url}/payment/success",
            notify_url=settings.ALIPAY_NOTIFY_URL,
        )

        payment_url = f"https://openapi.alipay.com/gateway.do?{order_string}"

        return {
            "order_id": order_no,
            "payment_url": payment_url,
            "qr_code": None,
        }
    except ImportError:
        return {
            "order_id": order_no,
            "payment_url": f"{base_url}/pay/alipay?order={order_no}",
            "qr_code": None,
        }
    except Exception as e:
        return {"error": "支付宝订单创建失败,请稍后重试"}


async def create_wechat_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    try:
        pricing = PLAN_PRICING.get(plan_type)
        if not pricing:
            return {"error": "无效的套餐类型"}

        amount_cents = int(pricing["price"] * 100)

        return {
            "order_id": order_no,
            "payment_url": None,
            "qr_code": f"weixin://wxpay/bizpayurl?pr={order_no}",
        }
    except Exception as e:
        return {"error": "微信订单创建失败,请稍后重试"}


async def verify_alipay_notification(data: dict) -> bool:
    try:
        alipay = _get_alipay_instance()
        if alipay is None:
            return False

        verify_data = {k: v for k, v in data.items() if k not in ("sign", "sign_type")}
        signature = data.get("sign")
        return alipay.verify(verify_data, signature)
    except Exception:
        return False


async def verify_wechat_notification(headers: dict, body: bytes) -> bool:
    if not settings.WECHAT_API_KEY:
        return False
    try:
        import hashlib
        from defusedxml.ElementTree import fromstring as safe_fromstring

        root = safe_fromstring(body)
        sign_node = root.find(".//sign")
        if sign_node is None:
            return False
        received_sign = sign_node.text

        root.remove(sign_node)
        sorted_elements = sorted(root, key=lambda x: x.tag)
        sign_str = "&".join(
            f"{el.tag}={el.text}" for el in sorted_elements if el.text
        )
        sign_str += f"&key={settings.WECHAT_API_KEY}"
        computed_sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

        import hmac as _hmac
        return _hmac.compare_digest(computed_sign, received_sign)
    except Exception:
        return False
