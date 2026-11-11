# -*- coding: utf-8 -*-
"""HTTP 接口层。

三条兼容协议 + 一套管理 API，全部收敛到 :mod:`app.pipeline`。
"""

from __future__ import annotations

import functools
import io
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

from . import __version__
from . import ai as ai_mod
from . import answer as ans
from . import bank
from . import images as img_mod
from . import logging_store as logs
from . import models as model_registry
from . import normalize as nz
from . import pipeline
from .cache import get_cache
from .settings import DATA_DIR, get_settings, is_masked

bp = Blueprint("api", __name__)

_STARTED_AT = time.time()


def _fail(message: str, status: int = 400, code: int = 0, **extra: Any) -> Tuple[Response, int]:
    payload = {"ok": False, "code": code, "error": message, "message": message}
    payload.update(extra)
    return jsonify(payload), status


def _ok(data: Any = None, **extra: Any) -> Response:
    payload: Dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


# --------------------------------------------------------------------------
# 排障日志：协议接口未返回答案时，把「客户端到底发了什么」记下来
# --------------------------------------------------------------------------
_MISS_LOG_LOCK = __import__("threading").Lock()


def _protocol_miss(protocol: str, data: Dict[str, Any], reason: str) -> None:
    """记录一次「没给出答案」的协议请求，便于排查客户端发来的字段。

    写 ``<data>/logs/protocol-miss.log``，一行一条 JSON。任何异常都吞掉，
    绝不影响正常响应。
    """
    try:
        record = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "protocol": protocol,
            "reason": reason,
            "remote_addr": request.remote_addr or "",
            "payload": data,
        }
        path = os.path.join(DATA_DIR, "logs", "protocol-miss.log")
        with _MISS_LOG_LOCK:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# 请求解析
# --------------------------------------------------------------------------
def _input() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    data.update({k: v for k, v in request.args.items()})
    if request.method != "GET":
        if request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                data.update(body)
        elif request.form:
            data.update(request.form.to_dict())
        elif request.data:
            try:
                body = json.loads(request.data.decode("utf-8", "ignore"))
                if isinstance(body, dict):
                    data.update(body)
            except (ValueError, UnicodeDecodeError):
                pass
    return data


def _first(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _options(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except ValueError:
                pass
        return nz.parse_options(text)
    return nz.parse_options(value)


def _bool_param(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or request.remote_addr or ""


def _guard() -> Optional[Tuple[Response, int]]:
    cfg = get_settings()
    ip = _client_ip()
    if ip not in _LOOPBACK and not cfg.get("security.allow_lan_admin"):
        return jsonify({"ok": False, "error": "管理接口仅允许本机访问"}), 403
    token = str(cfg.get("security.access_token") or "")
    if token:
        given = (request.headers.get("X-Token") or _input().get("token") or "").strip()
        if given != token:
            return jsonify({"ok": False, "error": "访问令牌不正确"}), 401
    return None


def require_admin(fn):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        blocked = _guard()
        if blocked is not None:
            return blocked
        return fn(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------
# 公共：健康检查
# --------------------------------------------------------------------------
@bp.get("/api/v1/health")
def health() -> Response:
    cfg = get_settings()
    course = bank.get_active_course()
    return _ok(
        {
            "version": __version__,
            "uptime": int(time.time() - _STARTED_AT),
            "course": course.get("name", "") if course else "",
            "ai_enabled": bool(cfg.get("ai.enabled")) and bool(cfg.get("answer.enable_ai")),
            "models": len(model_registry.enabled_models()),
            "time": logs.now_str() if hasattr(logs, "now_str") else time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


# --------------------------------------------------------------------------
# 三条兼容协议
# --------------------------------------------------------------------------
@bp.route("/search", methods=["GET", "POST"])
def protocol_autocourse() -> Response:
    """AutoCourse-DB 协议：直接返回 {"answer": "A#C"}。"""
    data = _input()
    try:
        result = _resolve(data, protocol="ocs_search")
    except pipeline.PipelineError as exc:
        _protocol_miss("ocs_search", data, f"PipelineError: {exc}")
        return jsonify({"answer": "", "code": 0, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _protocol_miss("ocs_search", data, f"异常: {exc}")
        return jsonify({"answer": "", "code": 0, "error": f"内部错误：{exc}"})
    if not result["contents"]:
        _protocol_miss("ocs_search", data, result.get("error") or "未找到答案")
        return jsonify({"answer": "", "code": 0, "error": result.get("error") or "未找到答案"})
    letters = result.get("letters") or ""
    if not ans.is_letters(letters):
        letters = ans.answer_for_ocs(result["contents"], result["options"], result["type"], "letters")
    if not letters:
        # 拿不到可用答案时宁可回 code=0：OCS 会提示「没搜索到答案」，
        # 比回一个空答案导致「答案和选项不匹配」准确得多。
        _protocol_miss("ocs_search", data, "答案与当前选项不匹配")
        return jsonify({"answer": "", "code": 0, "error": "答案与当前选项不匹配"})
    return jsonify(
        {
            "answer": letters,
            "code": 1,
            "source": result["hit_source"],
        }
    )


@bp.route("/api/search", methods=["GET", "POST"])
def protocol_service() -> Response:
    """ocsjs-ai-answer-service 协议：{"code": 1, "question": ..., "answer": ...}。"""
    data = _input()
    try:
        result = _resolve(data, protocol="service")
    except pipeline.PipelineError as exc:
        return jsonify({"code": 0, "msg": str(exc), "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"code": 0, "msg": f"内部错误：{exc}", "error": str(exc)})
    if not result["contents"]:
        _protocol_miss("service", data, result.get("error") or "未找到答案")
        return jsonify({"code": 0, "msg": result.get("error") or "未找到答案", "question": result["question"]})
    letters = result.get("letters") or ""
    if not ans.is_letters(letters):
        letters = ans.answer_for_ocs(result["contents"], result["options"], result["type"], "letters")
    if not letters:
        _protocol_miss("service", data, "答案与当前选项不匹配")
        return jsonify({"code": 0, "msg": "答案与当前选项不匹配", "question": result["question"]})
    return jsonify(
        {
            "code": 1,
            "question": result["question"],
            "answer": letters,
            "type": result["type"],
            "source": result["hit_source"],
            "elapsed_ms": result["elapsed_ms"],
        }
    )


@bp.route("/api/answer", methods=["GET", "POST"])
def protocol_answerer() -> Response:
    """ocs-ai-answerer 协议：返回 ocs_format 三元组。"""
    data = _input()
    try:
        result = _resolve(data, protocol="answerer")
    except pipeline.PipelineError as exc:
        return jsonify({"code": 0, "error": str(exc), "ocs_format": []})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"code": 0, "error": f"内部错误：{exc}", "ocs_format": []})
    if not result["contents"]:
        return jsonify({"code": 0, "error": result.get("error") or "未找到答案", "ocs_format": []})
    letters = ans.answer_for_ocs(result["contents"], result["options"], result["type"], "letters")
    ai_meta = result.get("ai") or {}
    meta = {
        "ai": bool(result["ai_used"]),
        "tags": [],
        "model": ai_meta.get("model_name", ""),
        "reasoning_used": bool(ai_meta.get("reasoning")),
        "source": result["hit_source"],
        "elapsed_ms": result["elapsed_ms"],
        "cost_cny": ai_meta.get("cost_cny", 0),
    }
    return jsonify(
        {
            "code": 1,
            "answer": letters,
            "question": result["question"],
            "ocs_format": [result["question"], letters, meta],
            "meta": meta,
        }
    )


@bp.route("/api/v1/ask", methods=["GET", "POST"])
def protocol_native() -> Response:
    """原生协议：返回完整结构，便于调试与前端调用。"""
    data = _input()
    try:
        result = _resolve(data, protocol="native")
    except pipeline.PipelineError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"内部错误：{exc}", 500)
    return _ok(_public_result(result))


def _resolve(data: Dict[str, Any], protocol: str) -> Dict[str, Any]:
    title = _first(data, "title", "question", "q", "text", "content") or ""
    qtype = _first(data, "type", "qtype", "question_type", "questionType") or "single"
    options_raw = _first(data, "options", "opts", "choices")

    # OCS 5.0「图片题优化」：suggestion_title / suggestion_options 是图片 URL 被
    # 换成 [图片N] 占位符后的干净文本，编号与 images 数组严格对应
    suggestion_title = _first(data, "suggestion_title", "suggestionTitle")
    suggestion_options = _first(data, "suggestion_options", "suggestionOptions")
    if isinstance(suggestion_title, str) and suggestion_title.strip():
        title = suggestion_title
    if suggestion_options not in (None, ""):
        options_raw = suggestion_options
    options = _options(options_raw)

    inline_images, image_list = img_mod.split_refs(data.get("images") or data.get("image") or [])
    if image_list:
        title = title + "\n" + "\n".join(image_list)

    course_id = _first(data, "course_id", "courseId")
    try:
        course_id_int = int(course_id) if course_id not in (None, "") else None
    except (TypeError, ValueError):
        course_id_int = None

    allow_ai_raw = _first(data, "ai", "allow_ai", "allowAi")
    use_cache_raw = _first(data, "cache", "use_cache", "useCache")
    cfg = get_settings()

    return pipeline.resolve(
        title,
        qtype,
        options,
        course_id=course_id_int,
        allow_ai=_bool_param(allow_ai_raw, bool(cfg.get("ai.enabled") and cfg.get("answer.enable_ai"))),
        use_cache=_bool_param(use_cache_raw, bool(cfg.get("cache.enabled"))),
        protocol=protocol,
        remote_addr=_client_ip(),
        images=inline_images,
    )


def _public_result(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = {k: v for k, v in result.items() if k not in ("ai_raw",)}
    payload["answer"] = result["answer"]
    payload["answer_letters"] = ans.answer_for_ocs(
        result["contents"], result["options"], result["type"], "letters"
    ) if result["contents"] else ""
    return payload


# --------------------------------------------------------------------------
# 管理：设置
# --------------------------------------------------------------------------
@bp.get("/api/admin/settings")
@require_admin
def get_settings_api() -> Response:
    cfg = get_settings()
    snap = cfg.snapshot(mask=True)
    snap["models"] = model_registry.public_list()
    snap["mapping_detail"] = model_registry.describe_mapping()
    snap["env"] = {
        "version": __version__,
        "data_dir": DATA_DIR,
        "python": os.sys.version.split()[0],
    }
    return _ok(snap)


@bp.post("/api/admin/settings")
@require_admin
def save_settings_api() -> Response:
    patch = _input().get("patch") if isinstance(_input().get("patch"), dict) else _input()
    patch = {k: v for k, v in patch.items() if k not in ("token", "patch")}
    if "models" in patch:
        patch.pop("models", None)  # 模型走独立接口，避免误覆盖 Key
    cfg = get_settings()
    cfg.update(patch)
    _apply_runtime_settings()
    return _ok(cfg.snapshot(mask=True))


@bp.post("/api/admin/settings/reset")
@require_admin
def reset_settings_api() -> Response:
    cfg = get_settings()
    cfg.reset()
    _apply_runtime_settings()
    return _ok(cfg.snapshot(mask=True))


def _apply_runtime_settings() -> None:
    cfg = get_settings()
    get_cache().configure(
        maxsize=int(cfg.get("cache.size") or 512),
        ttl=int(cfg.get("cache.ttl") or 3600),
    )


# --------------------------------------------------------------------------
# 管理：模型
# --------------------------------------------------------------------------
@bp.get("/api/admin/models")
@require_admin
def list_models_api() -> Response:
    return _ok(
        {
            "items": model_registry.public_list(),
            "mapping": model_registry.describe_mapping(),
            "fallback_models": get_settings().data.get("fallback_models") or [],
        }
    )


@bp.post("/api/admin/models")
@require_admin
def upsert_model_api() -> Response:
    data = _input()
    item = data.get("model") if isinstance(data.get("model"), dict) else data
    item = dict(item)
    item.pop("token", None)
    mid = str(item.get("id") or "").strip()
    cfg = get_settings()
    models = list(cfg.data.get("models") or [])

    existing = next((m for m in models if m.get("id") == mid), None) if mid else None
    if item.get("api_key") is not None and is_masked(str(item.get("api_key"))):
        item.pop("api_key", None)  # 前端回显的脱敏 Key，不覆盖真实值

    if existing is None:
        if not item.get("name"):
            item["name"] = "新模型"
        if not mid:
            item["id"] = f"m_{int(time.time() * 1000) % 10**9}"
        models.append(item)
    else:
        existing.update(item)
    cfg.update({"models": models})
    return _ok({"items": model_registry.public_list(), "mapping": model_registry.describe_mapping()})


@bp.delete("/api/admin/models/<model_id>")
@require_admin
def delete_model_api(model_id: str) -> Response:
    cfg = get_settings()
    models = [m for m in (cfg.data.get("models") or []) if m.get("id") != model_id]
    if len(models) == len(cfg.data.get("models") or []):
        return _fail("模型不存在", 404)
    mapping = cfg.data.get("type_mapping") or {}
    for node in mapping.values():
        if isinstance(node, dict) and isinstance(node.get("models"), list):
            node["models"] = [i for i in node["models"] if i != model_id]
    fallback = [i for i in (cfg.data.get("fallback_models") or []) if i != model_id]
    cfg.update({"models": models, "type_mapping": mapping, "fallback_models": fallback})
    return _ok({"items": model_registry.public_list(), "mapping": model_registry.describe_mapping()})


@bp.post("/api/admin/models/<model_id>/test")
@require_admin
def test_model_api(model_id: str) -> Response:
    result = ai_mod.test_model(model_id)
    return _ok(result)


@bp.post("/api/admin/mapping")
@require_admin
def save_mapping_api() -> Response:
    data = _input()
    mapping = data.get("mapping") if isinstance(data.get("mapping"), dict) else None
    fallback = data.get("fallback_models")
    patch: Dict[str, Any] = {}
    if mapping is not None:
        cfg_data = dict(get_settings().data)
        cfg_data["type_mapping"] = mapping
        cfg_data = model_registry.sanitize_mapping(cfg_data)
        patch["type_mapping"] = cfg_data["type_mapping"]
    if isinstance(fallback, list):
        patch["fallback_models"] = fallback
    if not patch:
        return _fail("没有需要保存的映射")
    get_settings().update(patch)
    return _ok({"mapping": model_registry.describe_mapping(), "fallback_models": get_settings().data.get("fallback_models")})


# --------------------------------------------------------------------------
# 管理：课程与题库
# --------------------------------------------------------------------------
@bp.get("/api/admin/courses")
@require_admin
def list_courses_api() -> Response:
    return _ok({"items": bank.list_courses()})


@bp.post("/api/admin/courses")
@require_admin
def create_course_api() -> Response:
    name = nz.clean_text(_input().get("name") or "")
    if not name:
        return _fail("课程名不能为空")
    course = bank.get_or_create_course(name, source="manual")
    return _ok(course)


@bp.delete("/api/admin/courses/<int:course_id>")
@require_admin
def delete_course_api(course_id: int) -> Response:
    if not bank.delete_course(course_id):
        return _fail("课程不存在", 404)
    return _ok({"deleted": course_id})


@bp.post("/api/admin/courses/<int:course_id>/activate")
@require_admin
def activate_course_api(course_id: int) -> Response:
    course = bank.set_active(course_id)
    if not course:
        return _fail("课程不存在", 404)
    return _ok(course)


@bp.get("/api/admin/questions")
@require_admin
def list_questions_api() -> Response:
    data = _input()
    verified_raw = data.get("verified")
    verified = None if verified_raw in (None, "") else int(_bool_param(verified_raw, False))
    result = bank.list_questions(
        course_id=int(data["course_id"]) if data.get("course_id") else None,
        keyword=str(data.get("keyword") or "").strip(),
        qtype=nz.normalize_qtype(data["qtype"]) if data.get("qtype") else "",
        verified=verified,
        source=str(data.get("source") or ""),
        page=int(data.get("page") or 1),
        size=int(data.get("size") or 50),
        order=str(data.get("order") or "id_desc"),
    )
    return _ok(result)


@bp.get("/api/admin/questions/<int:qid>")
@require_admin
def get_question_api(qid: int) -> Response:
    question = bank.get_question(qid)
    if not question:
        return _fail("题目不存在", 404)
    return _ok(question)


@bp.post("/api/admin/questions")
@require_admin
def create_question_api() -> Response:
    data = _input()
    course_id = data.get("course_id")
    if not course_id:
        course = bank.get_active_course() or bank.ensure_default_course()
        course_id = course["id"]
    try:
        qid, status = bank.upsert_question(
            int(course_id),
            nz.normalize_qtype(data.get("qtype") or data.get("type")),
            data.get("title") or "",
            _options(data.get("options")),
            _answer_list(data.get("answer")),
            source="manual",
            verified=bool(data.get("verified", True)),
            overwrite=True,
        )
    except ValueError as exc:
        return _fail(str(exc))
    return _ok({"id": qid, "status": status})


@bp.put("/api/admin/questions/<int:qid>")
@require_admin
def update_question_api(qid: int) -> Response:
    patch = dict(_input())
    if "options" in patch:
        patch["options"] = _options(patch["options"])
    if "answer" in patch:
        patch["answer"] = _answer_list(patch["answer"])
    if "verified" in patch:
        patch["verified"] = _bool_param(patch["verified"], True)
    try:
        question = bank.update_question(qid, patch)
    except ValueError as exc:
        return _fail(str(exc))
    if not question:
        return _fail("题目不存在", 404)
    return _ok(question)


@bp.delete("/api/admin/questions/<int:qid>")
@require_admin
def delete_question_api(qid: int) -> Response:
    if not bank.delete_question(qid):
        return _fail("题目不存在", 404)
    return _ok({"deleted": qid})


@bp.post("/api/admin/questions/verify")
@require_admin
def verify_questions_api() -> Response:
    data = _input()
    ids = data.get("ids")
    count = bank.bulk_verify(
        course_id=int(data["course_id"]) if data.get("course_id") else None,
        qtype=nz.normalize_qtype(data["qtype"]) if data.get("qtype") else "",
        ids=[int(i) for i in ids] if isinstance(ids, list) else None,
    )
    return _ok({"updated": count})


@bp.post("/api/admin/questions/dedupe")
@require_admin
def dedupe_api() -> Response:
    data = _input()
    result = bank.dedupe(int(data["course_id"]) if data.get("course_id") else None)
    return _ok(result)


def _answer_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value in (None, ""):
        return []
    return ans.split_contents(str(value))


# --------------------------------------------------------------------------
# 管理：导入导出
# --------------------------------------------------------------------------
@bp.post("/api/admin/import")
@require_admin
def import_api() -> Response:
    data = _input()
    payload: Any = data.get("data") or data.get("payload") or data.get("bank")
    course_name = str(data.get("course_name") or data.get("course") or "").strip()
    strategy = str(data.get("strategy") or "skip")
    if payload is None and request.files:
        file = next(iter(request.files.values()))
        try:
            payload = json.loads(file.read().decode("utf-8-sig", "ignore"))
        except (ValueError, UnicodeDecodeError):
            return _fail("上传的文件不是合法 JSON")
    if payload is None:
        return _fail("缺少导入数据（data 字段或文件）")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return _fail("导入数据不是合法 JSON")
    if not course_name:
        course_name = str(payload.get("course") or "") if isinstance(payload, dict) else ""
    try:
        result = bank.import_questions(payload, course_name, strategy=strategy, source="import")
    except ValueError as exc:
        return _fail(str(exc))
    return _ok(result)


@bp.get("/api/admin/export")
@require_admin
def export_api() -> Response:
    data = _input()
    course_id = int(data["course_id"]) if data.get("course_id") else None
    legacy = _bool_param(data.get("legacy"), True)
    exported = bank.export_course(course_id, use_legacy_key=legacy)
    if _bool_param(data.get("download"), False):
        text = json.dumps(exported, ensure_ascii=False, indent=2)
        filename = "题库"
        if course_id:
            course = bank.get_course(course_id)
            if course and course.get("name"):
                filename = str(course["name"])
        quoted = quote(f"{filename}.json")
        return Response(
            text,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
        )
    return _ok(exported)


# --------------------------------------------------------------------------
# 管理：日志与统计
# --------------------------------------------------------------------------
@bp.get("/api/admin/logs")
@require_admin
def list_logs_api() -> Response:
    data = _input()
    result = logs.query_logs(
        page=int(data.get("page") or 1),
        size=int(data.get("size") or 30),
        hit_source=str(data.get("hit_source") or ""),
        qtype=nz.normalize_qtype(data["qtype"]) if data.get("qtype") else "",
        keyword=str(data.get("keyword") or "").strip(),
        date_from=str(data.get("date_from") or ""),
        date_to=str(data.get("date_to") or ""),
    )
    return _ok(result)


@bp.delete("/api/admin/logs")
@require_admin
def clear_logs_api() -> Response:
    return _ok({"deleted": logs.clear_logs()})


@bp.get("/api/admin/logs/export")
@require_admin
def export_logs_api() -> Response:
    csv_text = logs.export_csv()
    return Response(
        "\ufeff" + csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="answer_logs.csv"'},
    )


@bp.get("/api/admin/stats")
@require_admin
def stats_api() -> Response:
    days = int(_input().get("days") or 7)
    cache_stats = get_cache().stats()
    return _ok(
        {
            "version": __version__,
            "uptime": int(time.time() - _STARTED_AT),
            "bank": bank.stats(),
            "logs": logs.stats(days=days),
            "cache": cache_stats,
            "images": img_mod.cache_size(),
            "courses": bank.list_courses(),
        }
    )


@bp.get("/api/admin/cache")
@require_admin
def cache_info_api() -> Response:
    return _ok({"cache": get_cache().stats(), "images": img_mod.cache_size()})


@bp.post("/api/admin/cache/clear")
@require_admin
def clear_cache_api() -> Response:
    count = get_cache().clear()
    images = img_mod.clear_cache()
    return _ok({"entries": count, "images": images})


@bp.post("/api/admin/ai-preview")
@require_admin
def ai_preview_api() -> Response:
    data = _input()
    title = nz.clean_text(_first(data, "title", "question") or "")
    if not title:
        return _fail("题目内容为空")
    qtype = _first(data, "type", "qtype") or "single"
    inline_images, _urls = img_mod.split_refs(data.get("images") or data.get("image") or [])
    result = pipeline.preview_ai(
        qtype,
        title,
        _options(_first(data, "options", "opts")),
        images=inline_images,
    )
    return _ok(result)


@bp.post("/api/admin/logs/flush")
@require_admin
def flush_logs_api() -> Response:
    logs.flush()
    return _ok({"flushed": True})


# --------------------------------------------------------------------------
# 统一错误处理
# --------------------------------------------------------------------------
@bp.app_errorhandler(404)
def not_found(_exc: Any) -> Tuple[Response, int]:
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "接口不存在"}), 404
    return jsonify({"ok": False, "error": "页面不存在"}), 404


@bp.app_errorhandler(500)
def server_error(exc: Any) -> Tuple[Response, int]:
    return jsonify({"ok": False, "error": f"服务器内部错误：{exc}"}), 500


def register(app: Any) -> None:
    app.register_blueprint(bp)
    _apply_runtime_settings()