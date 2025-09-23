from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from database import get_db
from crud.user import user_crud
from schemas.auth import Token
from schemas.user import UserCreate
from utils.security import verify_password, create_access_token, get_password_hash
from dependencies.auth import get_current_user
from config import settings

router = APIRouter()

@router.post("/login", response_model=Token)
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """用户登录 - 使用单独的Form参数而不是OAuth2PasswordRequestForm"""
    user = user_crud.get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    employee_id: str = Form(None),
    real_name: str = Form(None),
    department: str = Form("默认部门"),
    position: str = Form("默认职位"),
    db: Session = Depends(get_db)
):
    """用户注册 - 使用单独的Form参数"""
    # 检查用户名是否已存在
    existing_user = user_crud.get_user_by_username(db, username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 使用提供的employee_id或默认使用username
    if not employee_id:
        employee_id = username
    
    # 使用提供的real_name或默认使用username
    if not real_name:
        real_name = username
    
    # 创建用户
    user_create = UserCreate(
        employee_id=employee_id,
        username=username,
        password=password,
        real_name=real_name,
        department=department,
        position=position
    )
    
    user = user_crud.create_user(db, user_create)
    
    return {"message": "用户注册成功", "user_id": user.id}

@router.post("/change-password")
def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """修改密码"""
    user = user_crud.get_user_by_username(db, current_user["username"])
    if not user or not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误"
        )
    
    user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return {"message": "密码修改成功"}

@router.get("/me")
def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户信息"""
    user = user_crud.get_user_by_username(db, current_user["username"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "employee_id": user.employee_id,
        "department": user.department,
        "position": user.position,
        "last_login": user.last_login
    }