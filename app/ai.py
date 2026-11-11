# -*- coding: utf-8 -*-
"""大模型调用层：兼容 chat_completions 与 responses 两种协议。

移植自 ocs-ai-answerer 的 call_custom_model（MIT © 2025 Liu Keda），
补全了超时、重试、错误信息与费用统计。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence

from . import prompt as pm
from .settings import get_settings

try:  # requests 可选（requirements 里会装上，但保持降级能力）
    import requests as _requests  # type: ignore
except ImportError:  # pragma: no cover
    _requests = None


class AIError(RuntimeError):
    def __init__(self, message: str, status: int = 0, model_id: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.model_id = model_id


# --------------------------------------------------------------------------
# 基础 HTTP
# --------------------------------------------------------------------------
def _endpoint(base_url: str, suffix: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    for tail in ("/chat/completions", "/responses", "/completions"):
        if base.endswith(tail):
            base = base[: -len(tail)]
    if not base:
        raise AIError("未配置 Base URL")
    return base + suffix


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _proxies() -> Optional[Dict[str, str]]:
    proxy = get_settings().get("ai.proxy") or ""
    return {"http": proxy, "https": proxy} if proxy else None


def _post(url: str, payload: Dict[str, Any], api_key: str, timeout: int) -> Dict[str, Any]:
    if _requests is None:
        raise AIError("缺少 requests 依赖，请先 pip install requests")
    last_error = ""
    attempts = 1 + min(2, int(get_settings().get("answer.max_retries") or 0))
    for attempt in range(1, attempts + 1):
        try:
            resp = _requests.post(
                url,
                headers=_headers(api_key),
                json=payload,
                timeout=timeout,
                proxies=_proxies(),
            )
        except Exception as exc:  # noqa: BLE001 - 网络异常种类很多
            last_error = f"网络请求失败：{exc}"
            if attempt < attempts:
                time.sleep(0.6 * attempt)
                continue
            raise AIError(last_error) from exc

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                snippet = (resp.text or "").strip()[:120]
                raise AIError(f"接口返回的不是合法 JSON（可能输出被截断）：{snippet}") from exc

        detail = _extract_error(resp)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
            last_error = detail
            time.sleep(0.8 * attempt)
            continue
        raise AIError(detail, status=resp.status_code)
    raise AIError(last_error)


def _extract_error(resp: Any) -> str:
    text = ""
    try:
        data = resp.json()
        err = data.get("error")
        if isinstance(err, dict):
            text = str(err.get("message") or err.get("code") or "")
        elif isinstance(err, str):
            text = err
        if not text:
            text = str(data.get("message") or data.get("detail") or "")
    except Exception:  # noqa: BLE001
        text = (resp.text or "")[:300]
    text = text.strip() or f"HTTP {resp.status_code}"
    return f"接口返回 {resp.status_code}：{text[:300]}"


# --------------------------------------------------------------------------
# 协议实现
# --------------------------------------------------------------------------
def _token_limit(model: Dict[str, Any], max_tokens: int) -> int:
    """算这次请求的 max_tokens 预算。

    思考型模型的 reasoning token 也算在 completion 里，预算给少了就会出现
    「思考写满、正文为空」的截断，所以这里至少给到 reasoning_max_tokens。
    """
    cfg = get_settings()
    limit = int(max_tokens or model.get("max_tokens") or 0) or int(cfg.get("ai.max_tokens") or 500)
    if model.get("supports_reasoning"):
        limit = max(limit, int(cfg.get("ai.reasoning_max_tokens") or 4096))
    return limit


def _build_chat_payload(model: Dict[str, Any], messages: Sequence[Dict[str, Any]], reasoning: bool, max_tokens: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model.get("model_name") or model.get("name"),
        "messages": list(messages),
    }
    payload["max_tokens"] = _token_limit(model, max_tokens)

    temperature = float(model.get("temperature") or 0.0)
    top_p = float(model.get("top_p") or 0.0)
    if not reasoning:
        if temperature >= 0:
            payload["temperature"] = temperature
        if top_p > 0:
            payload["top_p"] = top_p
    if reasoning and model.get("supports_reasoning") and model.get("reasoning_param_name"):
        payload[str(model["reasoning_param_name"])] = _coerce(model.get("reasoning_param_value"))
    return payload


def _coerce(value: Any) -> Any:
    text = str(value or "").strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _build_responses_payload(model: Dict[str, Any], messages: Sequence[Dict[str, Any]], reasoning: bool, max_tokens: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model.get("model_name") or model.get("name"),
        "input": list(messages),
    }
    payload["max_output_tokens"] = _token_limit(model, max_tokens)
    if reasoning and model.get("supports_reasoning"):
        payload["reasoning"] = {"effort": str(model.get("reasoning_param_value") or "medium")}
    return payload


def _parse_chat(data: Dict[str, Any]) -> Dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise AIError("接口未返回 choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    reasoning_content = message.get("reasoning_content") or message.get("reasoning") or ""
    usage = data.get("usage") or {}
    return {
        "content": str(content),
        "reasoning_content": str(reasoning_content),
        "finish_reason": str(choices[0].get("finish_reason") or ""),
        "usage": {
            "input": int(usage.get("prompt_tokens") or 0),
            "output": int(usage.get("completion_tokens") or 0),
            "total": int(usage.get("total_tokens") or 0),
        },
    }


def _parse_responses(data: Dict[str, Any]) -> Dict[str, Any]:
    text = data.get("output_text")
    if not text:
        chunks: List[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                    chunks.append(str(part.get("text") or ""))
        text = "".join(chunks)
    usage = data.get("usage") or {}
    return {
        "content": str(text or ""),
        "reasoning_content": "",
        "finish_reason": str(data.get("status") or ""),
        "usage": {
            "input": int(usage.get("input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
            "total": int(usage.get("total_tokens") or 0),
        },
    }


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def call_model(
    model: Dict[str, Any],
    messages: Sequence[Dict[str, Any]],
    reasoning: bool = False,
    max_tokens: int = 0,
) -> Dict[str, Any]:
    """调用单个模型。失败抛 :class:`AIError`。"""
    cfg = get_settings()
    api_key = str(model.get("api_key") or "").strip()
    if not api_key:
        raise AIError(f"模型「{model.get('name')}」未填写 API Key", model_id=str(model.get("id")))
    timeout = int(cfg.get("answer.request_timeout") or 120)
    protocol = str(model.get("protocol") or "chat_completions")
    started = time.time()

    if protocol == "responses":
        payload = _build_responses_payload(model, messages, reasoning, max_tokens)
        data = _post(_endpoint(model.get("base_url", ""), "/responses"), payload, api_key, timeout)
        parsed = _parse_responses(data)
    else:
        payload = _build_chat_payload(model, messages, reasoning, max_tokens)
        data = _post(_endpoint(model.get("base_url", ""), "/chat/completions"), payload, api_key, timeout)
        parsed = _parse_chat(data)

    # 思考过程把预算吃光 → 正文为空。此时悄悄把预算翻倍再问一次，别让用户看到空答案。
    if not parsed["content"].strip() and parsed.get("finish_reason") == "length":
        bigger = min(max(int(payload.get("max_tokens") or payload.get("max_output_tokens") or 0) * 2, 1024), 16384)
        if protocol == "responses":
            payload = _build_responses_payload(model, messages, reasoning, bigger)
            data = _post(_endpoint(model.get("base_url", ""), "/responses"), payload, api_key, timeout)
            parsed = _parse_responses(data)
        else:
            payload = _build_chat_payload(model, messages, reasoning, bigger)
            data = _post(_endpoint(model.get("base_url", ""), "/chat/completions"), payload, api_key, timeout)
            parsed = _parse_chat(data)

    if not parsed["content"].strip() and parsed.get("finish_reason") == "length":
        raise AIError(
            "输出被截断：思考过程占满了 max_tokens，请在「模型管理」里调大「最大输出 tokens」",
            model_id=str(model.get("id")),
        )

    latency_ms = int((time.time() - started) * 1000)
    usage = parsed["usage"]
    price_in = float(model.get("price_in") or 0.0)
    price_out = float(model.get("price_out") or 0.0)
    cost = (usage["input"] * price_in + usage["output"] * price_out) / 1_000_000
    return {
        "content": parsed["content"],
        "reasoning_content": parsed["reasoning_content"],
        "usage": usage,
        "cost_cny": round(cost, 6),
        "latency_ms": latency_ms,
        "protocol": protocol,
        "model_id": str(model.get("id")),
        "model_name": str(model.get("name")),
        "reasoning_used": bool(reasoning),
        "raw": data,
    }


def test_model(model_id: str) -> Dict[str, Any]:
    """连通性自检，返回 ``{ok, message, latency_ms, model}``。"""
    from . import models as model_registry

    model = model_registry.get_model(model_id)
    if not model:
        return {"ok": False, "message": "模型不存在", "latency_ms": 0, "model": model_id}
    full = model_registry.with_key(model)
    try:
        result = call_model(full, pm.test_messages(), reasoning=False, max_tokens=32)
    except AIError as exc:
        return {"ok": False, "message": str(exc), "latency_ms": 0, "model": model_id}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"调用异常：{exc}", "latency_ms": 0, "model": model_id}
    return {
        "ok": True,
        "message": f"连接成功，返回：{result['content'][:60]}",
        "latency_ms": result["latency_ms"],
        "model": model_id,
    }