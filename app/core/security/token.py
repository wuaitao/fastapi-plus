"""固定 HS256 的 JWT 编解码；不从不可信请求选择算法"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.core.exceptions import AuthenticationException

TokenType = Literal["access", "refresh"]


class TokenClaims(BaseModel):
    model_config = ConfigDict(strict=True)

    sub: str = Field(min_length=1)
    type: TokenType
    iat: int = Field(ge=0)
    exp: int = Field(gt=0)
    jti: str = Field(min_length=1)


@dataclass(frozen=True, repr=False)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: Literal["bearer"] = "bearer"


class TokenProvider:
    def __init__(self, secret: SecretStr, access_expires_in: int, refresh_expires_in: int) -> None:
        self.secret = secret
        self.access_expires_in = access_expires_in
        self.refresh_expires_in = refresh_expires_in

    def create_token(self, subject: str, token_type: TokenType) -> str:
        issued_at = int(datetime.now(UTC).timestamp())
        lifetime = self.access_expires_in if token_type == "access" else self.refresh_expires_in
        claims = TokenClaims(
            sub=subject, type=token_type, iat=issued_at, exp=issued_at + lifetime, jti=uuid4().hex
        )
        return jwt.encode(claims.model_dump(), self.secret.get_secret_value(), algorithm="HS256")

    def create_pair(self, subject: str) -> TokenPair:
        return TokenPair(
            access_token=self.create_token(subject, "access"),
            refresh_token=self.create_token(subject, "refresh"),
            expires_in=self.access_expires_in,
        )

    def decode_token(self, token: str, expected_type: TokenType) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self.secret.get_secret_value(),
                algorithms=["HS256"],
                options={"require": ["sub", "type", "iat", "exp", "jti"]},
            )
            # require 只保证声明存在；再严格检查类型，拒绝布尔值或字符串时间戳。
            claims = TokenClaims.model_validate(payload)
            if claims.type != expected_type or claims.exp <= claims.iat:
                raise AuthenticationException()
            return claims
        except (jwt.InvalidTokenError, ValidationError, ValueError, TypeError, OverflowError):
            # 库对非有限时间声明做整数转换时可能溢出，同样属于无效令牌。
            raise AuthenticationException() from None
