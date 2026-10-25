"""
关键词判断引擎：单组 OR 逻辑，命中任意关键词即推荐。
纯英数字关键词按完整词匹配，避免 Q1 误命中 Q1R5。
"""
import re
from typing import Any, Dict, Iterable, List


_ASCII_TOKEN_KEYWORD_PATTERN = re.compile(r"^[a-z0-9 ]+$")
_ASCII_TOKEN_BOUNDARY = r"[a-z0-9]"


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def _collect_text_fragments(value: Any, bucket: List[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            bucket.append(text)
        return
    if isinstance(value, (int, float, bool)):
        bucket.append(str(value))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_text_fragments(item, bucket)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_fragments(item, bucket)


def build_search_text(record: Dict[str, Any]) -> str:
    fragments: List[str] = []
    product_info = record.get("商品信息", {})
    seller_info = record.get("卖家信息", {})

    _collect_text_fragments(product_info.get("商品标题"), fragments)
    _collect_text_fragments(product_info, fragments)
    _collect_text_fragments(seller_info, fragments)

    return normalize_text(" ".join(fragments))


def _normalize_keywords(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for raw in values or []:
        text = normalize_text(str(raw).strip())
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _uses_ascii_token_match(keyword: str) -> bool:
    return bool(keyword) and _ASCII_TOKEN_KEYWORD_PATTERN.fullmatch(keyword) is not None


def _keyword_matches(keyword: str, normalized_text: str) -> bool:
    if not _uses_ascii_token_match(keyword):
        return keyword in normalized_text
    pattern = rf"(?<!{_ASCII_TOKEN_BOUNDARY}){re.escape(keyword)}(?!{_ASCII_TOKEN_BOUNDARY})"
    return re.search(pattern, normalized_text) is not None


def item_matches_search_keyword(item: Dict[str, Any] | None, keyword: str) -> bool:
    """判断搜索结果是否真的命中任务关键词。

    闲鱼搜索常夹带相关推荐（搜 3090 会出现 3080/5070/整机），标题必须命中
    任务关键词才进入详情和 AI，避免结果页被无关商品淹没。
    """
    query = normalize_text(keyword)
    if not query:
        return True

    title = normalize_text(str((item or {}).get("商品标题") or ""))
    if _keyword_matches(query, title):
        return True

    # 纯数字型号允许常见写法：RTX3090、rtx-3090、3090ti，但不能命中 13090 这种更长数字。
    compact_query = query.replace(" ", "")
    if not compact_query.isalnum():
        return False
    compact_title = re.sub(r"[^a-z0-9]+", "", title)
    pattern = rf"(?:^|[^0-9])(?:rtx)?{re.escape(compact_query)}(?:ti)?(?:[^0-9]|$)"
    return re.search(pattern, compact_title) is not None


def evaluate_keyword_rules(keywords: List[str], search_text: str) -> Dict[str, Any]:
    normalized_text = normalize_text(search_text)
    normalized_keywords = _normalize_keywords(keywords)

    if not normalized_text:
        return {
            "analysis_source": "keyword",
            "is_recommended": False,
            "reason": "可匹配文本为空，关键词规则无法执行。",
            "matched_keywords": [],
            "keyword_hit_count": 0,
        }

    if not normalized_keywords:
        return {
            "analysis_source": "keyword",
            "is_recommended": False,
            "reason": "未配置关键词规则。",
            "matched_keywords": [],
            "keyword_hit_count": 0,
        }

    matched_keywords = [kw for kw in normalized_keywords if _keyword_matches(kw, normalized_text)]
    hit_count = len(matched_keywords)
    is_recommended = hit_count > 0

    if is_recommended:
        reason = f"命中 {hit_count} 个关键词：{', '.join(matched_keywords)}"
    else:
        reason = "未命中任何关键词。"

    return {
        "analysis_source": "keyword",
        "is_recommended": is_recommended,
        "reason": reason,
        "matched_keywords": matched_keywords,
        "keyword_hit_count": hit_count,
    }
