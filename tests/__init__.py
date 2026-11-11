# -*- coding: utf-8 -*-
"""测试公用脚手架：临时数据目录 + 空题库 + 已导入样例题库的 App。

运行：
    python -m unittest discover -s tests -v
不依赖 pytest。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import bank, db, settings as st  # noqa: E402

LIBRARY_DIRS = [
    os.path.join(ROOT, "libraries"),
    os.path.join(ROOT, "data", "libraries"),
]


def library_files():
    """返回可用的样例题库文件列表（AutoCourse-DB 平面格式）。"""
    found = []
    for directory in LIBRARY_DIRS:
        directory = os.path.abspath(directory)
        if os.path.isdir(directory):
            found.extend(sorted(glob.glob(os.path.join(directory, "*.json"))))
        if found:
            break
    return found


class TempEnv(unittest.TestCase):
    """每个测试类一份干净的 data 目录。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ocshub-test-")
        st.ensure_data_dir(cls.tmp)
        cls.cfg = st.Settings(os.path.join(cls.tmp, "config.json"))
        cls.cfg.load()
        st.set_settings(cls.cfg)
        db.set_db_path(os.path.join(cls.tmp, "bank.db"))
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        db.close_thread_conn()
        db.set_db_path(os.path.join(st.DATA_DIR, "bank.db"))
        st.set_settings(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 便捷方法 ---------------------------------------------------------
    def import_libraries(self, course_name_from_file=True):
        total = 0
        for path in library_files():
            with open(path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
            name = os.path.splitext(os.path.basename(path))[0] if course_name_from_file else "测试课程"
            report = bank.import_questions(payload, course_name=name, strategy="overwrite")
            total += report.get("created", 0) + report.get("updated", 0)
        return total