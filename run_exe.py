# -*- coding: utf-8 -*-
"""EXE 入口：双击后启动服务并自动打开浏览器。

源码运行时等价于 ``python -m app.main``；
PyInstaller 打包后就成为 exe 的主入口（资源从解包目录读，数据写在 exe 同级 data/）。
"""
from __future__ import annotations

import os
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main  # noqa: E402


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(0)