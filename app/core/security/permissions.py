"""通用权限策略，不依赖用户模型或 HTTP 依赖注入"""

from app.core.exceptions import AuthorizationException


def check_permission(permission: str, *, is_superuser: bool) -> None:
    """执行权限策略入口，当前规则统一要求超级管理员，可按业务替换"""
    # 当前所有 resource:action 共用管理员规则；扩展策略时在此解释权限名。
    if not is_superuser:
        raise AuthorizationException()
