# -*- coding: utf-8 -*-
"""授权管理 - 向后兼容的统一导出模块

本文件已重构为兼容层，所有业务逻辑和UI代码已拆分至：
- auth_core.py: 纯逻辑层（LicenseManager、心跳、签名验证）
- auth_dialogs.py: UI层（LoginDialog、PurchaseDialog、PasswordResetDialog）
- auth_fingerprint.py: 弹性机器指纹（评分制指纹验证）

所有原有 import 路径保持不变，确保现有代码无需修改：
  from video_generator.license_manager import LicenseManager       ✅
  from video_generator.license_manager import check_and_show_login ✅
  from .license_manager import LicenseManager                      ✅
"""

from .auth_core import (
    LicenseManager,
    _get_verify_secret,
    _verify_signature,
    _check_clock_rollback,
    _parse_iso_to_naive,
    _get_base_dir,
    _HMAC_KEY,
    _TRIAL_DAYS,
    _GRACE_HOURS,
    _HEARTBEAT_INTERVAL,
    _HEARTBEAT_JITTER,
    _HEARTBEAT_MAX_CONSECUTIVE_FAILURES,
    _OFFLINE_TOLERANCE,
)

from .auth_dialogs import (
    LoginDialog,
    PasswordResetDialog,
    PurchaseDialog,
    check_and_show_login,
)

from .auth_fingerprint import (
    get_machine_fingerprint,
    get_fingerprint_components,
    verify_fingerprint,
    compute_fingerprint_score,
    COMPONENTS_CONFIG,
    MATCH_THRESHOLD,
    REBIND_THRESHOLD,
)
