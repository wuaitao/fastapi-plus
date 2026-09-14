"""跨模块公共错误描述符"""

from app.core.exceptions.descriptors import ErrorDescriptor

INTERNAL_ERROR = ErrorDescriptor(10001, "INTERNAL_ERROR", "Internal server error", 500)
HTTP_ERROR = ErrorDescriptor(10002, "HTTP_ERROR", "HTTP request failed", 400)
NOT_FOUND = ErrorDescriptor(10003, "NOT_FOUND", "Not found", 404)
METHOD_NOT_ALLOWED = ErrorDescriptor(10004, "METHOD_NOT_ALLOWED", "Method not allowed", 405)
BODY_TOO_LARGE = ErrorDescriptor(10005, "BODY_TOO_LARGE", "Request body too large", 413)
INFRASTRUCTURE_UNAVAILABLE = ErrorDescriptor(11001, "INFRASTRUCTURE_UNAVAILABLE", "Service unavailable", 503)
INVALID_CREDENTIALS = ErrorDescriptor(20001, "INVALID_CREDENTIALS", "Invalid credentials", 401)
PERMISSION_DENIED = ErrorDescriptor(21001, "PERMISSION_DENIED", "Permission denied", 403)
VALIDATION_ERROR = ErrorDescriptor(40001, "VALIDATION_ERROR", "Validation error", 422)

COMMON_ERRORS = (
    INTERNAL_ERROR,
    HTTP_ERROR,
    NOT_FOUND,
    METHOD_NOT_ALLOWED,
    BODY_TOO_LARGE,
    INFRASTRUCTURE_UNAVAILABLE,
    INVALID_CREDENTIALS,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
)
