# -*- coding: utf-8 -*-
"""答案清洗与回填。

两块职责：
1. **清洗**：把模型输出（可能带解释、Markdown、前缀）变成干净的答案。
2. **回填**：题库存的是「内容」，要按当前页面的选项顺序映射回字母。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import normalize as nz
from .match import title_similarity

# --------------------------------------------------------------------------
# 清洗
# --------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.S)
_PREFIX_RE = re.compile(
    r"^\s*(?:最终答案|正确答案|参考答案|答案|answer|answer\s*is)\s*[:：]\s*", re.I
)
_CUT_RE = re.compile(r"\n\s*(?:解析|分析|解释|说明|理由|考点|explanation|analysis)\s*[:：]?", re.I)
_MD_RE = re.compile(r"[*_`~]+")
_LETTER_TOKEN_RE = re.compile(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])")
_LETTER_ANY_RE = re.compile(r"[A-Za-z]")


def clean_raw(raw: Any) -> str:
    """去掉代码块、答案前缀、解析段落、Markdown 强调。"""
    if raw is None:
        return ""
    text = str(raw)
    fenced = _FENCE_RE.findall(text)
    if fenced:
        text = max(fenced, key=len)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = _CUT_RE.split(text)[0]
    text = _MD_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = _PREFIX_RE.sub("", text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return ""
    if len(lines) > 1:
        # 优先取「只含字母/#/对错」的那一行
        for line in lines[:6]:
            if re.fullmatch(r"[A-Za-z#、,，\s]+", line) or line in ("对", "错", "正确", "错误", "是", "否"):
                return line
    return lines[0].strip()


def extract_letters(raw: str, option_count: int) -> List[str]:
    """从模型输出里提取选项字母（过滤越界字母）。"""
    text = clean_raw(raw)
    if not text:
        return []
    candidates: List[str] = []
    upper = text.upper()
    for match in _LETTER_TOKEN_RE.finditer(upper):
        letter = match.group(1)
        idx = ord(letter) - 65
        if 0 <= idx < option_count:
            candidates.append(letter)
    if not candidates:
        # 无分隔的连写，如 "AC" / "ABD"
        stripped = re.sub(r"[^A-Z]", "", upper)
        if stripped and len(stripped) <= option_count and all(
            ord(ch) - 65 < option_count for ch in stripped
        ):
            candidates = list(stripped)
    if not candidates:
        return []
    seen: List[str] = []
    for letter in candidates:
        if letter not in seen:
            seen.append(letter)
    return sorted(seen)


# --------------------------------------------------------------------------
# 内容 ↔ 字母
# --------------------------------------------------------------------------
def find_option_index(content: str, options: Sequence[str]) -> Optional[int]:
    """在一组选项中定位某段内容，返回 0 基下标。"""
    target = nz.normalize_text(content)
    if not target:
        return None
    norm_opts = [nz.normalize_text(o) for o in options]
    for idx, opt in enumerate(norm_opts):
        if opt and opt == target:
            return idx
    target_compact = nz.compact_text(content)
    for idx, opt in enumerate(norm_opts):
        if opt and nz.compact_text(opt) == target_compact:
            return idx
    # 包含关系（仅当较短一方足够长，避免 "A" 这种误命中）
    for idx, opt in enumerate(norm_opts):
        if not opt:
            continue
        short, long_ = (opt, target) if len(opt) <= len(target) else (target, opt)
        if len(short) >= 2 and short in long_:
            return idx
    best_idx, best_score = None, 0.0
    for idx, opt in enumerate(options):
        score = title_similarity(content, opt)
        if score > best_score:
            best_idx, best_score = idx, score
    if best_idx is not None and best_score >= 0.8:
        return best_idx
    return None


def contents_to_letters(
    contents: Sequence[str],
    options: Sequence[str],
    qtype: str,
) -> Tuple[str, bool]:
    """题库内容 → 当前页面字母。返回 ``(字母串, 是否全部匹配到)``。

    判断题不映射字母，直接返回「对/错」。
    一个都匹配不上时返回 ``#`` 连接的内容原文（OCS 允许按内容匹配）。
    """
    items = [nz.clean_text(c) for c in contents or [] if nz.clean_text(c)]
    if not items:
        return "", False

    if qtype == nz.QTYPE_JUDGEMENT:
        values = []
        for item in items:
            norm = nz.normalize_judgement(item)
            values.append(norm or item)
        return "#".join(values), True

    if not options:
        return "#".join(items), False

    letters: List[str] = []
    matched_all = True
    for item in items:
        idx = find_option_index(item, options)
        if idx is None:
            matched_all = False
            # 该条无法映射：整体退化为内容返回
            return "#".join(items), False
        letters.append(chr(65 + idx))
    letters = sorted(set(letters))
    return "#".join(letters), matched_all


def positional_letters(
    contents: Sequence[str],
    stored_options: Sequence[str],
    live_options: Sequence[str],
) -> str:
    """按**位置**把库里的答案映射成当前页面字母。

    用于选项文本对不上的场景：最典型的是图片题 —— OCS 打开图片题优化后
    会把选项里的图片换成 ``[图片1]``、``[图片2]``，与库里存的图片地址毫无关系，
    但两边选项数量与顺序是一致的，此时按位置映射才靠得住。

    仅在两边选项数量相同且全部能定位时才返回字母，否则返回空串，
    避免把模糊匹配错的题硬选一个答案。
    """
    if not contents or not stored_options or not live_options:
        return ""
    if len(stored_options) != len(live_options):
        return ""
    indexes: List[int] = []
    for item in contents:
        norm = nz.clean_text(item)
        if not norm:
            continue
        idx = find_option_index(norm, stored_options)
        if idx is None:
            return ""
        indexes.append(idx)
    if not indexes:
        return ""
    return "#".join(sorted({chr(65 + i) for i in indexes}))


def is_letters(value: str) -> bool:
    """答案串是否只由字母与 ``#`` 组成（即已经是可用的字母答案）。"""
    text = (value or "").strip()
    if not text:
        return False
    return all(ch in "#ABCDEFGHIJKLMNOPQRSTUVWXYZ" for ch in text.upper())


def letters_to_contents(letters: Sequence[str], options: Sequence[str]) -> List[str]:
    """字母 → 选项内容（用于「入库存内容」）。"""
    out: List[str] = []
    for letter in letters:
        idx = ord(str(letter).upper()) - 65
        if 0 <= idx < len(options):
            out.append(options[idx])
    return out


# --------------------------------------------------------------------------
# 模型输出结构化
# --------------------------------------------------------------------------
def process_choice(raw: str, options: Sequence[str], qtype: str = nz.QTYPE_SINGLE) -> Dict[str, Any]:
    """把模型对选择题的输出解析成 ``{letters, contents, mode}``。"""
    text = clean_raw(raw)
    letters = extract_letters(text, len(options))
    if letters:
        return {
            "letters": letters,
            "contents": letters_to_contents(letters, options),
            "mode": "letters",
            "clean": text,
        }
    # 模型直接答了内容：尝试匹配回选项
    pieces = [p for p in re.split(r"[#、,，;；/\s]+", text) if p]
    matched: List[str] = []
    for piece in pieces or [text]:
        idx = find_option_index(piece, options)
        if idx is not None:
            letter = chr(65 + idx)
            if letter not in matched:
                matched.append(letter)
    if matched:
        return {
            "letters": sorted(matched),
            "contents": letters_to_contents(sorted(matched), options),
            "mode": "content",
            "clean": text,
        }
    # 整个回答就是某个选项的一部分
    idx = find_option_index(text, options)
    if idx is not None:
        letter = chr(65 + idx)
        return {"letters": [letter], "contents": [options[idx]], "mode": "content", "clean": text}
    return {"letters": [], "contents": [], "mode": "unknown", "clean": text}


def process_judgement(raw: str) -> Dict[str, Any]:
    text = clean_raw(raw)
    value = nz.normalize_judgement(text)
    if value is None:
        # 模型可能返回了选项字母
        if re.search(r"(?<![A-Za-z])A(?![A-Za-z])", text.upper()):
            value = "对"
        elif re.search(r"(?<![A-Za-z])B(?![A-Za-z])", text.upper()):
            value = "错"
    return {"value": value or "", "clean": text, "mode": "judgement"}


def process_completion(raw: str) -> Dict[str, Any]:
    text = clean_raw(raw)
    text = re.sub(r"^[\s:：]+", "", text)
    if text.startswith(("答：", "答:")):
        text = text[2:]
    return {"value": text.strip(), "clean": text.strip(), "mode": "completion"}


def answer_for_ocs(
    contents: Sequence[str],
    options: Sequence[str],
    qtype: str,
    fmt: str = "auto",
) -> str:
    """最终返回给 OCS 的答案串。

    - ``letters``：只回字母（``/search`` 协议）
    - ``content``：回内容（``/api/search``、``/api/answer``）
    - ``auto``：选择/判断按内容语义返回字母或对错；填空回内容
    """
    items = [nz.clean_text(c) for c in contents or [] if nz.clean_text(c)]
    if not items:
        return ""
    if qtype == nz.QTYPE_JUDGEMENT:
        return nz.normalize_judgement(items[0]) or items[0]
    if qtype == nz.QTYPE_COMPLETION:
        return "#".join(items)
    if fmt == "content":
        return "#".join(items)
    letters, _ = contents_to_letters(items, options, qtype)
    return letters


def split_contents(raw: Any) -> List[str]:
    """把 ``#`` 分隔的答案文本拆成内容列表（人工录入/导入用）。"""
    text = clean_raw(raw)
    if not text:
        return []
    out: List[str] = []
    for part in re.split(r"[#＃]+", text):
        item = part.strip().strip("。.；;，,、 ")
        if item:
            out.append(item)
    return out