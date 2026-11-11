# -*- coding: utf-8 -*-
"""核心算法与题库读写测试（不依赖 Flask）。"""
from __future__ import annotations

import json
import os
import random
import unittest

from tests import TempEnv, library_files
from app import answer, bank, match, normalize as nz


class TestNormalize(unittest.TestCase):
    def test_parse_options_shapes(self):
        expect = ["富强，劳动创造财富", "强壮，坚持锻炼", "自强，努力劳动", "节俭，珍惜劳动成果"]
        self.assertEqual(nz.parse_options(expect), expect)
        self.assertEqual(
            nz.parse_options([f"{chr(65 + i)}. {t}" for i, t in enumerate(expect)]), expect
        )
        self.assertEqual(nz.parse_options("A. 苹果\nB. 香蕉"), ["苹果", "香蕉"])
        self.assertEqual(nz.parse_options("苹果\n香蕉"), ["苹果", "香蕉"])
        self.assertEqual(nz.parse_options("① 甲\n② 乙"), ["甲", "乙"])
        self.assertEqual(nz.parse_options("1. 甲\n2. 乙"), ["甲", "乙"])
        self.assertEqual(nz.parse_options("A. 苹果 B. 香蕉 C. 梨"), ["苹果", "香蕉", "梨"])
        # 续行拼到上一项
        self.assertEqual(nz.parse_options("A. 苹果\n它很好吃\nB. 香蕉"), ["苹果 它很好吃", "香蕉"])

    def test_parse_options_does_not_mangle_content(self):
        # 选项正文里出现字母也不应被当成序号切碎
        opts = ["A 股市场", "B 超检查"]
        self.assertEqual(nz.parse_options(opts), ["A 股市场", "B 超检查"])

    def test_canonical_key_order_independent(self):
        a = nz.canonical_key("single", " 1、中国的首都是（ ）", ["北京", "上海"])
        b = nz.canonical_key("single", "中国的首都是( )", ["上海", "北京"])
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("[single] "))

    def test_legacy_key_format(self):
        key = nz.legacy_key("multiple", "题干", ["甲", "乙"])
        self.assertEqual(key, "[multiple] 题干 | 乙 | 甲")

    def test_normalize_qtype(self):
        self.assertEqual(nz.normalize_qtype("0"), "single")
        self.assertEqual(nz.normalize_qtype(1), "multiple")
        self.assertEqual(nz.normalize_qtype(3), "completion")
        self.assertEqual(nz.normalize_qtype(4), "judgement")
        self.assertEqual(nz.normalize_qtype("判断题"), "judgement")
        self.assertEqual(nz.normalize_qtype("多选题"), "multiple")
        self.assertEqual(nz.normalize_qtype("怪类型"), "single")

    def test_judgement_normalize(self):
        self.assertEqual(nz.normalize_judgement("对"), "对")
        self.assertEqual(nz.normalize_judgement("正确"), "对")
        self.assertEqual(nz.normalize_judgement("T"), "对")
        self.assertEqual(nz.normalize_judgement("错误"), "错")
        self.assertEqual(nz.normalize_judgement("×"), "错")

    def test_image_urls(self):
        title = "看图回答 <img src=\"https://p.ananas.chaoxing.com/a.jpg\"> 这是？"
        self.assertEqual(nz.extract_image_urls(title), ["https://p.ananas.chaoxing.com/a.jpg"])
        self.assertFalse(nz.has_images(nz.strip_images(title)))


class TestMatch(unittest.TestCase):
    def test_similarity_ratio(self):
        self.assertGreater(match.title_similarity("中国的首都是哪里", "中国的首都是哪里？"), 0.9)
        self.assertLess(match.title_similarity("中国的首都", "劳动创造价值"), 0.5)

    def test_fuzzy_threshold(self):
        cands = [
            {"id": 1, "qtype": "single", "title": "中国的首都是哪里", "options": ["北京", "上海"]},
        ]
        hit = match.best_fuzzy_match("中国的首都是哪里呀", ["上海", "北京"], "single", cands, 0.85)
        self.assertIsNotNone(hit)
        best, score = hit
        self.assertEqual(best["id"], 1)
        self.assertGreaterEqual(score, 0.85)
        self.assertIsNone(
            match.best_fuzzy_match("完全无关的题目", ["甲", "乙"], "single", cands, 0.92)
        )


class TestAnswer(unittest.TestCase):
    def test_extract_letters(self):
        self.assertEqual(answer.extract_letters("答案是 C", 4), ["C"])
        self.assertEqual(answer.extract_letters("A#C", 4), ["A", "C"])
        self.assertEqual(answer.extract_letters("选 A 和 D", 4), ["A", "D"])
        self.assertEqual(answer.extract_letters("对", 2), [])

    def test_clean_raw(self):
        self.assertEqual(answer.clean_raw("答案：B\n解析：因为..."), "B")
        self.assertEqual(answer.clean_raw("```text\nC\n```"), "C")

    def test_answer_for_ocs(self):
        opts = ["富强", "强壮", "自强", "节俭"]
        self.assertEqual(answer.answer_for_ocs(["节俭"], opts, "single", "letters"), "D")
        self.assertEqual(answer.answer_for_ocs(["富强", "节俭"], opts, "multiple", "letters"), "A#D")
        self.assertEqual(answer.answer_for_ocs(["对"], ["对", "错"], "judgement", "letters"), "对")
        self.assertEqual(answer.answer_for_ocs(["对"], ["对", "错"], "judgement", "content"), "对")
        self.assertEqual(answer.answer_for_ocs(["节俭"], opts, "single", "content"), "节俭")

    def test_is_letters(self):
        self.assertTrue(answer.is_letters("A"))
        self.assertTrue(answer.is_letters("A#C"))
        self.assertFalse(answer.is_letters(""))
        self.assertFalse(answer.is_letters("对"))
        self.assertFalse(answer.is_letters("http://x/1.png"))

    def test_positional_fallback_for_image_options(self):
        """图片题：库里存的是图片地址，页面选项被 OCS 换成 [图片N]，按位置映射。"""
        stored = ["https://p.example.com/a.png", "https://p.example.com/b.png"]
        live = ["[图片1]", "[图片2]"]
        self.assertEqual(answer.contents_to_letters(["https://p.example.com/b.png"], live, "single")[0], "#".join(["https://p.example.com/b.png"]))
        self.assertEqual(
            answer.positional_letters(["https://p.example.com/b.png"], stored, live), "B"
        )
        self.assertEqual(
            answer.positional_letters(["https://p.example.com/a.png"], stored, live), "A"
        )
        # 选项数量对不上就不猜
        self.assertEqual(answer.positional_letters(["https://p.example.com/a.png"], stored, live[:1]), "")
        # 选项顺序变了也同样只按位置，不保证语义正确 —— 但绝不会返回空
        self.assertNotEqual(answer.positional_letters(["https://p.example.com/a.png"], stored, live), "")


class TestBank(TempEnv):
    def test_import_export_roundtrip(self):
        files = library_files()
        if not files:
            self.skipTest("没有可用的样例题库")
        before = bank.stats()["questions"]
        total = self.import_libraries()
        self.assertGreater(total, 0)

        stats = bank.stats()
        self.assertEqual(stats["questions"], before + total)

        course = bank.get_course_by_name(
            os.path.splitext(os.path.basename(files[0]))[0]
        )
        exported = bank.export_course(course["id"], use_legacy_key=True)
        self.assertGreater(len(exported), 0)
        for key, value in list(exported.items())[:5]:
            self.assertTrue(key.startswith("["), key)
            self.assertIsInstance(value, str)
            self.assertTrue(value)

    def test_upsert_dedupe(self):
        course = bank.ensure_default_course()
        cid = course["id"]
        qid, state = bank.upsert_question(
            cid, "single", "唯一题干X", ["甲", "乙"], ["甲"], source="manual"
        )
        self.assertEqual(state, "created")
        qid2, state2 = bank.upsert_question(
            cid, "single", "唯一题干X", ["乙", "甲"], ["甲"], source="manual"
        )
        self.assertEqual(qid2, qid)
        self.assertEqual(state2, "exists")
        row = bank.get_question(qid)
        self.assertEqual(row["answer"], ["甲"])

    def test_import_accepts_letters(self):
        course = bank.ensure_default_course()
        payload = {"[single] 字母题甲 | 甲 | 乙": "B"}
        report = bank.import_questions(payload, course_name="字母课", strategy="overwrite")
        self.assertEqual(report["created"], 1)
        cid = bank.get_course_by_name("字母课")["id"]
        qs = bank.list_questions(course_id=cid, size=10)["items"]
        self.assertEqual(qs[0]["answer"], ["乙"])


if __name__ == "__main__":
    unittest.main(verbosity=2)