import os
import uuid
from fastapi import UploadFile, HTTPException
from config import settings
from datetime import datetime

def save_upload_file(file: UploadFile, user_id: int) -> dict:
    """保存上传的文件并返回文件信息"""
    
    # 检查文件扩展名
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")
    
    # 创建用户目录
    user_dir = os.path.join(settings.UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = os.path.join(user_dir, filename)
    
    # 保存文件
    try:
        content = file.file.read()
        file_size = len(content)
        
        # 检查文件大小
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件大小超过限制")
        
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    finally:
        file.file.close()
    
    return {
        "filename": file.filename,
        "file_path": file_path,
        "file_size": file_size,
        "file_type": file_ext
    }

def generate_file_number(process_step: str) -> str:
    """生成文件编号"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    step_code = process_step[:3].upper() if len(process_step) >= 3 else "GEN"
    return f"{step_code}-{timestamp}"