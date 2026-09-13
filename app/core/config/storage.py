"""可选云后端的显式配置；秘密不参与 repr 或序列化"""

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


class CloudStorageSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    bucket: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    region: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    access_key_id: SecretStr = Field(min_length=1, repr=False, exclude=True)
    access_key_secret: SecretStr = Field(min_length=1, repr=False, exclude=True)


class StorageSettings(BaseSettings):
    storage_backend: Literal["local", "oss", "cos"] = "local"
    storage_local_root: Path = Path("data/storage")
    storage_oss: CloudStorageSettings | None = None
    storage_cos: CloudStorageSettings | None = None
    file_max_size: int = Field(default=10 * 1024 * 1024, gt=0)

    @model_validator(mode="after")
    def validate_storage(self) -> Self:
        if self.storage_backend == "oss" and self.storage_oss is None:
            raise ValueError("OSS 默认后端需要配置 STORAGE_OSS")
        if self.storage_backend == "cos" and self.storage_cos is None:
            raise ValueError("COS 默认后端需要配置 STORAGE_COS")
        return self
