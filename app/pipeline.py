# -*- coding: utf-8 -*-
"""答题主流水线：缓存 → 精确 → 旧格式 → 模糊 → AI → 入库 → 记日志。

这是整个项目的心脏，三条对外协议都收敛到这里。
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from . import ai as ai_mod
from . import answer as ans
from . import bank
from . import images as img_mod
from . import logging_store as logs
from . import match
from . import models as model_registry
from . import normalize as nz
from . import prompt as pm
from .cache import get_cache
from .settings import get_settings


class PipelineError(ValueError):
    pass


def resolve(
    title: str,
    qtype: Any = "single",
    options: Any = None,
    *,
    course_id: Optional[int] = None,
    allow_ai: Optional[bool] = None,
    use_cache: Optional[bool] = None,
    protocol: str = "api",
    remote_addr: str = "",
    similarity_threshold: float = 0.0,
    images: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """解析一道题，返回统一结构的结果。"""
    started = time.time()
    request_id = uuid.uuid4().hex[:12]
    cfg = get_settings()

    title = nz.clean_text(title)
    if not title:
        raise PipelineError("题目内容为空")
    qtype_norm = nz.normalize_qtype(qtype)
    opts = nz.parse_options(options)
    inline_images = [i for i in (images or []) if img_mod.is_data_uri(i)]
    urls_in_text = img_mod.collect_images(title, opts)
    has_images = bool(inline_images) or bool(urls_in_text)
    if has_images and qtype_norm not in (nz.QTYPE_SINGLE, nz.QTYPE_MULTIPLE, nz.QTYPE_IMAGE):
        qtype_norm = nz.QTYPE_IMAGE

    if use_cache is None:
        use_cache = bool(cfg.get("cache.enabled"))
    if allow_ai is None:
        allow_ai = bool(cfg.get("ai.enabled"))

    course = bank.get_course(course_id) if course_id else bank.get_active_course()
    if course is None:
        course = bank.ensure_default_course()
    course_id = int(course["id"])

    cache_key = f"{course_id}:{nz.canonical_key(qtype_norm, title, opts)}"
    cache = get_cache()
    threshold = float(similarity_threshold or cfg.get("answer.fuzzy_threshold") or 0.92)

    result: Dict[str, Any] = {
        "question": title,
        "type": qtype_norm,
        "type_label": nz.qtype_label(qtype_norm),
        "options": opts,
        "course": course.get("name", ""),
        "course_id": course_id,
        "images": len(inline_images) + len(urls_in_text),
        "request_id": request_id,
        "hit_source": "",
        "confidence": 0.0,
        "contents": [],
        "letters": "",
        "answer": "",
        "answer_content": "",
        "question_id": None,
        "verified": False,
        "ai_used": False,
        "ai": {},
        "raw": "",
        "error": "",
        "elapsed_ms": 0,
    }

    # 1) 缓存
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            result.update(
                {
                    "hit_source": "cache",
                    "confidence": 1.0,
                    "contents": list(cached.get("contents") or []),
                    "question_id": cached.get("question_id"),
                    "verified": bool(cached.get("verified")),
                }
            )
            # 缓存只复用「答案内容」，字母必须按本次请求的选项顺序重算：
            # 同一道题的选项顺序每次作答都可能不同，直接复用旧字母会选错选项。
            result["letters"] = ans.contents_to_letters(result["contents"], opts, qtype_norm)[0]
            return _finalize(result, started, cfg, protocol, remote_addr, logs_ok=True)

    # 2) 精确命中（cross_course=True 时跨课程查询）
    scope = None if cfg.get("answer.cross_course") else [course_id]
    row = bank.find_by_canonical([nz.canonical_key(qtype_norm, title, opts)], scope)
    if row is None:
        row = bank.find_by_legacy(nz.legacy_key_variants(qtype_norm, title, opts), scope)
        if row is not None:
            result["hit_source"] = "legacy"

    if row is not None:
        result.update(
            {
                "hit_source": result["hit_source"] or "bank",
                "confidence": 1.0,
                "contents": list(row.get("answer") or []),
                "question_id": row.get("id"),
                "verified": bool(row.get("verified")),
            }
        )
        result["letters"] = _letters_for(
            result["contents"], row.get("options") or [], opts, qtype_norm
        )
        bank.touch_hit(int(row["id"]))
        _remember(cache, cache_key, result, use_cache)
        return _finalize(result, started, cfg, protocol, remote_addr)

    # 3) 模糊匹配
    candidates = bank.fuzzy_candidates(scope, qtype_norm, limit=400)
    matched = match.best_fuzzy_match(title, opts, qtype_norm, candidates, threshold=threshold)
    best, score = matched if matched else (None, 0.0)
    if best is not None:
        result.update(
            {
                "hit_source": "fuzzy",
                "confidence": round(score, 4),
                "contents": list(best.get("answer") or []),
                "question_id": best.get("id"),
                "verified": bool(best.get("verified")),
            }
        )
        result["letters"] = _letters_for(
            result["contents"], best.get("options") or [], opts, qtype_norm
        )
        bank.touch_hit(int(best["id"]))
        _remember(cache, cache_key, result, use_cache)
        return _finalize(result, started, cfg, protocol, remote_addr)

    # 4) AI 兜底
    if not allow_ai:
        result["error"] = "未命中题库，且 AI 兜底已关闭"
        return _finalize(result, started, cfg, protocol, remote_addr, success=False)

    ai_result = _ask_ai(qtype_norm, title, opts, has_images, inline_images)
    result["ai_used"] = bool(ai_result.get("used"))
    result["ai"] = ai_result.get("meta") or {}
    result["raw"] = ai_result.get("raw", "")
    if ai_result.get("error"):
        result["error"] = ai_result["error"]
        return _finalize(result, started, cfg, protocol, remote_addr, success=False)

    contents: List[str] = ai_result.get("contents") or []
    if not contents:
        result["error"] = "AI 未给出可解析的答案"
        return _finalize(result, started, cfg, protocol, remote_addr, success=False)

    result["contents"] = contents
    result["letters"] = ai_result.get("letters", "")
    result["hit_source"] = "ai"
    result["verified"] = False
    result["confidence"] = 0.5

    # 5) 自动入库
    if cfg.get("answer.auto_save") and not ai_result.get("error"):
        verified = bool(cfg.get("answer.auto_save_verified"))
        try:
            qid, status = bank.upsert_question(
                course_id,
                qtype_norm,
                title,
                opts,
                contents,
                source="ai",
                verified=verified,
                original_title=title,
                note=f"AI:{ai_result.get('meta', {}).get('model_name', '')}",
                overwrite=True,
            )
            result["question_id"] = qid
            result["saved"] = status
        except Exception as exc:  # noqa: BLE001 - 入库失败不影响作答
            result["error"] = f"入库失败：{exc}"

    if use_cache:
        _remember(cache, cache_key, result, use_cache)

    return _finalize(result, started, cfg, protocol, remote_addr)


def _remember(cache, cache_key: str, result: Dict[str, Any], enabled: bool) -> None:
    """把命中结果写进内存缓存（失败不影响作答）。"""
    if not enabled:
        return
    try:
        cache.set(
            cache_key,
            {
                "contents": list(result.get("contents") or []),
                "letters": result.get("letters", ""),
                "question_id": result.get("question_id"),
                "verified": bool(result.get("verified")),
            },
        )
    except Exception:  # noqa: BLE001 - 缓存只是加速，不能影响主流程
        pass


# --------------------------------------------------------------------------
# AI 调用
# --------------------------------------------------------------------------
def _ask_ai(
    qtype: str,
    title: str,
    opts: Sequence[str],
    has_images: bool,
    inline_images: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    candidates = model_registry.pick_models(qtype, has_images=has_images)
    if not candidates:
        reason = "未配置可用的多模态模型" if has_images else "未配置可用模型"
        return {"used": False, "error": reason, "meta": {}, "raw": ""}

    cfg = get_settings()
    reasoning = bool(model_registry.reasoning_for(qtype))
    errors: List[str] = []

    for model in candidates:
        if has_images and not model.get("is_multimodal"):
            continue
        try:
            messages = _build_messages(qtype, title, opts, has_images)
            result = _call_with_images(
                model, messages, has_images, title, opts, reasoning, cfg, inline_images
            )
        except ai_mod.AIError as exc:
            errors.append(f"{model.get('name')}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model.get('name')}: {exc}")
            continue

        raw = result["content"]
        parsed = _process(qtype, raw, opts)
        if not parsed.get("contents"):
            errors.append(f"{model.get('name')}: 返回无法解析（{raw[:40]!r}）")
            continue
        meta = {
            "model_id": result["model_id"],
            "model_name": result["model_name"],
            "reasoning": result["reasoning_used"],
            "prompt_tokens": result["usage"]["input"],
            "completion_tokens": result["usage"]["output"],
            "total_tokens": result["usage"]["total"],
            "cost_cny": result["cost_cny"],
            "latency_ms": result["latency_ms"],
            "reasoning_content": (result.get("reasoning_content") or "")[:2000],
        }
        return {
            "used": True,
            "contents": parsed["contents"],
            "letters": parsed["letters"],
            "raw": raw,
            "meta": meta,
            "error": "",
        }

    return {"used": False, "error": "AI 调用全部失败：" + "；".join(errors[:3]), "meta": {"tried": len(errors)}, "raw": ""}


def _build_messages(qtype: str, title: str, opts: Sequence[str], has_images: bool) -> List[Dict[str, Any]]:
    extra = ""
    cfg = get_settings()
    if cfg.get("answer.extra_prompt"):
        extra = "\n" + str(cfg.get("answer.extra_prompt"))
    messages = pm.build_messages(
        qtype,
        title,
        opts,
        use_option_labels=cfg.get("answer.use_option_labels", True),
        has_images=has_images,
        extra_system=extra,
    )
    return messages


def _call_with_images(
    model: Dict[str, Any],
    messages: List[Dict[str, Any]],
    has_images: bool,
    title: str,
    opts: Sequence[str],
    reasoning: bool,
    cfg: Any,
    inline_images: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if not has_images or not model.get("is_multimodal"):
        return ai_mod.call_model(model, messages, reasoning=reasoning)

    user_text = messages[-1]["content"]
    if inline_images:
        # 客户端直接上传的 base64（OCS 5.0 图片题优化），无需下载
        parts, reports = img_mod.build_inline_content(user_text, list(inline_images))
    else:
        urls = img_mod.collect_images(title, opts)
        parts, reports = img_mod.build_user_content(user_text, urls)
    if not any(p.get("type") == "image_url" for p in parts):
        return ai_mod.call_model(model, messages, reasoning=reasoning)
    patched = list(messages[:-1]) + [{"role": "user", "content": parts}]
    result = ai_mod.call_model(model, patched, reasoning=reasoning)
    result["image_reports"] = [
        {"index": r["index"], "ok": r["ok"], "error": r.get("error", ""), "bytes": 0} for r in reports
    ]
    return result


def _process(qtype: str, raw: str, opts: Sequence[str]) -> Dict[str, Any]:
    if qtype in (nz.QTYPE_SINGLE, nz.QTYPE_MULTIPLE, nz.QTYPE_IMAGE):
        parsed = ans.process_choice(raw, opts, nz.QTYPE_MULTIPLE if qtype != nz.QTYPE_SINGLE else nz.QTYPE_SINGLE)
        contents = parsed.get("contents") or []
        if not contents:
            return {"contents": [], "letters": ""}
        letters = "#".join(parsed.get("letters") or [])
        return {"contents": contents, "letters": letters}
    if qtype == nz.QTYPE_JUDGEMENT:
        parsed = ans.process_judgement(raw)
        value = parsed.get("value") or ""
        if not value:
            return {"contents": [], "letters": ""}
        return {"contents": [value], "letters": value}
    parsed = ans.process_completion(raw)
    value = parsed.get("value") or ""
    if not value:
        return {"contents": [], "letters": ""}
    items = [p.strip() for p in re.split(r"[#＃]", value) if p.strip()] or [value]
    return {"contents": items, "letters": ""}


def _letters_for(
    contents: Sequence[str],
    stored_options: Sequence[str],
    live_options: Sequence[str],
    qtype: str,
) -> str:
    """把库里的答案内容映射成当前页面的字母。

    先按内容匹配；匹配不上（图片题选项被 OCS 换成 ``[图片N]`` 等）时，
    若两边选项数量一致，退化为按位置映射。
    """
    letters = ans.contents_to_letters(contents, live_options, qtype)[0]
    if qtype in (nz.QTYPE_SINGLE, nz.QTYPE_MULTIPLE) and not ans.is_letters(letters):
        fixed = ans.positional_letters(contents, stored_options, live_options)
        if fixed:
            return fixed
    return letters


# --------------------------------------------------------------------------
# 收尾：格式化 + 记日志
# --------------------------------------------------------------------------
def _finalize(
    result: Dict[str, Any],
    started: float,
    cfg: Any,
    protocol: str,
    remote_addr: str,
    success: Optional[bool] = None,
    logs_ok: bool = True,
) -> Dict[str, Any]:
    qtype = result["type"]
    fmt = str(cfg.get("answer.answer_format") or "auto")
    if fmt == "auto":
        fmt = "content" if qtype == nz.QTYPE_COMPLETION else "letters"
    opts = result["options"]
    contents = result["contents"]
    result["answer_content"] = "#".join(contents)
    if contents:
        letters = result.get("letters") or ""
        if fmt == "letters" and ans.is_letters(letters):
            result["answer"] = letters
        else:
            result["answer"] = ans.answer_for_ocs(contents, opts, qtype, fmt)
    else:
        result["answer"] = ""
    result["elapsed_ms"] = int((time.time() - started) * 1000)

    if logs_ok:
        ai_meta = result.get("ai") or {}
        logs.log_answer(
            {
                "request_id": result["request_id"],
                "ts": None,
                "protocol": protocol,
                "course_id": result["course_id"],
                "qtype": qtype,
                "title": result["question"],
                "options_json": opts,
                "hit_source": result["hit_source"],
                "answer": result["answer"],
                "matched_qid": result.get("question_id"),
                "similarity": result["confidence"],
                "model_id": ai_meta.get("model_id", ""),
                "model_name": ai_meta.get("model_name", ""),
                "reasoning": 1 if ai_meta.get("reasoning") else 0,
                "prompt_tokens": ai_meta.get("prompt_tokens", 0),
                "completion_tokens": ai_meta.get("completion_tokens", 0),
                "cost_cny": ai_meta.get("cost_cny", 0),
                "latency_ms": result["elapsed_ms"],
                "images_count": result["images"],
                "success": 1 if (bool(contents) if success is None else success) else 0,
                "error": result.get("error", ""),
                "remote_addr": remote_addr,
            }
        )
    return result


def preview_ai(
    qtype: str,
    title: str,
    options: Any,
    images: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """答题测试页「强制走 AI」用：跳过题库，直接问模型。"""
    opts = nz.parse_options(options)
    qtype_norm = nz.normalize_qtype(qtype)
    inline_images = [i for i in (images or []) if img_mod.is_data_uri(i)]
    has_images = bool(inline_images) or bool(img_mod.collect_images(title, opts))
    if has_images:
        qtype_norm = nz.QTYPE_IMAGE
    started = time.time()
    out = _ask_ai(qtype_norm, nz.clean_text(title), opts, has_images, inline_images)
    contents = out.get("contents") or []
    letters = out.get("letters", "")
    return {
        "ok": bool(contents) and not out.get("error"),
        "error": out.get("error", ""),
        "contents": contents,
        "letters": letters,
        "answer": ans.answer_for_ocs(contents, opts, qtype_norm, "letters") if contents else "",
        "raw": out.get("raw", ""),
        "ai": out.get("meta") or {},
        "elapsed_ms": int((time.time() - started) * 1000),
    }