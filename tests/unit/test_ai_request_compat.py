from src.services.ai_request_compat import (
    apply_thinking_mode,
    is_json_output_unsupported_error,
    is_responses_api_unsupported_error,
    is_temperature_unsupported_error,
    remove_temperature_param,
)


def test_is_temperature_unsupported_error_detects_unsupported_message():
    err = Exception("temperature is not supported by this gateway")
    assert is_temperature_unsupported_error(err) is True


def test_apply_thinking_mode_disables_thinking_for_deepseek_by_default():
    result = apply_thinking_mode(
        {"model": "deepseek-flash", "temperature": 0.1},
        enable_thinking=False,
    )

    assert result["extra_body"]["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in result["extra_body"]
    assert result["reasoning_effort"] == "none"
    assert "reasoning" not in result
    assert result["temperature"] == 0.1


def test_apply_thinking_mode_skips_unrelated_models_when_thinking_is_off():
    params = {"model": "gpt-4o-mini"}
    result = apply_thinking_mode(params, enable_thinking=False)

    assert "extra_body" not in result
    assert result is not params


def test_apply_thinking_mode_enables_thinking_when_requested():
    result = apply_thinking_mode({"model": "qwen-plus"}, enable_thinking=True)

    assert result["extra_body"]["thinking"] == {"type": "enabled"}
    assert "enable_thinking" not in result["extra_body"]
    assert "reasoning_effort" not in result


def test_apply_thinking_mode_disables_responses_api_reasoning_for_deepseek():
    result = apply_thinking_mode(
        {"model": "deepseek-flash", "input": [{"role": "user", "content": []}]},
        enable_thinking=False,
    )

    assert result["extra_body"]["thinking"] == {"type": "disabled"}
    assert result["reasoning_effort"] == "none"
    assert result["reasoning"] == {"effort": "none"}


def test_remove_temperature_param_removes_only_temperature():
    params = {"model": "x", "temperature": 0.5, "max_output_tokens": 128}
    result = remove_temperature_param(params)

    assert "temperature" not in result
    assert result["model"] == "x"
    assert result["max_output_tokens"] == 128


def test_is_responses_api_unsupported_error_detects_gemini_plain_404():
    class _Resp:
        text = ""

    class _Err(Exception):
        status_code = 404
        body = ""
        response = _Resp()

        def __str__(self):
            return "Error code: 404"

    assert is_responses_api_unsupported_error(_Err()) is True


# -- is_json_output_unsupported_error tests --


def test_json_output_error_detected_via_body_param_response_format():
    """Vercel AI Gateway returns 400 with param='response_format'."""

    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "type": "invalid_request_error",
            "param": "response_format",
            "code": "invalid_request_error",
        }

    assert is_json_output_unsupported_error(_Err()) is True


def test_json_output_error_detected_via_body_param_response_format_type():
    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "param": "response_format.type",
        }

    assert is_json_output_unsupported_error(_Err()) is True


def test_json_output_error_detected_via_legacy_string_matching():
    err = Exception(
        "response_format.type is not supported by this model"
    )
    assert is_json_output_unsupported_error(err) is True


def test_json_output_error_not_triggered_by_unrelated_400():
    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "param": "messages",
        }

    assert is_json_output_unsupported_error(_Err()) is False


def test_json_output_error_not_triggered_without_body():
    err = Exception("some random 400 error")
    assert is_json_output_unsupported_error(err) is False
