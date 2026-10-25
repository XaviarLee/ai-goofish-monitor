"""Normalize and validate AI product-analysis JSON."""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_PROMPT_VERSION = "EagleEye-V6.4"
TRUE_VALUES = {"true", "yes", "y", "1", "推荐", "是"}
FALSE_VALUES = {"false", "no", "n", "0", "不推荐", "否"}


def normalize_ai_analysis_result(parsed_response: Any) -> Optional[dict]:
    """Fill common missing fields so slightly incomplete model JSON can still be used."""
    if not isinstance(parsed_response, dict):
        return None

    result = dict(parsed_response)

    if not str(result.get("prompt_version") or "").strip():
        result["prompt_version"] = DEFAULT_PROMPT_VERSION

    recommended = _coerce_bool(result.get("is_recommended"))
    if recommended is None:
        recommended = _infer_recommendation(result)
    if recommended is None:
        return None
    result["is_recommended"] = recommended

    reason = result.get("reason")
    if reason is None:
        result["reason"] = "模型未给出综合理由。"
    else:
        result["reason"] = str(reason).strip() or "模型未给出综合理由。"

    result["risk_tags"] = _coerce_string_list(result.get("risk_tags"))

    criteria = result.get("criteria_analysis")
    if not isinstance(criteria, dict):
        criteria = {}
    else:
        criteria = dict(criteria)
    if "seller_type" not in criteria:
        criteria["seller_type"] = {
            "status": "UNKNOWN",
            "comment": "模型未给出卖家画像。",
        }
    result["criteria_analysis"] = criteria
    return result


def validate_ai_analysis_result(parsed_response: Any) -> bool:
    if not isinstance(parsed_response, dict):
        return False
    if not str(parsed_response.get("prompt_version") or "").strip():
        return False
    if not isinstance(parsed_response.get("is_recommended"), bool):
        return False
    if not isinstance(parsed_response.get("reason"), str):
        return False
    if not isinstance(parsed_response.get("risk_tags"), list):
        return False
    criteria = parsed_response.get("criteria_analysis")
    if not isinstance(criteria, dict) or not criteria:
        return False
    return "seller_type" in criteria


def _infer_recommendation(result: dict) -> Optional[bool]:
    reason = str(result.get("reason") or "")
    if any(marker in reason for marker in ("不推荐", "否决", "一票否决", "FAIL")):
        return False
    if "有条件推荐" in reason or "推荐" in reason:
        return True
    criteria = result.get("criteria_analysis")
    if isinstance(criteria, dict):
        statuses = [
            str((item or {}).get("status") or "").upper()
            for item in criteria.values()
            if isinstance(item, dict)
        ]
        if any(status == "FAIL" for status in statuses):
            return False
    return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        tags = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                tags.append(text)
        return tags
    return [str(value)]
