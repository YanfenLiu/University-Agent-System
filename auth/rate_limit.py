"""登录接口限流配置（slowapi）"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# 登录端点专用限流：每 IP 每分钟 5 次
LOGIN_LIMIT = "5/minute"
