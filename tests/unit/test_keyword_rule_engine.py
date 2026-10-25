from src.keyword_rule_engine import (
    build_search_text,
    evaluate_keyword_rules,
    item_matches_search_keyword,
)


def _sample_record():
    return {
        "商品信息": {
            "商品标题": "Sony A7M4 全画幅相机",
            "当前售价": "10000",
            "商品标签": ["验货宝", "包邮"],
        },
        "卖家信息": {
            "卖家昵称": "摄影器材店",
            "卖家个性签名": "可验机，支持同城面交",
        },
    }


def test_build_search_text_contains_product_and_seller_fields():
    text = build_search_text(_sample_record())
    assert "sony a7m4" in text
    assert "摄影器材店" in text
    assert "支持同城面交" in text


def test_keyword_rules_or_match_any_keyword():
    text = build_search_text(_sample_record())
    result = evaluate_keyword_rules(["a7m4", "佳能"], text)
    assert result["is_recommended"] is True
    assert result["analysis_source"] == "keyword"
    assert result["keyword_hit_count"] == 1
    assert result["matched_keywords"] == ["a7m4"]


def test_keyword_rules_count_multiple_hits():
    text = build_search_text(_sample_record())
    result = evaluate_keyword_rules(["a7m4", "验货宝", "摄影器材店"], text)
    assert result["is_recommended"] is True
    assert result["keyword_hit_count"] == 3


def test_keyword_rules_case_insensitive_contains():
    text = build_search_text(_sample_record())
    result = evaluate_keyword_rules(["SONY", "A7M4"], text)
    assert result["is_recommended"] is True
    assert result["keyword_hit_count"] == 2


def test_keyword_rules_no_match():
    text = build_search_text(_sample_record())
    result = evaluate_keyword_rules(["佳能", "单反"], text)
    assert result["is_recommended"] is False
    assert result["keyword_hit_count"] == 0


def test_keyword_rules_do_not_partially_match_alphanumeric_prefixes():
    result = evaluate_keyword_rules(["q1"], "富士 q1r5 旗舰相机")
    assert result["is_recommended"] is False
    assert result["keyword_hit_count"] == 0


def test_item_matches_search_keyword_keeps_rtx3090_variants():
    assert item_matches_search_keyword({"商品标题": "七彩虹 RTX 3090 24G"}, "3090") is True
    assert item_matches_search_keyword({"商品标题": "华硕rtx-3090ti 战斧"}, "3090") is True
    assert item_matches_search_keyword({"商品标题": "RTX3090 公版"}, "3090") is True


def test_item_matches_search_keyword_rejects_unrelated_gpu_listings():
    assert item_matches_search_keyword({"商品标题": "七彩虹 RTX 3080 10G"}, "3090") is False
    assert item_matches_search_keyword({"商品标题": "华硕 RTX 5070 12G"}, "3090") is False
    assert item_matches_search_keyword({"商品标题": "Barbour 夹克"}, "3090") is False


def test_item_matches_search_keyword_does_not_match_inside_longer_numbers():
    assert item_matches_search_keyword({"商品标题": "房间号 13090 钥匙"}, "3090") is False


def test_keyword_rules_still_match_full_alphanumeric_token():
    result = evaluate_keyword_rules(["q1r5"], "富士 q1r5 旗舰相机")
    assert result["is_recommended"] is True
    assert result["keyword_hit_count"] == 1
