"""发布时对全部路由检查 OpenAPI 引用、操作标识和公开响应契约。"""

from typing import Any, cast

from app.bootstrap.application import create_app
from app.core.config import Settings


def test_complete_openapi_contract(settings: Settings) -> None:
    app = create_app(settings)
    schema: dict[str, Any] = app.openapi()

    # 遍历完整 schema，确保嵌套泛型或未来新增路由不会留下悬空引用。
    def check_references(value: Any) -> None:
        if isinstance(value, dict):
            mapping = cast(dict[str, Any], value)
            if "$ref" in mapping:
                reference = cast(str, mapping["$ref"])
                assert reference.startswith("#/")
                target = schema
                for part in reference[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            for child in mapping.values():
                check_references(child)
        elif isinstance(value, list):
            for child in cast(list[Any], value):
                check_references(child)

    check_references(schema)
    operation_ids: set[str] = set()
    for path, methods in schema["paths"].items():
        for operation in methods.values():
            operation_id = operation["operationId"]
            assert operation_id not in operation_ids
            operation_ids.add(operation_id)
            assert operation["summary"]
            assert operation["description"]
            assert operation["tags"]
            for status, response in operation["responses"].items():
                if status in {"404", "405", "422", "500"}:
                    assert "X-Request-ID" in response["headers"]
                if int(status) >= 400:
                    assert response["content"]["application/json"]["schema"] == {
                        "$ref": "#/components/schemas/ErrorResponse"
                    }
            if path.startswith("/api/v1/") and not path.endswith("/download"):
                status = "201" if "201" in operation["responses"] else "200"
                response_schema = operation["responses"][status]["content"]["application/json"][
                    "schema"
                ]
                model = schema["components"]["schemas"][response_schema["$ref"].split("/")[-1]]
                assert set(model["properties"]) == {"code", "message", "data"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    for name in ("UserResponse", "FileResponse"):
        properties = schema["components"]["schemas"][name]["properties"]
        assert properties["id"]["type"] == "string"
        assert "password" not in properties and "password_hash" not in properties
