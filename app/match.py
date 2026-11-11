# -*- coding: utf-8 -*-
"""匹配算法：精确 Key、legacy Key、模糊匹配。

模糊匹配只在「同课程 + 同题型」范围内进行，且**不写库**——避免错题扩散。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .normalize import compact_text, normalize_text


def _bigrams(text: str) -> set:
    s = text.replace(" ", "")
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def bigram_overlap(a: str, b: str) -> float:
    """2-gram 重合度（Jaccard），用于廉价预筛。"""
    sa, sb = _bigrams(a), _bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = {normalize_text(x) for x in a if normalize_text(x)}
    sb = {normalize_text(x) for x in b if normalize_text(x)}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ca, cb = compact_text(a), compact_text(b)
    if ca and ca == cb:
        return 1.0
    if ca and cb:
        # 长题干只看前缀时差异会很大，用包含关系补一点分
        if len(ca) > 8 and len(cb) > 8 and (ca in cb or cb in ca):
            ratio = max(ratio, 0.95)
    return ratio


def score_question(
    title: str,
    options: Sequence[str],
    cand_title: str,
    cand_options: Sequence[str],
) -> float:
    """综合相似度：题干 0.7 + 选项集合 0.3。"""
    t = title_similarity(title, cand_title)
    o = jaccard(options, cand_options)
    if not options or not cand_options:
        return t
    return 0.7 * t + 0.3 * o


def best_fuzzy_match(
    title: str,
    options: Sequence[str],
    qtype: str,
    candidates: List[Dict[str, Any]],
    threshold: float = 0.92,
    prefilter: float = 0.45,
) -> Optional[Tuple[Dict[str, Any], float]]:
    """在候选集中找最相似的一题。

    ``candidates`` 元素需含 ``title`` / ``options`` 字段。
    返回 ``(candidate, score)`` 或 None。
    """
    if not candidates:
        return None
    norm_title = normalize_text(title)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cand in candidates:
        if cand.get("qtype") and cand["qtype"] != qtype:
            continue
        if bigram_overlap(norm_title, normalize_text(cand.get("title", ""))) < prefilter:
            continue
        score = score_question(title, options, cand.get("title", ""), cand.get("options") or [])
        scored.append((score, cand))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if best_score >= threshold:
        return best, round(best_score, 4)
    return None