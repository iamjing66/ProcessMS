"""文件编号规则：工序代码-YYYYMM-4位流水号（如 CN-202611-0001）。"""
from __future__ import annotations

import re
from typing import Optional

from config import settings
from utils.exceptions import validation_error
from utils.time import business_now

PROCESS_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,4}$")


def validate_process_code(process_code: str) -> str:
    """校验工序代码格式 ^[A-Z0-9]{2,4}$。"""
    code = (process_code or "").strip().upper()
    if not PROCESS_CODE_PATTERN.match(code):
        raise validation_error("process_code", "工序代码应为 2-4 位大写字母或数字")
    return code


def normalize_process_code(
    process_code: Optional[str], process_step: Optional[str] = None
) -> str:
    """确定工序代码：显式传入优先；未传时按契约固定使用默认值 GEN。"""
    if process_code is not None and str(process_code).strip() != "":
        return validate_process_code(str(process_code))
    return validate_process_code(settings.DEFAULT_PROCESS_CODE)


def current_period() -> str:
    """当前业务时区的年月 YYYYMM。"""
    return business_now().strftime("%Y%m")


def format_file_number(process_code: str, period: str, seq: int) -> str:
    """拼装文件编号。"""
    width = max(4, int(settings.FILE_NUMBER_SEQ_LENGTH))
    return f"{process_code}-{period}-{seq:0{width}d}"
