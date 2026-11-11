# -*- coding: utf-8 -*-
"""模型注册表与题型映射。

配置里 models 是唯一真相；本模块只做「查、筛选、排序、补全 Key」。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from . import normalize as nz
from .settings import get_settings, mask_key


def all_models() -> List[Dict[str, Any]]:
    return list(get_settings().data.get("models") or [])


def get_model(model_id: str) -> Optional[Dict[str, Any]]:
    for model in all_models():
        if model.get("id") == model_id:
            return dict(model)
    return None


def with_key(model: Dict[str, Any]) -> Dict[str, Any]:
    """把真实 API Key 补进模型 dict（对外展示请勿调用）。"""
    cfg = get_settings()
    out = dict(model)
    out["api_key"] = cfg.raw_key(model.get("id", ""))
    return out


def enabled_models() -> List[Dict[str, Any]]:
    return [m for m in all_models() if m.get("enabled")]


def multimodal_models() -> List[Dict[str, Any]]:
    return [m for m in enabled_models() if m.get("is_multimodal")]


def mapping_for(qtype: str) -> Dict[str, Any]:
    cfg = get_settings()
    mapping = (cfg.data.get("type_mapping") or {}).get(qtype) or {}
    if qtype == nz.QTYPE_IMAGE:
        mapping = (cfg.data.get("type_mapping") or {}).get("image") or {}
    return {
        "models": list(mapping.get("models") or []),
        "enable_reasoning": bool(mapping.get("enable_reasoning", qtype in ("multiple", "image"))),
    }


def pick_models(qtype: str, has_images: bool = False) -> List[Dict[str, Any]]:
    """按题型映射返回候选模型（已含 Key，可直接调用）。

    - 有图片 → 只用多模态模型（映射里的非多模态被过滤；若映射为空则从全局多模态里挑）
    - 无图片 → 按映射顺序
    - 映射为空 → 使用 fallback_models
    """
    mapping = mapping_for(qtype)
    ids = mapping["models"] or list(get_settings().data.get("fallback_models") or [])
    picked: List[Dict[str, Any]] = []
    for model_id in ids:
        model = get_model(model_id)
        if not model or not model.get("enabled"):
            continue
        if has_images and not model.get("is_multimodal"):
            continue
        picked.append(with_key(model))
    if has_images and not picked:
        picked = [with_key(m) for m in multimodal_models()]
    if not picked and not has_images:
        picked = [with_key(m) for m in enabled_models()]
    return picked


def reasoning_for(qtype: str) -> bool:
    """该题型是否应开启深度思考。"""
    cfg = get_settings()
    mapping = mapping_for(qtype)
    if cfg.get("ai.force_reasoning"):
        return True
    return mapping["enable_reasoning"]


def sanitize_mapping(cfg_data: Dict[str, Any]) -> Dict[str, Any]:
    """前端保存映射前调用：剔除图片映射里的非多模态模型。"""
    models = {m["id"]: m for m in cfg_data.get("models") or []}
    mapping = cfg_data.get("type_mapping") or {}
    image = mapping.get("image") or {}
    if image.get("models"):
        image["models"] = [i for i in image["models"] if i in models and models[i].get("is_multimodal")]
        mapping["image"] = image
    cfg_data["type_mapping"] = mapping
    return cfg_data


def public_list() -> List[Dict[str, Any]]:
    """对外展示：Key 脱敏。"""
    out = []
    for model in all_models():
        item = dict(model)
        item["api_key"] = mask_key(model.get("api_key"))
        item["has_key"] = bool(model.get("api_key"))
        out.append(item)
    return out


def describe_mapping() -> Dict[str, Any]:
    cfg = get_settings()
    result: Dict[str, Any] = {}
    labels = {
        nz.QTYPE_SINGLE: "单选题",
        nz.QTYPE_MULTIPLE: "多选题",
        nz.QTYPE_JUDGEMENT: "判断题",
        nz.QTYPE_COMPLETION: "填空题",
        nz.QTYPE_IMAGE: "图片题",
    }
    names = {m["id"]: m["name"] for m in all_models()}
    for key in ("single", "multiple", "judgement", "completion", "image"):
        node = (cfg.data.get("type_mapping") or {}).get(key) or {}
        items = []
        for model_id in node.get("models") or []:
            model = get_model(model_id)
            items.append(
                {
                    "id": model_id,
                    "name": names.get(model_id, model_id),
                    "enabled": bool(model and model.get("enabled")),
                    "multimodal": bool(model and model.get("is_multimodal")),
                }
            )
        result[key] = {
            "label": labels.get(key, key),
            "models": items,
            "enable_reasoning": bool(node.get("enable_reasoning")),
        }
    return result