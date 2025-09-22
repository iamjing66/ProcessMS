def generate_next_version(current_version: str, update_type: str = "minor") -> str:
    """
    生成下一个版本号
    update_type: 'major', 'minor', 'patch'
    """
    if not current_version or current_version == "":
        return "V1.0.0"
    
    # 移除V前缀
    version_str = current_version.lstrip('Vv')
    
    try:
        major, minor, patch = map(int, version_str.split('.'))
    except ValueError:
        # 如果版本号格式不正确，返回默认版本
        return "V1.0.0"
    
    if update_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif update_type == "minor":
        minor += 1
        patch = 0
    elif update_type == "patch":
        patch += 1
    else:
        minor += 1
        patch = 0
    
    return f"V{major}.{minor}.{patch}"

def validate_version_format(version: str) -> bool:
    """验证版本号格式"""
    import re
    pattern = r'^V\d+\.\d+\.\d+$'
    return bool(re.match(pattern, version, re.IGNORECASE))