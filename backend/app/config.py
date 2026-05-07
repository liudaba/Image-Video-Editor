from pydantic_settings import BaseSettings
from typing import List, Optional
import os
import sys


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./videogen.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    HMAC_SIGN_KEY: str = "dev-hmac-key-change-in-production"
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

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""

    CORS_ORIGINS: List[str] = ["https://api.videogen.com", "http://localhost"]

    RATE_LIMIT_PER_MINUTE: int = 60

    LOG_LEVEL: str = "INFO"

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
    "JWT_SECRET_KEY": "dev-secret-key-change-in-production",
    "HMAC_SIGN_KEY": "dev-hmac-key-change-in-production",
}


def check_production_safety():
    unsafe = []
    for key, default in _INSECURE_DEFAULTS.items():
        if getattr(settings, key) == default:
            unsafe.append(key)
    if not settings.ADMIN_PASSWORD:
        unsafe.append("ADMIN_PASSWORD")
    if unsafe and os.getenv("VIDEOGEN_ENV") != "development":
        print(f"检测到不安全的默认配置: {', '.join(unsafe)}")
        print("请修改 .env 文件中的上述配置项")
        sys.exit(1)
    elif unsafe:
        print(f"警告: 开发环境使用默认配置: {', '.join(unsafe)}，请勿在生产环境使用!")
