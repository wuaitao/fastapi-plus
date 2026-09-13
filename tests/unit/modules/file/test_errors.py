"""文件错误描述符与公共错误保持唯一。"""

from app.core.exceptions import COMMON_ERRORS
from app.modules.file.errors import (
    FILE_INVALID_NAME,
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    FILE_TYPE_NOT_ALLOWED,
)


def test_file_error_descriptors_are_unique() -> None:
    descriptors = (
        *COMMON_ERRORS,
        FILE_INVALID_NAME,
        FILE_NOT_FOUND,
        FILE_TOO_LARGE,
        FILE_TYPE_NOT_ALLOWED,
    )
    assert len({item.code for item in descriptors}) == len(descriptors)
    assert len({item.key for item in descriptors}) == len(descriptors)
