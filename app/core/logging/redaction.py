"""日志脱敏与安全异常诊断，不输出原始异常或秘密"""

import re
from collections.abc import Mapping
from traceback import walk_tb
from typing import cast

from structlog.typing import EventDict

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|authorization|cookie|secret|api[_-]?key|access[_-]?key", re.I
)
_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s<>\"']+", re.I)
_CREDENTIAL = re.compile(
    r"\b(?:password|passwd|password_hash|[\w-]*token|authorization|cookie|"
    r"[\w-]*secret[\w-]*|api[_-]?key|[\w-]*access[_-]?key[\w-]*)\b[\"']?\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.I,
)
_BEARER = re.compile(r"\b(?:Bearer|Basic)\s+[^\s,;\"']+", re.I)


def redact_text(value: str) -> str:
    """隐藏文本中带标签的凭据、认证头和敏感 URL"""
    # 含用户信息或查询参数的 URL 整体隐藏，避免连接凭据和签名链接泄漏。
    value = _URL.sub(
        lambda match: REDACTED if "@" in match[0] or "?" in match[0] else match[0], value
    )
    return _CREDENTIAL.sub(REDACTED, _BEARER.sub(REDACTED, value))


def _redact(value: object) -> object:
    """递归复制并脱敏结构化数据，未知对象不调用其字符串表示"""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in cast(list[object] | tuple[object, ...], value)]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # 不调用未知对象的 repr，异常、SDK 对象和 SecretStr 都可能携带秘密。
    return REDACTED


def exception_diagnostics(exc: BaseException) -> dict[str, object]:
    """提取异常类型和栈帧位置，避免泄漏异常正文或局部变量"""
    # 只保留异常类型与调用位置；不提取源码、路径、异常文本或局部变量。
    return {
        "error_type": type(exc).__name__,
        "frames": [
            {"function": frame.f_code.co_name, "line": line}
            for frame, line in walk_tb(exc.__traceback__)
        ],
    }


def redact_sensitive_fields(logger: object, method_name: str, event_dict: EventDict) -> EventDict:
    """在最终渲染前移除原始异常信息并脱敏全部日志字段"""
    for key in ("exc_info", "exception", "stack", "stack_info"):
        event_dict.pop(key, None)
    return cast(EventDict, _redact(event_dict))
