from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_
from typing import Optional, List
from datetime import datetime
from models.file import ProcessFile, FileVersion, FileOperationLog, FileStatus
from schemas.file import FileCreate, FileUpdate, FileSearch
from utils.file_upload import generate_file_number

class FileCRUD:
    async def create_file(self, db: AsyncSession, file_data: FileCreate, uploader_id: int, file_info: dict) -> ProcessFile:
        file_number = generate_file_number(file_data.process_step)
        
        db_file = ProcessFile(
            file_number=file_number,
            file_name=file_data.file_name,
            file_type=file_info["file_type"],
            version=file_data.version,
            process_step=file_data.process_step,
            uploader_id=uploader_id,
            creator_id=uploader_id,
            file_size=file_info["file_size"],
            storage_path=file_info["file_path"],
            remarks=file_data.remarks
        )
        
        db.add(db_file)
        await db.commit()
        await db.refresh(db_file)
        return db_file

    async def get_file_by_id(self, db: AsyncSession, file_id: int) -> Optional[ProcessFile]:
        result = await db.execute(
            select(ProcessFile).where(ProcessFile.id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_files(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[ProcessFile]:
        result = await db.execute(
            select(ProcessFile)
            .where(ProcessFile.file_status != FileStatus.DELETED)
            .order_by(ProcessFile.last_update_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def search_files(self, db: AsyncSession, search: FileSearch) -> List[ProcessFile]:
        query = select(ProcessFile).where(ProcessFile.file_status != FileStatus.DELETED)
        
        if search.file_name:
            query = query.where(ProcessFile.file_name.contains(search.file_name))
        if search.file_number:
            query = query.where(ProcessFile.file_number.contains(search.file_number))
        if search.process_step:
            query = query.where(ProcessFile.process_step.contains(search.process_step))
        if search.upload_date_start:
            query = query.where(ProcessFile.initial_upload_time >= search.upload_date_start)
        if search.upload_date_end:
            query = query.where(ProcessFile.initial_upload_time <= search.upload_date_end)
        
        query = query.order_by(ProcessFile.last_update_time.desc())
        
        result = await db.execute(query)
        return result.scalars().all()

    async def update_file_status(self, db: AsyncSession, file_id: int, status: FileStatus) -> Optional[ProcessFile]:
        file = await self.get_file_by_id(db, file_id)
        if file:
            file.file_status = status
            await db.commit()
            await db.refresh(file)
        return file

    async def create_file_version(self, db: AsyncSession, file_id: int, version_data: dict) -> FileVersion:
        db_version = FileVersion(
            file_id=file_id,
            version=version_data["version"],
            file_path=version_data["file_path"],
            uploader_id=version_data["uploader_id"],
            change_description=version_data.get("change_description"),
            file_size=version_data["file_size"]
        )
        db.add(db_version)
        await db.commit()
        await db.refresh(db_version)
        return db_version

    async def log_file_operation(self, db: AsyncSession, operation_data: dict):
        db_log = FileOperationLog(**operation_data)
        db.add(db_log)
        await db.commit()

file_crud = FileCRUD()