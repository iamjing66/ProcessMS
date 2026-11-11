# -*- coding: utf-8 -*-
"""纯函数单元测试：版本号、文件编号、分页、调度时间、密码与令牌。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils.exceptions import AppError


# ---------------------------------------------------------------------------
# 版本号规则
# ---------------------------------------------------------------------------
def test_version_increment_rules():
    from utils.versioning import next_version

    assert next_version("V1.2.3", "major") == "V2.0.0"
    assert next_version("V1.2.3", "minor") == "V1.3.0"
    assert next_version("V1.2.3", "patch") == "V1.2.4"
    assert next_version("V1.2.3") == "V1.2.4"  # 默认 patch
    assert next_version("V9.9.9", "major") == "V10.0.0"


def test_version_parse_and_validate():
    from utils.versioning import is_valid_version, next_version, parse_version, validate_version

    assert parse_version("V2.3.4") == (2, 3, 4)
    assert validate_version("v1.0.0") == "V1.0.0"
    assert is_valid_version("V1.0.0") is True
    assert is_valid_version("1.0.0") is False
    assert is_valid_version("V1.0") is False

    for bad in ["1.0.0", "V1.0", "Vx.y.z", "", "V1.0.0.0"]:
        with pytest.raises(AppError):
            validate_version(bad)

    with pytest.raises(AppError):
        parse_version("bad")

    with pytest.raises(AppError) as exc:
        next_version("V1.0.0", "super")
    assert exc.value.code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 文件编号规则
# ---------------------------------------------------------------------------
def test_process_code_normalization():
    from utils.file_number import normalize_process_code, validate_process_code

    assert normalize_process_code(None) == "GEN"
    assert normalize_process_code("") == "GEN"
    assert normalize_process_code("cn") == "CN"
    assert validate_process_code("A1") == "A1"
    for bad in ["车削", "ABCDE", "A", "a-b", ""]:
        with pytest.raises(AppError):
            validate_process_code(bad)


def test_file_number_format():
    from utils.file_number import current_period, format_file_number

    assert format_file_number("CN", "202611", 1) == "CN-202611-0001"
    assert format_file_number("CN", "202611", 42) == "CN-202611-0042"
    # 超过 4 位不截断
    assert format_file_number("CN", "202611", 12345) == "CN-202611-12345"
    period = current_period()
    assert len(period) == 6 and period.isdigit()


# ---------------------------------------------------------------------------
# 分页工具
# ---------------------------------------------------------------------------
def test_pagination_normalize_and_result():
    from utils.pagination import check_sort, normalize_page, page_result

    assert normalize_page(0, 0) == (1, 1)
    assert normalize_page(-3, -5) == (1, 1)
    assert normalize_page(1, 1000) == (1, 100)
    assert normalize_page(2, 10) == (2, 10)

    result = page_result([1, 2], total=25, page=1, size=10)
    assert result == {"items": [1, 2], "total": 25, "page": 1, "size": 10, "pages": 3}
    assert page_result([], total=0, page=1, size=10)["pages"] == 0

    assert check_sort("file_number", ["file_number"], "id", "asc") == ("file_number", "asc")
    with pytest.raises(AppError):
        check_sort("bad", ["file_number"], "file_number", "desc")
    with pytest.raises(AppError):
        check_sort("file_number", ["file_number"], "file_number", "sideways")


# ---------------------------------------------------------------------------
# 每日 0 点调度时间计算（UTC naive 入参/出参）
# ---------------------------------------------------------------------------
def test_scheduler_next_run_at():
    from utils.scheduler import next_run_at

    tz = "Asia/Shanghai"
    # UTC 04:30 = 上海 12:30 → 下一次上海 0 点 = UTC 16:00（当天）
    now = datetime(2026, 11, 11, 4, 30, 0)
    assert next_run_at(now, tz_name=tz) == datetime(2026, 11, 11, 16, 0, 0)

    # 上海 23:59:59（UTC 15:59:59）→ 下一次仍是 UTC 16:00
    late = datetime(2026, 11, 11, 15, 59, 59)
    assert next_run_at(late, tz_name=tz) == datetime(2026, 11, 11, 16, 0, 0)

    # 已过当天 0 点（UTC 16:00 整）→ 次日 0 点
    exact = datetime(2026, 11, 11, 16, 0, 0)
    assert next_run_at(exact, tz_name=tz) == datetime(2026, 11, 12, 16, 0, 0)


# ---------------------------------------------------------------------------
# 密码与令牌
# ---------------------------------------------------------------------------
def test_password_hash_and_verify():
    from utils.security import hash_password, validate_password, verify_password

    hashed = hash_password("Test@12345")
    assert hashed.startswith("$2")
    assert verify_password("Test@12345", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert verify_password("", hashed) is False

    for bad in ["", "123", "a" * 73]:
        with pytest.raises(AppError) as exc:
            validate_password(bad)
        assert exc.value.code == "PASSWORD_INVALID"


def test_jwt_create_and_decode():
    from utils.security import create_access_token, decode_token

    token = create_access_token("engineer01", 11)
    payload = decode_token(token)
    assert payload["sub"] == "engineer01"
    assert payload["uid"] == 11
    assert "exp" in payload

    expired = create_access_token("engineer01", 11, expires_delta=timedelta(seconds=-5))
    with pytest.raises(AppError) as exc:
        decode_token(expired)
    assert exc.value.code == "AUTH_TOKEN_EXPIRED"

    with pytest.raises(AppError) as exc:
        decode_token("not-a-token")
    assert exc.value.code == "AUTH_TOKEN_INVALID"


# ---------------------------------------------------------------------------
# 工序代码映射（配置）
# ---------------------------------------------------------------------------
def test_business_timezone_helpers():
    from utils.time import business_now, utcnow

    now = utcnow()
    assert now.tzinfo is None  # 统一存 UTC naive
    business = business_now()
    assert business is not None