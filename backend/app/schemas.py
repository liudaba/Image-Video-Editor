from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import re


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    fingerprint: Optional[str] = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9:_\-\.]*$")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6位")
        return v


class UserLogin(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)


class LicenseActivate(BaseModel):
    license_key: str = Field(..., min_length=1, max_length=100)


class PaymentCreateOrder(BaseModel):
    plan_type: str = Field(..., pattern=r"^(monthly|quarterly|yearly|lifetime)$")
    payment_method: str = Field(..., pattern=r"^(alipay|wechat)$")


class HeartbeatRequest(BaseModel):
    fingerprint: Optional[str] = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9:_\-\.]*$")
    app_version: Optional[str] = Field(None, max_length=50, pattern=r"^[\d\.\-a-zA-Z]*$")


class LicenseData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, by_alias=True)

    sig: Optional[str] = Field(None, alias="_sig")
    sig_ver: Optional[int] = Field(None, alias="_sig_ver")
    username: str
    license_type: str
    plan_type: Optional[str] = None
    is_valid: bool
    days_left: int
    trial_start: Optional[str] = None
    trial_end: Optional[str] = None
    expiry_date: Optional[str] = None
    license_key: Optional[str] = None
    offline_until: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    license: Optional[LicenseData] = None


class ActivateResponse(BaseModel):
    license: Optional[LicenseData] = None
    expiry_date: Optional[str] = None


class LicenseStatusResponse(BaseModel):
    license: Optional[LicenseData] = None
    reason: Optional[str] = None


class HeartbeatResponse(BaseModel):
    is_valid: bool
    license: Optional[LicenseData] = None
    reason: Optional[str] = None
    timestamp: Optional[float] = None


class OrderResponse(BaseModel):
    order_id: str
    payment_url: Optional[str] = None
    qr_code: Optional[str] = None
    method: Optional[str] = None
    message: Optional[str] = None


class VersionInfo(BaseModel):
    has_update: Optional[bool] = False
    version: Optional[str] = None
    release_date: Optional[str] = None
    changelog: Optional[List[str]] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    download_url: Optional[str] = None
    priority: Optional[str] = "normal"
    force_update: Optional[bool] = False
    is_active: Optional[bool] = True
    # 增量补丁更新字段
    update_type: Optional[str] = "full"  # full / patch
    patch_url: Optional[str] = None
    patch_hash: Optional[str] = None
    patch_size: Optional[int] = None
    from_version: Optional[str] = None


class TokenData(BaseModel):
    user_id: int
    username: str
    exp: float = 0


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6位")
        return v
