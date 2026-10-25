from src.services.ai_analysis_schema import (
    normalize_ai_analysis_result,
    validate_ai_analysis_result,
)


def test_normalize_ai_analysis_result_fills_missing_prompt_version():
    result = normalize_ai_analysis_result(
        {
            "is_recommended": False,
            "reason": "信息不完整",
            "criteria_analysis": {"seller_type": {"status": "UNKNOWN"}},
        }
    )

    assert result is not None
    assert result["prompt_version"] == "EagleEye-V6.4"
    assert result["risk_tags"] == []
    assert validate_ai_analysis_result(result) is True


def test_normalize_ai_analysis_result_coerces_string_boolean_and_risk_tags():
    result = normalize_ai_analysis_result(
        {
            "is_recommended": "false",
            "reason": "商家痕迹明显",
            "risk_tags": "矿卡风险",
        }
    )

    assert result is not None
    assert result["is_recommended"] is False
    assert result["risk_tags"] == ["矿卡风险"]
    assert "seller_type" in result["criteria_analysis"]
    assert validate_ai_analysis_result(result) is True


def test_normalize_ai_analysis_result_rejects_missing_recommendation():
    assert normalize_ai_analysis_result({"reason": "ok"}) is None


def test_normalize_ai_analysis_result_infers_false_from_reason():
    result = normalize_ai_analysis_result({"reason": "不推荐，明确仅限同城面交。"})

    assert result is not None
    assert result["is_recommended"] is False
