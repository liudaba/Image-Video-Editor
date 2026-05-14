import json
import time
import hashlib
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import settings
from ..database import get_db
from ..models import Order, OrderStatus, PlanType, User
from ..schemas import OrderResponse

logger = logging.getLogger("videogen")


PLAN_PRICING = {
    "monthly": {"price": 14.9, "name": "月度会员"},
    "quarterly": {"price": 39.9, "name": "季度会员"},
    "yearly": {"price": 129.9, "name": "年度会员"},
    "lifetime": {"price": 219.9, "name": "终身会员"},
}


def generate_order_no() -> str:
    import secrets
    timestamp = int(time.time())
    random_part = secrets.token_hex(4)
    return f"ORD{timestamp}{random_part}"


def calculate_plan_amount(plan_type: PlanType) -> float:
    """根据计划类型计算金额"""
    amounts = {
        PlanType.MONTHLY: 14.9,
        PlanType.QUARTERLY: 39.9,
        PlanType.YEARLY: 129.9,
        PlanType.LIFETIME: 219.9,
    }
    return amounts.get(plan_type, 0.0)


def _get_site_base_url() -> str:
    base = getattr(settings, "SITE_BASE_URL", "")
    if base:
        return base.rstrip("/")
    return "https://api.videogen.com"


def _get_alipay_instance():
    """获取支付宝实例"""
    try:
        from alipay import AliPay
        import os
        
        if not settings.ALIPAY_APP_ID or not os.path.exists(settings.ALIPAY_PRIVATE_KEY_PATH):
            return None
        
        with open(settings.ALIPAY_PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()
        
        with open(settings.ALIPAY_PUBLIC_KEY_PATH, "r") as f:
            public_key = f.read()
        
        return AliPay(
            appid=settings.ALIPAY_APP_ID,
            app_notify_url=settings.ALIPAY_NOTIFY_URL,
            app_private_key_string=private_key,
            alipay_public_key_string=public_key,
            sign_type="RSA2",
            debug=False,
        )
    except ImportError:
        return None
    except Exception:
        return None


def _get_wechat_client():
    """获取微信支付客户端"""
    try:
        from wechatpayv3 import WeChatPay, SignType
        
        if not settings.WECHAT_MCH_ID or not settings.WECHAT_API_KEY:
            return None
        
        return WeChatPay(
            mchid=settings.WECHAT_MCH_ID,
            private_key=settings.WECHAT_KEY_PATH if settings.WECHAT_KEY_PATH else None,
            certificate=settings.WECHAT_CERT_PATH if settings.WECHAT_CERT_PATH else None,
            secret=settings.WECHAT_API_KEY,
            sign_type=SignType.HMAC_SHA256,
        )
    except ImportError:
        return None
    except Exception:
        return None


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
    base_url = _get_site_base_url()
    return f"{base_url}/api/payment/callback/{method}"


def verify_alipay_signature(params: Dict, alipay_public_key: str) -> bool:
    try:
        alipay = _get_alipay_instance()
        if alipay is None:
            return False

        verify_data = {k: v for k, v in params.items() if k not in ("sign", "sign_type")}
        signature = params.get("sign")
        return alipay.verify(verify_data, signature)
    except Exception:
        return False


def verify_wechat_signature(params: Dict, wechat_api_key: str) -> bool:
    try:
        if not settings.WECHAT_API_KEY:
            return False

        sign = params.get('sign')
        if not sign:
            return False

        filtered = {k: v for k, v in params.items() if k != 'sign' and v}
        sign_str = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))
        sign_str += f"&key={settings.WECHAT_API_KEY}"
        computed_sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()

        import hmac as _hmac
        return _hmac.compare_digest(computed_sign, sign)
    except Exception:
        return False


async def create_alipay_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    """创建支付宝订单（支持扫码支付）"""
    base_url = _get_site_base_url()
    
    pricing = PLAN_PRICING.get(plan_type.lower())
    if not pricing:
        return {"error": "无效的套餐类型"}
    
    amount = pricing["price"]
    subject = f"短视频生成器-{pricing['name']}"
    
    try:
        alipay = _get_alipay_instance()
        if alipay is None:
            logger.error("Alipay SDK not configured - cannot create real payment order")
            return {"error": "支付宝支付暂未开通，请联系客服"}

        result = alipay.api_alipay_trade_precreate(
            out_trade_no=order_no,
            total_amount=str(amount),
            subject=subject,
            notify_url=settings.ALIPAY_NOTIFY_URL,
        )

        if result.get("code") == "10000":
            return {
                "order_id": order_no,
                "payment_url": None,
                "qr_code": result.get("qr_code"),
                "method": "alipay",
            }
        else:
            logger.error(f"Alipay API error: {result.get('msg')}, sub_msg: {result.get('sub_msg')}")
            return {"error": f"支付宝接口调用失败: {result.get('sub_msg') or result.get('msg')}"}
    except ImportError:
        logger.error("Alipay SDK not installed")
        return {"error": "支付宝支付暂未开通，请联系客服"}
    except Exception as e:
        logger.error(f"Alipay order creation failed: {e}", exc_info=True)
        return {"error": "支付订单创建失败，请稍后重试"}


async def create_wechat_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    """创建微信支付订单（支持扫码支付）"""
    pricing = PLAN_PRICING.get(plan_type.lower())
    if not pricing:
        return {"error": "无效的套餐类型"}
    
    amount = pricing["price"]
    amount_cents = int(amount * 100)
    description = f"短视频生成器-{pricing['name']}"
    
    try:
        wechat = _get_wechat_client()
        if wechat is None:
            logger.error("WeChat Pay SDK not configured - cannot create real payment order")
            return {"error": "微信支付暂未开通，请联系客服"}

        result = wechat.pay.transactions.native(
            out_trade_no=order_no,
            amount={
                "total": amount_cents,
                "currency": "CNY",
            },
            description=description,
            notify_url=settings.WECHAT_NOTIFY_URL,
        )

        if result and "code_url" in result:
            return {
                "order_id": order_no,
                "payment_url": None,
                "qr_code": result["code_url"],
                "method": "wechat",
            }
        else:
            logger.error(f"WeChat Pay API error: {result}")
            return {"error": "微信支付接口调用失败，请稍后重试"}
    except ImportError:
        logger.error("WeChat Pay SDK not installed")
        return {"error": "微信支付暂未开通，请联系客服"}
    except Exception as e:
        logger.error(f"WeChat order creation failed: {e}", exc_info=True)
        return {"error": "支付订单创建失败，请稍后重试"}


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
        computed_sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()

        import hmac as _hmac
        return _hmac.compare_digest(computed_sign, received_sign)
    except Exception:
        return False


async def create_payment_order(
    db: AsyncSession,
    user_id: int,
    plan_type: str,
    payment_method: str,
) -> Dict[str, Any]:
    """统一创建支付订单接口"""
    plan_type_enum = PlanType(plan_type.lower())
    order = await create_order(db, user_id, plan_type_enum, payment_method)
    
    if payment_method.lower() == "alipay":
        result = await create_alipay_order(order.order_no, plan_type, user_id)
    elif payment_method.lower() == "wechat":
        result = await create_wechat_order(order.order_no, plan_type, user_id)
    else:
        return {"error": "不支持的支付方式"}
    
    order.payment_url = result.get("payment_url")
    order.qr_code = result.get("qr_code")
    await db.flush()
    await db.commit()
    
    return result