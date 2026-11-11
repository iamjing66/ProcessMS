"""文件上传与路径安全工具。

文件落盘规则：UPLOAD_DIR/YYYY/MM/<uuid><ext>，数据库只存相对 UPLOAD_DIR 的路径。
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from config import BASE_DIR, settings
from utils.exceptions import AppError
from utils.time import business_now


def upload_root() -> Path:
    """运行时解析上传根目录（支持测试 monkeypatch settings.UPLOAD_DIR）。"""
    raw = Path(settings.UPLOAD_DIR)
    root = raw if raw.is_absolute() else (BASE_DIR / raw)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def ensure_upload_root() -> Path:
    return upload_root()


def validate_extension(filename: Optional[str]) -> str:
    """校验扩展名白名单，返回小写扩展名（含点）。"""
    ext = Path(filename or "").suffix.lower()
    if not ext or ext not in settings.ALLOWED_EXTENSIONS:
        shown = ext or "无扩展名"
        raise AppError(400, "FILE_TYPE_NOT_ALLOWED", f"不支持的文件类型：{shown}")
    return ext


async def save_upload_file(upload: UploadFile) -> dict:
    """分块保存上传文件，返回相对路径、大小、扩展名与 SHA-256。"""
    ext = validate_extension(upload.filename)
    now = business_now()
    target_dir = upload_root() / now.strftime("%Y") / now.strftime("%m")
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{ext}"
    target_path = target_dir / stored_name
    hasher = hashlib.sha256()
    total = 0
    chunk_size = max(64 * 1024, int(settings.UPLOAD_CHUNK_SIZE))
    limit = int(settings.MAX_FILE_SIZE)

    try:
        with target_path.open("wb") as out:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    out.close()
                    target_path.unlink(missing_ok=True)
                    max_mb = limit // (1024 * 1024)
                    raise AppError(
                        413, "FILE_SIZE_EXCEEDED", f"文件大小超过限制（{max_mb}MB）"
                    )
                hasher.update(chunk)
                out.write(chunk)
    except AppError:
        raise
    except OSError as exc:
        target_path.unlink(missing_ok=True)
        raise AppError(500, "INTERNAL_ERROR", f"文件保存失败：{exc}")
    finally:
        await upload.close()

    if total == 0:
        target_path.unlink(missing_ok=True)
        raise AppError(400, "FILE_EMPTY", "不能上传空文件")

    relative = target_path.relative_to(upload_root()).as_posix()
    return {
        "relative_path": relative,
        "file_size": total,
        "file_type": ext,
        "file_hash": hasher.hexdigest(),
        "original_name": upload.filename,
    }


def resolve_storage_path(relative_path: str) -> Path:
    """把数据库相对路径解析为绝对路径，并防止目录穿越。"""
    root = upload_root()
    candidate = (root / (relative_path or "")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise AppError(403, "FORBIDDEN", "文件路径非法")
    return candidate


def remove_stored_file(relative_path: str) -> None:
    """尽力删除磁盘文件（用于保存失败回滚）。"""
    try:
        resolve_storage_path(relative_path).unlink(missing_ok=True)
    except Exception:
        pass


def build_content_disposition(file_number: str, version: str, ext: str) -> str:
    """构造 RFC 5987 的下载响应头，避免中文/特殊字符头注入。"""
    from urllib.parse import quote

    safe_ext = ext if ext.startswith(".") else (f".{ext}" if ext else "")
    raw_name = f"{file_number}_{version}{safe_ext}"
    ascii_name = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "._-")) else "_" for ch in raw_name
    )
    utf8_name = quote(raw_name, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def guess_media_type(ext: str) -> str:
    """按扩展名推断响应 Content-Type。"""
    mapping = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain; charset=utf-8",
    }
    return mapping.get((ext or "").lower(), "application/octet-stream")


def build_stored_filename(version: str, ext: str) -> str:
    """生成给用户的下载文件名。"""
    safe_ext = ext if ext.startswith(".") else (f".{ext}" if ext else "")
    return f"{version}{safe_ext}"
