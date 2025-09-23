from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from database import get_db
from crud.file import file_crud
from schemas.file import FileResponse, FileCreate, FileUpdate, FileSearch, FileVersionResponse
from dependencies.auth import get_current_user
from utils.file_upload import save_upload_file
from utils.versioning import generate_next_version
from models.file import FileStatus

router = APIRouter()

@router.post("/upload", response_model=FileResponse)
def upload_file(
    file_name: str = Form(...),
    process_step: str = Form(...),
    remarks: Optional[str] = Form(None),
    version: str = Form("V1.0.0"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """上传文件"""
    # 创建文件数据对象
    file_data = FileCreate(
        file_name=file_name,
        process_step=process_step,
        remarks=remarks,
        version=version
    )
    
    # 保存文件
    file_info = save_upload_file(file, current_user["id"])
    
    # 创建文件记录
    db_file = file_crud.create_file(db, file_data, current_user["id"], file_info)
    
    # 记录操作日志
    file_crud.log_file_operation(db, {
        "file_id": db_file.id,
        "operator_id": current_user["id"],
        "operation_type": "upload",
        "operation_details": f"上传新文件: {db_file.file_name}",
        "ip_address": "127.0.0.1"
    })
    
    return db_file

@router.get("/", response_model=List[FileResponse])
def get_files(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取文件列表"""
    return file_crud.get_files(db, skip, limit)

@router.post("/search", response_model=List[FileResponse])
def search_files(
    search: FileSearch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """搜索文件"""
    return file_crud.search_files(db, search)

@router.get("/{file_id}", response_model=FileResponse)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取文件详情"""
    db_file = file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    return db_file

@router.put("/{file_id}", response_model=FileResponse)
def update_file(
    file_id: int,
    file_name: Optional[str] = Form(None),
    process_step: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    change_description: Optional[str] = Form(None),
    new_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """更新文件"""
    # 获取原文件
    db_file = file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 准备更新数据
    update_data = FileUpdate(
        file_name=file_name,
        process_step=process_step,
        remarks=remarks,
        change_description=change_description
    )
    
    # 如果有新文件上传，创建新版本
    if new_file:
        file_info = save_upload_file(new_file, current_user["id"])
        
        # 创建版本记录
        new_version = generate_next_version(db_file.version, "minor")
        file_crud.create_file_version(db, file_id, {
            "version": new_version,
            "file_path": file_info["file_path"],
            "uploader_id": current_user["id"],
            "change_description": change_description,
            "file_size": file_info["file_size"]
        })
        
        # 更新文件信息
        db_file.version = new_version
        db_file.file_size = file_info["file_size"]
        db_file.storage_path = file_info["file_path"]
    
    # 更新其他信息
    for field, value in update_data.dict(exclude_unset=True, exclude={"change_description"}).items():
        if value is not None:
            setattr(db_file, field, value)
    
    db.commit()
    
    # 记录操作日志
    file_crud.log_file_operation(db, {
        "file_id": file_id,
        "operator_id": current_user["id"],
        "operation_type": "update",
        "operation_details": f"更新文件: {db_file.file_name}",
        "ip_address": "127.0.0.1"
    })
    
    return db_file

@router.post("/{file_id}/submit-review")
def submit_for_review(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """提交审核"""
    db_file = file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if db_file.uploader_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="无权操作此文件")
    
    db_file.file_status = FileStatus.PENDING_REVIEW
    db.commit()
    
    file_crud.log_file_operation(db, {
        "file_id": file_id,
        "operator_id": current_user["id"],
        "operation_type": "submit_review",
        "operation_details": "提交审核",
        "ip_address": "127.0.0.1"
    })
    
    return {"message": "文件已提交审核"}

@router.get("/{file_id}/versions", response_model=List[FileVersionResponse])
def get_file_versions(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取文件版本历史"""
    db_file = file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return db_file.versions