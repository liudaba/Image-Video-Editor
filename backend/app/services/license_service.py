import secrets
import string
import hashlib
import hmac as _hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..config import settings
from ..models import License, LicenseKey, User, LicenseKeyStatus, LicenseType, PlanType
from ..schemas import LicenseData

_SIG_KEY = "_sig"
_SIG_VERSION_KEY = "_sig_ver"

_ecdsa_private_key = None
_hmac_signing_key = None


def _get_ecdsa_private_key():
    global _ecdsa_private_key
    if _ecdsa_private_key is not None:
        return _ecdsa_private_key
    key_path = getattr(settings, "ECDSA_PRIVATE_KEY_PATH", "") or ""
    if not key_path:
        key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_sign_private.pem")
    if not os.path.isabs(key_path):
        key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", key_path)
    if os.path.exists(key_path):
        try:
            from cryptography.hazmat.primitives import serialization
            with open(key_path, "rb") as f:
                _ecdsa_private_key = serialization.load_pem_private_key(f.read(), password=None)
            return _ecdsa_private_key
        except Exception:
            pass
    return None


def _get_hmac_signing_key() -> bytes:
    global _hmac_signing_key
    if _hmac_signing_key is not None:
        return _hmac_signing_key
    if settings.HMAC_SIGN_KEY and settings.HMAC_SIGN_KEY.strip():
        _hmac_signing_key = settings.HMAC_SIGN_KEY.encode("utf-8")
        return _hmac_signing_key
    key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_verify_key")
    try:
        with open(key_path, "rb") as f:
            key = f.read().strip()
            if key:
                _hmac_signing_key = key
                return _hmac_signing_key
    except FileNotFoundError:
        pass
    return None


def _make_payload(data: dict) -> bytes:
    check = {k: v for k, v in data.items() if k != _SIG_KEY and k != _SIG_VERSION_KEY and v is not None}
    return json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign_license_data(data: dict) -> tuple:
    payload = _make_payload(data)
    ecdsa_key = _get_ecdsa_private_key()
    if ecdsa_key is not None:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        signature = ecdsa_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature.hex(), 2
    hmac_key = _get_hmac_signing_key()
    if hmac_key is not None:
        sig = _hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
        return sig, 1
    raise RuntimeError("No signing key configured. Set ECDSA_PRIVATE_KEY_PATH or HMAC_SIGN_KEY")


def verify_signature(data: dict, signature: str) -> bool:
    try:
        sig_ver = data.get(_SIG_VERSION_KEY, 1)
        payload = _make_payload(data)
        if sig_ver == 2:
            pubkey_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "keys", ".license_verify_pubkey.pem")
            if os.path.exists(pubkey_path):
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ec
                from cryptography.hazmat.primitives import hashes
                with open(pubkey_path, "rb") as f:
                    public_key = serialization.load_pem_public_key(f.read())
                public_key.verify(bytes.fromhex(signature), payload, ec.ECDSA(hashes.SHA256()))
                return True
        elif sig_ver == 1:
            hmac_key = _get_hmac_signing_key()
            if hmac_key is not None:
                expected = _hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
                return _hmac.compare_digest(expected, signature)
    except Exception:
        pass
    return False


def is_license_expired(license_obj: License) -> bool:
    """判断许可证是否已失效（过期或被标记无效）

    注意：此函数同时检查is_valid状态和过期时间，
    如果需要仅检查过期时间，请使用 is_license_time_expired()
    """
    if not license_obj.is_valid:
        return True
    if license_obj.expiry_date is not None:
        now = datetime.now(timezone.utc)
        exp = license_obj.expiry_date
        if exp.tzinfo is None:
            from datetime import timezone as _tz
            exp = exp.replace(tzinfo=_tz.utc)
        if exp < now:
            return True
    return False


def is_license_time_expired(license_obj: License) -> bool:
    """仅判断许可证是否已过期（不检查is_valid状态）"""
    if license_obj.expiry_date is None:
        return False
    now = datetime.now(timezone.utc)
    exp = license_obj.expiry_date
    if exp.tzinfo is None:
        from datetime import timezone as _tz
        exp = exp.replace(tzinfo=_tz.utc)
    return exp < now


# 套餐对应的有效期增量
PLAN_DELTAS = {
    PlanType.MONTHLY: timedelta(days=30),
    PlanType.QUARTERLY: timedelta(days=90),
    PlanType.YEARLY: timedelta(days=365),
    PlanType.TRIAL_15D: timedelta(days=15),
}

# 续费最大叠加倍数（防止无限叠加有效期）
MAX_STACK_MULTIPLIER = 3


def calc_renewal_expiry(existing_expiry_date, plan_type: PlanType) -> Optional[datetime]:
    """计算续费后的到期时间，带3倍上限保护

    Args:
        existing_expiry_date: 当前许可证的到期时间（可为None表示终身）
        plan_type: 新购买的套餐类型

    Returns:
        新的到期时间，终身返回None
    """
    if plan_type == PlanType.LIFETIME:
        return None

    delta = PLAN_DELTAS.get(plan_type)
    if delta is None:
        # 未知套餐类型，无法计算
        return None

    now = datetime.now(timezone.utc)
    remaining = timedelta(0)
    if existing_expiry_date:
        cur = existing_expiry_date
        if cur.tzinfo is None:
            cur = cur.replace(tzinfo=timezone.utc)
        remaining = max(cur - now, timedelta(0))
    # 如果现有到期时间为None（终身会员），视为剩余时间为0
    # 终身会员不应通过支付回调降级，但此处仅计算到期时间
    # 调用方应在调用前检查终身会员保护

    max_total = delta * MAX_STACK_MULTIPLIER
    if remaining + delta > max_total:
        return now + max_total
    else:
        return now + remaining + delta


def generate_license_key(length: int = 32) -> str:
    alphabet = string.ascii_uppercase + string.digits
    key = "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(length // 4)
    )
    return key


async def create_trial_license(db: AsyncSession, user_id: int) -> License:
    trial_days = settings.TRIAL_DAYS
    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=trial_days)

    license_obj = License(
        user_id=user_id,
        license_type=LicenseType.TRIAL,
        plan_type=PlanType.TRIAL_15D,
        is_valid=True,
        trial_start=trial_start,
        trial_end=trial_end,
        expiry_date=trial_end,
    )

    db.add(license_obj)
    await db.flush()

    return license_obj


async def activate_license(db: AsyncSession, user_id: int, license_key: str) -> Optional[Union[License, str]]:
    q = select(LicenseKey).where(LicenseKey.license_key == license_key).with_for_update()
    key_result = await db.execute(q)
    license_key_obj = key_result.scalar_one_or_none()

    if not license_key_obj:
        return None

    if license_key_obj.status == LicenseKeyStatus.REVOKED:
        return None

    if license_key_obj.status == LicenseKeyStatus.ACTIVATED:
        return None

    # 检查用户是否已是PRO会员，如果是则拒绝激活试用码（避免浪费）
    if license_key_obj.plan_type == PlanType.TRIAL_15D:
        existing_check = await db.execute(select(License).where(License.user_id == user_id).with_for_update())
        existing_check_lic = existing_check.scalar_one_or_none()
        if existing_check_lic and existing_check_lic.license_type == LicenseType.PRO:
            return "already_pro"

    # 终身会员不允许被任何激活码降级
    existing_check2 = await db.execute(select(License).where(License.user_id == user_id).with_for_update())
    existing_check_lic2 = existing_check2.scalar_one_or_none()
    if existing_check_lic2 and existing_check_lic2.plan_type == PlanType.LIFETIME:
        return "already_lifetime"

    # 检查用户是否被禁用，禁用用户不允许激活
    user_result = await db.execute(select(User).where(User.id == user_id))
    user_obj = user_result.scalar_one_or_none()
    if user_obj and not user_obj.is_active:
        return "user_disabled"

    license_key_obj.status = LicenseKeyStatus.ACTIVATED
    license_key_obj.activated_at = datetime.now(timezone.utc)
    license_key_obj.activated_by = user_id

    if license_key_obj.plan_type == PlanType.LIFETIME:
        expiry_date = None
        license_type = LicenseType.PRO
    elif license_key_obj.plan_type == PlanType.TRIAL_15D:
        expiry_delta = timedelta(days=15)
        expiry_date = datetime.now(timezone.utc) + expiry_delta
        license_type = LicenseType.TRIAL
    else:
        if license_key_obj.plan_type == PlanType.MONTHLY:
            expiry_delta = timedelta(days=30)
        elif license_key_obj.plan_type == PlanType.QUARTERLY:
            expiry_delta = timedelta(days=90)
        elif license_key_obj.plan_type == PlanType.YEARLY:
            expiry_delta = timedelta(days=365)
        else:
            expiry_delta = timedelta(days=30)

        expiry_date = datetime.now(timezone.utc) + expiry_delta
        license_type = LicenseType.PRO

    # 设置LicenseKey的到期时间，便于管理后台展示
    license_key_obj.expiry_date = expiry_date

    existing_result = await db.execute(
        select(License).where(License.user_id == user_id).with_for_update()
    )
    existing_license = existing_result.scalar_one_or_none()

    if existing_license:
        existing_license.plan_type = license_key_obj.plan_type
        if license_key_obj.plan_type == PlanType.LIFETIME:
            existing_license.license_type = LicenseType.PRO
            existing_license.license_key = license_key
            existing_license.is_valid = user_obj.is_active if user_obj else True
            existing_license.expiry_date = None
            await db.flush()
            return existing_license
        elif license_key_obj.plan_type == PlanType.TRIAL_15D:
            if existing_license.expiry_date:
                current_expiry = existing_license.expiry_date
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                remaining = max(current_expiry - now, timedelta(0))
                max_total = expiry_delta * 3
                if remaining + expiry_delta > max_total:
                    expiry_date = now + max_total
                else:
                    expiry_date = now + remaining + expiry_delta
            else:
                expiry_date = datetime.now(timezone.utc) + expiry_delta
            existing_license.trial_end = expiry_date
            if not existing_license.trial_start:
                existing_license.trial_start = datetime.now(timezone.utc)
        else:
            if existing_license.expiry_date:
                current_expiry = existing_license.expiry_date
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                remaining = max(current_expiry - now, timedelta(0))
                same_plan = (existing_license.plan_type == license_key_obj.plan_type)
                if same_plan:
                    max_total = expiry_delta * 3
                    if remaining + expiry_delta > max_total:
                        expiry_date = now + max_total
                    else:
                        expiry_date = now + remaining + expiry_delta
                else:
                    # 不同套餐升级时，保留原有剩余时间
                    expiry_date = now + remaining + expiry_delta
            else:
                expiry_date = datetime.now(timezone.utc) + expiry_delta

        existing_license.license_type = license_type
        existing_license.license_key = license_key
        existing_license.is_valid = user_obj.is_active if user_obj else True
        existing_license.expiry_date = expiry_date
        if license_key_obj.plan_type != PlanType.TRIAL_15D:
            existing_license.trial_start = None
            existing_license.trial_end = None
        await db.flush()
        return existing_license
    else:
        if license_key_obj.plan_type == PlanType.TRIAL_15D:
            expiry_date = datetime.now(timezone.utc) + expiry_delta

        license_obj = License(
            user_id=user_id,
            license_type=license_type,
            plan_type=license_key_obj.plan_type,
            license_key=license_key,
            is_valid=user_obj.is_active if user_obj else True,
            expiry_date=expiry_date,
            trial_start=datetime.now(timezone.utc) if license_type == LicenseType.TRIAL else None,
            trial_end=expiry_date if license_type == LicenseType.TRIAL else None,
        )
        db.add(license_obj)
        await db.flush()
        return license_obj


async def cleanup_expired_license_keys(db: AsyncSession) -> int:
    # 清理已激活且过期的试用码（激活后15天过期）
    activated_cutoff = datetime.now(timezone.utc) - timedelta(days=15)
    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
        .where(LicenseKey.status == LicenseKeyStatus.ACTIVATED)
        .where(LicenseKey.activated_at < activated_cutoff)
    )
    expired_activated = result.scalars().all()

    # 清理超过90天未使用的试用码（长期未激活的码才清理，给用户足够的使用窗口）
    unused_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
        .where(LicenseKey.status == LicenseKeyStatus.UNUSED)
        .where(LicenseKey.created_at < unused_cutoff)
    )
    expired_unused = result.scalars().all()

    count = 0
    for key in expired_activated + expired_unused:
        key.status = LicenseKeyStatus.REVOKED
        count += 1

    if count > 0:
        await db.flush()

    return count


def encode_license_data(license: License, username: str) -> LicenseData:
    days_left = -1
    if license.expiry_date:
        now = datetime.now(timezone.utc)
        exp = license.expiry_date
        if exp.tzinfo is None:
            from datetime import timezone as _tz
            exp = exp.replace(tzinfo=_tz.utc)
        delta = exp - now
        # 向上取整：不足1天算1天，确保用户看到的天数不会少
        days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))
    elif license.plan_type == PlanType.LIFETIME or (license.license_type == LicenseType.PRO and license.expiry_date is None):
        days_left = 9999

    expiry_str = license.expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ") if license.expiry_date else None
    trial_start_str = license.trial_start.strftime("%Y-%m-%dT%H:%M:%SZ") if license.trial_start else None
    trial_end_str = license.trial_end.strftime("%Y-%m-%dT%H:%M:%SZ") if license.trial_end else None

    # 计算离线容忍截止时间
    offline_until_str = None
    if license.is_valid:
        from ..config import settings
        now = datetime.now(timezone.utc)
        plan_type_val = license.plan_type.value if license.plan_type else None
        license_type_val = license.license_type.value if isinstance(license.license_type, str) else license.license_type.value
        # 离线容忍时长（小时），与客户端_OFFLINE_TOLERANCE保持一致
        # 商业运营版：收紧离线容忍窗口，防止钻空子
        offline_hours_map = {
            "trial": 2, "trial_15d": 2,
            "monthly": 12, "quarterly": 24,
            "yearly": 48,
            "lifetime": 72, "pro": 48,
        }
        tolerance_key = plan_type_val if plan_type_val and plan_type_val in offline_hours_map else license_type_val
        tolerance_hours = offline_hours_map.get(tolerance_key, 2)
        offline_until_dt = now + timedelta(hours=tolerance_hours)
        offline_until_str = offline_until_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 判断是否终身/试用
    is_lifetime = license.plan_type == PlanType.LIFETIME or (license.license_type == LicenseType.PRO and license.expiry_date is None)
    is_trial = license.license_type == LicenseType.TRIAL

    # 会员类型显示名称
    membership_name_map = {
        PlanType.MONTHLY: "月度会员",
        PlanType.QUARTERLY: "季度会员",
        PlanType.YEARLY: "年度会员",
        PlanType.LIFETIME: "终身会员",
        PlanType.TRIAL_15D: "试用版",
    }
    membership_type_name = membership_name_map.get(license.plan_type, "会员") if license.plan_type else "会员"

    data_without_sig = {
        "username": username,
        "license_type": license.license_type if isinstance(license.license_type, str) else license.license_type.value,
        "plan_type": license.plan_type.value if license.plan_type else None,
        "is_valid": license.is_valid,
        "is_lifetime": is_lifetime,
        "is_trial": is_trial,
        "days_left": days_left,
        "membership_type_name": membership_type_name,
        "trial_start": trial_start_str,
        "trial_end": trial_end_str,
        "expiry_date": expiry_str,
        "expires_at": expiry_str,
        "license_key": license.license_key,
        "offline_until": offline_until_str,
    }

    sig, sig_ver = sign_license_data(data_without_sig)

    return LicenseData(
        sig=sig,
        sig_ver=sig_ver,
        username=username,
        license_type=license.license_type if isinstance(license.license_type, str) else license.license_type.value,
        plan_type=license.plan_type.value if license.plan_type else None,
        is_valid=license.is_valid,
        is_lifetime=is_lifetime,
        is_trial=is_trial,
        days_left=days_left,
        membership_type_name=membership_type_name,
        trial_start=trial_start_str,
        trial_end=trial_end_str,
        expiry_date=expiry_str,
        expires_at=expiry_str,
        license_key=license.license_key,
        offline_until=offline_until_str,
    )
