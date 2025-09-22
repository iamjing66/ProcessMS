from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from database import get_db
from crud.file import file_crud
from crud.user import user_crud
from schemas.file import FileResponse, FileCreate, FileUpdate, FileSearch, FileVersionResponse
from utils.security import verify_token
from utils.file_upload import save_upload_file
from utils.versioning import generate_next_version
from models.file import FileStatus

router = APIRouter(prefix="/files", tags=["files"])

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await user_crud.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@router.post("/upload", response_model=FileResponse)
async def upload_file(
    file_data: FileCreate,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 保存文件
    file_info = await save_upload_file(file, current_user.id)
    
    # 创建文件记录
    db_file = await file_crud.create_file(db, file_data, current_user.id, file_info)
    
    # 记录操作日志
    await file_crud.log_file_operation(db, {
        "file_id": db_file.id,
        "operator_id": current_user.id,
        "operation_type": "upload",
        "operation_details": f"上传新文件: {db_file.file_name}",
        "ip_address": "127.0.0.1"  # 实际应用中从请求中获取
    })
    
    return db_file

@router.get("/", response_model=List[FileResponse])
async def get_files(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    files = await file_crud.get_files(db, skip, limit)
    return files

@router.post("/search", response_model=List[FileResponse])
async def search_files(
    search: FileSearch,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    files = await file_crud.search_files(db, search)
    return files

@router.put("/{file_id}", response_model=FileResponse)
async def update_file(
    file_id: int,
    update_data: FileUpdate,
    new_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 获取原文件
    db_file = await file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 如果有新文件上传，创建新版本
    if new_file:
        file_info = await save_upload_file(new_file, current_user.id)
        
        # 创建版本记录
        new_version = generate_next_version(db_file.version, "minor")
        await file_crud.create_file_version(db, file_id, {
            "version": new_version,
            "file_path": file_info["file_path"],
            "uploader_id": current_user.id,
            "change_description": update_data.change_description,
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
    
    await db.commit()
    await db.refresh(db_file)
    
    # 记录操作日志
    await file_crud.log_file_operation(db, {
        "file_id": file_id,
        "operator_id": current_user.id,
        "operation_type": "update",
        "operation_details": f"更新文件: {db_file.file_name}",
        "ip_address": "127.0.0.1"
    })
    
    return db_file

@router.post("/{file_id}/submit-review")
async def submit_for_review(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    db_file = await file_crud.get_file_by_id(db, file_id)
    if not db_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if db_file.uploader_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此文件")
    
    db_file.file_status = FileStatus.PENDING_REVIEW
    await db.commit()
    
    await file_crud.log_file_operation(db, {
        "file_id": file_id,
        "operator_id": current_user.id,
        "operation_type": "submit_review",
        "operation_details": "提交审核",
        "ip_address": "127.0.0.1"
    })
    
    return {"message": "文件已提交审核"}