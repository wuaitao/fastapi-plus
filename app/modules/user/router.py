"""HTTP 入口只解析输入、调用 Service 并序列化公开 Schema"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.common.pagination import Page
from app.common.response import ApiResponse, ErrorResponse
from app.modules.auth.dependencies import CurrentUserDep, require_permission
from app.modules.user.dependencies import get_user_service
from app.modules.user.schema import UserCreate, UserQuery, UserResponse, UserUpdate
from app.modules.user.service import UserService

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
    },
)
Service = Annotated[UserService, Depends(get_user_service)]
UserId = Annotated[int, Path(gt=0, le=9223372036854775807)]


@router.post(
    "",
    status_code=201,
    summary="创建用户",
    dependencies=[Depends(require_permission("user:create"))],
    responses={409: {"model": ErrorResponse, "description": "User already exists"}},
)
async def create_user(data: UserCreate, service: Service) -> ApiResponse[UserResponse]:
    """创建普通用户，响应不包含密码或哈希"""
    user = await service.create_user(data)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.get("", summary="分页查询用户", dependencies=[Depends(require_permission("user:read"))])
async def list_users(
    query: Annotated[UserQuery, Query()], service: Service
) -> ApiResponse[Page[UserResponse]]:
    """按用户 ID 升序分页，默认每页 20 条，最多 100 条"""
    result = await service.list_users(query)
    return ApiResponse(
        data=Page(
            items=[UserResponse.model_validate(user) for user in result.items],
            total=result.total,
            page=result.page,
            size=result.size,
        )
    )


@router.get("/{id}", summary="查询用户", dependencies=[Depends(require_permission("user:read"))])
async def get_user(id: UserId, service: Service) -> ApiResponse[UserResponse]:
    """返回用户公开信息；用户不存在时返回 404"""
    user = await service.get_user(id)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.patch(
    "/{id}",
    summary="更新用户",
    dependencies=[Depends(require_permission("user:update"))],
    responses={409: {"model": ErrorResponse, "description": "User already exists"}},
)
async def update_user(id: UserId, data: UserUpdate, service: Service) -> ApiResponse[UserResponse]:
    """只更新提供的用户名、邮箱和启用状态；邮箱可通过 null 清空"""
    user = await service.update_user(id, data)
    return ApiResponse(data=UserResponse.model_validate(user))


@router.delete(
    "/{id}", summary="删除用户", dependencies=[Depends(require_permission("user:delete"))]
)
async def delete_user(id: UserId, service: Service, user: CurrentUserDep) -> ApiResponse[None]:
    """物理删除用户，成功返回 200 和 data=null"""
    await service.delete_user(id, actor_id=user.id)
    return ApiResponse(data=None)
