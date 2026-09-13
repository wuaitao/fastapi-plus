"""认证 HTTP 入口；业务失败统一交给全局异常处理器"""

from fastapi import APIRouter, Response

from app.common.response import ApiResponse, ErrorResponse
from app.core.security.dependencies import AccessTokenDep
from app.modules.auth.dependencies import AuthServiceDep, CurrentUserDep
from app.modules.auth.schema import LoginRequest, RefreshRequest, TokenResponse
from app.modules.user.schema import UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials or token"},
        403: {"model": ErrorResponse, "description": "User disabled"},
    },
)


@router.post("/login", summary="登录")
async def login(
    data: LoginRequest, service: AuthServiceDep, response: Response
) -> ApiResponse[TokenResponse]:
    """使用用户名和密码登录，返回 access/refresh token"""
    pair = await service.login(data.username, data.password.get_secret_value())
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ApiResponse(data=TokenResponse.model_validate(pair))


@router.post("/refresh", summary="刷新令牌")
async def refresh(
    data: RefreshRequest, service: AuthServiceDep, response: Response
) -> ApiResponse[TokenResponse]:
    """重新验证 refresh token 及用户状态；无状态模式不撤销旧令牌"""
    pair = await service.refresh(data.refresh_token.get_secret_value())
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ApiResponse(data=TokenResponse.model_validate(pair))


@router.post("/logout", summary="退出登录")
async def logout(token: AccessTokenDep, service: AuthServiceDep) -> ApiResponse[None]:
    """默认无状态模式仅要求客户端删除两个令牌；服务端令牌在到期前仍有效"""
    await service.logout(token)
    return ApiResponse(data=None)


@router.get("/me", summary="当前用户")
async def me(user: CurrentUserDep) -> ApiResponse[UserResponse]:
    """返回当前启用用户的公开信息，不包含密码及哈希"""
    return ApiResponse(data=UserResponse.model_validate(user))
