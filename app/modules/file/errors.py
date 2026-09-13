"""文件业务的稳定错误描述符"""

from app.core.exceptions import ErrorDescriptor

FILE_NOT_FOUND = ErrorDescriptor(31001, "FILE_NOT_FOUND", "File not found", 404)
FILE_TOO_LARGE = ErrorDescriptor(31002, "FILE_TOO_LARGE", "File too large", 413)
FILE_TYPE_NOT_ALLOWED = ErrorDescriptor(
    31003, "FILE_TYPE_NOT_ALLOWED", "File type not allowed", 415
)
FILE_INVALID_NAME = ErrorDescriptor(31004, "FILE_INVALID_NAME", "Invalid filename", 422)
