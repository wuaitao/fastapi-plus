"""HTTP 输入和响应；业务授权与存储流程留在 Service"""

from typing import Annotated

from fastapi import APIRouter, Form, Path, Request, UploadFile
from fastapi.responses import FileResponse as LocalFileResponse
from fastapi.responses import RedirectResponse, Response

from app.common.response import ApiResponse, ErrorResponse
from app.modules.auth.dependencies import CurrentUserDep
from app.modules.file.dependencies import FileServiceDep, OptionalUserDep
from app.modules.file.model import FileRecord
from app.modules.file.schema import FileResponse
from app.providers.storage import LocalAccess, Visibility

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        503: {"model": ErrorResponse, "description": "Storage unavailable"},
    },
)
FileId = Annotated[int, Path(gt=0, le=9223372036854775807)]


def metadata(record: FileRecord, request: Request) -> FileResponse:
    """转换公开元数据，仅为 public 文件生成当前应用的下载路由 URL。"""
    result = FileResponse.model_validate(record)
    if record.visibility == "public":
        # URL 来自当前路由，不保存厂商地址；私有响应始终保持 null。
        result.url = str(request.url_for("download_file", id=record.id))
    return result


@router.post(
    "",
    status_code=201,
    summary="上传文件",
    responses={
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "File type not allowed"},
    },
)
async def upload_file(
    request: Request,
    file: UploadFile,
    service: FileServiceDep,
    user: CurrentUserDep,
    visibility: Annotated[Visibility, Form()] = "private",
) -> ApiResponse[FileResponse]:
    """登录用户上传 multipart file；visibility 默认 private"""
    try:
        record = await service.upload(
            file.file,
            filename=file.filename or "",
            content_type=file.content_type or "",
            visibility=visibility,
            actor=user,
        )
        return ApiResponse(data=metadata(record, request))
    finally:
        await file.close()


@router.get("/{id}", summary="查询文件元数据", openapi_extra={"security": [{}, {"HTTPBearer": []}]})
async def get_file(
    id: FileId,
    request: Request,
    service: FileServiceDep,
    user: OptionalUserDep,
    response: Response,
) -> ApiResponse[FileResponse]:
    """公开文件可匿名查询；私有元数据仅所有者或超级管理员可读"""
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(data=metadata(await service.get_file(id, user), request))


@router.get(
    "/{id}/download",
    summary="下载文件",
    response_class=Response,
    openapi_extra={"security": [{}, {"HTTPBearer": []}]},
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        307: {
            "description": "Short-lived cloud download URL",
            "headers": {"Location": {"schema": {"type": "string"}}},
        },
    },
)
async def download_file(id: FileId, service: FileServiceDep, user: OptionalUserDep) -> Response:
    """公开文件可匿名下载；私有文件仅所有者或超级管理员可访问"""
    result = await service.download(id, user)
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if isinstance(result.access, LocalAccess):
        return LocalFileResponse(
            result.access.path,
            filename=result.record.original_name,
            media_type=result.record.content_type,
            headers=headers,
        )
    return RedirectResponse(result.access.url, status_code=307, headers=headers)


@router.delete("/{id}", summary="删除文件")
async def delete_file(
    id: FileId, service: FileServiceDep, user: CurrentUserDep
) -> ApiResponse[None]:
    """仅所有者或超级管理员可删除文件；成功返回 200 和 data=null"""
    await service.delete_file(id, user)
    return ApiResponse(data=None)
