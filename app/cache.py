# -*- coding: utf-8 -*-
"""进程内 LRU + TTL 缓存（线程安全）。

只缓存「题目 Key → 答案」的最终结果，容量小（默认 512），进程重启即失效。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, maxsize: int = 512, ttl: int = 3600) -> None:
        self.maxsize = max(16, int(maxsize))
        self.ttl = max(0, int(ttl))
        self._data: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # -- 基础操作 -----------------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        if self.ttl <= 0:
            return None
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires_at, value = item
            if expires_at < now:
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        expires_at = time.time() + self.ttl
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
                self.evictions += 1

    def clear(self) -> int:
        with self._lock:
            count = len(self._data)
            self._data.clear()
        return count

    def configure(self, maxsize: Optional[int] = None, ttl: Optional[int] = None) -> None:
        with self._lock:
            if maxsize is not None:
                self.maxsize = max(16, int(maxsize))
            if ttl is not None:
                self.ttl = max(0, int(ttl))
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            size = len(self._data)
            total = self.hits + self.misses
            return {
                "size": size,
                "maxsize": self.maxsize,
                "ttl": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
            }


_cache = TTLCache()


def get_cache() -> TTLCache:
    return _cache