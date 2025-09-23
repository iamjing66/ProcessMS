from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class FileStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ARCHIVED = "archived"
    DELETED = "deleted"

class FileBase(BaseModel):
    file_name: str
    file_type: Optional[str] = None
    process_step: str
    remarks: Optional[str] = None

class FileCreate(FileBase):
    version: str = "V1.0.0"

class FileUpdate(BaseModel):
    file_name: Optional[str] = None
    process_step: Optional[str] = None
    remarks: Optional[str] = None
    change_description: Optional[str] = None

class FileResponse(FileBase):
    id: int
    file_number: str
    version: str
    uploader_id: int
    creator_id: int
    initial_upload_time: datetime
    last_update_time: datetime
    file_size: Optional[int]
    file_status: FileStatus
    current_approver_id: Optional[int]

    class Config:
        from_attributes = True

class FileVersionBase(BaseModel):
    version: str
    change_description: Optional[str] = None

class FileVersionResponse(FileVersionBase):
    id: int
    file_id: int
    uploader_id: int
    upload_time: datetime
    file_size: Optional[int]

    class Config:
        from_attributes = True

class FileSearch(BaseModel):
    file_name: Optional[str] = None
    file_number: Optional[str] = None
    process_step: Optional[str] = None
    creator_name: Optional[str] = None
    upload_date_start: Optional[datetime] = None
    upload_date_end: Optional[datetime] = None

class ApprovalRequest(BaseModel):
    comment: Optional[str] = None

class ApprovalStepBase(BaseModel):
    step_number: int
    step_name: str
    approver_id: int

class ApprovalFlowCreate(BaseModel):
    flow_type: str
    steps: List[ApprovalStepBase]