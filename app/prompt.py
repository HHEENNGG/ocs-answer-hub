# -*- coding: utf-8 -*-
"""Prompt 构建：四类题型分别定制，强制「只输出答案」。

移植自 ocs-ai-answerer 的 PromptBuilder（MIT © 2025 Liu Keda），做了简化与中文化。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from . import normalize as nz

SYSTEM_PROMPT = (
    "你是一个严谨、准确的答题助手。你只会看到一道题目和它的选项。\n"
    "规则：\n"
    "1. 只输出最终答案，绝不输出任何解释、分析、推理过程、客套话或额外说明；\n"
    "2. 不要重复题目，不要输出「答案是」之类的引导语；\n"
    "3. 如果信息不足以确定答案，选择你认为最可能的一项，仍然只输出答案。"
)

_IMAGE_HINT = (
    "\n注意：题干或选项中包含图片，请仔细阅读图片内容后再作答。"
    "如果选项本身是图片，请只输出对应选项的字母。"
)


def build_messages(
    qtype: str,
    title: str,
    options: Sequence[str],
    use_option_labels: bool = True,
    has_images: bool = False,
    extra_system: str = "",
) -> List[Dict[str, Any]]:
    """构造 OpenAI 风格 messages。"""
    system = SYSTEM_PROMPT + (extra_system or "")
    option_block = _format_options(options, use_option_labels)
    body_parts: List[str] = [f"题型：{nz.qtype_label(qtype)}", f"题目：{title}"]

    if option_block:
        body_parts.append("选项：\n" + option_block)

    if qtype == nz.QTYPE_SINGLE:
        if use_option_labels:
            body_parts.append("请作答：只输出一个选项字母（如 A），不要输出其他任何内容。")
        else:
            body_parts.append("请作答：只输出正确选项的完整内容，不要输出字母或解释。")
    elif qtype == nz.QTYPE_MULTIPLE:
        if use_option_labels:
            body_parts.append("请作答：只输出所有正确选项的字母，用 # 连接并按字母升序（如 A#C#D），不要输出其他任何内容。")
        else:
            body_parts.append("请作答：只输出所有正确选项的完整内容，用 # 连接，不要输出字母或解释。")
    elif qtype == nz.QTYPE_JUDGEMENT:
        body_parts.append("请作答：只输出「对」或「错」两个字之一，不要输出其他任何内容。")
    elif qtype == nz.QTYPE_COMPLETION:
        body_parts.append("请作答：只输出填空处的答案内容；如果有多个空，用 # 分隔。不要输出解释。")
    else:
        body_parts.append("请作答：只输出答案。")

    if has_images:
        body_parts.append(_IMAGE_HINT.strip())

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(p for p in body_parts if p)},
    ]


def _format_options(options: Sequence[str], use_labels: bool) -> str:
    if not options:
        return ""
    lines = []
    for idx, opt in enumerate(options):
        prefix = f"{chr(65 + idx)}. " if use_labels else ""
        lines.append(f"{prefix}{opt}")
    return "\n".join(lines)


def build_image_blocks(
    text: str,
    image_urls: Sequence[str],
    label: str = "题目图片",
) -> List[Dict[str, Any]]:
    """把图片与文本组装成 OpenAI 多模态 content 数组。"""
    parts: List[Dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for idx, url in enumerate(image_urls, start=1):
        parts.append({"type": "text", "text": f"[{label} {idx}]"})
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def test_messages() -> List[Dict[str, Any]]:
    """连通性测试用的极简对话。"""
    return [
        {"role": "system", "content": "你是一个测试助手，只输出答案本身。"},
        {"role": "user", "content": "1+1=? 只输出数字。"},
    ]