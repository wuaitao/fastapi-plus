"""可选 Prometheus 指标；一个进程一个注册表，按实例独立采集"""

from time import perf_counter
from typing import cast

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class Metrics:
    def __init__(self) -> None:
        # 避免全局默认注册表，让测试和多个应用工厂互不污染。
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "http_requests_total",
            "HTTP 请求总数",
            ("method", "route", "status"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "http_request_duration_seconds",
            "HTTP 请求处理时长（含响应流）",
            ("method", "route"),
            registry=self.registry,
        )
        self.checked_out = Gauge(
            "db_pool_checked_out",
            "当前借出的数据库连接数",
            registry=self.registry,
        )
        self.pool_size = Gauge(
            "db_pool_size",
            "配置的常驻连接池容量",
            registry=self.registry,
        )


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """记录已结束请求，排除探针与采集自身，标签不包含用户数据"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status = 500

        async def send_response(message: Message) -> None:
            """记录真实响应状态，不读取或缓冲响应体"""
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        finally:
            # 用路由模板收敛标签，未知路径与任意 HTTP 方法不能无限增加时序。
            route = scope.get("route")
            path = route.path if isinstance(route, Route) else "unmatched"
            if path not in {"/health", "/health/ready", "/metrics"}:
                method = scope["method"]
                if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
                    method = "OTHER"
                self.metrics.requests.labels(method, path, str(status)).inc()
                self.metrics.duration.labels(method, path).observe(perf_counter() - started)


def register_metrics(app: FastAPI) -> None:
    """显式启用采集端点；部署时只允许监控网络访问该端点"""
    metrics = Metrics()
    app.state.metrics = metrics

    @app.get("/metrics", include_in_schema=False)
    async def scrape(request: Request) -> Response:
        """读取当前进程的计数器与池状态，不连接数据库"""
        engine = cast(AsyncEngine, request.app.state.engine)
        pool = engine.pool
        if isinstance(pool, QueuePool):
            metrics.checked_out.set(pool.checkedout())
            metrics.pool_size.set(pool.size())
        return Response(
            generate_latest(metrics.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST, "Cache-Control": "no-store"},
        )
