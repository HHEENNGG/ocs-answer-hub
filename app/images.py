# -*- coding: utf-8 -*-
"""图片题支持：URL 提取、带缓存下载、Base64 内联、图文混排。

移植自 ocs-ai-answerer 的 download_image_as_base64 / build_multimodal_messages
（MIT © 2025 Liu Keda），增加了磁盘缓存与失败降级。
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import normalize as nz
from .settings import DATA_DIR, get_settings

CACHE_DIR = os.path.join(DATA_DIR, "cache", "images")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://mooc1.chaoxing.com/",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}

_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "svg": "image/svg+xml",
}

TOKEN_RE = re.compile(r"⟦IMG(\d+)⟧")

_requests_mod = None
try:  # requests 可选
    import requests as _requests_mod  # type: ignore
except ImportError:  # pragma: no cover
    _requests_mod = None


# --------------------------------------------------------------------------
# 收集 URL
# --------------------------------------------------------------------------
def collect_images(title: str, options: Sequence[str]) -> List[str]:
    """按「题干 → 选项」出现顺序收集去重后的图片 URL。"""
    urls: List[str] = []
    for text in [title] + [o for o in options or []]:
        for url in nz.extract_image_urls(text):
            if url not in urls:
                urls.append(url)
    limit = int(get_settings().get("ai.max_images") or 8)
    return urls[:limit]


def needs_multimodal(title: str, options: Sequence[str]) -> bool:
    return bool(collect_images(title, options))


# --------------------------------------------------------------------------
# 下载与缓存
# --------------------------------------------------------------------------
def _hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _cache_path(url: str) -> str:
    ext = "png"
    m = re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)", url, re.I)
    if m:
        ext = m.group(1).lower()
    return os.path.join(CACHE_DIR, f"{_hash(url)}.{ext}")


def _guess_mime(url: str, path: str = "") -> str:
    m = re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)", url, re.I)
    if m:
        return _MIME_BY_EXT.get(m.group(1).lower(), "image/png")
    if path:
        m = re.search(r"\.(\w+)$", path)
        if m:
            return _MIME_BY_EXT.get(m.group(1).lower(), "image/png")
    return "image/png"


def _download_bytes(url: str) -> Tuple[bool, bytes, str]:
    cfg = get_settings()
    timeout = int(cfg.get("ai.image_timeout") or 15)
    max_mb = int(cfg.get("ai.image_max_mb") or 5)
    max_bytes = max_mb * 1024 * 1024
    proxy = cfg.get("ai.proxy") or ""

    if _requests_mod is not None:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        try:
            resp = _requests_mod.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
            if resp.status_code != 200:
                return False, b"", f"HTTP {resp.status_code}"
            data = resp.content
            if len(data) > max_bytes:
                return False, b"", f"图片超过 {max_mb}MB"
            return True, data, ""
        except Exception as exc:  # noqa: BLE001
            return False, b"", str(exc)
    # 退化到 urllib
    try:
        import urllib.request

        req = urllib.request.Request(url, headers=HEADERS)
        handlers = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(req, timeout=timeout) as resp:  # noqa: S310 - 用户自己的题目图片
            data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            return False, b"", f"图片超过 {max_mb}MB"
        return True, data, ""
    except Exception as exc:  # noqa: BLE001
        return False, b"", str(exc)


def fetch_image(url: str) -> Dict[str, Any]:
    """下载（带磁盘缓存）。返回 ``{ok, path, data_uri, mime, error}``。"""
    path = _cache_path(url)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            mime = _guess_mime(url, path)
            return {
                "ok": True,
                "path": path,
                "mime": mime,
                "data_uri": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                "error": "",
                "cached": True,
            }
        except OSError:
            pass
    ok, data, error = _download_bytes(url)
    if not ok or not data:
        return {"ok": False, "path": "", "mime": "", "data_uri": "", "error": error or "下载失败"}
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError:
        pass
    mime = _guess_mime(url, path)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    return {
        "ok": True,
        "path": path,
        "mime": mime,
        "data_uri": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
        "error": "",
        "cached": False,
    }


def clear_cache() -> int:
    if not os.path.isdir(CACHE_DIR):
        return 0
    count = 0
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                count += 1
            except OSError:
                pass
    return count


def cache_size() -> Dict[str, int]:
    if not os.path.isdir(CACHE_DIR):
        return {"files": 0, "bytes": 0}
    files = 0
    total = 0
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            files += 1
            total += os.path.getsize(path)
    return {"files": files, "bytes": total}


# --------------------------------------------------------------------------
# 图文混排
# --------------------------------------------------------------------------
def build_user_content(
    text: str,
    urls: Sequence[str],
    label: str = "题目图片",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把带图片 URL 的文本转成图文混排的 content 数组。

    返回 ``(content_parts, image_reports)``；
    若所有图片都下载失败，降级为纯文本（content_parts 只有一个 text 块）。
    """
    if not urls:
        return [{"type": "text", "text": text}], []

    reports: List[Dict[str, Any]] = []
    token_map: Dict[str, str] = {}
    for idx, url in enumerate(urls, start=1):
        report = fetch_image(url)
        report["url"] = url
        report["index"] = idx
        reports.append(report)
        if report["ok"]:
            token_map[url] = f"⟦IMG{idx}⟧"

    if not token_map:
        return [{"type": "text", "text": nz.strip_images(text) or text}], reports

    # 用 token 替换 URL（保留首次出现位置）
    replaced = text
    for url, token in token_map.items():
        replaced = replaced.replace(url, token)
    # 未成功的 URL 去掉，避免模型读 URL
    for url in urls:
        if url not in token_map:
            replaced = replaced.replace(url, "[图片未能加载]")

    parts: List[Dict[str, Any]] = []
    buffer: List[str] = []
    images_by_index = {r["index"]: r for r in reports if r["ok"]}

    def flush() -> None:
        chunk = "".join(buffer).strip()
        if chunk:
            parts.append({"type": "text", "text": chunk})
        buffer.clear()

    pos = 0
    for match in TOKEN_RE.finditer(replaced):
        buffer.append(replaced[pos : match.start()])
        flush()
        idx = int(match.group(1))
        report = images_by_index.get(idx)
        if report:
            parts.append({"type": "text", "text": f"[{label} {idx}]"})
            parts.append({"type": "image_url", "image_url": {"url": report["data_uri"]}})
        pos = match.end()
    buffer.append(replaced[pos:])
    flush()

    if not parts:
        parts = [{"type": "text", "text": nz.strip_images(text) or text}]
    return parts, reports


# --------------------------------------------------------------------------
# 客户端内联 base64（OCS 5.0「图片题优化」直接上传 data URL，无需下载）
# --------------------------------------------------------------------------
MARKER_RE = re.compile(r"[\[【]\s*图片\s*(\d+)\s*[\]】]")

_DATA_URI_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.I)


def is_data_uri(value: Any) -> bool:
    return isinstance(value, str) and bool(_DATA_URI_RE.match(value.strip()))


def split_refs(values: Any) -> Tuple[List[str], List[str]]:
    """把入参里的图片引用分成 ``(data_uri 列表, http url 列表)``，顺序不变。"""
    inline: List[str] = []
    urls: List[str] = []
    items = values if isinstance(values, (list, tuple)) else [values]
    for item in items:
        if not isinstance(item, str):
            continue
        ref = item.strip()
        if not ref:
            continue
        if is_data_uri(ref):
            if ref not in inline:
                inline.append(ref)
        elif ref.startswith(("http://", "https://")):
            if ref not in urls:
                urls.append(ref)
        else:
            for found in nz.extract_image_urls(ref):
                if found not in urls:
                    urls.append(found)
    limit = int(get_settings().get("ai.max_images") or 8)
    return inline[:limit], urls[:limit]


def inline_report(ref: str) -> Dict[str, Any]:
    """校验一个 data URI，返回与 ``fetch_image`` 同形状的字典。"""
    ref = (ref or "").strip()
    if not is_data_uri(ref):
        return {"ok": False, "path": "", "mime": "", "data_uri": "", "error": "不是 base64 图片", "cached": False}
    max_bytes = int(float(get_settings().get("ai.image_max_mb") or 5) * 1024 * 1024)
    payload = ref.split(",", 1)[1] if "," in ref else ""
    approx = len(payload) * 3 // 4
    if approx > max_bytes:
        return {
            "ok": False,
            "path": "",
            "mime": "",
            "data_uri": "",
            "error": f"图片超过 {max_bytes // (1024 * 1024)}MB",
            "cached": False,
        }
    mime = (_DATA_URI_RE.match(ref).group(0)[5:-8] or "image/png") if _DATA_URI_RE.match(ref) else "image/png"
    return {"ok": True, "path": "", "mime": mime, "data_uri": ref, "error": "", "cached": False}


def build_inline_content(
    text: str,
    refs: Sequence[str],
    label: str = "题目图片",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按文本里的 ``[图片N]`` 标记顺序内联 base64 图片。

    OCS 5.0 的 ``suggestion_title`` / ``suggestion_options`` 会把图片 URL 换成
    `` [图片N] ``，而 ``env.images`` 是按同一顺序排列的 data URL 数组，
    因此直接用编号定位，不做任何下载。
    """
    if not refs:
        return [{"type": "text", "text": text}], []

    reports: List[Dict[str, Any]] = []
    available: Dict[int, str] = {}
    for idx, ref in enumerate(refs, start=1):
        report = inline_report(ref)
        report["index"] = idx
        report["url"] = ""
        reports.append(report)
        if report["ok"]:
            available[idx] = report["data_uri"]

    if not available:
        return [{"type": "text", "text": nz.strip_images(text) or text}], reports

    parts: List[Dict[str, Any]] = []
    buffer: List[str] = []

    def flush() -> None:
        chunk = "".join(buffer).strip()
        if chunk:
            parts.append({"type": "text", "text": chunk})
        buffer.clear()

    pos = 0
    for match in MARKER_RE.finditer(text):
        buffer.append(text[pos : match.start()])
        flush()
        number = int(match.group(1))
        data_uri = available.get(number)
        if data_uri:
            parts.append({"type": "text", "text": f"[{label} {number}]"})
            parts.append({"type": "image_url", "image_url": {"url": data_uri}})
        else:
            buffer.append(f"[图片{number}未能加载]")
        pos = match.end()
    buffer.append(text[pos:])
    flush()

    if not parts:
        parts = [{"type": "text", "text": text}]
    return parts, reports