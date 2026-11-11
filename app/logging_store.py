# -*- coding: utf-8 -*-
"""答题日志：异步落库 + 查询聚合 + CSV 导出。

写入走队列，后台线程每 200 ms 或攒够 50 条批量提交，避免拖慢答题主流程。
"""

from __future__ import annotations

import atexit
import csv
import io
import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional

from . import db

_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=20000)
_worker: Optional[threading.Thread] = None
_stop = threading.Event()
_lock = threading.Lock()
DROPPED = 0

FIELDS = (
    "request_id",
    "ts",
    "protocol",
    "course_id",
    "qtype",
    "title",
    "options_json",
    "hit_source",
    "answer",
    "matched_qid",
    "similarity",
    "model_id",
    "model_name",
    "reasoning",
    "prompt_tokens",
    "completion_tokens",
    "cost_cny",
    "latency_ms",
    "images_count",
    "success",
    "error",
    "remote_addr",
)


def _ensure_worker() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _stop.clear()
            _worker = threading.Thread(target=_run, name="log-writer", daemon=True)
            _worker.start()


def _run() -> None:
    while not _stop.is_set():
        batch: List[Dict[str, Any]] = []
        try:
            first = _QUEUE.get(timeout=0.2)
            batch.append(first)
        except queue.Empty:
            continue
        deadline = time.time() + 0.2
        while len(batch) < 50 and time.time() < deadline:
            try:
                batch.append(_QUEUE.get_nowait())
            except queue.Empty:
                break
        _write_batch(batch)


def _write_batch(batch: List[Dict[str, Any]]) -> None:
    if not batch:
        return
    rows = [tuple(_normalize_record(item).get(f) for f in FIELDS) for item in batch]
    placeholders = ",".join("?" for _ in FIELDS)
    try:
        with db.write() as conn:
            conn.executemany(
                f"INSERT INTO answer_logs({','.join(FIELDS)}) VALUES({placeholders})",
                rows,
            )
    except Exception as exc:  # noqa: BLE001 - 日志失败绝不能影响主流程
        print(f"[日志] 写入失败：{exc}")


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    data = {key: record.get(key) for key in FIELDS}
    data.setdefault("ts", db.now_str())
    data["ts"] = data.get("ts") or db.now_str()
    data["title"] = (data.get("title") or "")[:2000]
    if isinstance(data.get("options_json"), (list, tuple)):
        data["options_json"] = json.dumps(list(data["options_json"]), ensure_ascii=False)
    data["reasoning"] = int(bool(data.get("reasoning")))
    data["success"] = int(bool(data.get("success", True)))
    for key in ("prompt_tokens", "completion_tokens"):
        data[key] = int(data.get(key) or 0)
    data["cost_cny"] = float(data.get("cost_cny") or 0)
    data["latency_ms"] = int(data.get("latency_ms") or 0)
    data["images_count"] = int(data.get("images_count") or 0)
    if data.get("similarity") is not None:
        data["similarity"] = float(data["similarity"])
    return data


def log_answer(record: Dict[str, Any]) -> None:
    global DROPPED
    _ensure_worker()
    try:
        _QUEUE.put_nowait(record)
    except queue.Full:
        DROPPED += 1


def flush(timeout: float = 3.0) -> None:
    """等待队列写空（测试与退出时用）。"""
    deadline = time.time() + timeout
    while not _QUEUE.empty() and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.25)


def stop() -> None:
    flush()
    _stop.set()


atexit.register(stop)


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------
def query_logs(
    page: int = 1,
    size: int = 50,
    hit_source: str = "",
    qtype: str = "",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if hit_source:
        where.append("hit_source = ?")
        params.append(hit_source)
    if qtype:
        where.append("qtype = ?")
        params.append(qtype)
    if keyword:
        like = f"%{keyword}%"
        where.append("(title LIKE ? OR answer LIKE ?)")
        params.extend([like, like])
    if date_from:
        where.append("ts >= ?")
        params.append(date_from)
    if date_to:
        where.append("ts <= ?")
        params.append(date_to + " 23:59:59" if len(date_to) == 10 else date_to)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = int(db.scalar(f"SELECT COUNT(*) FROM answer_logs{clause}", params, 0))
    page = max(1, int(page))
    size = max(1, min(500, int(size)))
    rows = db.query(
        f"SELECT * FROM answer_logs{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [size, (page - 1) * size],
    )
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "size": size}


def clear_logs() -> int:
    with db.write() as conn:
        cur = conn.execute("DELETE FROM answer_logs")
        return int(cur.rowcount or 0)


def export_csv() -> str:
    rows = db.query("SELECT * FROM answer_logs ORDER BY id DESC")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = [
        "时间",
        "请求ID",
        "协议",
        "题型",
        "题目",
        "选项",
        "命中来源",
        "答案",
        "模型",
        "思考",
        "输入Token",
        "输出Token",
        "费用(元)",
        "耗时(ms)",
        "图片数",
        "成功",
        "错误",
    ]
    writer.writerow(header)
    for row in rows:
        item = dict(row)
        writer.writerow(
            [
                item.get("ts"),
                item.get("request_id"),
                item.get("protocol"),
                item.get("qtype"),
                item.get("title"),
                item.get("options_json"),
                item.get("hit_source"),
                item.get("answer"),
                item.get("model_name") or item.get("model_id") or "",
                "是" if item.get("reasoning") else "否",
                item.get("prompt_tokens"),
                item.get("completion_tokens"),
                item.get("cost_cny"),
                item.get("latency_ms"),
                item.get("images_count"),
                "是" if item.get("success") else "否",
                item.get("error") or "",
            ]
        )
    return buffer.getvalue()


def stats(days: int = 7) -> Dict[str, Any]:
    days = max(1, min(90, int(days)))
    today = db.now_str()[:10]
    total = int(db.scalar("SELECT COUNT(*) FROM answer_logs", (), 0))
    today_total = int(db.scalar("SELECT COUNT(*) FROM answer_logs WHERE ts LIKE ?", (today + "%",), 0))
    today_ai = int(db.scalar("SELECT COUNT(*) FROM answer_logs WHERE ts LIKE ? AND hit_source = 'ai'", (today + "%",), 0))
    today_hit = int(
        db.scalar(
            "SELECT COUNT(*) FROM answer_logs WHERE ts LIKE ? AND hit_source IN ('exact','legacy','fuzzy','cache')",
            (today + "%",),
            0,
        )
    )
    today_cost = float(db.scalar("SELECT COALESCE(SUM(cost_cny),0) FROM answer_logs WHERE ts LIKE ?", (today + "%",), 0.0))
    today_tokens = int(db.scalar("SELECT COALESCE(SUM(prompt_tokens+completion_tokens),0) FROM answer_logs WHERE ts LIKE ?", (today + "%",), 0))
    sources = [
        {"source": row["hit_source"], "count": int(row["n"])}
        for row in db.query(
            "SELECT hit_source, COUNT(*) AS n FROM answer_logs WHERE ts >= date('now', ?) GROUP BY hit_source ORDER BY n DESC",
            (f"-{days} days",),
        )
    ]
    trend = []
    for row in db.query(
        """SELECT substr(ts,1,10) AS day, COUNT(*) AS total,
                  SUM(CASE WHEN hit_source = 'ai' THEN 1 ELSE 0 END) AS ai
           FROM answer_logs WHERE ts >= date('now', ?) GROUP BY day ORDER BY day""",
        (f"-{days} days",),
    ):
        trend.append({"day": row["day"], "total": int(row["total"]), "ai": int(row["ai"] or 0)})
    by_type = {
        row["qtype"] or "unknown": int(row["n"])
        for row in db.query("SELECT qtype, COUNT(*) AS n FROM answer_logs WHERE ts >= date('now', ?) GROUP BY qtype", (f"-{days} days",))
    }
    avg_latency = float(
        db.scalar("SELECT COALESCE(AVG(latency_ms),0) FROM answer_logs WHERE ts LIKE ?", (today + "%",), 0.0)
    )
    return {
        "total": total,
        "today": {
            "total": today_total,
            "ai": today_ai,
            "hit": today_hit,
            "hit_rate": round(today_hit / today_total, 4) if today_total else 0.0,
            "cost_cny": round(today_cost, 6),
            "tokens": today_tokens,
            "avg_latency_ms": round(avg_latency, 1),
        },
        "sources": sources,
        "trend": trend,
        "by_type": by_type,
        "days": days,
    }


def recent(limit: int = 10) -> List[Dict[str, Any]]:
    rows = db.query("SELECT * FROM answer_logs ORDER BY id DESC LIMIT ?", (max(1, int(limit)),))
    return [dict(r) for r in rows]