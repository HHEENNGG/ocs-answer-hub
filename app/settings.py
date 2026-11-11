# -*- coding: utf-8 -*-
"""配置读写：data/config.json 为唯一来源，环境变量可覆盖。

设计要点
--------
1. 单文件 JSON，GUI 一键保存，人可手改。
2. 保存后调用方决定是否热重载（本项目大部分配置运行期读，无需重启）。
3. 对外输出一律经过 ``mask_key`` 脱敏，避免 API Key 从接口泄漏。
"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
from typing import Any, Dict, List


def _resource_root() -> str:
    """只读资源根目录（web/、libraries/ 所在地）。

    源码运行：项目根目录。
    PyInstaller 打包后：解包目录 ``sys._MEIPASS``（onefile）或 exe 同级（onedir）。
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data_dir() -> str:
    """可写数据目录（bank.db、config.json 所在）。

    优先级：环境变量 ``OCS_HUB_DATA_DIR``（**就是数据目录本身**）> 打包后 exe 同级 data/ >
    源码运行时的项目根 data/。这样打包运行时不会把数据写进临时解包目录。
    """
    override = os.environ.get("OCS_HUB_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
    return os.path.join(BASE_DIR, "data")


def _writable_root() -> str:
    """可写数据目录的上一级（放导出文件、日志等次级目录用）。"""
    return os.path.dirname(DATA_DIR)


BASE_DIR = _resource_root()
DATA_DIR = _data_dir()
APP_DIR = _writable_root()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

MASK = "****"


# --------------------------------------------------------------------------
# 默认配置
# --------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "open_browser": True,
        "log_level": "INFO",
    },
    "answer": {
        "offline_first": True,
        "enable_ai": True,
        "auto_save": True,
        "auto_save_verified": False,
        "fuzzy_enabled": True,
        "fuzzy_threshold": 0.92,
        "cross_course": True,
        "current_course_id": 0,
        "answer_format": "auto",
        "request_timeout": 120,
        "max_retries": 3,
        "use_option_labels": True,
        "extra_prompt": "",
    },
    "ai": {
        "enabled": True,
        "temperature": 0.1,
        "max_tokens": 500,
        "reasoning_max_tokens": 4096,
        "top_p": 0.95,
        "force_reasoning": False,
        "reasoning_effort": "medium",
        "auto_reasoning_multiple": True,
        "auto_reasoning_images": True,
        "proxy": "",
        "image_timeout": 15,
        "image_max_mb": 5,
        "max_images": 8,
    },
    "security": {
        "access_token": "",
        "allow_lan_admin": False,
        "rate_limit_attempts": 5,
        "rate_limit_window": 300,
    },
    "models": [],
    "type_mapping": {
        "single": {"models": [], "enable_reasoning": False},
        "multiple": {"models": [], "enable_reasoning": True},
        "judgement": {"models": [], "enable_reasoning": False},
        "completion": {"models": [], "enable_reasoning": False},
        "image": {"models": [], "enable_reasoning": True},
    },
    "fallback_models": [],
    "cache": {"enabled": True, "ttl": 3600, "size": 512},
}

# 内置预设（首次启动写入，用户可改可删，builtin=True 仅用于 UI 提示）
BUILTIN_MODELS: List[Dict[str, Any]] = [
    {
        "id": "preset_deepseek_chat",
        "name": "DeepSeek Chat",
        "protocol": "chat_completions",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "api_key": "",
        "is_multimodal": False,
        "supports_reasoning": False,
        "reasoning_param_name": "reasoning_effort",
        "reasoning_param_value": "medium",
        "max_tokens": 0,
        "temperature": 0,
        "top_p": 0,
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "preset_deepseek_reasoner",
        "name": "DeepSeek Reasoner",
        "protocol": "chat_completions",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-reasoner",
        "api_key": "",
        "is_multimodal": False,
        "supports_reasoning": True,
        "reasoning_param_name": "reasoning_effort",
        "reasoning_param_value": "medium",
        "max_tokens": 0,
        "temperature": 0,
        "top_p": 0,
        "enabled": False,
        "builtin": True,
    },
    {
        "id": "preset_doubao_vision",
        "name": "豆包 Vision（多模态）",
        "protocol": "chat_completions",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model_name": "doubao-1-5-vision-pro-32k",
        "api_key": "",
        "is_multimodal": True,
        "supports_reasoning": False,
        "reasoning_param_name": "",
        "reasoning_param_value": "",
        "max_tokens": 0,
        "temperature": 0,
        "top_p": 0,
        "enabled": False,
        "builtin": True,
    },
]

TYPE_KEYS = ("single", "multiple", "judgement", "completion", "image")


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def ensure_data_dir(path: str = DATA_DIR) -> str:
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, "cache", "images"), exist_ok=True)
    os.makedirs(os.path.join(path, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(path, "logs"), exist_ok=True)
    return path


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """把 patch 递归合并进 base 的副本（dict 合并，其他类型直接覆盖）。"""
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def mask_key(value: Any) -> str:
    """密钥脱敏：sk-abcdefgh → sk-****efgh；空值返回空串。"""
    if not value or not isinstance(value, str):
        return ""
    if len(value) <= 8:
        return MASK
    return f"{value[:3]}{MASK}{value[-4:]}"


def is_masked(value: Any) -> bool:
    return isinstance(value, str) and MASK in value


def _env_override(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """环境变量覆盖（OCS_HUB_PORT / OCS_HUB_HOST / OCS_HUB_TOKEN）。"""
    mapping = {
        "OCS_HUB_PORT": ("server", "port", int),
        "OCS_HUB_HOST": ("server", "host", str),
        "OCS_HUB_TOKEN": ("security", "access_token", str),
        "OCS_HUB_ENABLE_AI": ("answer", "enable_ai", lambda v: str(v).lower() not in ("0", "false", "no")),
    }
    for env_name, (section, key, caster) in mapping.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            cfg.setdefault(section, {})[key] = caster(raw)
        except (TypeError, ValueError):
            continue
    return cfg


# --------------------------------------------------------------------------
# 设置对象
# --------------------------------------------------------------------------
class Settings:
    """线程安全的配置容器。"""

    def __init__(self, path: str = CONFIG_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.loaded_from_disk = False
        self.load()

    # -- 读写 ---------------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        with self._lock:
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as fh:
                        disk = json.load(fh)
                    if isinstance(disk, dict):
                        cfg = deep_merge(cfg, disk)
                        self.loaded_from_disk = True
                except (OSError, json.JSONDecodeError) as exc:
                    self._backup_bad_config(str(exc))
            else:
                # 首次启动：写入内置预设
                cfg["models"] = copy.deepcopy(BUILTIN_MODELS)
                cfg["fallback_models"] = ["preset_deepseek_chat"]
                for key in TYPE_KEYS:
                    if key != "image":
                        cfg["type_mapping"][key]["models"] = ["preset_deepseek_chat"]
                self.data = _env_override(cfg)
                self.save()
                return self.data

            cfg = _env_override(cfg)
            cfg = self._normalize(cfg)
            self.data = cfg
            return cfg

    def reload(self) -> Dict[str, Any]:
        return self.load()

    def save(self) -> None:
        with self._lock:
            ensure_data_dir(os.path.dirname(self.path) or DATA_DIR)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """合并补丁 → 校验 → 落盘 → 热更新内存。"""
        with self._lock:
            merged = deep_merge(self.data, patch or {})
            merged = self._normalize(merged)
            self.data = merged
            self.save()
            return self.data

    def reset(self) -> Dict[str, Any]:
        """恢复默认（保留 models 与题库）。"""
        with self._lock:
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["models"] = copy.deepcopy(self.data.get("models") or BUILTIN_MODELS)
            cfg["fallback_models"] = copy.deepcopy(self.data.get("fallback_models") or [])
            cfg["type_mapping"] = copy.deepcopy(self.data.get("type_mapping") or DEFAULT_CONFIG["type_mapping"])
            self.data = self._normalize(cfg)
            self.save()
            return self.data

    def _backup_bad_config(self, reason: str) -> None:
        try:
            bad = f"{self.path}.bad-{int(__import__('time').time())}"
            os.replace(self.path, bad)
            print(f"[配置] 配置文件损坏（{reason}），已备份为 {os.path.basename(bad)}，将使用默认配置。")
        except OSError:
            pass

    # -- 取值 ---------------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> Dict[str, Any]:
        value = self.data.get(name)
        return value if isinstance(value, dict) else {}

    # -- 校验与规范化 -------------------------------------------------------
    def _normalize(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        cfg = copy.deepcopy(cfg)
        cfg["version"] = 1

        server = cfg.setdefault("server", {})
        server["port"] = _clamp_int(server.get("port"), 1024, 65535, 8000)
        server["host"] = str(server.get("host") or "127.0.0.1").strip()
        server["open_browser"] = bool(server.get("open_browser", True))
        server["log_level"] = str(server.get("log_level") or "INFO").upper()

        answer = cfg.setdefault("answer", {})
        answer["offline_first"] = True
        answer["enable_ai"] = bool(answer.get("enable_ai", True))
        answer["auto_save"] = bool(answer.get("auto_save", True))
        answer["auto_save_verified"] = bool(answer.get("auto_save_verified", False))
        answer["fuzzy_enabled"] = bool(answer.get("fuzzy_enabled", True))
        answer["fuzzy_threshold"] = _clamp_float(answer.get("fuzzy_threshold"), 0.70, 1.0, 0.92)
        answer["cross_course"] = bool(answer.get("cross_course", True))
        answer["current_course_id"] = _clamp_int(answer.get("current_course_id"), 0, 10**9, 0)
        fmt = str(answer.get("answer_format") or "auto").lower()
        answer["answer_format"] = fmt if fmt in ("auto", "letters", "content") else "auto"
        answer["request_timeout"] = _clamp_int(answer.get("request_timeout"), 5, 600, 120)
        answer["max_retries"] = _clamp_int(answer.get("max_retries"), 0, 5, 3)
        answer["use_option_labels"] = bool(answer.get("use_option_labels", True))
        answer["extra_prompt"] = str(answer.get("extra_prompt") or "").strip()

        ai = cfg.setdefault("ai", {})
        ai["enabled"] = bool(ai.get("enabled", True))
        ai["temperature"] = _clamp_float(ai.get("temperature"), 0.0, 2.0, 0.1)
        ai["max_tokens"] = _clamp_int(ai.get("max_tokens"), 16, 32000, 500)
        ai["reasoning_max_tokens"] = _clamp_int(ai.get("reasoning_max_tokens"), 256, 64000, 4096)
        ai["top_p"] = _clamp_float(ai.get("top_p"), 0.01, 1.0, 0.95)
        ai["force_reasoning"] = bool(ai.get("force_reasoning", False))
        effort = str(ai.get("reasoning_effort") or "medium").lower()
        ai["reasoning_effort"] = effort if effort in ("low", "medium", "high") else "medium"
        ai["auto_reasoning_multiple"] = bool(ai.get("auto_reasoning_multiple", True))
        ai["auto_reasoning_images"] = bool(ai.get("auto_reasoning_images", True))
        ai["proxy"] = str(ai.get("proxy") or "").strip()
        ai["image_timeout"] = _clamp_int(ai.get("image_timeout"), 3, 120, 15)
        ai["image_max_mb"] = _clamp_int(ai.get("image_max_mb"), 1, 50, 5)
        ai["max_images"] = _clamp_int(ai.get("max_images"), 1, 20, 8)

        sec = cfg.setdefault("security", {})
        sec["access_token"] = str(sec.get("access_token") or "")
        sec["allow_lan_admin"] = bool(sec.get("allow_lan_admin", False))
        sec["rate_limit_attempts"] = _clamp_int(sec.get("rate_limit_attempts"), 1, 50, 5)
        sec["rate_limit_window"] = _clamp_int(sec.get("rate_limit_window"), 30, 3600, 300)

        cfg["models"] = self._normalize_models(cfg.get("models"))
        cfg["type_mapping"] = self._normalize_mapping(cfg.get("type_mapping"), cfg["models"], cfg.get("fallback_models"))
        ids = [m["id"] for m in cfg["models"]]
        cfg["fallback_models"] = [i for i in (cfg.get("fallback_models") or []) if i in ids] or ids[:1]

        cache = cfg.setdefault("cache", {})
        cache["enabled"] = bool(cache.get("enabled", True))
        cache["ttl"] = _clamp_int(cache.get("ttl"), 0, 86400, 3600)
        cache["size"] = _clamp_int(cache.get("size"), 16, 4096, 512)
        return cfg

    @staticmethod
    def _normalize_models(models: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for raw in models if isinstance(models, list) else []:
            if not isinstance(raw, dict):
                continue
            mid = str(raw.get("id") or "").strip() or f"m_{len(out) + 1}"
            if mid in seen:
                mid = f"{mid}_{len(out) + 1}"
            seen.add(mid)
            protocol = str(raw.get("protocol") or "chat_completions").lower()
            if protocol not in ("chat_completions", "responses"):
                protocol = "chat_completions"
            out.append(
                {
                    "id": mid,
                    "name": str(raw.get("name") or mid).strip(),
                    "protocol": protocol,
                    "base_url": str(raw.get("base_url") or "").strip(),
                    "model_name": str(raw.get("model_name") or "").strip(),
                    "api_key": str(raw.get("api_key") or "").strip(),
                    "is_multimodal": bool(raw.get("is_multimodal", False)),
                    "supports_reasoning": bool(raw.get("supports_reasoning", False)),
                    "reasoning_param_name": str(raw.get("reasoning_param_name") or ""),
                    "reasoning_param_value": str(raw.get("reasoning_param_value") or ""),
                    "max_tokens": _clamp_int(raw.get("max_tokens"), 0, 32000, 0),
                    "price_in": _clamp_float(raw.get("price_in"), 0.0, 10000.0, 0.0),
                    "price_out": _clamp_float(raw.get("price_out"), 0.0, 10000.0, 0.0),
                    "temperature": _clamp_float(raw.get("temperature"), -1.0, 2.0, 0.0),
                    "top_p": _clamp_float(raw.get("top_p"), 0.0, 1.0, 0.0),
                    "enabled": bool(raw.get("enabled", True)),
                    "builtin": bool(raw.get("builtin", False)),
                }
            )
        return out

    @staticmethod
    def _normalize_mapping(mapping: Any, models: List[Dict[str, Any]], fallback: Any) -> Dict[str, Any]:
        ids = {m["id"] for m in models}
        mm_ids = {m["id"] for m in models if m["is_multimodal"]}
        fallback_ids = [i for i in (fallback or []) if i in ids]
        default_ids = fallback_ids or [m["id"] for m in models][:1]
        src = mapping if isinstance(mapping, dict) else {}
        out: Dict[str, Any] = {}
        for key in TYPE_KEYS:
            node = src.get(key) if isinstance(src.get(key), dict) else {}
            chosen = [i for i in (node.get("models") or []) if i in ids]
            if key == "image":
                # 图片题只能使用多模态模型
                chosen = [i for i in chosen if i in mm_ids]
                if not chosen:
                    chosen = [i for i in default_ids if i in mm_ids]
            elif not chosen:
                chosen = list(default_ids)
            out[key] = {"models": chosen, "enable_reasoning": bool(node.get("enable_reasoning", key in ("multiple", "image")))}
        return out

    # -- 对外快照 -----------------------------------------------------------
    def snapshot(self, mask: bool = True) -> Dict[str, Any]:
        data = copy.deepcopy(self.data)
        if mask:
            for model in data.get("models") or []:
                model["api_key"] = mask_key(model.get("api_key"))
                model["has_key"] = bool(self.raw_key(model["id"]))
            sec = data.get("security") or {}
            sec["has_token"] = bool(sec.get("access_token"))
            sec["access_token"] = MASK if sec.get("access_token") else ""
        return data

    def raw_key(self, model_id: str) -> str:
        for model in self.data.get("models") or []:
            if model.get("id") == model_id:
                return model.get("api_key") or ""
        return ""


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


def _clamp_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


# 全局单例（懒加载，测试可替换）
_settings: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        with _settings_lock:
            if _settings is None:
                ensure_data_dir()
                _settings = Settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """替换全局单例（测试用；传 None 表示下次重新加载）。"""
    global _settings
    _settings = settings