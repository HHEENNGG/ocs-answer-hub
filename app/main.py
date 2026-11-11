# -*- coding: utf-8 -*-
"""程序入口：创建 Flask 应用、启动服务、打开浏览器。

用法::

    python -m app.main                 # 默认 127.0.0.1:8000
    python -m app.main --port 8001     # 指定端口
    python -m app.main --no-browser    # 不自动打开浏览器
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from flask import Flask, Response, request, send_from_directory

from . import __version__
from . import api as api_mod
from . import bank
from . import db
from . import logging_store as logs
from .settings import BASE_DIR, DATA_DIR, get_settings, ensure_data_dir

PROJECT_ROOT = BASE_DIR  # 只读资源根（源码=项目根；打包后=解包目录）
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
LIBRARY_DIRS = [
    os.path.join(PROJECT_ROOT, "libraries"),
    os.path.join(DATA_DIR, "libraries"),
]


# --------------------------------------------------------------------------
# 应用
# --------------------------------------------------------------------------
def create_app() -> Flask:
    ensure_data_dir()
    init_state = db.init_db()
    if init_state != "ok":
        print(f"[初始化] 数据库状态：{init_state}")
    app = Flask(__name__, static_folder=None)
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

    try:  # 允许 OCS 脚本从任意源访问
        from flask_cors import CORS

        CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)
    except ImportError:  # pragma: no cover
        pass

    api_mod.register(app)

    @app.get("/")
    @app.get("/index.html")
    def index() -> Response:
        _log_client()
        return _send_web("index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str) -> Response:
        return _send_web(os.path.join("static", filename))

    @app.get("/favicon.ico")
    def favicon() -> Response:
        path = os.path.join(WEB_DIR, "favicon.ico")
        if os.path.exists(path):
            return send_from_directory(WEB_DIR, "favicon.ico")
        return Response(status=204)

    return app


def _log_client() -> None:
    """记录访问首页的客户端信息，排查浏览器兼容问题用。"""
    try:
        path = os.path.join(DATA_DIR, "logs", "ua.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = "%s\t%s\t%s\n" % (
            db.now_str(),
            request.remote_addr or "-",
            (request.headers.get("User-Agent") or "-").replace("\t", " "),
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:  # pragma: no cover - 日志失败不影响页面
        pass


def _send_web(relative: str) -> Response:
    path = os.path.join(WEB_DIR, relative)
    if not os.path.exists(path):
        return Response(
            "<h1>前端文件缺失</h1><p>请确认 web/ 目录完整：%s</p>" % path,
            status=500,
            mimetype="text/html; charset=utf-8",
        )
    return send_from_directory(WEB_DIR, relative.replace("\\", "/"))


# --------------------------------------------------------------------------
# 首次启动：自动导入同目录下的题库 JSON
# --------------------------------------------------------------------------
def bootstrap_data() -> None:
    default_course = bank.ensure_default_course()
    stats = bank.stats()
    if stats["questions"] > 0:
        return
    imported: List[str] = []
    first_course_id: int = 0
    for directory in LIBRARY_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(".json"):
                continue
            path = os.path.join(directory, name)
            try:
                with open(path, "r", encoding="utf-8-sig") as fh:
                    payload = json.load(fh)
                course_name = os.path.splitext(name)[0]
                result = bank.import_questions(payload, course_name, strategy="skip", source="bootstrap")
                created = int(result.get("created") or 0) + int(result.get("updated") or 0)
                if created and not first_course_id:
                    first_course_id = int(result.get("course_id") or 0) or first_course_id
                imported.append(f"{course_name}（{created} 题）")
            except (OSError, ValueError, TypeError) as exc:
                print(f"[初始化] 跳过 {name}：{exc}")
    if imported:
        print("[初始化] 已自动导入题库：" + "、".join(imported))
    # 有正式题库时，清掉空壳默认课程并切到第一个题库
    if first_course_id:
        try:
            bank.set_active(first_course_id)
            if default_course and int(default_course.get("id", 0)) != first_course_id:
                empty = bank.get_course(int(default_course["id"]))
                if empty and int(empty.get("question_count") or 0) == 0:
                    bank.delete_course(int(empty["id"]))
        except Exception:  # noqa: BLE001 - 初始化阶段不阻断启动
            pass


# --------------------------------------------------------------------------
# 端口与服务
# --------------------------------------------------------------------------
def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str, preferred: int, span: int = 20) -> int:
    for port in range(preferred, preferred + span):
        if _port_free(host, port):
            return port
    return preferred


def _banner(host: str, port: int) -> None:
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    base = f"http://{shown_host}:{port}"
    print("")
    print("=" * 62)
    print(f"  {__version__}  OCS 智题库 · AnswerHub  已启动")
    print("=" * 62)
    print(f"  管理界面      {base}/")
    print(f"  OCS 协议①     {base}/search            （AutoCourse-DB 风格）")
    print(f"  OCS 协议②     {base}/api/search        （ocsjs 服务风格）")
    print(f"  OCS 协议③     {base}/api/answer        （AI 答题机风格）")
    print(f"  原生接口      {base}/api/v1/ask")
    print(f"  健康检查      {base}/api/v1/health")
    print("-" * 62)
    print(f"  题库文件      {os.path.join(DATA_DIR, 'bank.db')}")
    print(f"  配置文件      {os.path.join(DATA_DIR, 'config.json')}")
    print("=" * 62)
    print("  按 Ctrl+C 停止服务")
    print("")


def _run_server(app: Flask, host: str, port: int) -> None:
    try:
        from waitress import serve  # type: ignore

        print(f"[服务] 使用 waitress 多线程模式，监听 {host}:{port}")
        serve(app, host=host, port=port, threads=8, channel_timeout=120)
        return
    except ImportError:
        pass
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)


def main(argv: Optional[List[str]] = None) -> int:
    cfg = get_settings()
    parser = argparse.ArgumentParser(description="OCS 智题库 · AnswerHub")
    parser.add_argument("--host", default=None, help="监听地址（默认取配置，127.0.0.1）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认 8000）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不打开浏览器")
    parser.add_argument("--open-browser", action="store_true", help="启动后打开浏览器（默认行为，显式声明用）")
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    host = args.host or str(cfg.get("server.host") or "127.0.0.1")
    preferred = args.port or int(cfg.get("server.port") or 8000)
    port = pick_port(host, preferred)

    app = create_app()
    bootstrap_data()
    logs.flush()

    _banner(host, port)
    if port != preferred:
        print(f"[提示] 端口 {preferred} 已被占用，改用 {port}")

    should_open = bool(cfg.get("server.open_browser", True)) and not (args.no_browser or args.no_open)
    if should_open:
        shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        url = f"http://{shown}:{port}/"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        _run_server(app, host, port)
    except KeyboardInterrupt:
        print("\n[服务] 正在退出…")
    finally:
        logs.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())