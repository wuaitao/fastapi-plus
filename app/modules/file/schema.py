"""文件公开元数据；私有文件不自动发放访问 URL"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.providers.storage import Visibility


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    backend: str
    key: str
    original_name: str
    content_type: str
    size: int
    visibility: Visibility
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    url: str | None = None

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        """将数据库整数 ID 序列化为字符串，避免客户端数值精度丢失"""
        return str(value)

    @field_serializer("created_by")
    def serialize_creator(self, value: int | None) -> str | None:
        """序列化所有者 ID，已删除用户保留空值"""
        return str(value) if value is not None else None
