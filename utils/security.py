"""安全工具：bcrypt 密码哈希 + PyJWT 令牌。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from config import settings
from utils.exceptions import AppError

# bcrypt 算法上限 72 字节
BCRYPT_MAX_BYTES = 72
PASSWORD_MIN_BYTES = 6


def validate_password(password: str) -> str:
    """校验密码长度（6-72 字节），返回原密码。"""
    if not isinstance(password, str):
        raise AppError(400, "PASSWORD_INVALID", "密码长度需为 6-72 字节")
    size = len(password.encode("utf-8"))
    if size < PASSWORD_MIN_BYTES or size > BCRYPT_MAX_BYTES:
        raise AppError(400, "PASSWORD_INVALID", "密码长度需为 6-72 字节")
    return password


def hash_password(password: str) -> str:
    """使用 bcrypt 直接哈希密码（cost 12）。"""
    validate_password(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码，任何异常都视为不匹配。"""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:BCRYPT_MAX_BYTES],
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str,
    uid: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """签发 JWT（HS256），载荷 {sub, uid, iat, exp}。"""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "uid": uid,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """解析 JWT；过期/非法分别抛对应业务异常。"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录凭证无效")
