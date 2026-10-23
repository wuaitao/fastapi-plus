"""文件业务的稳定错误描述符"""

from app.core.exceptions import ErrorDescriptor

FILE_NOT_FOUND = ErrorDescriptor(31001, "FILE_NOT_FOUND", "文件不存在", 404)
FILE_TOO_LARGE = ErrorDescriptor(31002, "FILE_TOO_LARGE", "文件过大", 413)
FILE_TYPE_NOT_ALLOWED = ErrorDescriptor(31003, "FILE_TYPE_NOT_ALLOWED", "文件类型不允许", 415)
FILE_INVALID_NAME = ErrorDescriptor(31004, "FILE_INVALID_NAME", "文件名无效", 422)
