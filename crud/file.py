from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime

from models.file import ProcessFile, FileVersion, FileOperationLog, FileStatus
from schemas.file import FileCreate, FileUpdate, FileSearch
from utils.file_upload import generate_file_number

class FileCRUD:
    @staticmethod
    def create_file(db: Session, file_data: FileCreate, uploader_id: int, file_info: dict) -> ProcessFile:
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
            remarks=file_data.remarks,
            initial_upload_time=datetime.utcnow(),
            last_update_time=datetime.utcnow()
        )
        
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        return db_file

    @staticmethod
    def get_file_by_id(db: Session, file_id: int) -> Optional[ProcessFile]:
        result = db.execute(select(ProcessFile).where(ProcessFile.id == file_id))
        return result.scalar_one_or_none()

    @staticmethod
    def get_files(db: Session, skip: int = 0, limit: int = 100) -> List[ProcessFile]:
        result = db.execute(
            select(ProcessFile)
            .where(ProcessFile.file_status != FileStatus.DELETED)
            .order_by(ProcessFile.last_update_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    def search_files(db: Session, search: FileSearch) -> List[ProcessFile]:
        query = select(ProcessFile).where(ProcessFile.file_status != FileStatus.DELETED)
        
        if search.file_name:
            query = query.where(ProcessFile.file_name.contains(search.file_name))
        if search.file_number:
            query = query.where(ProcessFile.file_number.contains(search.file_number))
        if search.process_step:
            query = query.where(ProcessFile.process_step.contains(search.process_step))
        
        query = query.order_by(ProcessFile.last_update_time.desc())
        
        result = db.execute(query)
        return result.scalars().all()

    @staticmethod
    def update_file_status(db: Session, file_id: int, status: FileStatus) -> Optional[ProcessFile]:
        file = FileCRUD.get_file_by_id(db, file_id)
        if file:
            file.file_status = status
            file.last_update_time = datetime.utcnow()
            db.commit()
            db.refresh(file)
        return file

    @staticmethod
    def create_file_version(db: Session, file_id: int, version_data: dict) -> FileVersion:
        db_version = FileVersion(
            file_id=file_id,
            version=version_data["version"],
            file_path=version_data["file_path"],
            uploader_id=version_data["uploader_id"],
            upload_time=datetime.utcnow(),
            change_description=version_data.get("change_description"),
            file_size=version_data["file_size"]
        )
        db.add(db_version)
        db.commit()
        db.refresh(db_version)
        return db_version

    @staticmethod
    def log_file_operation(db: Session, operation_data: dict):
        db_log = FileOperationLog(
            file_id=operation_data["file_id"],
            operator_id=operation_data["operator_id"],
            operation_type=operation_data["operation_type"],
            operation_time=datetime.utcnow(),
            operation_details=operation_data["operation_details"],
            ip_address=operation_data.get("ip_address", "127.0.0.1")
        )
        db.add(db_log)
        db.commit()

file_crud = FileCRUD()