"""版本号规则 Vx.y.z 的解析、校验与递增。"""
from __future__ import annotations

import re
from typing import Tuple

from utils.exceptions import validation_error

VERSION_PATTERN = re.compile(r"^V\d+\.\d+\.\d+$")
VERSION_TYPES = ("major", "minor", "patch")


def validate_version(version: str) -> str:
    """校验并规范化版本号（强制 V 大写前缀），格式错误 -> 400 VERSION_FORMAT_INVALID。"""
    from utils.exceptions import AppError

    text = (version or "").strip()
    if text and text[0] == "v":
        text = "V" + text[1:]
    if not VERSION_PATTERN.match(text):
        raise AppError(
            400,
            "VERSION_FORMAT_INVALID",
            "版本号格式应为 Vx.y.z",
            {"version": "版本号格式应为 Vx.y.z"},
        )
    return text


def parse_version(version: str) -> Tuple[int, int, int]:
    """解析版本号，失败抛 VERSION_FORMAT_INVALID。"""
    from utils.exceptions import AppError

    try:
        text = validate_version(version)
        major, minor, patch = text[1:].split(".")
        return int(major), int(minor), int(patch)
    except ValueError:
        raise AppError(400, "VERSION_FORMAT_INVALID", "版本号格式应为 Vx.y.z")


def next_version(current_version: str, version_type: str = "patch") -> str:
    """按 major/minor/patch 规则生成下一个版本号。"""
    from utils.exceptions import AppError

    if version_type not in VERSION_TYPES:
        raise validation_error("version_type", "version_type 必须是 major/minor/patch")
    major, minor, patch = parse_version(current_version)
    if version_type == "major":
        major, minor, patch = major + 1, 0, 0
    elif version_type == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"V{major}.{minor}.{patch}"


def is_valid_version(version: str) -> bool:
    return bool(VERSION_PATTERN.match(version or ""))
