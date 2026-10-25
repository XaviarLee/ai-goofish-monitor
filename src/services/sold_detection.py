"""成交检测：搜索消失只是候选，必须用卖家主页已售确认。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from src.services.price_history_service import parse_price_value


DEFAULT_SOLD_RECRAWL_LIMIT = 10
DEFAULT_DETAIL_SOLD_CHECK_LIMIT = 10

_SELLER_PATH_RE = re.compile(r"alicdn\.com/bao/uploaded/i\d+/(\d{6,})/", re.I)
_SELLER_BANG_RE = re.compile(r"!!(\d{6,})-")


def collect_search_item_ids(items: Iterable[dict] | None) -> set[str]:
    ids: set[str] = set()
    for item in items or []:
        item_id = str((item or {}).get("商品ID") or "").strip()
        if item_id:
            ids.add(item_id)
    return ids


def extract_seller_id(record: dict | None) -> str:
    return infer_seller_id_from_record(record)


def _iter_record_urls(record: dict | None) -> list[str]:
    payload = record or {}
    item = payload.get("商品信息") or {}
    urls: list[str] = []
    for value in item.get("商品图片列表") or []:
        if value:
            urls.append(str(value))
    for key in ("商品主图链接", "商品主图"):
        value = item.get(key)
        if value:
            urls.append(str(value))
    return urls


def infer_seller_id_from_urls(urls: Iterable[str] | None) -> str:
    """旧结果没存卖家ID时，从当前商品图片 URL 还原。多个不同 ID 则放弃。"""
    path_ids: set[str] = set()
    bang_ids: set[str] = set()
    for url in urls or []:
        text = str(url or "")
        path_ids.update(_SELLER_PATH_RE.findall(text))
        for bang_id in _SELLER_BANG_RE.findall(text):
            if 6 <= len(bang_id) <= 13:
                bang_ids.add(bang_id)
    if len(path_ids) == 1:
        return next(iter(path_ids))
    if not path_ids and len(bang_ids) == 1:
        return next(iter(bang_ids))
    return ""


def infer_seller_id_from_record(record: dict | None) -> str:
    payload = record or {}
    seller = payload.get("卖家信息") or {}
    item = payload.get("商品信息") or {}
    for source in (seller, item, payload):
        value = str((source or {}).get("卖家ID") or "").strip()
        if value:
            return value
    return infer_seller_id_from_urls(_iter_record_urls(payload))


def attach_inferred_seller_id(record: dict) -> str:
    """把推断出的卖家ID写回记录，方便按卖家批量核验。"""
    seller_id = infer_seller_id_from_record(record)
    if not seller_id:
        return ""
    seller = record.setdefault("卖家信息", {})
    seller["卖家ID"] = seller_id
    item = record.setdefault("商品信息", {})
    item.setdefault("卖家ID", seller_id)
    record["seller_id"] = seller_id
    return seller_id


def select_sold_candidates(
    previous_items: Iterable[dict],
    search_ids: set[str],
) -> list[dict]:
    """旧结果里仍未成交、且本轮搜索没出现的商品。"""
    candidates: list[dict] = []
    seen: set[str] = set()
    for record in previous_items or []:
        if record.get("sold_at") or record.get("_sold_at"):
            continue
        status = str(record.get("status") or record.get("_status") or "active")
        if status in {"hidden", "expired", "sold"}:
            continue
        item = record.get("商品信息") or {}
        item_id = str(item.get("商品ID") or record.get("item_id") or "").strip()
        if not item_id or item_id in seen or item_id in search_ids:
            continue
        seen.add(item_id)
        attach_inferred_seller_id(record)
        candidates.append(record)
    return candidates


def group_candidates_by_seller(candidates: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for record in candidates or []:
        seller_id = extract_seller_id(record)
        if not seller_id:
            continue
        grouped.setdefault(seller_id, []).append(record)
    return grouped


def select_sellers_to_recrawl(
    grouped: dict[str, list[dict]],
    *,
    already_loaded: set[str] | None = None,
    limit: int = DEFAULT_SOLD_RECRAWL_LIMIT,
) -> tuple[list[str], list[str]]:
    loaded = already_loaded or set()
    remaining = [seller_id for seller_id in grouped if seller_id not in loaded]
    return remaining[: max(0, limit)], remaining[max(0, limit) :]


def _seller_item_id(seller_item: dict) -> str:
    return str((seller_item or {}).get("商品ID") or "").strip()


def is_seller_item_sold(seller_item: dict | None) -> bool:
    item = seller_item or {}
    status_code = item.get("itemStatus")
    if status_code == 1:
        return True
    return str(item.get("商品状态") or "") == "已售"


def find_seller_item(seller_items: Iterable[dict] | None, item_id: str) -> Optional[dict]:
    target = str(item_id or "").strip()
    if not target:
        return None
    for seller_item in seller_items or []:
        if _seller_item_id(seller_item) == target:
            return seller_item
    return None


def resolve_sold_price(
    *,
    seller_item: dict | None,
    listing_price: Any = None,
) -> tuple[Optional[float], str, str]:
    seller_price = parse_price_value((seller_item or {}).get("商品价格"))
    if seller_price is not None:
        display = str((seller_item or {}).get("商品价格") or seller_price)
        return seller_price, display, "seller_list"
    listing = parse_price_value(listing_price)
    if listing is not None:
        return listing, str(listing_price or listing), "listing_fallback"
    return None, "", ""


@dataclass(frozen=True)
class SoldMatch:
    item_id: str
    title: str
    sold_price: float
    sold_price_display: str
    last_listing_price: Optional[float]
    source: str
    seller: str
    seller_id: str
    link: str
    record: dict


def classify_candidates_against_seller_list(
    candidates: Iterable[dict],
    seller_item_list: Iterable[dict] | None,
    *,
    search_ids: set[str],
    seller_id: str = "",
) -> tuple[list[SoldMatch], list[dict], list[dict]]:
    """对照卖家列表：已售 / 仍在售 / 列表没有。"""
    matches = match_sold_items(
        candidates,
        seller_item_list,
        search_ids=search_ids,
        seller_id=seller_id,
    )
    matched_ids = {match.item_id for match in matches}
    still_listed: list[dict] = []
    missing: list[dict] = []
    seller_items = list(seller_item_list or [])
    for record in candidates or []:
        item = record.get("商品信息") or {}
        item_id = str(item.get("商品ID") or record.get("item_id") or "").strip()
        if not item_id or item_id in search_ids or item_id in matched_ids:
            continue
        if find_seller_item(seller_items, item_id) is None:
            missing.append(record)
        else:
            still_listed.append(record)
    return matches, still_listed, missing


def parse_detail_sold_status(detail_json: dict | None) -> dict:
    """从商品详情 API 判断是否已售。找不到已售证据时不记成交。"""
    payload = detail_json or {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    item_do = data.get("itemDO") if isinstance(data.get("itemDO"), dict) else {}
    seller_do = data.get("sellerDO") if isinstance(data.get("sellerDO"), dict) else {}

    seller_id = str(seller_do.get("sellerId") or item_do.get("sellerId") or "").strip()
    title = str(item_do.get("title") or item_do.get("itemTitle") or "").strip()
    price_value = parse_price_value(
        item_do.get("soldPrice")
        or item_do.get("price")
        or item_do.get("itemPrice")
        or (item_do.get("priceInfo") or {}).get("price")
    )
    price_display = str(
        item_do.get("soldPrice")
        or item_do.get("price")
        or item_do.get("itemPrice")
        or (item_do.get("priceInfo") or {}).get("price")
        or (price_value if price_value is not None else "")
    )

    status_code = item_do.get("itemStatus")
    status_text = str(
        item_do.get("itemStatusStr")
        or item_do.get("itemStatusText")
        or item_do.get("soldStatus")
        or ""
    )
    sold_flag = item_do.get("sold")
    if status_code == 1 or sold_flag is True or sold_flag == 1 or "已售" in status_text or "卖出" in status_text:
        return {
            "state": "sold",
            "seller_id": seller_id,
            "title": title,
            "sold_price": price_value,
            "sold_price_display": price_display,
            "source": "item_detail",
        }
    if status_code == 0 or "在售" in status_text:
        return {
            "state": "listed",
            "seller_id": seller_id,
            "title": title,
            "sold_price": price_value,
            "sold_price_display": price_display,
            "source": "item_detail",
        }
    return {
        "state": "unknown",
        "seller_id": seller_id,
        "title": title,
        "sold_price": price_value,
        "sold_price_display": price_display,
        "source": "item_detail",
    }


def match_sold_items(
    candidates: Iterable[dict],
    seller_item_list: Iterable[dict] | None,
    *,
    search_ids: set[str],
    seller_id: str = "",
) -> list[SoldMatch]:
    """候选必须同时：本轮搜索缺失 + 卖家列表 itemStatus==1。"""
    matches: list[SoldMatch] = []
    seller_items = list(seller_item_list or [])
    for record in candidates or []:
        item = record.get("商品信息") or {}
        item_id = str(item.get("商品ID") or record.get("item_id") or "").strip()
        if not item_id or item_id in search_ids:
            continue
        seller_item = find_seller_item(seller_items, item_id)
        if seller_item is None or not is_seller_item_sold(seller_item):
            continue
        listing_price = record.get("price")
        if listing_price is None:
            listing_price = item.get("当前售价")
        sold_price, display, source = resolve_sold_price(
            seller_item=seller_item,
            listing_price=listing_price,
        )
        if sold_price is None:
            continue
        seller_info = record.get("卖家信息") or {}
        matches.append(
            SoldMatch(
                item_id=item_id,
                title=str(
                    item.get("商品标题")
                    or record.get("title")
                    or seller_item.get("商品标题")
                    or ""
                ),
                sold_price=sold_price,
                sold_price_display=display,
                last_listing_price=parse_price_value(listing_price),
                source=source,
                seller=str(
                    seller_info.get("卖家昵称")
                    or item.get("卖家昵称")
                    or record.get("seller_nickname")
                    or ""
                ),
                seller_id=seller_id or extract_seller_id(record),
                link=str(item.get("商品链接") or record.get("link") or ""),
                record=record,
            )
        )
    return matches
