"""通用 HTTP Bearer 解析，不查询用户或装配业务 Service"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationException

bearer = HTTPBearer(auto_error=False)


def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None:
        raise AuthenticationException()
    return credentials.credentials


AccessTokenDep = Annotated[str, Depends(get_access_token)]
