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
        return str(value)

    @field_serializer("created_by")
    def serialize_creator(self, value: int | None) -> str | None:
        return str(value) if value is not None else None
