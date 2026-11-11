# -*- coding: utf-8 -*-
"""用 PyInstaller 打包单文件 exe。

产物：``dist\\OCS-AnswerHub.exe``（双击即启动服务并打开浏览器）。
可写数据放在 exe 同级的 ``data\\`` 目录，删掉 exe 时数据不会跟着丢。

直接运行：
    python build_exe.py
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "OCS-AnswerHub"

# 明显用不到的大块头，排除掉能显著缩小体积
EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc",
    "pytest",
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "PIL",
    "IPython",
    "notebook",
    "setuptools",
    "pip",
]


def _add_data(src: str, dest: str) -> list:
    sep = ";" if os.name == "nt" else ":"
    return ["--add-data", f"{src}{sep}{dest}"]


def main() -> int:
    try:
        import flask  # noqa: F401
        import flask_cors  # noqa: F401
        import requests  # noqa: F401
    except ImportError as exc:
        print(f"[错误] 当前解释器缺少依赖：{exc}")
        print(f"       {sys.executable}")
        print("       请先执行： python -m pip install -r requirements.txt")
        return 1

    try:
        import PyInstaller.__main__ as pyi  # noqa: F401
    except ImportError:
        print("[错误] 没有安装 PyInstaller。")
        print("       请先执行： python -m pip install -U pyinstaller")
        return 1

    old_exe = os.path.join(ROOT, "dist", NAME + (".exe" if os.name == "nt" else ""))
    if os.path.exists(old_exe):
        try:  # 上一版 exe 还在运行时无法覆盖，提前给出人话提示
            with open(old_exe, "ab"):
                pass
        except OSError:
            print("[错误] 旧的 dist\\OCS-AnswerHub.exe 正在被占用。")
            print("       请先关掉正在运行的那个程序窗口，再重新打包。")
            return 1

    web_dir = os.path.join(ROOT, "web")
    lib_dir = os.path.join(ROOT, "libraries")
    if not os.path.isdir(web_dir):
        print(f"[错误] 找不到前端目录：{web_dir}")
        return 1
    if not os.path.isdir(lib_dir):
        print(f"[提示] 没有 libraries 目录，exe 将不带内置题库：{lib_dir}")

    print("[1/3] 清理旧产物…")
    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    shutil.rmtree(os.path.join(ROOT, "dist"), ignore_errors=True)
    spec = os.path.join(ROOT, f"{NAME}.spec")
    if os.path.exists(spec):
        os.remove(spec)

    args = [
        os.path.join(ROOT, "run_exe.py"),
        "--name", NAME,
        "--onefile",
        "--console",
        "--noconfirm",
        "--clean",
        "--paths", ROOT,
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
        "--hidden-import", "flask_cors",
        "--collect-submodules", "flask_cors",
    ]
    args += _add_data(web_dir, "web")
    if os.path.isdir(lib_dir):
        args += _add_data(lib_dir, "libraries")
    for name in EXCLUDES:
        args += ["--exclude-module", name]

    print("[2/3] 开始打包（首次约 1~3 分钟）…")
    import PyInstaller.__main__ as pyi_main

    pyi_main.run(args)

    exe = os.path.join(ROOT, "dist", NAME + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        print("[错误] 打包结束但没有找到产物，请翻看上面的日志。")
        return 1

    size_mb = os.path.getsize(exe) / (1024 * 1024)
    print(f"[3/3] 完成：{exe}  （{size_mb:.1f} MB）")
    print("      双击即可使用；data 目录会自动创建在 exe 旁边。")
    return 0


if __name__ == "__main__":
    sys.exit(main())