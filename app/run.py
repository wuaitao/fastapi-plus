"""
供 IDE 直接运行或设置断点的本地启动入口

如果你正在通过 python 命令启动此文件，请遵循以下事宜：
1. 按照官方文档通过 uv 安装依赖
2. 使用项目 .venv 中的 Python 解释器，数据库和管理员按 README 显式初始化
"""

import os
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # IDE 的工作目录可能是 app；统一 .env、数据库和存储的相对路径基准
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)
    # app_dir 保证直接运行文件时可导入 app；单进程关闭重载，断点留在当前进程
    uvicorn.run(
        "app.main:app",
        app_dir=str(project_root),
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
    )
