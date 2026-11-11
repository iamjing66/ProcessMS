"""工艺文件数据访问层（全部异步，只 flush 不 commit）。"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from dependencies.permissions import visibility_condition
from models.approval import ApprovalFlow, ApprovalStep, FileSignature
from models.catalog import FileNumberSequence
from models.enums import FileStatus
from models.file import FileOperationLog, FileVersion, ProcessFile
from models.user import User
from utils.exceptions import AppError
from utils.file_number import current_period, format_file_number
from utils.names import build_name_key
from utils.pagination import like_contains
from utils.time import utcnow

FILE_SORT_FIELDS = ("last_update_time", "initial_upload_time", "file_number", "file_name")
LOG_SORT_FIELDS = ("operation_time",)


# ---------------------------------------------------------------------------
# 预加载选项
# ---------------------------------------------------------------------------
def base_file_options():
    return [
        selectinload(ProcessFile.creator),
        selectinload(ProcessFile.uploader),
        selectinload(ProcessFile.current_approver),
    ]


def detail_file_options():
    return base_file_options() + [
        selectinload(ProcessFile.versions).selectinload(FileVersion.uploader),
        selectinload(ProcessFile.flows).selectinload(ApprovalFlow.initiator),
        selectinload(ProcessFile.flows).selectinload(ApprovalFlow.planned_approver),
        selectinload(ProcessFile.flows)
        .selectinload(ApprovalFlow.steps)
        .selectinload(ApprovalStep.approver),
        selectinload(ProcessFile.signatures).selectinload(FileSignature.signer),
    ]


# ---------------------------------------------------------------------------
# 编号与创建
# ---------------------------------------------------------------------------
async def _next_sequence(db: AsyncSession, process_code: str, period: str) -> int:
    """原子自增 (process_code, period) 流水号。"""
    result = await db.execute(
        update(FileNumberSequence)
        .where(
            FileNumberSequence.process_code == process_code,
            FileNumberSequence.period == period,
        )
        .values(
            last_seq=FileNumberSequence.last_seq + 1,
            updated_at=utcnow(),
        )
    )
    if result.rowcount:
        seq = await db.scalar(
            select(FileNumberSequence.last_seq).where(
                FileNumberSequence.process_code == process_code,
                FileNumberSequence.period == period,
            )
        )
        return int(seq or 1)
    row = FileNumberSequence(
        process_code=process_code, period=period, last_seq=1, updated_at=utcnow()
    )
    db.add(row)
    await db.flush()
    return 1


async def create_file(
    db: AsyncSession,
    *,
    file_name: str,
    name_key: str,
    process_code: str,
    process_step: str,
    version: str,
    uploader_id: int,
    creator_id: int,
    relative_path: str,
    file_type: str,
    file_size: int,
    file_hash: str,
    remarks: Optional[str] = None,
) -> ProcessFile:
    """创建文件记录并生成唯一编号（编号冲突重试最多 5 次；重名直接 409）。"""
    period = current_period()
    for _ in range(5):
        try:
            async with db.begin_nested():
                seq = await _next_sequence(db, process_code, period)
                file_number = format_file_number(process_code, period, seq)
                now = utcnow()
                file = ProcessFile(
                    file_number=file_number,
                    file_name=file_name,
                    name_key=name_key,
                    file_type=file_type,
                    process_code=process_code,
                    process_step=process_step,
                    version=version,
                    uploader_id=uploader_id,
                    creator_id=creator_id,
                    initial_upload_time=now,
                    last_update_time=now,
                    file_size=file_size,
                    storage_path=relative_path,
                    file_status=int(FileStatus.DRAFT),
                    remarks=remarks,
                )
                db.add(file)
                await db.flush()
            return file
        except IntegrityError:
            # 唯一冲突可能来自 name_key（并发重名）或 file_number（编号并发）
            duplicated = await db.scalar(
                select(ProcessFile.id).where(ProcessFile.name_key == name_key)
            )
            if duplicated is not None:
                raise AppError(
                    409,
                    "FILE_NAME_DUPLICATED",
                    "同一工序代码下已存在同名文件（忽略大小写/首尾空白）",
                )
            continue
    raise AppError(409, "FILE_NUMBER_CONFLICT", "文件编号生成冲突，请重试")


async def add_file_version(
    db: AsyncSession,
    file: ProcessFile,
    *,
    version: str,
    relative_path: str,
    file_hash: str,
    file_size: int,
    uploader_id: int,
    change_description: Optional[str],
) -> FileVersion:
    row = FileVersion(
        file_id=file.id,
        version=version,
        file_path=relative_path,
        file_hash=file_hash,
        uploader_id=uploader_id,
        upload_time=utcnow(),
        change_description=(change_description or "").strip() or "未填写",
        file_size=file_size,
    )
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------
async def get_file_by_id(
    db: AsyncSession, file_id: int, *, with_detail: bool = True
) -> Optional[ProcessFile]:
    options = detail_file_options() if with_detail else base_file_options()
    stmt = (
        select(ProcessFile)
        .where(ProcessFile.id == file_id)
        .options(*options)
        .execution_options(populate_existing=True)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_file_for_detail(db: AsyncSession, file_id: int) -> Optional[ProcessFile]:
    return await get_file_by_id(db, file_id, with_detail=True)


async def find_duplicate_name(
    db: AsyncSession,
    process_code: str,
    file_name: str,
    exclude_id: Optional[int] = None,
) -> Optional[ProcessFile]:
    """同工序代码下同名未删除文件检测（使用归一化 name_key）。"""
    return await find_by_name_key(
        db, build_name_key(process_code, file_name), exclude_id=exclude_id
    )


async def find_by_name_key(
    db: AsyncSession, name_key: str, exclude_id: Optional[int] = None
) -> Optional[ProcessFile]:
    stmt = select(ProcessFile).where(
        ProcessFile.name_key == name_key,
        ProcessFile.file_status != int(FileStatus.DELETED),
    )
    if exclude_id is not None:
        stmt = stmt.where(ProcessFile.id != exclude_id)
    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def search_files(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    keyword: Optional[str] = None,
    file_number: Optional[str] = None,
    file_name: Optional[str] = None,
    process_step: Optional[str] = None,
    process_code: Optional[str] = None,
    creator_id: Optional[int] = None,
    creator_name: Optional[str] = None,
    statuses: Optional[Sequence[int]] = None,
    upload_date_start=None,
    upload_date_end=None,
    sort: str = "last_update_time",
    order: str = "desc",
) -> Tuple[List[ProcessFile], int]:
    creator_alias = aliased(User)
    conditions = [ProcessFile.file_status != int(FileStatus.DELETED)]
    vis = visibility_condition(current_user)
    if vis is not None:
        conditions.append(vis)

    if keyword:
        like = like_contains(keyword)
        conditions.append(
            or_(
                ProcessFile.file_name.like(like, escape="\\"),
                ProcessFile.file_number.like(like, escape="\\"),
                ProcessFile.process_step.like(like, escape="\\"),
                creator_alias.real_name.like(like, escape="\\"),
            )
        )
    if file_number:
        conditions.append(
            ProcessFile.file_number.like(like_contains(file_number), escape="\\")
        )
    if file_name:
        conditions.append(
            ProcessFile.file_name.like(like_contains(file_name), escape="\\")
        )
    if process_step:
        conditions.append(
            ProcessFile.process_step.like(like_contains(process_step), escape="\\")
        )
    if process_code:
        conditions.append(ProcessFile.process_code == process_code.strip().upper())
    if creator_id is not None:
        conditions.append(ProcessFile.creator_id == int(creator_id))
    if creator_name:
        conditions.append(
            creator_alias.real_name.like(like_contains(creator_name), escape="\\")
        )
    if statuses:
        conditions.append(ProcessFile.file_status.in_([int(item) for item in statuses]))
    if upload_date_start is not None:
        conditions.append(ProcessFile.initial_upload_time >= upload_date_start)
    if upload_date_end is not None:
        conditions.append(ProcessFile.initial_upload_time < upload_date_end)

    join_condition = creator_alias.id == ProcessFile.creator_id
    total = await db.scalar(
        select(func.count(ProcessFile.id))
        .select_from(ProcessFile)
        .join(creator_alias, join_condition)
        .where(*conditions)
    )

    sort_mapping = {
        "last_update_time": ProcessFile.last_update_time,
        "initial_upload_time": ProcessFile.initial_upload_time,
        "file_number": ProcessFile.file_number,
        "file_name": ProcessFile.file_name,
    }
    sort_column = sort_mapping.get(sort, ProcessFile.last_update_time)
    order_by = sort_column.asc() if order == "asc" else sort_column.desc()

    result = await db.execute(
        select(ProcessFile)
        .join(creator_alias, join_condition)
        .where(*conditions)
        .options(*base_file_options())
        .order_by(order_by, ProcessFile.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def get_versions(db: AsyncSession, file_id: int) -> List[FileVersion]:
    result = await db.execute(
        select(FileVersion)
        .where(FileVersion.file_id == file_id)
        .options(selectinload(FileVersion.uploader))
        .order_by(FileVersion.upload_time.desc(), FileVersion.id.desc())
    )
    return list(result.scalars().all())


async def get_version_by_number(
    db: AsyncSession, file_id: int, version: str
) -> Optional[FileVersion]:
    result = await db.execute(
        select(FileVersion)
        .where(FileVersion.file_id == file_id, FileVersion.version == version)
        .options(selectinload(FileVersion.uploader))
    )
    return result.scalar_one_or_none()


async def get_latest_flow(db: AsyncSession, file_id: int) -> Optional[ApprovalFlow]:
    result = await db.execute(
        select(ApprovalFlow)
        .where(ApprovalFlow.file_id == file_id)
        .options(
            selectinload(ApprovalFlow.initiator),
            selectinload(ApprovalFlow.planned_approver),
            selectinload(ApprovalFlow.steps).selectinload(ApprovalStep.approver),
        )
        .order_by(ApprovalFlow.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_active_flow(db: AsyncSession, file_id: int) -> Optional[ApprovalFlow]:
    result = await db.execute(
        select(ApprovalFlow)
        .where(ApprovalFlow.file_id == file_id, ApprovalFlow.status == 1)
        .options(
            selectinload(ApprovalFlow.initiator),
            selectinload(ApprovalFlow.planned_approver),
            selectinload(ApprovalFlow.steps).selectinload(ApprovalStep.approver),
        )
        .order_by(ApprovalFlow.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_flow_by_id(db: AsyncSession, flow_id: int) -> Optional[ApprovalFlow]:
    result = await db.execute(
        select(ApprovalFlow)
        .where(ApprovalFlow.id == flow_id)
        .options(
            selectinload(ApprovalFlow.file),
            selectinload(ApprovalFlow.initiator),
            selectinload(ApprovalFlow.planned_approver),
            selectinload(ApprovalFlow.steps).selectinload(ApprovalStep.approver),
        )
    )
    return result.scalar_one_or_none()


async def get_signatures(db: AsyncSession, file_id: int) -> List[FileSignature]:
    result = await db.execute(
        select(FileSignature)
        .where(FileSignature.file_id == file_id)
        .options(selectinload(FileSignature.signer))
        .order_by(FileSignature.signed_at.asc(), FileSignature.id.asc())
    )
    return list(result.scalars().all())


async def list_file_logs(
    db: AsyncSession, file_id: int, *, page: int, size: int
) -> Tuple[List[FileOperationLog], int]:
    total = await db.scalar(
        select(func.count(FileOperationLog.id)).where(FileOperationLog.file_id == file_id)
    )
    result = await db.execute(
        select(FileOperationLog)
        .where(FileOperationLog.file_id == file_id)
        .options(selectinload(FileOperationLog.operator))
        .order_by(FileOperationLog.operation_time.desc(), FileOperationLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    file_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    operation_types: Optional[Sequence[str]] = None,
    target_type: Optional[str] = None,
    date_start=None,
    date_end=None,
    sort: str = "operation_time",
    order: str = "desc",
) -> Tuple[List[FileOperationLog], int]:
    conditions = []
    if file_id is not None:
        conditions.append(FileOperationLog.file_id == int(file_id))
    if operator_id is not None:
        conditions.append(FileOperationLog.operator_id == int(operator_id))
    if operation_types:
        conditions.append(FileOperationLog.operation_type.in_(list(operation_types)))
    if target_type:
        conditions.append(FileOperationLog.target_type == target_type)
    if date_start is not None:
        conditions.append(FileOperationLog.operation_time >= date_start)
    if date_end is not None:
        conditions.append(FileOperationLog.operation_time < date_end)

    total = await db.scalar(
        select(func.count(FileOperationLog.id)).where(*conditions)
    )
    order_by = (
        FileOperationLog.operation_time.asc()
        if order == "asc"
        else FileOperationLog.operation_time.desc()
    )
    result = await db.execute(
        select(FileOperationLog)
        .where(*conditions)
        .options(selectinload(FileOperationLog.operator))
        .order_by(order_by, FileOperationLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().all()), int(total or 0)


async def count_versions(db: AsyncSession, file_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count(FileVersion.id)).where(FileVersion.file_id == file_id)
        )
        or 0
    )


async def list_flows(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    file_id: Optional[int] = None,
    statuses: Optional[Sequence[int]] = None,
) -> Tuple[List[ApprovalFlow], int]:
    conditions = []
    vis = visibility_condition(current_user)
    stmt = (
        select(ApprovalFlow)
        .join(ProcessFile, ProcessFile.id == ApprovalFlow.file_id)
        .where(*conditions)
    )
    if vis is not None:
        stmt = stmt.where(vis)
    if file_id is not None:
        stmt = stmt.where(ApprovalFlow.file_id == int(file_id))
    if statuses:
        stmt = stmt.where(ApprovalFlow.status.in_([int(item) for item in statuses]))

    count_stmt = (
        select(func.count(ApprovalFlow.id))
        .select_from(ApprovalFlow)
        .join(ProcessFile, ProcessFile.id == ApprovalFlow.file_id)
    )
    if vis is not None:
        count_stmt = count_stmt.where(vis)
    if file_id is not None:
        count_stmt = count_stmt.where(ApprovalFlow.file_id == int(file_id))
    if statuses:
        count_stmt = count_stmt.where(ApprovalFlow.status.in_([int(item) for item in statuses]))
    total = await db.scalar(count_stmt)

    result = await db.execute(
        stmt.options(
            selectinload(ApprovalFlow.file),
            selectinload(ApprovalFlow.initiator),
            selectinload(ApprovalFlow.planned_approver),
            selectinload(ApprovalFlow.steps).selectinload(ApprovalStep.approver),
        )
        .order_by(ApprovalFlow.created_at.desc(), ApprovalFlow.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().unique().all()), int(total or 0)
