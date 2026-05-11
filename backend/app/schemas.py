from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import re


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    fingerprint: Optional[str] = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9:_\-\.]*$")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含至少一个数字")
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
    username: str
    license_type: str
    is_valid: bool
    days_left: int
    trial_start: Optional[str] = None
    trial_end: Optional[str] = None
    expiry_date: Optional[str] = None
    license_key: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    license: Optional[LicenseData] = None


class ActivateResponse(BaseModel):
    license: Optional[LicenseData] = None
    expiry_date: Optional[str] = None


class LicenseStatusResponse(BaseModel):
    license: Optional[LicenseData] = None


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
    has_update: bool
    version: Optional[str] = None
    release_date: Optional[str] = None
    changelog: Optional[List[str]] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    download_url: Optional[str] = None
    priority: Optional[str] = "normal"
    force_update: Optional[bool] = False


class TokenData(BaseModel):
    user_id: int
    username: str
    exp: float = 0


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含至少一个数字")
        return v
