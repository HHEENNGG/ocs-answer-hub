# -*- coding: utf-8 -*-
"""题库仓储层：课程、题目、导入导出、统计。

所有 SQL 都集中在这里，上层只操作 dict。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import db, normalize as nz
from .settings import get_settings

JSON_ANSWER_SEP = "#"


# --------------------------------------------------------------------------
# 行转换
# --------------------------------------------------------------------------
def row_to_question(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    data = dict(row)
    data["options"] = _loads_list(data.pop("options_json", "[]"))
    data["answer"] = _loads_list(data.pop("answer_json", "[]"))
    data["verified"] = bool(data.get("verified"))
    return data


def _loads_list(raw: Any) -> List[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []


def _dumps(value: Sequence[str]) -> str:
    return json.dumps([str(v) for v in value or []], ensure_ascii=False)


# --------------------------------------------------------------------------
# 课程
# --------------------------------------------------------------------------
def list_courses() -> List[Dict[str, Any]]:
    rows = db.query(
        """
        SELECT c.*, (SELECT COUNT(*) FROM questions q WHERE q.course_id = c.id) AS question_count
        FROM courses c ORDER BY c.is_active DESC, c.id ASC
        """
    )
    return [dict(r) for r in rows]


def get_course(course_id: int) -> Optional[Dict[str, Any]]:
    row = db.query_one("SELECT * FROM courses WHERE id = ?", (course_id,))
    return dict(row) if row else None


def get_course_by_name(name: str) -> Optional[Dict[str, Any]]:
    row = db.query_one("SELECT * FROM courses WHERE name = ?", (name,))
    return dict(row) if row else None


def create_course(name: str, source: str = "manual") -> Dict[str, Any]:
    name = nz.clean_text(name)
    if not name:
        raise ValueError("课程名称不能为空")
    existing = get_course_by_name(name)
    if existing:
        return existing
    stamp = db.now_str()
    with db.write() as conn:
        cur = conn.execute(
            "INSERT INTO courses(name, source, is_active, created_at, updated_at) VALUES(?,?,0,?,?)",
            (name, source, stamp, stamp),
        )
        course_id = cur.lastrowid
    return get_course(course_id) or {"id": course_id, "name": name}


def get_or_create_course(name: str, source: str = "manual") -> Dict[str, Any]:
    return get_course_by_name(nz.clean_text(name)) or create_course(name, source)


def delete_course(course_id: int) -> bool:
    with db.write() as conn:
        cur = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        deleted = cur.rowcount > 0
        # 兜底：显式删题（外键已 ON DELETE CASCADE）
        conn.execute("DELETE FROM questions WHERE course_id = ?", (course_id,))
    cfg = get_settings()
    if cfg.get("answer.current_course_id") == course_id:
        cfg.update({"answer": {"current_course_id": 0}})
    return deleted


def set_active(course_id: int) -> Optional[Dict[str, Any]]:
    course = get_course(course_id)
    if not course:
        return None
    with db.write() as conn:
        conn.execute("UPDATE courses SET is_active = 0")
        conn.execute("UPDATE courses SET is_active = 1, updated_at = ? WHERE id = ?", (db.now_str(), course_id))
    get_settings().update({"answer": {"current_course_id": course_id}})
    return get_course(course_id)


def get_active_course() -> Optional[Dict[str, Any]]:
    row = db.query_one("SELECT * FROM courses WHERE is_active = 1 ORDER BY id LIMIT 1")
    if row:
        return dict(row)
    configured = get_settings().get("answer.current_course_id") or 0
    if configured:
        course = get_course(int(configured))
        if course:
            return course
    row = db.query_one("SELECT * FROM courses ORDER BY id LIMIT 1")
    return dict(row) if row else None


def active_course_id() -> int:
    course = get_active_course()
    return int(course["id"]) if course else 0


def ensure_default_course() -> Optional[Dict[str, Any]]:
    """题库为空时创建一个默认课程，避免 UI 空白。"""
    if list_courses():
        return get_active_course()
    course = create_course("默认题库", source="manual")
    set_active(int(course["id"]))
    return get_course(int(course["id"]))


# --------------------------------------------------------------------------
# 题目读取
# --------------------------------------------------------------------------
def get_question(qid: int) -> Optional[Dict[str, Any]]:
    row = db.query_one("SELECT * FROM questions WHERE id = ?", (qid,))
    return row_to_question(row) if row else None


def find_by_canonical(keys: Sequence[str], course_ids: Optional[Sequence[int]] = None) -> Optional[Dict[str, Any]]:
    keys = [k for k in keys if k]
    if not keys:
        return None
    placeholders = ",".join("?" for _ in keys)
    sql = f"SELECT * FROM questions WHERE canonical_key IN ({placeholders})"
    params: List[Any] = list(keys)
    if course_ids:
        sql += f" AND course_id IN ({','.join('?' for _ in course_ids)})"
        params.extend(course_ids)
    sql += " ORDER BY verified DESC, hit_count DESC LIMIT 1"
    row = db.query_one(sql, params)
    return row_to_question(row) if row else None


def find_by_legacy(keys: Sequence[str], course_ids: Optional[Sequence[int]] = None) -> Optional[Dict[str, Any]]:
    keys = [k for k in keys if k]
    if not keys:
        return None
    placeholders = ",".join("?" for _ in keys)
    sql = f"SELECT * FROM questions WHERE legacy_key IN ({placeholders})"
    params: List[Any] = list(keys)
    if course_ids:
        sql += f" AND course_id IN ({','.join('?' for _ in course_ids)})"
        params.extend(course_ids)
    sql += " ORDER BY verified DESC, hit_count DESC LIMIT 1"
    row = db.query_one(sql, params)
    return row_to_question(row) if row else None


def fuzzy_candidates(course_ids: Optional[Sequence[int]], qtype: str, limit: int = 400) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM questions WHERE qtype = ?"
    params: List[Any] = [qtype]
    if course_ids:
        sql += f" AND course_id IN ({','.join('?' for _ in course_ids)})"
        params.extend(course_ids)
    sql += " ORDER BY verified DESC, hit_count DESC LIMIT ?"
    params.append(max(1, limit))
    return [row_to_question(r) for r in db.query(sql, params)]


def list_questions(
    course_id: Optional[int] = None,
    keyword: str = "",
    qtype: str = "",
    verified: Optional[int] = None,
    source: str = "",
    page: int = 1,
    size: int = 50,
    order: str = "id_desc",
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if course_id:
        where.append("course_id = ?")
        params.append(course_id)
    if qtype:
        where.append("qtype = ?")
        params.append(qtype)
    if verified is not None:
        where.append("verified = ?")
        params.append(int(verified))
    if source:
        where.append("source = ?")
        params.append(source)
    if keyword:
        like = f"%{keyword}%"
        where.append("(title LIKE ? OR original_title LIKE ? OR answer_json LIKE ? OR options_json LIKE ?)")
        params.extend([like, like, like, like])
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = int(db.scalar(f"SELECT COUNT(*) FROM questions{clause}", params, 0))
    page = max(1, int(page))
    size = max(1, min(500, int(size)))
    order_sql = {
        "id_desc": "id DESC",
        "id_asc": "id ASC",
        "hits_desc": "hit_count DESC, id DESC",
        "type_asc": "qtype ASC, id DESC",
    }.get(order, "id DESC")
    rows = db.query(
        f"SELECT * FROM questions{clause} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        params + [size, (page - 1) * size],
    )
    return {"items": [row_to_question(r) for r in rows], "total": total, "page": page, "size": size}


def touch_hit(qid: int) -> None:
    if not qid:
        return
    try:
        with db.write() as conn:
            conn.execute(
                "UPDATE questions SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
                (db.now_str(), qid),
            )
    except Exception:  # 统计失败不能影响答题
        pass


# --------------------------------------------------------------------------
# 题目写入
# --------------------------------------------------------------------------
def upsert_question(
    course_id: int,
    qtype: str,
    title: str,
    options: Sequence[str],
    answer: Sequence[str],
    source: str = "manual",
    verified: bool = False,
    original_title: str = "",
    note: str = "",
    legacy_key_value: str = "",
    overwrite: bool = False,
) -> Tuple[int, str]:
    """写入一题。返回 ``(qid, 状态)``，状态 ∈ created / exists / updated。"""
    qtype = nz.normalize_qtype(qtype)
    clean_title = nz.clean_text(title)
    opts = [nz.clean_text(o) for o in options or [] if nz.clean_text(o)]
    ans = [nz.normalize_answer_item(a) for a in answer or [] if nz.normalize_answer_item(a)]
    if not clean_title:
        raise ValueError("题干不能为空")
    if not ans:
        raise ValueError("答案不能为空，且不能为纯 # 分隔符")

    ckey = nz.canonical_key(qtype, clean_title, opts)
    lkey = legacy_key_value or nz.legacy_key(qtype, original_title or clean_title, opts)
    stamp = db.now_str()

    with db.write() as conn:
        row = conn.execute(
            "SELECT id, verified FROM questions WHERE course_id = ? AND canonical_key = ?",
            (course_id, ckey),
        ).fetchone()
        if row:
            qid = int(row["id"])
            if overwrite:
                conn.execute(
                    """UPDATE questions SET answer_json = ?, options_json = ?, source = ?,
                       verified = ?, original_title = COALESCE(NULLIF(?, ''), original_title),
                       note = COALESCE(NULLIF(?, ''), note), updated_at = ? WHERE id = ?""",
                    (_dumps(ans), _dumps(opts), source, int(bool(verified)), original_title, note, stamp, qid),
                )
                return qid, "updated"
            return qid, "exists"
        cur = conn.execute(
            """INSERT INTO questions(course_id, qtype, title, original_title, options_json, answer_json,
                   canonical_key, legacy_key, source, verified, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                course_id,
                qtype,
                clean_title,
                nz.clean_text(original_title or title),
                _dumps(opts),
                _dumps(ans),
                ckey,
                lkey,
                source,
                int(bool(verified)),
                stamp,
                stamp,
            ),
        )
        return int(cur.lastrowid), "created"


def update_question(qid: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = get_question(qid)
    if not current:
        return None
    qtype = nz.normalize_qtype(patch.get("qtype", current["qtype"]))
    title = patch.get("title", current["original_title"] or current["title"])
    options = patch.get("options", current["options"])
    answer = patch.get("answer", current["answer"])
    verified = patch.get("verified", current["verified"])
    note = patch.get("note", current.get("note") or "")
    ckey = nz.canonical_key(qtype, title, options)
    with db.write() as conn:
        conn.execute(
            """UPDATE questions SET qtype = ?, title = ?, original_title = ?, options_json = ?, answer_json = ?,
                   canonical_key = ?, legacy_key = ?, verified = ?, note = ?, updated_at = ? WHERE id = ?""",
            (
                qtype,
                nz.clean_text(title),
                nz.clean_text(title),
                _dumps(options),
                _dumps(answer),
                ckey,
                nz.legacy_key(qtype, title, options),
                int(bool(verified)),
                note,
                db.now_str(),
                qid,
            ),
        )
    return get_question(qid)


def delete_question(qid: int) -> bool:
    with db.write() as conn:
        cur = conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
        return cur.rowcount > 0


def bulk_verify(course_id: Optional[int] = None, qtype: str = "", ids: Optional[Sequence[int]] = None) -> int:
    with db.write() as conn:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            cur = conn.execute(
                f"UPDATE questions SET verified = 1, updated_at = ? WHERE id IN ({placeholders})",
                [db.now_str()] + list(ids),
            )
        else:
            sql = "UPDATE questions SET verified = 1, updated_at = ? WHERE 1=1"
            params: List[Any] = [db.now_str()]
            if course_id:
                sql += " AND course_id = ?"
                params.append(course_id)
            if qtype:
                sql += " AND qtype = ?"
                params.append(qtype)
            cur = conn.execute(sql, params)
        return int(cur.rowcount or 0)


def dedupe(course_id: Optional[int] = None) -> Dict[str, int]:
    """按「题型 + 压缩题干 + 选项集合」去重，保留 verified / 命中多的那条。"""
    sql = "SELECT * FROM questions"
    params: List[Any] = []
    if course_id:
        sql += " WHERE course_id = ?"
        params.append(course_id)
    sql += " ORDER BY verified DESC, hit_count DESC, id ASC"
    rows = [row_to_question(r) for r in db.query(sql, params)]
    seen: Dict[Tuple[Any, ...], int] = {}
    remove: List[int] = []
    for item in rows:
        key = (
            item["course_id"],
            item["qtype"],
            nz.compact_text(item["title"]),
            tuple(sorted(nz.compact_text(o) for o in item["options"])),
        )
        if key in seen:
            remove.append(int(item["id"]))
        else:
            seen[key] = int(item["id"])
    if remove:
        with db.write() as conn:
            conn.executemany("DELETE FROM questions WHERE id = ?", [(i,) for i in remove])
    return {"checked": len(rows), "removed": len(remove), "kept": len(rows) - len(remove)}


# --------------------------------------------------------------------------
# 导入 / 导出
# --------------------------------------------------------------------------
_ANSWER_LETTER_RE = re.compile(r"^[A-Za-z]$")


def _normalize_answer_value(value: Any, options: Sequence[str]) -> List[str]:
    """把 JSON 里的答案值转成内容列表。"""
    if isinstance(value, (list, tuple)):
        items = [nz.normalize_answer_item(v) for v in value]
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if JSON_ANSWER_SEP in raw:
            items = [nz.normalize_answer_item(v) for v in raw.split(JSON_ANSWER_SEP)]
        else:
            items = [nz.normalize_answer_item(raw)]
    else:
        return []
    items = [i for i in items if i]
    if not items:
        return []
    # 兼容「库里存的是字母」的题库
    if options and all(_ANSWER_LETTER_RE.match(i) for i in items):
        mapped: List[str] = []
        for letter in items:
            idx = ord(letter.upper()) - 65
            if 0 <= idx < len(options):
                mapped.append(options[idx])
            else:
                mapped = []
                break
        if mapped:
            return mapped
    return items


def import_questions(
    payload: Any,
    course_name: str,
    strategy: str = "skip",
    source: str = "import",
) -> Dict[str, Any]:
    """导入题库。

    支持两种结构：
    1. AutoCourse-DB 平面字典 ``{"[single] 题干 | 选项": "答案"}``
    2. 本项目导出结构 ``{"course": "...", "questions": [{...}]}``
    """
    course_name = nz.clean_text(course_name) or "导入题库"
    course = get_or_create_course(course_name, source="import")
    course_id = int(course["id"])

    entries: List[Dict[str, Any]] = []
    invalid = 0

    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        for item in payload["questions"]:
            if not isinstance(item, dict):
                invalid += 1
                continue
            entries.append(
                {
                    "qtype": nz.normalize_qtype(item.get("qtype") or item.get("type")),
                    "title": item.get("title") or item.get("question") or "",
                    "options": item.get("options") or [],
                    "answer": item.get("answer") or [],
                    "verified": bool(item.get("verified", True)),
                    "note": item.get("note") or "",
                    "legacy_key": item.get("legacy_key") or "",
                }
            )
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str) or not key.strip().startswith("["):
                invalid += 1
                continue
            qtype, title, options = nz.split_key(key)
            entries.append(
                {
                    "qtype": qtype,
                    "title": title,
                    "options": options,
                    "answer": value,
                    "verified": True,
                    "note": "",
                    "legacy_key": key.strip(),
                }
            )
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                entries.append(
                    {
                        "qtype": nz.normalize_qtype(item.get("qtype") or item.get("type")),
                        "title": item.get("title") or "",
                        "options": item.get("options") or [],
                        "answer": item.get("answer") or [],
                        "verified": bool(item.get("verified", True)),
                        "note": item.get("note") or "",
                        "legacy_key": item.get("legacy_key") or "",
                    }
                )
            else:
                invalid += 1
    else:
        raise ValueError("无法识别的题库格式")

    created = updated = skipped = 0
    errors: List[str] = []
    for entry in entries:
        title = nz.clean_text(entry["title"])
        if not title:
            invalid += 1
            continue
        options = [nz.clean_text(o) for o in entry["options"] if nz.clean_text(o)]
        answers = _normalize_answer_value(entry["answer"], options)
        if not answers:
            invalid += 1
            if len(errors) < 5:
                errors.append(f"答案为空：{title[:30]}")
            continue
        overwrite = strategy == "overwrite"
        try:
            qid, state = upsert_question(
                course_id=course_id,
                qtype=entry["qtype"],
                title=title,
                options=options,
                answer=answers,
                source=source,
                verified=entry["verified"],
                original_title=title,
                note=entry["note"],
                legacy_key_value=entry["legacy_key"],
                overwrite=overwrite,
            )
            if state == "created":
                created += 1
            elif state == "updated":
                updated += 1
            else:
                if strategy == "overwrite_unverified":
                    existing = get_question(qid)
                    if existing and not existing["verified"]:
                        update_question(qid, {"answer": answers, "options": options, "verified": True})
                        updated += 1
                        continue
                skipped += 1
        except (ValueError, Exception) as exc:  # noqa: BLE001 - 单题失败不阻断整批
            invalid += 1
            if len(errors) < 5:
                errors.append(f"{title[:24]} → {exc}")
    return {
        "course_id": course_id,
        "course_name": course["name"],
        "total": len(entries),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "invalid": invalid,
        "errors": errors,
    }


def export_course(course_id: Optional[int] = None, use_legacy_key: bool = True) -> Dict[str, Any]:
    """导出为 AutoCourse-DB 兼容的平面字典。"""
    sql = "SELECT * FROM questions"
    params: List[Any] = []
    if course_id:
        sql += " WHERE course_id = ?"
        params.append(course_id)
    sql += " ORDER BY id ASC"
    rows = [row_to_question(r) for r in db.query(sql, params)]
    payload: Dict[str, str] = {}
    for item in rows:
        key = ""
        if use_legacy_key and item.get("legacy_key"):
            key = item["legacy_key"]
        if not key:
            key = nz.legacy_key(item["qtype"], item["original_title"] or item["title"], item["options"])
        payload[key] = JSON_ANSWER_SEP.join(item["answer"])
    return payload


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------
def stats() -> Dict[str, Any]:
    by_type = {row["qtype"]: int(row["n"]) for row in db.query("SELECT qtype, COUNT(*) AS n FROM questions GROUP BY qtype")}
    courses = list_courses()
    today = db.now_str()[:10]
    today_new = int(db.scalar("SELECT COUNT(*) FROM questions WHERE created_at LIKE ?", (today + "%",), 0))
    total = sum(by_type.values())
    verified = int(db.scalar("SELECT COUNT(*) FROM questions WHERE verified = 1", (), 0))
    return {
        "courses": len(courses),
        "questions": total,
        "verified": verified,
        "unverified": total - verified,
        "by_type": {k: by_type.get(k, 0) for k in nz.QTYPES},
        "today_new": today_new,
    }