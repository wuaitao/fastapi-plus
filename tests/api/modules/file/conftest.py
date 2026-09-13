"""复用真实认证、迁移和数据库 fixtures。"""

from tests.api.modules.auth.conftest import auth_app as auth_app
from tests.api.modules.auth.conftest import client as client
from tests.api.modules.auth.conftest import users as users
