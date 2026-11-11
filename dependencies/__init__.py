"""依赖包：认证与权限。"""
from dependencies.auth import get_current_user, get_current_user_optional, oauth2_scheme
from dependencies.permissions import (
    can_view_file,
    compute_allowed_actions,
    ensure_owner_or_admin,
    is_pending_approver,
    require_any_permission,
    require_permission,
    visibility_condition,
)

__all__ = [
    "oauth2_scheme",
    "get_current_user",
    "get_current_user_optional",
    "require_permission",
    "require_any_permission",
    "can_view_file",
    "compute_allowed_actions",
    "ensure_owner_or_admin",
    "is_pending_approver",
    "visibility_condition",
]
