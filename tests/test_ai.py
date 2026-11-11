# -*- coding: utf-8 -*-
"""AI 链路测试：用本地 mock 服务模拟 OpenAI 兼容接口，不联网、不花钱。

覆盖：
- 单选题字母解析、多选题排序、判断题归一化
- 思考模式（reasoning_content）能否透传到结果里
- AI 报错时降级不崩（接口仍返回结构化结果）
- 没配 API Key 的模型会被跳过，不会白连
- AI 答对后自动入库，第二次请求能命中题库
"""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

from tests import TempEnv
from app import bank
from app.main import create_app
from app.settings import get_settings

TYPE_KEYS = ("single", "multiple", "judgement", "completion", "image")

# 1×1 透明 PNG，用于模拟 OCS 图片题优化上传的 base64
PNG_1PX = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class MockAI:
    """极简 OpenAI 兼容服务：POST /v1/chat/completions。"""

    def __init__(self) -> None:
        self.reply: Dict[str, Any] = {"content": "C"}
        self.replies: List[Dict[str, Any]] = []
        self.requests: List[Dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8", "replace")
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = {}
                outer.requests.append(
                    {
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "payload": payload,
                    }
                )
                reply = outer._next_reply()
                status = int(reply.get("status", 200))
                if status != 200:
                    self._send(status, {"error": {"message": reply.get("error", "boom")}})
                    return
                message: Dict[str, Any] = {
                    "role": "assistant",
                    "content": reply.get("content", ""),
                }
                if reply.get("reasoning"):
                    message["reasoning_content"] = reply["reasoning"]
                self._send(
                    status,
                    {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion",
                        "created": 0,
                        "model": payload.get("model") or "mock-model",
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": reply.get("finish_reason", "stop"),
                            }
                        ],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 8, "total_tokens": 128},
                    },
                )

            def _send(self, status: int, body: Dict[str, Any]) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:  # 静音
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> "MockAI":
        self._thread.start()
        return self

    def _next_reply(self) -> Dict[str, Any]:
        if self.replies:
            return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return self.reply

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:%d/v1" % self.port


class AITest(TempEnv):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.client = create_app().test_client()

    # -- 工具 -------------------------------------------------------------
    def use_ai(self, content: str = "C", reasoning: str = "", status: int = 200,
               error: str = "boom", api_key: str = "sk-mock",
               multimodal: bool = False) -> MockAI:
        srv = MockAI()
        srv.reply = {"content": content, "reasoning": reasoning, "status": status, "error": error}
        srv.start()
        self.addCleanup(srv.stop)
        model = {
            "id": "mock",
            "name": "Mock AI",
            "protocol": "chat_completions",
            "base_url": srv.base_url,
            "model_name": "mock-model",
            "api_key": api_key,
            "enabled": True,
            "is_multimodal": bool(multimodal),
            "supports_reasoning": bool(reasoning),
            "reasoning_param_name": "reasoning_effort",
            "reasoning_param_value": "medium",
            "max_tokens": 0,
            "temperature": 0,
            "top_p": 0,
            "price_in": 1.0,
            "price_out": 2.0,
        }
        cfg = get_settings()
        cfg.update(
            {
                "models": [model],
                "type_mapping": {
                    key: {"models": ["mock"], "enable_reasoning": key in ("multiple", "image")}
                    for key in TYPE_KEYS
                },
                "fallback_models": ["mock"],
                "answer": {"auto_save": True, "auto_save_verified": False},
            }
        )
        return srv

    def ask(self, **payload: Any) -> Dict[str, Any]:
        resp = self.client.post("/api/v1/ask", json=payload)
        self.assertEqual(resp.status_code, 200, resp.data[:400])
        body = resp.get_json()
        self.assertTrue(body.get("ok"), body)
        return body["data"]

    # -- 用例 -------------------------------------------------------------
    def test_single_choice_by_letter(self) -> None:
        srv = self.use_ai("C")
        data = self.ask(
            title="这是一道只有 AI 才答得出的题：地球的天然卫星是？",
            type="single",
            options=["A. 火星", "B. 金星", "C. 月球"],
        )
        self.assertEqual(data["hit_source"], "ai")
        self.assertEqual(data["letters"], "C")
        self.assertEqual(data["answer_letters"], "C")
        self.assertEqual(data["contents"], ["月球"])
        self.assertTrue(data["ai_used"])
        self.assertEqual(data["ai"]["model_name"], "Mock AI")
        self.assertGreater(data["ai"]["total_tokens"], 0)
        self.assertGreater(data["ai"].get("cost_cny", 0), 0)
        self.assertEqual(len(srv.requests), 1)
        self.assertEqual(srv.requests[0]["auth"], "Bearer sk-mock")
        self.assertTrue(srv.requests[0]["path"].endswith("/chat/completions"))

    def test_multiple_choice_sorted(self) -> None:
        self.use_ai("C#A")
        data = self.ask(
            title="多选题测试：以下哪些属于水果？",
            type="multiple",
            options=["A. 苹果", "B. 白菜", "C. 香蕉"],
        )
        self.assertEqual(data["letters"], "A#C")
        self.assertEqual(data["answer_letters"], "A#C")
        self.assertEqual(data["contents"], ["苹果", "香蕉"])

    def test_judgement_normalized(self) -> None:
        self.use_ai("正确")
        data = self.ask(title="判断题测试：地球是圆的。", type="judgement", options=[])
        self.assertEqual(data["contents"], ["对"])
        self.assertEqual(data["letters"], "对")
        self.assertEqual(data["answer_letters"], "对")

    def test_reasoning_passthrough(self) -> None:
        self.use_ai("B", reasoning="先看题干，再排除 A 和 C，所以选 B")
        data = self.ask(
            title="思考模式测试：1+1 等于几？",
            type="single",
            options=["A. 1", "B. 2", "C. 3"],
        )
        self.assertEqual(data["letters"], "B")
        self.assertIn("排除", data["ai"].get("reasoning_content", ""))

    def test_ai_error_degrades(self) -> None:
        self.use_ai("", status=500, error="upstream exploded")
        data = self.ask(
            title="AI 挂掉时的行为：这题注定答不出来吧？",
            type="single",
            options=["A. 甲", "B. 乙"],
        )
        self.assertEqual(data["answer"], "")
        self.assertEqual(data["letters"], "")
        self.assertTrue(data.get("error") or not data["ai_used"])

    def test_missing_key_skips_request(self) -> None:
        srv = self.use_ai("C", api_key="")
        data = self.ask(
            title="没有 Key 的模型不应该被调用：随便问问？",
            type="single",
            options=["A. 甲", "B. 乙", "C. 丙"],
        )
        self.assertEqual(len(srv.requests), 0, "没有 Key 却发起了请求")
        self.assertEqual(data["answer"], "")

    def test_truncated_then_retry_bigger_budget(self) -> None:
        """思考把预算吃光（finish_reason=length、正文空）时应自动加大 max_tokens 重试一次。"""
        srv = self.use_ai("")
        srv.replies = [
            {"content": "", "finish_reason": "length"},
            {"content": "A", "finish_reason": "stop"},
        ]
        data = self.ask(
            title="截断重试测试：以下哪个是质数？",
            type="single",
            options=["A. 7", "B. 8", "C. 9"],
        )
        self.assertEqual(data["letters"], "A")
        self.assertEqual(len(srv.requests), 2, "截断后应重试一次")
        first = int(srv.requests[0]["payload"]["max_tokens"])
        second = int(srv.requests[1]["payload"]["max_tokens"])
        self.assertGreater(second, first)

    def test_ocs_image_optimize_inline_base64(self) -> None:
        """OCS 5.0 图片题优化：suggestion_* + images(base64) 应变成图文混排的 content。"""
        srv = self.use_ai("A", multimodal=True)
        data = self.ask(
            suggestion_title="看图选择 [图片1] 中的图形",
            suggestion_options="A. 三角形\nB. 圆形",
            type="single",
            images=[PNG_1PX],
        )
        self.assertEqual(data["hit_source"], "ai")
        self.assertEqual(data["letters"], "A")
        self.assertEqual(len(srv.requests), 1)
        content = srv.requests[0]["payload"]["messages"][-1]["content"]
        self.assertIsInstance(content, list, "多模态请求的 content 应该是数组")
        images = [p for p in content if p.get("type") == "image_url"]
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        text = "".join(p.get("text", "") for p in content if p.get("type") == "text")
        self.assertIn("题目图片 1", text)
        self.assertNotIn("[图片1]", text, "占位符应被真实图片替换")

    def test_auto_save_then_hit(self) -> None:
        self.use_ai("B")
        title = "自动入库测试：光在真空中的速度约为？"
        options = ["A. 3×10^5 km/s", "B. 3×10^8 m/s"]
        first = self.ask(title=title, type="single", options=options, cache=False)
        self.assertEqual(first["hit_source"], "ai")
        self.assertEqual(first["letters"], "B")
        self.assertEqual(first["verified"], False)

        rows = bank.list_questions(keyword="光在真空中的速度", size=5)["items"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "ai")
        self.assertFalse(rows[0]["verified"])

        second = self.ask(title=title, type="single", options=options, cache=False)
        self.assertIn(second["hit_source"], ("bank", "fuzzy"))
        self.assertEqual(second["answer_letters"], "B")
        self.assertFalse(second["ai_used"])