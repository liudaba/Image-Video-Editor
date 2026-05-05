import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.services.license_service import PLAN_PRICING

_alipay_instance = None
_alipay_instance_lock = None


def _get_alipay_instance():
    global _alipay_instance, _alipay_instance_lock
    try:
        import threading
        if _alipay_instance_lock is None:
            _alipay_instance_lock = threading.Lock()
        with _alipay_instance_lock:
            if _alipay_instance is not None:
                return _alipay_instance
            from alipay import AliPay
            with open(settings.ALIPAY_PRIVATE_KEY_PATH, "r") as f:
                app_private_key = f.read()
            with open(settings.ALIPAY_PUBLIC_KEY_PATH, "r") as f:
                alipay_public_key = f.read()
            _alipay_instance = AliPay(
                appid=settings.ALIPAY_APP_ID,
                app_notify_url=settings.ALIPAY_NOTIFY_URL,
                app_private_key_string=app_private_key,
                alipay_public_key_string=alipay_public_key,
                sign_type="RSA2",
                debug=False,
            )
            return _alipay_instance
    except Exception:
        return None


def generate_order_no() -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8].upper()
    return f"VG{date_str}{short_uuid}"


async def create_alipay_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    try:
        alipay = _get_alipay_instance()
        if alipay is None:
            return {
                "order_id": order_no,
                "payment_url": f"https://videogen.com/pay/alipay?order={order_no}",
                "qr_code": None,
            }

        pricing = PLAN_PRICING.get(plan_type)
        if not pricing:
            return {"error": "无效的套餐类型"}

        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_no,
            total_amount=str(pricing["price"]),
            subject=f"短视频生成器专业版-{plan_type}",
            return_url="https://videogen.com/payment/success",
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
            "payment_url": f"https://videogen.com/pay/alipay?order={order_no}",
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
        from lxml import etree

        root = etree.fromstring(body)
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
