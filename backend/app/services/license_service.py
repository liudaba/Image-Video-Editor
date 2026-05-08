import secrets
import string
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..config import settings  # 使用相对导入
from ..database import get_db
from ..models import License, LicenseKey, User, LicenseKeyStatus
from ..schemas import LicenseData


def generate_license_key(length: int = 32) -> str:
    """生成指定长度的许可证密钥"""
    alphabet = string.ascii_uppercase + string.digits
    key = "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4)) 
        for _ in range(length // 4)
    )
    return key


def calculate_signature(payload: str) -> str:
    """使用HMAC计算签名"""
    key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_verify_key")
    try:
        with open(key_path, "rb") as f:
            signing_key = f.read().strip()
    except FileNotFoundError:
        signing_key = settings.HMAC_SIGN_KEY.encode("utf-8")
    
    signature = hmac.new(signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return signature


def verify_signature(payload: str, signature: str) -> bool:
    """验证签名是否匹配"""
    key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_verify_key")
    try:
        with open(key_path, "rb") as f:
            signing_key = f.read().strip()
    except FileNotFoundError:
        signing_key = settings.HMAC_SIGN_KEY.encode("utf-8")
    
    expected_sig = hmac.new(signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


async def create_trial_license(db: AsyncSession, user_id: int) -> License:
    """为用户创建试用许可证"""
    trial_days = settings.TRIAL_DAYS
    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=trial_days)
    
    license_obj = License(
        user_id=user_id,
        license_type="trial",
        is_valid=True,
        trial_start=trial_start,
        trial_end=trial_end,
        expiry_date=trial_end,
    )
    
    db.add(license_obj)
    await db.flush()
    
    return license_obj


async def activate_license(db: AsyncSession, user_id: int, license_key: str) -> Optional[License]:
    """激活许可证"""
    # 查找许可证密钥
    key_result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.license_key == license_key)
        .where(LicenseKey.status == LicenseKeyStatus.UNUSED)
    )
    license_key_obj = key_result.scalar_one_or_none()
    
    if not license_key_obj:
        return None
    
    # 更新许可证密钥状态
    license_key_obj.status = LicenseKeyStatus.ACTIVATED
    license_key_obj.activated_at = datetime.now(timezone.utc)
    license_key_obj.activated_by = user_id
    
    # 创建用户许可证
    if license_key_obj.plan_type == "lifetime":
        expiry_date = None
    else:
        # 根据计划类型计算过期日期
        if license_key_obj.plan_type == "monthly":
            expiry_delta = timedelta(days=30)
        elif license_key_obj.plan_type == "yearly":
            expiry_delta = timedelta(days=365)
        else:
            expiry_delta = timedelta(days=30)  # 默认为月度计划
        
        expiry_date = datetime.now(timezone.utc) + expiry_delta
    
    license_obj = License(
        user_id=user_id,
        license_type="pro",
        license_key=license_key,
        is_valid=True,
        expiry_date=expiry_date,
    )
    
    db.add(license_obj)
    await db.flush()
    
    return license_obj


def create_license_payload(username: str, license_type: str, expiry_date: Optional[datetime] = None) -> str:
    """创建许可证载荷"""
    if expiry_date:
        exp_str = expiry_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        exp_str = ""
    
    payload = f"{username}|{license_type}|{exp_str}"
    return payload


def encode_license_data(license: License, username: str) -> LicenseData:
    """将许可证对象编码为LicenseData"""
    # 创建载荷并计算签名
    payload = create_license_payload(
        username, 
        license.license_type, 
        license.expiry_date
    )
    
    sig = calculate_signature(payload)
    
    # 计算剩余天数
    days_left = -1  # 默认值，对于永久许可证
    if license.expiry_date:
        now = datetime.now(timezone.utc)
        days_left = max(0, (license.expiry_date - now).days)
    
    # 格式化日期
    expiry_str = license.expiry_date.strftime("%Y-%m-%d %H:%M:%S") if license.expiry_date else None
    trial_start_str = license.trial_start.strftime("%Y-%m-%d %H:%M:%S") if license.trial_start else None
    trial_end_str = license.trial_end.strftime("%Y-%m-%d %H:%M:%S") if license.trial_end else None
    
    return LicenseData(
        sig=sig,
        username=username,
        license_type=license.license_type,
        is_valid=license.is_valid,
        days_left=days_left,
        trial_start=trial_start_str,
        trial_end=trial_end_str,
        expiry_date=expiry_str,
        license_key=license.license_key,
    )