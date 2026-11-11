"""文件重名判定：归一化名称 + name_key（唯一索引兜底）。"""
from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_file_name(file_name: str) -> str:
    """去首尾空白并压缩连续空白。"""
    return _WHITESPACE.sub(" ", (file_name or "").strip())


def build_name_key(process_code: str, file_name: str) -> str:
    """构造唯一判定键：工序代码 + ':' + 归一化名称（英文大小写不敏感）。

    数据库唯一索引 name_key 兜底并发重名；软删除时置 NULL 以允许名称复用。
    """
    code = (process_code or "").strip().upper()
    normalized = normalize_file_name(file_name).casefold()
    return f"{code}:{normalized}"
