# -*- coding: utf-8 -*-
"""端到端协议测试：四种接入方式 + 153 题乱序回归。

关键断言：把选项打乱并加前缀后，返回的字母必须仍然指向「原答案内容」。
"""
from __future__ import annotations

import json
import os
import random
import unittest

from tests import TempEnv, library_files
from app import bank, normalize as nz

HAS_LIBRARY = bool(library_files())
need_library = unittest.skipUnless(HAS_LIBRARY, "需要 libraries/ 下的题库文件")
SYNTH_COURSE = "合成回归课"


class TestProtocols(TempEnv):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from app import main as app_main

        cls.app = app_main.create_app()
        cls.client = cls.app.test_client()
        cls.courses = []
        for path in __import__("tests").library_files():
            with open(path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
            name = os.path.splitext(os.path.basename(path))[0]
            bank.import_questions(payload, course_name=name, strategy="overwrite")

    def _sample(self, limit=None):
        rows = bank.db.query(
            "SELECT qtype, title, original_title, options_json, answer_json, course_id "
            "FROM questions WHERE qtype != 'completion'"
        )
        out = []
        for row in rows:
            out.append(
                {
                    "qtype": row["qtype"],
                    "title": row["original_title"] or row["title"],
                    "options": json.loads(row["options_json"]),
                    "answer": json.loads(row["answer_json"]),
                }
            )
        if limit:
            random.shuffle(out)
            out = out[:limit]
        return out

    def _shuffled(self, item):
        opts = list(item["options"])
        random.shuffle(opts)
        raw = [f"{chr(65 + i)}. {t}" for i, t in enumerate(opts)]
        # 原答案内容在新顺序下的字母
        expect = sorted({chr(65 + opts.index(c)) for c in item["answer"] if c in opts})
        return raw, opts, expect

    @need_library
    def test_search_letters_all_questions(self):
        rows = self._sample()
        self.assertGreater(len(rows), 0, "题库为空，先把示例题库或自己的题库放进 libraries/")
        bad = []
        for item in rows:
            raw, opts, expect = self._shuffled(item)
            resp = self.client.post("/search", json={"title": item["title"], "type": item["qtype"], "options": raw})
            data = resp.get_json()
            got = data.get("answer") or ""
            got_letters = [p for p in str(got).split("#") if p]
            if item["qtype"] == "judgement":
                ok = got in ("对", "错")
            else:
                ok = got_letters == expect
            if not ok:
                bad.append((item["title"][:30], expect, got))
        self.assertEqual(bad, [], f"{len(bad)} 题不匹配，示例：{bad[:3]}")

    def test_search_letters_synthetic_150(self):
        """不依赖任何题库文件：现场合成 150 道题，验证选项乱序后字母仍然指向正确内容。"""
        bank.import_questions(
            self._synthetic_payload(150), course_name=SYNTH_COURSE, strategy="overwrite"
        )
        course = bank.get_course_by_name(SYNTH_COURSE)
        rows = bank.db.query(
            "SELECT qtype, title, options_json, answer_json FROM questions WHERE course_id = ?",
            (course["id"],),
        )
        self.assertEqual(len(rows), 150)
        bad = []
        for row in rows:
            opts = json.loads(row["options_json"])
            random.shuffle(opts)
            raw = [f"{chr(65 + i)}. {t}" for i, t in enumerate(opts)]
            want = sorted({chr(65 + opts.index(t)) for t in json.loads(row["answer_json"])})
            data = self.client.post(
                "/search",
                json={"title": row["title"], "type": row["qtype"], "options": raw},
            ).get_json()
            got = data.get("answer") or ""
            if row["qtype"] == "judgement":
                ok = got in ("对", "错")
            else:
                ok = data.get("code") == 1 and [p for p in str(got).split("#") if p] == want
            if not ok:
                bad.append((row["title"], want, got))
        self.assertEqual(bad, [], f"{len(bad)} 题不匹配，示例：{bad[:3]}")

    @staticmethod
    def _synthetic_payload(count):
        payload = {}
        for i in range(count):
            kind = ("single", "multiple", "judgement")[i % 3]
            title = f"合成回归第 {i} 题：请选出正确项"
            if kind == "judgement":
                opts = ["对", "错"]
                value = "对" if i % 2 == 0 else "错"
            else:
                opts = [f"选项甲{i}", f"选项乙{i}", f"选项丙{i}", f"选项丁{i}"]
                picked = [opts[i % 4]] if kind == "single" else [opts[i % 4], opts[(i + 2) % 4]]
                value = "#".join(picked)
            payload[f"[{kind}] {title} | " + " | ".join(opts)] = value
        return payload

    @need_library
    def test_api_answer_ocs_format(self):
        samples = self._sample(1)
        if not samples:
            self.skipTest("题库为空")
        item = samples[0]
        raw, opts, expect = self._shuffled(item)
        resp = self.client.post("/api/answer", json={"title": item["title"], "type": item["qtype"], "options": raw})
        data = resp.get_json()
        self.assertEqual(data["code"], 1)
        ocs = data["ocs_format"]
        self.assertEqual(len(ocs), 3)
        self.assertEqual(ocs[0], item["title"])
        self.assertIn("ai", ocs[2])

    @need_library
    def test_api_search_shape(self):
        samples = self._sample(1)
        if not samples:
            self.skipTest("题库为空")
        item = samples[0]
        raw, opts, expect = self._shuffled(item)
        resp = self.client.post("/api/search", json={"title": item["title"], "type": item["qtype"], "options": raw})
        data = resp.get_json()
        self.assertEqual(data["code"], 1)
        self.assertIn("answer", data)

    @need_library
    def test_ask_full_shape(self):
        samples = self._sample(1)
        if not samples:
            self.skipTest("题库为空")
        item = samples[0]
        raw, opts, expect = self._shuffled(item)
        resp = self.client.post("/api/v1/ask", json={"title": item["title"], "type": item["qtype"], "options": raw})
        data = resp.get_json()["data"]
        self.assertEqual(data["hit_source"], "bank")
        self.assertTrue(data["request_id"])
        self.assertEqual(data["question"], nz.clean_text(item["title"]))

    def test_health_and_metadata(self):
        health = self.client.get("/api/v1/health").get_json()
        self.assertTrue(health["ok"])
        self.assertIn("version", health["data"])

    def test_admin_requires_loopback_or_token(self):
        # 默认配置：非本机访问需 token，但 test_client 是 127.0.0.1
        resp = self.client.get("/api/admin/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertIn("server", data)
        self.assertIn("answer", data)

    def test_admin_rejects_remote(self):
        with self.app.test_request_context():
            resp = self.client.get("/api/admin/settings", environ_base={"REMOTE_ADDR": "10.0.0.9"})
            self.assertEqual(resp.status_code, 403)

    def test_settings_roundtrip(self):
        resp = self.client.post("/api/admin/settings", json={"answer": {"similarity_threshold": 0.9}})
        self.assertEqual(resp.status_code, 200)
        data = self.client.get("/api/admin/settings").get_json()["data"]
        self.assertAlmostEqual(data["answer"]["similarity_threshold"], 0.9, places=3)

    @need_library
    def test_cache_and_logs(self):
        samples = self._sample(1)
        if not samples:
            self.skipTest("题库为空")
        item = samples[0]
        raw, _, _ = self._shuffled(item)
        for _ in range(2):
            self.client.post("/api/v1/ask", json={"title": item["title"], "type": item["qtype"], "options": raw})
        logs = self.client.get("/api/admin/logs?size=5").get_json()["data"]
        self.assertGreaterEqual(len(logs["items"]), 1)
        cache = self.client.get("/api/admin/cache").get_json()["data"]["cache"]
        self.assertGreaterEqual(cache["size"], 1)

    def test_import_export_via_api(self):
        payload = {"[single] 接口导入题 | 甲 | 乙": "甲"}
        resp = self.client.post(
            "/api/admin/import",
            json={"course_name": "接口课", "data": payload, "strategy": "overwrite"},
        )
        self.assertEqual(resp.status_code, 200)
        cid = bank.get_course_by_name("接口课")["id"]
        resp = self.client.get(f"/api/admin/export?course_id={cid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "[single] 接口导入题",
            "\n".join(resp.get_json()["data"].keys()),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)