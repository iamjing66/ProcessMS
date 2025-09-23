# init_data.py - 初始化测试数据
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from crud.user import user_crud
from schemas.user import UserCreate

def init_test_data():
    """初始化测试数据"""
    db = SessionLocal()
    
    try:
        # 检查是否已存在管理员用户
        admin_user = user_crud.get_user_by_username(db, "admin")
        if not admin_user:
            # 创建管理员用户
            admin_data = UserCreate(
                employee_id="000001",
                username="admin",
                password="admin123",
                real_name="系统管理员",
                department="IT部",
                position="系统管理员"
            )
            user_crud.create_user(db, admin_data)
            print("管理员用户创建成功: admin/admin123")
        
        # 创建测试用户
        test_user = user_crud.get_user_by_username(db, "test")
        if not test_user:
            test_data = UserCreate(
                employee_id="000002",
                username="test",
                password="test123",
                real_name="测试用户",
                department="测试部",
                position="测试员"
            )
            user_crud.create_user(db, test_data)
            print("测试用户创建成功: test/test123")
        
        print("测试数据初始化完成")
        
    except Exception as e:
        print(f"初始化测试数据失败: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_test_data()