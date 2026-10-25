from src.services.sold_detection import (
    classify_candidates_against_seller_list,
    collect_search_item_ids,
    extract_seller_id,
    group_candidates_by_seller,
    infer_seller_id_from_urls,
    match_sold_items,
    parse_detail_sold_status,
    select_sellers_to_recrawl,
    select_sold_candidates,
)


def _record(item_id, *, seller_id="s1", price="1000", status="active", sold_at=None):
    return {
        "status": status,
        "sold_at": sold_at,
        "price": float(price) if price is not None else None,
        "商品信息": {
            "商品ID": item_id,
            "商品标题": f"item-{item_id}",
            "当前售价": price,
            "商品链接": f"https://www.goofish.com/item?id={item_id}",
        },
        "卖家信息": {"卖家ID": seller_id, "卖家昵称": "seller"},
    }


def test_select_sold_candidates_skips_search_hits_and_already_sold():
    previous = [
        _record("1"),
        _record("2"),
        _record("3", sold_at="2026-01-01T00:00:00"),
        _record("4", status="expired"),
        _record("5", status="hidden"),
    ]
    candidates = select_sold_candidates(previous, {"1"})
    assert [item["商品信息"]["商品ID"] for item in candidates] == ["2"]


def test_match_sold_items_requires_search_miss_and_seller_sold():
    candidates = [_record("2", price="1800"), _record("3", price="1900")]
    seller_list = [
        {"商品ID": "2", "商品价格": "1750", "商品状态": "已售", "itemStatus": 1},
        {"商品ID": "3", "商品价格": "1900", "商品状态": "在售", "itemStatus": 0},
    ]
    matches = match_sold_items(candidates, seller_list, search_ids={"1"}, seller_id="s1")
    assert len(matches) == 1
    assert matches[0].item_id == "2"
    assert matches[0].sold_price == 1750.0
    assert matches[0].source == "seller_list"
    assert matches[0].last_listing_price == 1800.0


def test_search_hit_is_not_sold_even_if_seller_list_says_sold():
    candidates = [_record("2")]
    seller_list = [{"商品ID": "2", "商品价格": "1000", "itemStatus": 1, "商品状态": "已售"}]
    matches = match_sold_items(candidates, seller_list, search_ids={"2"})
    assert matches == []


def test_classify_missing_seller_item_is_expired_not_sold():
    candidates = [_record("2"), _record("9")]
    seller_list = [
        {"商品ID": "2", "商品价格": "1000", "itemStatus": 0, "商品状态": "在售"},
    ]
    matches, still_listed, missing = classify_candidates_against_seller_list(
        candidates, seller_list, search_ids=set(), seller_id="s1"
    )
    assert matches == []
    assert [item["商品信息"]["商品ID"] for item in still_listed] == ["2"]
    assert [item["商品信息"]["商品ID"] for item in missing] == ["9"]


def test_group_and_recrawl_limit():
    grouped = group_candidates_by_seller(
        [_record("1", seller_id="a"), _record("2", seller_id="b"), _record("3", seller_id="c")]
    )
    recrawl, skipped = select_sellers_to_recrawl(grouped, already_loaded={"a"}, limit=1)
    assert recrawl == ["b"]
    assert skipped == ["c"]


def test_collect_search_item_ids_and_extract_seller_id():
    assert collect_search_item_ids([{"商品ID": "1"}, {"商品ID": ""}, {}]) == {"1"}
    assert extract_seller_id(_record("1", seller_id="abc")) == "abc"


def test_infer_seller_id_from_item_image_url():
    path_url = "http://img.alicdn.com/bao/uploaded/i3/655082890/O1CN019XaKolGaSWK2BxV2_!!4611686018427381130-0-xy_item.jpg"
    bang_url = "http://img.alicdn.com/bao/uploaded/i4/O1CN012uW6NII3VPH9M4dU_!!2200590625525-0-fleamarket.jpg"
    mixed = [
        path_url,
        "http://img.alicdn.com/bao/uploaded/i3/655082890/O1CN01Cgk9PHbdybE3thGS_!!4611686018427381130-0-xy_item.jpg",
    ]
    assert infer_seller_id_from_urls(mixed) == "655082890"
    assert infer_seller_id_from_urls([bang_url]) == "2200590625525"
    assert infer_seller_id_from_urls([path_url, bang_url.replace("2200590625525", "999999999")]) == "655082890"
    assert infer_seller_id_from_urls([
        "http://img.alicdn.com/bao/uploaded/i3/111111111/a.jpg",
        "http://img.alicdn.com/bao/uploaded/i3/222222222/b.jpg",
    ]) == ""

    record = {
        "商品信息": {
            "商品ID": "9",
            "商品图片列表": [path_url],
        },
        "卖家信息": {},
    }
    assert extract_seller_id(record) == "655082890"
    candidates = select_sold_candidates([record], set())
    grouped = group_candidates_by_seller(candidates)
    assert list(grouped.keys()) == ["655082890"]


def test_parse_detail_sold_status():
    sold = parse_detail_sold_status({
        "data": {
            "itemDO": {"itemStatus": 1, "title": "sold gpu", "price": "3200"},
            "sellerDO": {"sellerId": "s9"},
        }
    })
    assert sold["state"] == "sold"
    assert sold["seller_id"] == "s9"
    listed = parse_detail_sold_status({
        "data": {"itemDO": {"itemStatus": 0, "title": "listed"}}
    })
    assert listed["state"] == "listed"
    unknown = parse_detail_sold_status({"data": {"itemDO": {}}})
    assert unknown["state"] == "unknown"
