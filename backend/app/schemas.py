from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class LicenseActivate(BaseModel):
    license_key: str = Field(..., min_length=1, max_length=100)


class PaymentCreateOrder(BaseModel):
    plan_type: str = Field(..., pattern=r"^(monthly|yearly|lifetime)$")
    payment_method: str = Field(..., pattern=r"^(alipay|wechat)$")


class HeartbeatRequest(BaseModel):
    fingerprint: Optional[str] = None
    app_version: Optional[str] = None


class LicenseData(BaseModel):
    _sig: Optional[str] = None
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


class OrderResponse(BaseModel):
    order_id: str
    payment_url: Optional[str] = None
    qr_code: Optional[str] = None


class VersionInfo(BaseModel):
    has_update: bool
    version: Optional[str] = None
    release_date: Optional[str] = None
    changelog: Optional[List[str]] = None
    file_size: Optional[int] = None
    download_url: Optional[str] = None
    priority: Optional[str] = "normal"
    force_update: Optional[bool] = False


class TokenData(BaseModel):
    user_id: int
    username: str
