from pydantic_settings import BaseSettings
from typing import List, Optional
import os
import sys


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./videogen.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    HMAC_SIGN_KEY: str = ""
    TRIAL_DAYS: int = 7
    GRACE_HOURS: int = 2

    ALIPAY_APP_ID: str = ""
    ALIPAY_PRIVATE_KEY_PATH: str = "keys/alipay_private_key.pem"
    ALIPAY_PUBLIC_KEY_PATH: str = "keys/alipay_public_key.pem"
    ALIPAY_NOTIFY_URL: str = ""

    WECHAT_MCH_ID: str = ""
    WECHAT_API_KEY: str = ""
    WECHAT_CERT_PATH: str = ""
    WECHAT_KEY_PATH: str = ""
    WECHAT_NOTIFY_URL: str = ""

    SITE_BASE_URL: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    CORS_ORIGINS: List[str] = ["https://api.videogen.com"]

    RATE_LIMIT_PER_MINUTE: int = 60

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/videogen.log"
    LOG_FILE_MAX_BYTES: int = 50 * 1024 * 1024
    LOG_FILE_BACKUP_COUNT: int = 5

    CLEANUP_INTERVAL_HOURS: int = 6
    AUDIT_LOG_RETENTION_DAYS: int = 90
    PAYMENT_NOTIFY_RETENTION_DAYS: int = 90
    EXPIRED_ORDER_RETENTION_DAYS: int = 30
    HEARTBEAT_RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @classmethod
    def from_env(cls):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CORS_ORIGINS="):
                        os.environ["CORS_ORIGINS"] = line.split("=", 1)[1]
                        break
        except Exception:
            pass
        return cls()


settings = Settings.from_env()

_INSECURE_DEFAULTS = {
    "JWT_SECRET_KEY": "",
    "HMAC_SIGN_KEY": "",
    "DATABASE_URL": "sqlite+aiosqlite:///./videogen.db",
}


def check_production_safety():
    unsafe = []
    for key, default in _INSECURE_DEFAULTS.items():
        val = getattr(settings, key)
        if val == default or (isinstance(val, str) and not val.strip()):
            unsafe.append(key)
    if not settings.ADMIN_PASSWORD:
        unsafe.append("ADMIN_PASSWORD")
    if unsafe:
        env_name = os.environ.get("VIDEOGEN_ENV", "").lower()
        if env_name == "production":
            print(f"CRITICAL: 不安全的配置: {', '.join(unsafe)}")
            print("生产环境必须在 .env 文件中设置上述配置项")
            sys.exit(1)
        else:
            critical_keys = [k for k in unsafe if k in ("JWT_SECRET_KEY", "HMAC_SIGN_KEY")]
            if critical_keys:
                print(f"CRITICAL: 必须配置: {', '.join(critical_keys)}")
                print("请在 .env 文件中设置上述配置项（系统无法在没有这些配置的情况下安全运行）")
                sys.exit(1)
            print(f"警告: 检测到不安全的配置: {', '.join(unsafe)}")
            print("建议在 .env 文件中设置上述配置项（生产环境下将阻止启动）")
