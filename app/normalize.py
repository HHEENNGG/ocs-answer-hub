# -*- coding: utf-8 -*-
"""文本归一化、选项解析、稳定 Key —— 全项目最核心的算法层。

设计目标
--------
1. **选项乱序无关**：Key 由「排序后的选项内容」构成（继承 AutoCourse-DB）。
2. **跨平台鲁棒**：全角/半角、引号、空白、题号前缀都归一（本项目增强）。
3. **向后兼容**：同时生成 ``legacy_key``（AutoCourse-DB 原始格式），
   保证导入的旧题库一定命中。
4. 不依赖 Flask / 数据库，纯函数，便于单测。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 题型
# --------------------------------------------------------------------------
QTYPE_SINGLE = "single"
QTYPE_MULTIPLE = "multiple"
QTYPE_JUDGEMENT = "judgement"
QTYPE_COMPLETION = "completion"
QTYPE_IMAGE = "image"

QTYPES = (QTYPE_SINGLE, QTYPE_MULTIPLE, QTYPE_JUDGEMENT, QTYPE_COMPLETION)
QTYPE_LABELS = {
    QTYPE_SINGLE: "单选题",
    QTYPE_MULTIPLE: "多选题",
    QTYPE_JUDGEMENT: "判断题",
    QTYPE_COMPLETION: "填空题",
    QTYPE_IMAGE: "图片题",
}

_QTYPE_ALIASES = {
    "single": QTYPE_SINGLE,
    "0": QTYPE_SINGLE,
    "single_choice": QTYPE_SINGLE,
    "radio": QTYPE_SINGLE,
    "单选题": QTYPE_SINGLE,
    "单选": QTYPE_SINGLE,
    "multiple": QTYPE_MULTIPLE,
    "1": QTYPE_MULTIPLE,
    "multi": QTYPE_MULTIPLE,
    "multiple_choice": QTYPE_MULTIPLE,
    "checkbox": QTYPE_MULTIPLE,
    "多选题": QTYPE_MULTIPLE,
    "多选": QTYPE_MULTIPLE,
    "2": QTYPE_SINGLE,  # 原 answerer 未定义 2，按单选处理
    "completion": QTYPE_COMPLETION,
    "3": QTYPE_COMPLETION,
    "blank": QTYPE_COMPLETION,
    "fill": QTYPE_COMPLETION,
    "填空题": QTYPE_COMPLETION,
    "填空": QTYPE_COMPLETION,
    "judgement": QTYPE_JUDGEMENT,
    "judgment": QTYPE_JUDGEMENT,
    "4": QTYPE_JUDGEMENT,
    "judge": QTYPE_JUDGEMENT,
    "true_false": QTYPE_JUDGEMENT,
    "判断题": QTYPE_JUDGEMENT,
    "判断": QTYPE_JUDGEMENT,
    "image": QTYPE_IMAGE,
    "图片题": QTYPE_IMAGE,
    "图片": QTYPE_IMAGE,
}


def normalize_qtype(value: Any, default: str = QTYPE_SINGLE) -> str:
    """把任意平台的题型标识归一为内部四类。"""
    if value is None:
        return default
    key = str(value).strip().lower()
    if key in _QTYPE_ALIASES:
        return _QTYPE_ALIASES[key]
    if str(value).strip() in _QTYPE_ALIASES:
        return _QTYPE_ALIASES[str(value).strip()]
    return default


def qtype_label(qtype: str) -> str:
    return QTYPE_LABELS.get(qtype, qtype)


# --------------------------------------------------------------------------
# 文本归一化
# --------------------------------------------------------------------------
_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": '"',
    "\u2019": '"',
    "\u300c": '"',
    "\u300d": '"',
    "\u300e": '"',
    "\u300f": '"',
    "\uff02": '"',
}
_QUOTE_TABLE = str.maketrans(_QUOTES)

# 题号前缀：第3题 / 1. / (1) / （1） / 1、/ 1)
_NUMBER_PREFIX_RE = re.compile(
    r"^\s*(?:第\s*\d{1,3}\s*[题道]|\(\s*\d{1,3}\s*\)|（\s*\d{1,3}\s*）|\d{1,3}\s*[.、．)）])\s*"
)


def normalize_text(text: Any) -> str:
    """题干/选项归一化：全角转半角、引号统一、压缩空白、去题号、小写。"""
    if text is None:
        return ""
    s = str(text)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = s.translate(_QUOTE_TABLE)
    s = re.sub(r"\s+", " ", s).strip()
    s = _NUMBER_PREFIX_RE.sub("", s)
    s = s.strip()
    return s.lower()


def clean_text(text: Any) -> str:
    """只做轻清洗（不 lowercase、不去题号），用于展示与存储原文。"""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def compact_text(text: Any) -> str:
    """去全部空白与常见标点，用于宽松比对。"""
    s = normalize_text(text)
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[\"'`.,;:!?()\[\]{}<>~_\-+=*/\\|@#$%^&]", "", s)
    return s


# --------------------------------------------------------------------------
# 选项解析
# --------------------------------------------------------------------------
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

_PREFIX_LETTER_RE = re.compile(r"^([A-Za-z])\s*[.、．)）:：]\s*(.+)$", re.S)
_PREFIX_CIRCLED_RE = re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*[.、．)）:：]?\s*(.+)$", re.S)
_PREFIX_DIGIT_RE = re.compile(r"^\(?(\d{1,2})\)?[.、．)）:：]\s*(.+)$", re.S)

_MARKER_RE = re.compile(r"(?<![^\s])([A-Za-z])\s*[.、．)）:：]\s*")


def _split_raw_lines(raw: Any) -> List[str]:
    """把 str / list 统一成行列表。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        lines: List[str] = []
        for item in raw:
            if item is None:
                continue
            if isinstance(item, (list, tuple)):
                lines.extend(_split_raw_lines(item))
            else:
                lines.extend(_split_raw_lines(str(item)))
        return [ln for ln in lines if ln.strip()]

    text = str(raw)
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")  # 有的平台转义未还原
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [ln for ln in text.split("\n") if ln.strip()]


def _maybe_split_markers(lines: List[str]) -> List[str]:
    """单行内出现 A. B. C. 时按字母切分。"""
    if len(lines) != 1:
        return lines
    text = lines[0]
    marks = [(m.start(), m.group(1).upper()) for m in _MARKER_RE.finditer(text)]
    if len(marks) < 2:
        return lines
    expect = [chr(65 + i) for i in range(len(marks))]
    if [letter for _, letter in marks] != expect:
        return lines
    parts: List[str] = []
    for idx, (start, _) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
    return parts or lines


def _strip_expected_prefix(line: str, index: int) -> Optional[str]:
    """仅当序号与位置吻合时才剥离前缀，避免把正文当序号。"""
    s = line.strip()
    m = _PREFIX_LETTER_RE.match(s)
    if m and m.group(1).upper() == chr(65 + index):
        return m.group(2).strip()
    m = _PREFIX_CIRCLED_RE.match(s)
    if m and index < len(_CIRCLED) and m.group(1) == _CIRCLED[index]:
        return m.group(2).strip()
    m = _PREFIX_DIGIT_RE.match(s)
    if m and int(m.group(1)) == index + 1:
        return m.group(2).strip()
    return None


def parse_options(raw: Any) -> List[str]:
    """把各种形态的选项解析成「纯内容列表」，顺序与页面一致。

    支持：
    - ``"A. 苹果\\nB. 香蕉"``
    - ``["A. 苹果", "B. 香蕉"]`` / ``["苹果", "香蕉"]``
    - ``"苹果\\n香蕉"``（无字母）
    - 单行 ``"A. 苹果 B. 香蕉"``（自动切分）
    - 选项内容跨行（下一行无前缀 → 拼到上一个选项）
    """
    if raw is None:
        return []
    # 列表形态：每个元素本身就是一个选项（元素内部允许自带前缀 / 换行续写）
    if isinstance(raw, (list, tuple)):
        options: List[str] = []
        for item in raw:
            if item is None:
                continue
            if isinstance(item, (list, tuple)):
                options.extend(parse_options(item))
                continue
            options.extend(_parse_option_block(str(item), len(options)))
        return [opt for opt in options if opt]

    return [opt for opt in _parse_option_block(str(raw), 0) if opt]


def _parse_option_block(text: str, start: int) -> List[str]:
    """解析一段文本块。

    - 首行带 ``A.``（或 ① / 1.）标记 → 标记模式：同序号的另起一项，
      无序号的续行拼到上一项（选项内容跨行）。
    - 无标记 → 每行一项（``"苹果\\n香蕉"``）。
    """
    lines = [ln.strip() for ln in _maybe_split_markers(_split_raw_lines(text)) if ln.strip()]
    if not lines:
        return []

    marked = _strip_expected_prefix(lines[0], start) is not None
    if not marked:
        return [clean_text(ln) for ln in lines]

    options: List[str] = []
    for line in lines:
        content = _strip_expected_prefix(line, start + len(options))
        if content is None:
            # 无序号 → 上一项的续行
            if options:
                options[-1] = clean_text(options[-1] + " " + line)
            else:
                options.append(clean_text(line))
        elif content == "":
            continue
        else:
            options.append(clean_text(content))
    return options


def options_to_text(options: Sequence[str]) -> str:
    """选项列表 → ``A. x\\nB. y`` 形式（给 Prompt 与导出用）。"""
    if not options:
        return ""
    return "\n".join(f"{chr(65 + i)}. {opt}" for i, opt in enumerate(options))


# --------------------------------------------------------------------------
# 稳定 Key
# --------------------------------------------------------------------------
def _sorted_option_texts(options: Sequence[str]) -> List[str]:
    cleaned = {normalize_text(opt) for opt in options or []}
    cleaned.discard("")
    return sorted(cleaned)


def canonical_key(qtype: str, title: str, options: Sequence[str]) -> str:
    """本项目主 Key：与 AutoCourse-DB 同构，额外做归一化。"""
    key_title = normalize_text(title)
    opts = _sorted_option_texts(options)
    return f"[{qtype}] {key_title} | {' | '.join(opts)}" if opts else f"[{qtype}] {key_title}"


def legacy_key(qtype: str, title: str, options: Sequence[str]) -> str:
    """AutoCourse-DB 原始 Key（不归一化，仅排序），用于兼容旧题库。"""
    key_title = clean_text(title)
    opts = sorted({clean_text(opt) for opt in options or [] if clean_text(opt)})
    return f"[{qtype}] {key_title} | {' | '.join(opts)}" if opts else f"[{qtype}] {key_title}"


def legacy_key_variants(qtype: str, title: str, options: Sequence[str]) -> List[str]:
    """生成数个 legacy 候选：原始 / 去题号 / 压缩空白，提高旧题库命中率。"""
    variants = {legacy_key(qtype, title, options)}
    stripped_title = _NUMBER_PREFIX_RE.sub("", clean_text(title)).strip()
    if stripped_title and stripped_title != clean_text(title):
        variants.add(legacy_key(qtype, stripped_title, options))
    compact = canonical_key(qtype, title, options)
    variants.add(compact)
    variants.discard("")
    return list(variants)


def split_key(stored_key: str) -> Tuple[str, str, List[str]]:
    """把 ``[single] 题干 | 选项1 | 选项2`` 拆回 (qtype, title, options)。"""
    text = (stored_key or "").strip()
    qtype = QTYPE_SINGLE
    m = re.match(r"^\[([a-zA-Z]+)\]\s*(.*)$", text, re.S)
    if m:
        qtype = normalize_qtype(m.group(1))
        text = m.group(2)
    parts = [p.strip() for p in text.split(" | ")]
    if not parts:
        return qtype, "", []
    title = parts[0]
    options = [p for p in parts[1:] if p]
    return qtype, title, options


# --------------------------------------------------------------------------
# 图片识别
# --------------------------------------------------------------------------
_IMG_URL_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(https?://[^\s)]+?)\s*\)"  # markdown 图片
    r"|<img[^>]+src=[\"']([^\"']+)[\"']"  # html img
    r"|(https?://[^\s\"'<>()（）]+?\.(?:png|jpe?g|gif|webp|bmp|svg))(?:\?[^\s\"'<>]*)?",
    re.I,
)
_IMG_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp|svg)", re.I)
_ICON_HINTS = (
    "/icon/",
    "icon_",
    "/static/images/icon",
    "video.png",
    "audio.png",
    "play.png",
    "pause.png",
    "loading",
    "placeholder",
    "/logo",
    "favicon",
    "blank.gif",
    "spacer",
)


def extract_image_urls(text: Any) -> List[str]:
    """从题干/选项中抽取图片 URL（去重、过滤图标、截断到扩展名）。"""
    if not text:
        return []
    found: List[str] = []
    for m in _IMG_URL_RE.finditer(str(text)):
        url = m.group(1) or m.group(2) or m.group(3) or ""
        url = clean_image_url(url)
        if url and url not in found:
            found.append(url)
    return found


def clean_image_url(url: str) -> str:
    """补全协议、去掉末尾标点、截断到图片扩展名、过滤明显图标。"""
    u = (url or "").strip().strip("\"'")
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if not u.lower().startswith(("http://", "https://")):
        return ""
    match = _IMG_EXT_RE.search(u)
    if match:
        u = u[: match.end()]
    else:
        return ""  # 无图片扩展名，视为非图片
    low = u.lower()
    if any(hint in low for hint in _ICON_HINTS):
        return ""
    return u


def strip_images(text: str) -> str:
    """把文本中的图片标记替换为占位说明（给纯文本模型用）。"""
    if not text:
        return ""
    out = _IMG_URL_RE.sub("[图片]", str(text))
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def has_images(text: Any) -> bool:
    return bool(extract_image_urls(text))


def is_image_option(options: Sequence[str]) -> bool:
    """选项本身是图片（内容全是 URL / markdown 图片）。"""
    if not options:
        return False
    hits = sum(1 for opt in options if extract_image_urls(opt))
    return hits >= max(1, len(options) // 2 + len(options) % 2) or hits == len(options)


# --------------------------------------------------------------------------
# 判断题答案归一
# --------------------------------------------------------------------------
_TRUE_SET = {"对", "正确", "是", "√", "✓", "true", "t", "yes", "y", "1", "right", "a"}
_FALSE_SET = {"错", "错误", "否", "×", "✗", "x", "false", "f", "no", "n", "0", "wrong", "b"}


def normalize_judgement(value: Any) -> Optional[str]:
    """判断答案归一为 '对' / '错'，无法判断返回 None。"""
    s = normalize_text(value)
    s = re.sub(r"[\s.,;:!?()\[\]{}\"'`]", "", s)
    if not s:
        return None
    if s in _TRUE_SET:
        return "对"
    if s in _FALSE_SET:
        return "错"
    if s.startswith("对") or s.startswith("正确") or s.startswith("√"):
        return "对"
    if s.startswith("错") or s.startswith("×"):
        return "错"
    if s in ("是", "是的"):
        return "对"
    if s in ("不是", "否"):
        return "错"
    return None


def normalize_answer_item(value: Any) -> str:
    """答案内容统一空白（保留中文标点与大小写）。"""
    return clean_text(value)