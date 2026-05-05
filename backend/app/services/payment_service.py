import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.services.license_service import PLAN_PRICING


def generate_order_no() -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8].upper()
    return f"VG{date_str}{short_uuid}"


async def create_alipay_order(order_no: str, plan_type: str, user_id: int) -> Dict[str, Any]:
    try:
        from alipay import AliPay

        with open(settings.ALIPAY_PRIVATE_KEY_PATH, "r") as f:
            app_private_key = f.read()
        with open(settings.ALIPAY_PUBLIC_KEY_PATH, "r") as f:
            alipay_public_key = f.read()

        alipay = AliPay(
            appid=settings.ALIPAY_APP_ID,
            app_notify_url=settings.ALIPAY_NOTIFY_URL,
            app_private_key_string=app_private_key,
            alipay_public_key_string=alipay_public_key,
            sign_type="RSA2",
            debug=False,
        )

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
        return {"error": f"支付宝订单创建失败: {str(e)}"}


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
        return {"error": f"微信订单创建失败: {str(e)}"}


async def verify_alipay_notification(data: dict) -> bool:
    try:
        from alipay import AliPay

        with open(settings.ALIPAY_PRIVATE_KEY_PATH, "r") as f:
            app_private_key = f.read()
        with open(settings.ALIPAY_PUBLIC_KEY_PATH, "r") as f:
            alipay_public_key = f.read()

        alipay = AliPay(
            appid=settings.ALIPAY_APP_ID,
            app_notify_url=settings.ALIPAY_NOTIFY_URL,
            app_private_key_string=app_private_key,
            alipay_public_key_string=alipay_public_key,
            sign_type="RSA2",
            debug=False,
        )

        signature = data.pop("sign", None)
        sign_type = data.pop("sign_type", None)
        return alipay.verify(data, signature)
    except Exception:
        return False


async def verify_wechat_notification(headers: dict, body: bytes) -> bool:
    return True
